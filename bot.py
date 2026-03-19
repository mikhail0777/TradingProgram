import asyncio
import logging
from datetime import datetime

from config import settings
from db import init_db, get_db, add_trade, DBTrade
from models import WebhookPayload
from strategy import evaluate_strategy
from risk_engine import evaluate_risk
from ai_review import run_ai_review
from notifier import send_notification
from execution import Executor
from data_feed import MarketDataFeed
from analyzer import MarketAnalyzer
from sqlalchemy.orm import Session

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
    def __init__(self, symbol='BTC/USD'):
        self.symbol = symbol
        self.data_feed = MarketDataFeed(symbol=symbol)
        self.analyzer = MarketAnalyzer()
        self.executor = Executor()
        
        # Initialize DB
        init_db()
        self.db = next(get_db())

    async def run_loop(self):
        logger.info(f"Starting bot loop for {self.symbol}...")
        while True:
            try:
                await self.tick()
            except Exception as e:
                logger.error(f"Error in main loop tick: {e}", exc_info=True)
            # Fetch data continually (every 60 seconds is typical for 1m base candles)
            await asyncio.sleep(60)

    async def tick(self):
        # 1. Fetch Market Data
        df_1m = self.data_feed.fetch_latest_candles(limit=200)
        if df_1m.empty:
            logger.warning("No data retrieved.")
            return
            
        # Manage open trades based on latest 1m candle
        latest_1m = df_1m.iloc[-1]
        await self.manage_open_trades(latest_1m['close'], latest_1m['high'], latest_1m['low'])
        
        # 2. Aggregate to 5m for primary strategy.
        df_5m = self.data_feed.get_aggregated_candles(df_1m, timeframe_rule='5min')
        df_5m = self.data_feed.compute_atr(df_5m)
        
        # 3. Analyze Technicals
        df_analyzed = self.analyzer.analyze(df_5m)
        latest = df_analyzed.iloc[-1]
        
        # Check if we have an active setup forming right now (active FVG + BOS present)
        # Note: the setup logic triggers when FVG activates just after a BOS.
        if not latest['fvg_active'] or latest['bos_direction'] == 'NONE':
            return
            
        # Valid setup metrics generated. Construct Payload!
        direction = 'LONG' if latest['bos_direction'] == 'BULLISH' else 'SHORT'
        
        # Calculate conservative entry off FVG Midpoint
        if direction == 'LONG':
            entry_price = latest['fvg_bottom'] + (latest['fvg_top'] - latest['fvg_bottom']) * 0.5
            stop = latest['last_swing_low_price']
            tp1 = entry_price + (entry_price - stop) * settings.min_rr
            tp2 = entry_price + (entry_price - stop) * (settings.min_rr + 2)
        else:
            entry_price = latest['fvg_top'] - (latest['fvg_top'] - latest['fvg_bottom']) * 0.5
            stop = latest['last_swing_high_price']
            tp1 = entry_price - (stop - entry_price) * settings.min_rr
            tp2 = entry_price - (stop - entry_price) * (settings.min_rr + 2)
            
        htf_trend = self.analyzer.get_htf_trend(df_1m)
        
        payload = WebhookPayload(
            symbol=self.symbol,
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
            entry_zone="FVG_MIDPOINT",
            be_enabled=True,
            trail_enabled=False
        )
        
        logger.info(f"\n+++ Setup Identified: {direction} @ {payload.entry} (SL: {payload.stop}) +++")
        self.process_signal(payload)
        
    def process_signal(self, payload: WebhookPayload):
        trade_data = payload.model_dump(exclude={
            "fvg_atr_mult", "displacement_atr_mult", "active_session", 
            "liquidity_sweep", "be_enabled", "trail_enabled"
        })
        trade_data["rr"] = payload.rr
        trade_data["stop_distance"] = payload.stop_distance
        
        # 1. Strategy Filters
        strategy_passed, strat_reason = evaluate_strategy(payload)
        if not strategy_passed:
            trade_data.update({"status": "REJECTED", "reason": strat_reason})
            add_trade(self.db, trade_data)
            logger.info(strat_reason)
            return
            
        # 2. Risk Engine
        daily_losses = get_daily_losses(self.db)
        risk_passed, risk_reason, risk_details = evaluate_risk(payload, daily_losses)
        if not risk_passed:
            trade_data.update({"status": "REJECTED", "reason": risk_reason})
            add_trade(self.db, trade_data)
            logger.info(risk_reason)
            return

        # 3. AI Review
        ai_result = run_ai_review(payload)
        trade_data.update({
            "ai_action": ai_result.action,
            "ai_grade": ai_result.grade,
            "reason": f"AI Reasons: {', '.join(ai_result.reasons)}",
            "status": "PENDING"
        })
        add_trade(self.db, trade_data)
        logger.info(f"AI Review Complete: Action={ai_result.action}, Grade={ai_result.grade}")
        send_notification(payload, ai_result)
        
        # 4. Execute Live/Paper
        if ai_result.action == "TAKE":
            self.executor.place_order(
                symbol=payload.symbol, 
                direction=payload.direction, 
                quantity=risk_details["units_to_buy"],
                entry_price=payload.entry,
                stop_loss_price=payload.stop,
                take_profit_price=payload.tp1
            )

    async def manage_open_trades(self, current_price: float, current_high: float, current_low: float):
        """Monitors PENDING (open) trades to see if they hit SL or TP based on latest candle."""
        open_trades = self.db.query(DBTrade).filter(DBTrade.status == "PENDING").all()
        for t in open_trades:
            # Check Stop Loss
            if t.direction == "LONG" and current_low <= t.stop:
                t.status = "LOSS"
            elif t.direction == "SHORT" and current_high >= t.stop:
                t.status = "LOSS"
            # Check TP1
            elif t.direction == "LONG" and current_high >= t.tp1:
                t.status = "WIN"
            elif t.direction == "SHORT" and current_low <= t.tp1:
                t.status = "WIN"
                
            if t.status in ["WIN", "LOSS"]:
                logger.info(f"Trade {t.id} closed as {t.status} (Direction: {t.direction})")
                self.db.commit()

if __name__ == "__main__":
    bot = TradingBot()
    try:
        asyncio.run(bot.run_loop())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
