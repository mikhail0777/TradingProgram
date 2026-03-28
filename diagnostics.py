import logging
import json
import os
from collections import defaultdict
from datetime import datetime
from models import TradeSetupPayload

# Setup a dedicated diagnostics logger that writes to both console and file
diag_logger = logging.getLogger("diagnostics")
diag_logger.setLevel(logging.INFO)

# File handler for diagnostics.log
fh = logging.FileHandler("diagnostics.log")
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
fh.setFormatter(formatter)
diag_logger.addHandler(fh)

class DiagnosticEngine:
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.symbols = set()
        
        # Track counts per symbol.
        # Structure: { symbol: { counter_name: count } }
        self.counters = defaultdict(lambda: defaultdict(int))
        
        # We need a way to deduplicate counting candles/candidates to just once per candle.
        self.last_candle_time = defaultdict(str)
        self.last_alert_time = datetime.utcnow()

    def register_symbols(self, symbols: list[str]):
        for sym in symbols:
            self.symbols.add(sym)

    def process_new_candle(self, symbol: str, timestamp_str: str, raw_bos_dir: str, valid_bos_dir: str, raw_fvg: bool, valid_fvg: bool):
        """Called once per tick for the most recent closed 5m candle. Deduplicates via timestamp."""
        if self.last_candle_time[symbol] == timestamp_str:
            return # Already processed this candle
            
        self.last_candle_time[symbol] = timestamp_str
        self.increment(symbol, "candles_processed")
        
        if raw_bos_dir != 'NONE':
            self.increment(symbol, "bos_candidates_found")
        if valid_bos_dir != 'NONE':
            self.increment(symbol, "valid_bos_found")
            
        if raw_fvg:
            self.increment(symbol, "fvg_candidates_found")
        if valid_fvg:
            self.increment(symbol, "valid_fvg_found")

    def increment(self, symbol: str, counter_name: str, amount: int = 1):
        self.counters[symbol][counter_name] += amount
        self.symbols.add(symbol)
        
    def log_rejection(self, symbol: str, reason: str, stage: str):
        """
        Parses strategy failure reason to bucket into specific counters.
        stage can be 'STRATEGY', 'RISK', 'AI'.
        """
        if stage == 'STRATEGY':
            if "choppy" in reason or "compressed" in reason:
                self.increment(symbol, "setups_rejected_chop")
            elif "volume" in reason.lower():
                self.increment(symbol, "setups_rejected_volume")
            elif "HTF" in reason or "LTF" in reason:
                self.increment(symbol, "setups_rejected_htf")
            elif "session" in reason.lower():
                self.increment(symbol, "setups_rejected_session")
            elif "stale" in reason.lower():
                self.increment(symbol, "setups_rejected_stale")
            elif "displacement" in reason.lower():
                self.increment(symbol, "setups_rejected_displacement")
            else:
                self.increment(symbol, "strategy_rejected_other")
        elif stage == 'RISK':
            self.increment(symbol, "trades_rejected_risk")
        elif stage == 'AI':
            self.increment(symbol, "trades_rejected_ai")
            
        # Log to specifics
        diag_logger.info(f"[{symbol}] REJECTED ({stage}): {reason}")

    def log_waiting_for_retrace(self, payload: TradeSetupPayload, db_id: int, detected_time: datetime):
        self.increment(payload.symbol, "setups_created_waiting_for_retrace")
        msg = (
            f"[\u23f3 WAITING_FOR_RETRACE] {payload.symbol} {payload.direction} | "
            f"FVG: {payload.fvg_bottom:.2f} to {payload.fvg_top:.2f} | "
            f"Entry: {payload.entry:.2f} | Stop: {payload.stop:.2f} | "
            f"TP1: {payload.tp1:.2f} | TP2: {payload.tp2:.2f} | "
            f"Detected: {detected_time.strftime('%H:%M:%S UTC')}"
        )
        diag_logger.info(msg)

    def log_expired(self, symbol: str, detected_time: datetime, reason: str, missed_by_points: float, missed_by_atr: float):
        self.increment(symbol, "setups_expired")
        missed_atr_str = f"({missed_by_atr:.2f}x ATR)" if missed_by_atr > 0 else ""
        msg = (
            f"[\u23f1\ufe0f EXPIRED] {symbol} | "
            f"Detected: {detected_time.strftime('%H:%M:%S UTC')} | "
            f"Reason: {reason} | "
            f"Missed entry by: {missed_by_points:.4f} pts {missed_atr_str}"
        )
        diag_logger.info(msg)

    def log_cancelled(self, symbol: str, reason: str):
        self.increment(symbol, "setups_cancelled")
        diag_logger.info(f"[\u274c CANCELLED] {symbol} | Reason: {reason}")
        
    def log_entered(self, symbol: str):
        self.increment(symbol, "entries_triggered")
        diag_logger.info(f"[\u2705 ENTERED] {symbol}")

    def print_summary(self, is_shutdown=False):
        now = datetime.utcnow()
        elapsed = now - self.start_time
        
        title = "=== SHUTDOWN SUMMARY ===" if is_shutdown else "=== PERIODIC SUMMARY ==="
        title += f" (Uptime: {elapsed})"
        
        diag_logger.info("\n" + "="*50)
        diag_logger.info(title)
        
        global_counters = defaultdict(int)
        
        for sym in sorted(self.symbols):
            sym_stats = self.counters[sym]
            diag_logger.info(f"\n--- {sym} ---")
            for k, v in sym_stats.items():
                diag_logger.info(f"  {k}: {v}")
                global_counters[k] += v
                
        diag_logger.info("\n--- OVERALL TOTALS ---")
        for k, v in global_counters.items():
            diag_logger.info(f"  {k}: {v}")
            
        diag_logger.info("="*50 + "\n")
        self.last_alert_time = now

# Global instance to be imported by bot.py
diagnostics = DiagnosticEngine()
