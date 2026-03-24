from models import TradeSetupPayload
from config import settings
from datetime import datetime
import pytz

def evaluate_strategy(payload: TradeSetupPayload) -> tuple[bool, str]:
    """
    Evaluates the incoming alert against strict strategy filters.
    Returns a tuple (is_valid, reason_if_invalid).
    """
    # 1. Structure Check
    if payload.bos_direction == "NONE":
        return False, "Rejected: Missing structural BOS direction."
        
    # Check if FVG was marked freshly stale (bot.py sets it to True if broken, but payload defaults to False if not in model)
    if getattr(payload, 'fvg_stale', False):
        return False, "Rejected: FVG was mapped as stale."

    if payload.fvg_atr_mult <= 0.0:
        return False, "Rejected: Missing FVG (Gap <= 0)."
        
    if payload.entry_zone == "NONE":
        return False, "Rejected: Entry must occur inside the FVG retracement zone."

    # 2. Momentum / Displacement Check
    if payload.displacement_atr_mult < 1.0:
        return False, f"Rejected: Weak displacement ({payload.displacement_atr_mult}x ATR, needs >= 1.0)."

    # 3. Market State Filters (Phase 2 additions)
    # Check chop flag
    if getattr(payload, 'chop_flag', False):
        return False, "Rejected: Setup occurred during choppy/compressed market conditions."
        
    # Check relative volume (volume_ratio is 1.0 by default)
    vol_ratio = getattr(payload, 'volume_ratio', 1.0)
    if vol_ratio < 0.8:
        return False, f"Rejected: Weak relative volume ({vol_ratio:.2f}x average)."

    # 4. Session Check using specific ET configured boundaries
    try:
        et_tz = pytz.timezone('US/Eastern')
        # Here we check the current execution runtime, but ideally we'd use the candle time.
        # Given this is evaluated natively when bot generates setup, it is close.
        now_et = datetime.now(et_tz).time()
        
        def parse_time(t_str):
            h, m = map(int, t_str.split(':'))
            from datetime import time
            return time(h, m)

        p_start = parse_time(settings.session_primary_start)
        p_end = parse_time(settings.session_primary_end)
        s_start = parse_time(settings.session_secondary_start)
        s_end = parse_time(settings.session_secondary_end)

        in_primary = p_start <= now_et <= p_end
        in_secondary = s_start <= now_et <= s_end
        
        if not (in_primary or in_secondary):
            return False, f"Rejected: Setup occurred outside active US Equities sessions."
    except Exception as e:
        # Graceful fallback if pytz isn't installed in the environment just yet 
        # (it should be, but just in case)
        if payload.active_session.upper() == "NONE":
            return False, "Rejected: Setup occurred outside of an active general session."

    # 5. HTF Alignment Check
    if payload.direction == "LONG" and payload.htf_trend.upper() != "BULLISH":
        return False, f"Rejected: Long setup against HTF trend ({payload.htf_trend})."
        
    if payload.direction == "SHORT" and payload.htf_trend.upper() != "BEARISH":
        return False, f"Rejected: Short setup against HTF trend ({payload.htf_trend})."
        
    return True, "Passed all strict strategy filters"
