import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd

from config import settings
from db import init_db, get_db, add_trade, DBTrade
from models import TradeSetupPayload
from strategy import evaluate_strategy
from risk_engine import evaluate_risk
from ai_review import run_ai_review
from notifier import send_notification
from execution import Executor
from data_feed import MarketDataFeed
from analyzer import MarketAnalyzer
from sqlalchemy.orm import Session
from diagnostics import diagnostics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_current_session() -> str:
    """Basic session logic based on current UTC hour."""
    now_utc = datetime.utcnow().time()
    hour = now_utc.hour
    if 8 <= hour < 13:
        return "LONDON"
    elif 13 <= hour < 21:
        return "NEW_YORK"
    else:
        return "ASIA"

def get_daily_losses(db: Session) -> int:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(DBTrade).filter(
        DBTrade.timestamp >= today_start,
        DBTrade.status == "LOSS"
    ).count()

class TradingBot:
    def __init__(self):
        self.symbols = settings.symbols
        self.data_feeds = {sym: MarketDataFeed(symbol=sym) for sym in self.symbols}
        self.analyzer = MarketAnalyzer()
        self.executor = Executor()
        
        # {symbol: {payload, db_id, detected_time, fvg_time}}
        self.active_setups = {}
        self.last_fvg_time = {sym: None for sym in self.symbols}
        self.symbol_cooldowns = {sym: None for sym in self.symbols}
        
        init_db()
        self.db = next(get_db())

    def cancel_setup(self, symbol: str, db_id: int, reason: str, end_status: str = "CANCELLED", stage: str = "UNKNOWN"):
        logger.info(f"Setup {db_id} {end_status} on {symbol}: {reason}")
        self.db.query(DBTrade).filter(DBTrade.id == db_id).update({"status": end_status, "reason": reason})
        self.db.commit()
        self.active_setups.pop(symbol, None)
        
        if end_status == "REJECTED":
            diagnostics.log_rejection(symbol, reason, stage)
        elif end_status == "CANCELLED":
            diagnostics.log_cancelled(symbol, reason)
        
    def apply_cooldown(self, symbol: str, minutes: int = 15):
        self.symbol_cooldowns[symbol] = datetime.utcnow() + timedelta(minutes=minutes)
        logger.info(f"Applied {minutes}m cooldown for {symbol}.")

    async def run_loop(self):
        logger.info(f"Starting bot loop for {self.symbols}...")
        asyncio.create_task(self.periodic_reporting())
        while True:
            for sym in self.symbols:
                try:
                    await self.tick(sym)
                except Exception as e:
                    logger.error(f"Error in main loop tick for {sym}: {e}", exc_info=True)
            await asyncio.sleep(60)

    async def tick(self, symbol: str):
        # 1. Fetch Market Data
        df_1m = self.data_feeds[symbol].fetch_latest_candles(limit=200)
        if df_1m.empty:
            logger.warning(f"No data retrieved for {symbol}.")
            return
            
        latest_1m = df_1m.iloc[-1]
        
        # 2. Manage existing setups & trades
        self.manage_active_setup(symbol, df_1m)
        await self.manage_open_trades(symbol, latest_1m['close'], latest_1m['high'], latest_1m['low'])
        
        # 3. Aggregate to 5m for primary strategy.
        df_5m = self.data_feeds[symbol].get_aggregated_candles(df_1m, timeframe_rule='5min')
        df_5m = self.data_feeds[symbol].compute_atr(df_5m)
        
        # 4. Analyze Technicals
        df_analyzed = self.analyzer.analyze(df_5m)
        latest = df_analyzed.iloc[-1]
        
        # Track diagnostics on the freshly closed 5m candle
        timestamp_str = str(latest['timestamp'])
        raw_bos = latest.get('raw_bos_direction', 'NONE')
        valid_bos = latest.get('bos_direction', 'NONE')
        raw_fvg = latest.get('raw_fvg_active', False)
        valid_fvg = latest.get('fvg_active', False)
        
        diagnostics.process_new_candle(
            symbol=symbol,
            timestamp_str=timestamp_str,
            raw_bos_dir=raw_bos,
            valid_bos_dir=valid_bos,
            raw_fvg=raw_fvg,
            valid_fvg=valid_fvg
        )
        
        if not latest['fvg_active'] or latest['bos_direction'] == 'NONE':
            return
            
        self.evaluate_new_setup(symbol, latest, df_1m, df_5m)
        
    async def periodic_reporting(self):
        while True:
            await asyncio.sleep(15 * 60) # 15 minutes
            diagnostics.print_summary()

    def evaluate_new_setup(self, symbol: str, latest: pd.Series, df_1m: pd.DataFrame, df_5m: pd.DataFrame):
        # Prevent secondary setup if one is already active
        if symbol in self.active_setups:
            return
            
        if self.symbol_cooldowns[symbol] and datetime.utcnow() < self.symbol_cooldowns[symbol]:
            return
            
        open_count = self.db.query(DBTrade).filter(DBTrade.status.in_(["ENTERED", "PARTIAL_TP1"])).count()
        if open_count >= settings.max_open_positions:
            return
            
        fvg_time = latest.get('fvg_time')
        # Prevent duplicate from same FVG
        if self.last_fvg_time.get(symbol) == fvg_time:
            return
            
        direction = 'LONG' if latest['bos_direction'] == 'BULLISH' else 'SHORT'
        
        # Configure entry price based on entry_mode
        mode = settings.entry_mode
        if direction == 'LONG':
            stop = latest['last_swing_low_price'] - settings.stop_buffer_atr * latest.get('ATR', 0)
            if mode == 'FVG_TOP':
                entry_price = latest['fvg_top']
            elif mode == 'FULL_ZONE_TOUCH':
                entry_price = latest['fvg_bottom']
            else: # MIDPOINT
                entry_price = latest['fvg_bottom'] + (latest['fvg_top'] - latest['fvg_bottom']) * 0.5
        else:
            stop = latest['last_swing_high_price'] + settings.stop_buffer_atr * latest.get('ATR', 0)
            if mode == 'FVG_TOP': # Technically bottom for bearish
                entry_price = latest['fvg_bottom']
            elif mode == 'FULL_ZONE_TOUCH':
                entry_price = latest['fvg_top']
            else:
                entry_price = latest['fvg_bottom'] + (latest['fvg_top'] - latest['fvg_bottom']) * 0.5
                
        # Calculate TPs
        if direction == 'LONG':
            tp1 = entry_price + (entry_price - stop) * settings.min_rr
            tp2 = entry_price + (entry_price - stop) * settings.tp2_rr
        else:
            tp1 = entry_price - (stop - entry_price) * settings.min_rr
            tp2 = entry_price - (stop - entry_price) * settings.tp2_rr
            
        htf_trend = self.analyzer.get_htf_trend(df_1m)
        
        try:
            payload = TradeSetupPayload(
                symbol=symbol,
                timeframe='5m',
                direction=direction,
                entry=round(entry_price, 2),
                stop=round(stop, 2),
                tp1=round(tp1, 2),
                tp2=round(tp2, 2),
                bos_direction=latest['bos_direction'],
                fvg_top=latest['fvg_top'],
                fvg_bottom=latest['fvg_bottom'],
                fvg_atr_mult=latest['fvg_atr_mult'],
                displacement_atr_mult=latest['displacement_atr_mult'],
                active_session=get_current_session(),
                htf_trend=htf_trend,
                liquidity_sweep=False,
                entry_zone=mode,
                be_enabled=settings.break_even_after_tp1,
                trail_enabled=settings.trailing_after_tp1,
                volume_ratio=latest.get('volume_ratio', 1.0),
                chop_flag=bool(latest.get('chop_flag', False)),
                stop_buffer=settings.stop_buffer_atr,
                tp2_rr=settings.tp2_rr,
                expiry_bars=settings.max_bars_to_retrace,
                fvg_stale=bool(latest.get('fvg_stale', False))
            )
        except Exception as e:
            logger.error(f"Critical error generating TradeSetupPayload for {symbol}: {e}", exc_info=True)
            return
            
        self.process_signal(payload, fvg_time)
        
    def process_signal(self, payload: TradeSetupPayload, fvg_time: str):
        trade_data = payload.model_dump(exclude={
            "fvg_atr_mult", "displacement_atr_mult", "active_session", 
            "liquidity_sweep", "be_enabled", "trail_enabled"
        })
        trade_data["rr_to_tp1"] = payload.rr_to_tp1
        trade_data["rr_to_tp2"] = payload.rr_to_tp2
        trade_data["stop_distance"] = payload.stop_distance
        now_utc = datetime.utcnow()
        trade_data["detected_at"] = now_utc
        trade_data["fvg_time"] = fvg_time
        
        strategy_passed, strat_reason = evaluate_strategy(payload)
        if not strategy_passed:
            trade_data.update({"status": "REJECTED", "reason": strat_reason})
            add_trade(self.db, trade_data)
            logger.info(strat_reason)
            diagnostics.log_rejection(payload.symbol, strat_reason, 'STRATEGY')
            return

        trade_data.update({
            "status": "WAITING_FOR_RETRACE"
        })
        
        db_trade = add_trade(self.db, trade_data)
        logger.info(f"\n+++ Setup Identified: {payload.direction} @ {payload.entry} (SL: {payload.stop}) +++")
        logger.info(f"Setup {db_trade.id} WAITING_FOR_RETRACE on {payload.symbol}")
        
        diagnostics.log_waiting_for_retrace(payload, db_trade.id, now_utc)
        
        self.active_setups[payload.symbol] = {
            'payload': payload,
            'db_id': db_trade.id,
            'detected_time': now_utc,
            'fvg_time': fvg_time
        }
        self.last_fvg_time[payload.symbol] = fvg_time

    def manage_active_setup(self, symbol: str, df_1m: pd.DataFrame):
        setup = self.active_setups.get(symbol)
        if not setup:
            return
            
        latest = df_1m.iloc[-1]
        payload: TradeSetupPayload = setup['payload']
        db_id = setup['db_id']
        
        # 1. Cancel if FVG is stale (close violates fvg bounds)
        fvg_stale = False
        if payload.direction == "LONG" and latest['close'] < payload.fvg_bottom:
            fvg_stale = True
        elif payload.direction == "SHORT" and latest['close'] > payload.fvg_top:
            fvg_stale = True
            
        # Reject late / extended entries (e.g., if price runs to TP1 before entry)
        extended = False
        if payload.direction == "LONG" and latest['high'] >= payload.tp1:
            extended = True
        elif payload.direction == "SHORT" and latest['low'] <= payload.tp1:
            extended = True
            
        if fvg_stale or extended:
            reason = "Stale FVG" if fvg_stale else "Price ran to TP1 before entry"
            self.cancel_setup(symbol, db_id, reason)
            return
            
        # 2. Check for entry
        hit_entry = False
        if payload.direction == "LONG" and latest['low'] <= payload.entry:
            hit_entry = True
        elif payload.direction == "SHORT" and latest['high'] >= payload.entry:
            hit_entry = True
            
        if hit_entry:
            # 1. Global Safety Guards
            open_count = self.db.query(DBTrade).filter(DBTrade.status.in_(["ENTERED", "PARTIAL_TP1"])).count()
            if open_count >= settings.max_open_positions:
                self.cancel_setup(symbol, db_id, f"Max Positions Reached globally ({settings.max_open_positions})")
                return

            active_symbol_trades = self.db.query(DBTrade).filter(DBTrade.symbol == symbol, DBTrade.status.in_(["ENTERED", "PARTIAL_TP1"])).count()
            if active_symbol_trades > 0:
                self.cancel_setup(symbol, db_id, "Active trade already running for symbol")
                return
                
            open_trades = self.db.query(DBTrade).filter(DBTrade.status.in_(["ENTERED", "PARTIAL_TP1"])).all()
            current_notional = sum(t.entry * t.units for t in open_trades)
            
            # 2. Setup Sizing & Risk rules
            db_trade = self.db.query(DBTrade).filter(DBTrade.id == db_id).first()
            daily_losses = get_daily_losses(self.db)
            risk_passed, risk_reason, risk_details = evaluate_risk(payload, daily_losses)
            
            if not risk_passed:
                self.cancel_setup(symbol, db_id, f"Risk/Sizing: {risk_reason}", "REJECTED", "RISK")
                return
                
            projected_notional = current_notional + (payload.entry * risk_details["units_to_buy"])
            if projected_notional > settings.max_notional_exposure:
                self.cancel_setup(symbol, db_id, f"Max Notional Exposure exceeded (${projected_notional:.2f})", "REJECTED")
                return
                
            ai_result = run_ai_review(payload)
            if ai_result.action != "TAKE":
                self.cancel_setup(symbol, db_id, f"AI Rejected: {ai_result.action} ({', '.join(ai_result.reasons)})", "REJECTED", "AI")
                send_notification(payload, ai_result)
                return
                
            logger.info(f"Setup {db_id} ENTERED on {symbol}!")
            db_trade.status = "ENTERED"
            db_trade.entered_at = datetime.utcnow()
            db_trade.units = risk_details["units_to_buy"]
            db_trade.ai_action = ai_result.action
            db_trade.ai_grade = ai_result.grade
            db_trade.reason = f"AI Reasons: {', '.join(ai_result.reasons)}"
            self.db.commit()
            
            self.executor.place_order(
                symbol=payload.symbol, 
                direction=payload.direction, 
                quantity=db_trade.units,
                entry_price=payload.entry,
                stop_loss_price=payload.stop,
                take_profit_price=payload.tp1
            )
            diagnostics.log_entered(symbol)
            send_notification(payload, ai_result)
            self.active_setups.pop(symbol, None)
            return
            
        # 3. Check for expiry timeout
        # timeframe is 5m, so 8 bars * 5 mins = 40 mins
        max_mins = settings.max_bars_to_retrace * 5
        mins_elapsed = (datetime.utcnow() - setup['detected_time']).total_seconds() / 60
        
        if mins_elapsed > max_mins:
            # Calculate distance missed
            setup_time_utc = pd.to_datetime(setup['detected_time'], utc=True)
            recent_df = df_1m[df_1m['timestamp'] > setup_time_utc]
            
            if recent_df.empty:
                recent_df = df_1m.tail(1)
                
            if payload.direction == "LONG":
                min_price = recent_df['low'].min()
                missed_by = min_price - payload.entry
            else:
                max_price = recent_df['high'].max()
                missed_by = payload.entry - max_price
                
            atr = latest.get('ATR', 0)
            missed_by_atr = abs(missed_by) / atr if atr > 0 else 0
            
            diagnostics.log_expired(symbol, setup['detected_time'], "Timeout - Failed to retrace in time", abs(missed_by), missed_by_atr)
            self.cancel_setup(symbol, db_id, "Timeout - Failed to retrace in time", "EXPIRED")

    async def manage_open_trades(self, symbol: str, current_price: float, current_high: float, current_low: float):
        """Monitors ENTERED trades for proper Stage 4 Exits (Partials, BE, TP2, Early Exit)."""
        open_trades = self.db.query(DBTrade).filter(DBTrade.symbol == symbol, DBTrade.status.in_(["ENTERED", "PARTIAL_TP1"])).all()
        for t in open_trades:
            # 1. State-Dependent Stop Target
            current_stop = t.stop
            if t.status == "PARTIAL_TP1" and t.be_triggered == "TRUE":
                current_stop = t.entry
                
            # 2. Early Invalidation (Structure Fails After Entry)
            early_exit = False
            if t.status == "ENTERED":
                if t.direction == "LONG" and current_price < t.fvg_bottom:
                    early_exit = True
                elif t.direction == "SHORT" and current_price > t.fvg_top:
                    early_exit = True

            # 3. Native Stop / BreakEven Evaluation
            if (t.direction == "LONG" and current_low <= current_stop) or \
               (t.direction == "SHORT" and current_high >= current_stop):
                if t.status == "PARTIAL_TP1":
                    t.status = "BREAKEVEN_EXIT"
                    logger.info(f"Trade {t.id} BREAKEVEN_EXIT (Direction: {t.direction})")
                else:
                    t.status = "STOPPED"
                    logger.info(f"Trade {t.id} STOPPED (Direction: {t.direction})")
                
                t.closed_at = datetime.utcnow()
                self.db.commit()
                self.executor.close_position(t.symbol, t.direction, t.units if t.status == "STOPPED" else t.units / 2.0, "STOP/BE")
                self.apply_cooldown(t.symbol, minutes=15)
                continue

            # 4. Native Early Invalidation Execution
            if early_exit:
                t.status = "STOPPED"
                t.reason = "Early Invalidation Post-Entry"
                t.closed_at = datetime.utcnow()
                logger.info(f"Trade {t.id} STOPPED via Early Invalidation (Direction: {t.direction})")
                self.db.commit()
                self.executor.close_position(t.symbol, t.direction, t.units, "EARLY_INVALIDATION")
                self.apply_cooldown(t.symbol, minutes=15)
                continue

            # 5. TP1 Evaluation
            if t.status == "ENTERED":
                if (t.direction == "LONG" and current_high >= t.tp1) or \
                   (t.direction == "SHORT" and current_low <= t.tp1):
                    t.status = "PARTIAL_TP1"
                    if settings.break_even_after_tp1:
                        t.be_triggered = "TRUE"
                    self.db.commit()
                    logger.info(f"Trade {t.id} hit TP1! Taking 50% partial. (Direction: {t.direction})")
                    self.executor.close_position(t.symbol, t.direction, t.units / 2.0, "TP1")

            # 6. TP2 & Trailing Evaluation
            if t.status == "PARTIAL_TP1":
                # Basic Trailing hook (OFF by default)
                if t.trailing_active == "TRUE":
                    pass 
                
                if (t.direction == "LONG" and current_high >= t.tp2) or \
                   (t.direction == "SHORT" and current_low <= t.tp2):
                    t.status = "TP2_HIT"
                    t.closed_at = datetime.utcnow()
                    self.db.commit()
                    logger.info(f"Trade {t.id} fully completed at TP2! (Direction: {t.direction})")
                    self.executor.close_position(t.symbol, t.direction, t.units / 2.0, "TP2")
                    self.apply_cooldown(t.symbol, minutes=15)

if __name__ == "__main__":
    bot = TradingBot()
    try:
        asyncio.run(bot.run_loop())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        diagnostics.print_summary(is_shutdown=True)
