from models import WebhookPayload

def evaluate_strategy(payload: WebhookPayload) -> tuple[bool, str]:
    """
    Evaluates the incoming alert against strict strategy filters.
    Returns a tuple (is_valid, reason_if_invalid).
    """
    # 1. Structure Check
    if not payload.bos_detected:
        return False, "Rejected: Missing BOS (Break of Structure)."
        
    if not payload.fvg_detected:
        return False, "Rejected: Missing FVG (Fair Value Gap)."

    # 2. Momentum / Displacement Check (Require at least an average sized candle, > 1.0 ATR)
    if payload.displacement_atr_mult < 1.0:
        return False, f"Rejected: Weak displacement ({payload.displacement_atr_mult}x ATR, needs >= 1.0)."

    # 3. Session Check
    if payload.active_session.upper() == "NONE":
        return False, "Rejected: Setup occurred outside of an active session."

    # 4. HTF Alignment Check
    if payload.direction == "LONG" and payload.htf_bias.upper() != "BULLISH":
        return False, f"Rejected: Long setup against HTF bias ({payload.htf_bias})."
        
    if payload.direction == "SHORT" and payload.htf_bias.upper() != "BEARISH":
        return False, f"Rejected: Short setup against HTF bias ({payload.htf_bias})."
        
    return True, "Passed all strict strategy filters"
