import datetime
import pytz
import asyncio
from unittest.mock import patch

from config import settings
from data_feed import MarketDataFeed
from analyzer import MarketAnalyzer
from diagnostics import diagnostics, diag_logger
from models import TradeSetupPayload
from strategy import evaluate_strategy
from bot import TradingBot

def run_historical_diagnostics():
    bot = TradingBot() # just to access symbols
    
    print("\nStarting historical diagnostics over the last 5 days...")
    
    for symbol in bot.symbols:
        print(f"Fetching data for {symbol}...")
        feed = MarketDataFeed(symbol=symbol)
        df_1m = feed.fetch_latest_candles(limit=200) # fetches 5d internally
        if df_1m.empty:
            continue
            
        print(f"Aggregating 5m candles for {symbol}...")
        df_5m = feed.get_aggregated_candles(df_1m, timeframe_rule='5min')
        df_5m = feed.compute_atr(df_5m)
        
        analyzer = MarketAnalyzer()
        df_analyzed = analyzer.analyze(df_5m)
        
        for i in range(len(df_analyzed)):
            row = df_analyzed.iloc[i]
            
            timestamp_str = str(row['timestamp'])
            raw_bos = row.get('raw_bos_direction', 'NONE')
            valid_bos = row.get('bos_direction', 'NONE')
            raw_fvg = row.get('raw_fvg_active', False)
            valid_fvg = row.get('fvg_active', False)
            
            diagnostics.process_new_candle(
                symbol=symbol,
                timestamp_str=timestamp_str,
                raw_bos_dir=raw_bos,
                valid_bos_dir=valid_bos,
                raw_fvg=raw_fvg,
                valid_fvg=valid_fvg
            )
            
            if not valid_fvg or valid_bos == 'NONE':
                continue
                
            # A valid strategy candidate! Generate payload.
            direction = 'LONG' if valid_bos == 'BULLISH' else 'SHORT'
            stop = row['last_swing_low_price'] - settings.stop_buffer_atr * row.get('ATR', 0) if direction == 'LONG' else row['last_swing_high_price'] + settings.stop_buffer_atr * row.get('ATR', 0)
            
            # Simple midpoint entry for test
            entry_price = row['fvg_bottom'] + (row['fvg_top'] - row['fvg_bottom']) * 0.5
            
            try:
                payload = TradeSetupPayload(
                    symbol=symbol,
                    timeframe='5m',
                    direction=direction,
                    entry=entry_price,
                    stop=stop,
                    tp1=entry_price,
                    tp2=entry_price,
                    bos_direction=row['bos_direction'],
                    fvg_top=row['fvg_top'],
                    fvg_bottom=row['fvg_bottom'],
                    fvg_atr_mult=row['fvg_atr_mult'],
                    displacement_atr_mult=row['displacement_atr_mult'],
                    active_session="MOCK",
                    htf_trend=analyzer.get_htf_trend(df_1m),
                    liquidity_sweep=False,
                    entry_zone="MIDPOINT",
                    chop_flag=bool(row.get('chop_flag', False)),
                    volume_ratio=row.get('volume_ratio', 1.0),
                    fvg_stale=bool(row.get('fvg_stale', False))
                )
            except Exception as e:
                diag_logger.error(f"Failed to create payload for {symbol}: {e}")
                continue
            
            # evaluate_strategy uses datetime.now() to check session.
            # We must mock it to use the candle's timestamp.
            candle_dt = row['timestamp']
            
            class MockDatetime:
                @classmethod
                def now(cls, tz=None):
                    if tz:
                        return candle_dt.astimezone(tz)
                    return candle_dt

            with patch('strategy.datetime', MockDatetime):
                passed, reason = evaluate_strategy(payload)
                
            if not passed:
                diagnostics.log_rejection(symbol, reason, "STRATEGY")
            else:
                # Setup reached WAITING FOR RETRACE
                diagnostics.log_waiting_for_retrace(payload, 9999, candle_dt)
                
    diagnostics.print_summary(is_shutdown=True)

if __name__ == "__main__":
    run_historical_diagnostics()
