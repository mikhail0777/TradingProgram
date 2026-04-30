import logging
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
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
        self.start_time = datetime.now(timezone.utc)
        self.symbols = set()
        
        # Track counts per symbol.
        # Structure: { symbol: { counter_name: count } }
        self.counters = defaultdict(lambda: defaultdict(int))
        
        # We need a way to deduplicate counting candles/candidates to just once per candle.
        self.last_candle_time = defaultdict(str)
        self.last_alert_time = datetime.now(timezone.utc)

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

    def log_waiting_for_retrace(self, payload: TradeSetupPayload, db_id: int, detected_time: datetime, tolerance_buffer: float = 0.0):
        self.increment(payload.symbol, "setups_created_waiting_for_retrace")
        msg = (
            f"[WAITING_FOR_RETRACE] {payload.symbol} {payload.direction} | "
            f"Mode: {payload.entry_zone} | "
            f"FVG: {payload.fvg_bottom:.2f} to {payload.fvg_top:.2f} | "
            f"Entry Limit: {payload.entry:.2f} (Buffer: {tolerance_buffer:.3f}) | Stop: {payload.stop:.2f} | "
            f"TP1: {payload.tp1:.2f} | TP2: {payload.tp2:.2f} | "
            f"Detected: {detected_time.strftime('%H:%M:%S UTC')}"
        )
        diag_logger.info(msg)

    def log_expired(self, symbol: str, detected_time: datetime, reason: str, missed_by_points: float, missed_by_atr: float):
        self.increment(symbol, "setups_expired")
        missed_atr_str = f"({missed_by_atr:.2f}x ATR)" if missed_by_atr > 0 else ""
        msg = (
            f"[EXPIRED] {symbol} | "
            f"Detected: {detected_time.strftime('%H:%M:%S UTC')} | "
            f"Reason: {reason} | "
            f"Missed entry by: {missed_by_points:.4f} pts {missed_atr_str}"
        )
        diag_logger.info(msg)

    def log_cancelled(self, symbol: str, detected_time: datetime, reason: str, missed_by_points: float = 0.0, missed_by_atr: float = 0.0):
        if "Stale" in reason:
            self.increment(symbol, "setups_cancelled_stale")
        elif "TP1" in reason:
            self.increment(symbol, "setups_cancelled_tp1")
        else:
            self.increment(symbol, "setups_cancelled_other")
            
        missed_atr_str = f"({missed_by_atr:.2f}x ATR)" if missed_by_atr > 0 else ""
        msg = (
            f"[CANCELLED] {symbol} | "
            f"Detected: {detected_time.strftime('%H:%M:%S UTC')} | "
            f"Reason: {reason} | "
            f"Missed entry by: {missed_by_points:.4f} pts {missed_atr_str}"
        )
        diag_logger.info(msg)
        
    def log_entered(self, symbol: str):
        self.increment(symbol, "entries_triggered")
        diag_logger.info(f"[ENTERED] {symbol}")

    def print_summary(self, is_shutdown=False):
        now = datetime.now(timezone.utc)
        elapsed = now - self.start_time
        
        title = "=== SHUTDOWN SUMMARY ===" if is_shutdown else "=== PERIODIC SUMMARY ==="
        title += f" (Uptime: {elapsed})"
        
        diag_logger.info("\n" + "="*50)
        diag_logger.info(title)
        
        ALL_KEYS = [
            "candles_processed",
            "bos_candidates_found",
            "valid_bos_found",
            "fvg_candidates_found",
            "valid_fvg_found",
            "bos_and_fvg_overlap_found",
            "setup_creation_attempted",
            "setup_creation_skipped_reason",
            "setups_rejected_chop",
            "setups_rejected_volume",
            "setups_rejected_htf",
            "setups_rejected_session",
            "setups_rejected_stale",
            "setups_rejected_displacement",
            "strategy_rejected_other",
            "setups_created_waiting_for_retrace",
            "setups_expired",
            "setups_cancelled_stale",
            "setups_cancelled_tp1",
            "setups_cancelled_other",
            "entries_triggered",
            "trades_rejected_risk",
            "trades_rejected_ai"
        ]
        
        global_counters = defaultdict(int)
        
        for sym in sorted(self.symbols):
            sym_stats = self.counters[sym]
            diag_logger.info(f"\n--- {sym} ---")
            for k in ALL_KEYS:
                v = sym_stats.get(k, 0)
                diag_logger.info(f"  {k}: {v}")
                global_counters[k] += v
                
        diag_logger.info("\n--- OVERALL TOTALS ---")
        for k in ALL_KEYS:
            v = global_counters.get(k, 0)
            diag_logger.info(f"  {k}: {v}")
            
        diag_logger.info("\n--- FUNNEL ANALYSIS (OVERALL) ---")
        b1 = global_counters.get("bos_candidates_found", 0)
        b2 = global_counters.get("valid_bos_found", 0)
        f1 = global_counters.get("fvg_candidates_found", 0)
        f2 = global_counters.get("valid_fvg_found", 0)
        ov = global_counters.get("bos_and_fvg_overlap_found", 0)
        att = global_counters.get("setup_creation_attempted", 0)
        w = global_counters.get("setups_created_waiting_for_retrace", 0)
        e = global_counters.get("entries_triggered", 0)
        
        diag_logger.info(f"  Raw BOS: {b1} -> Valid BOS: {b2} -> Raw FVG: {f1} -> Valid FVG: {f2} -> Overlap: {ov} -> Attempted: {att} -> Waiting: {w} -> Entered: {e}")
            
        diag_logger.info("="*50 + "\n")
        self.last_alert_time = now

# Global instance to be imported by bot.py
diagnostics = DiagnosticEngine()
