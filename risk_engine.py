from config import settings
from models import WebhookPayload

def evaluate_risk(payload: WebhookPayload, current_daily_losses: int) -> tuple[bool, str, dict]:
    """
    Validates risk rules and calculates position size.
    Returns (is_valid, reason_if_invalid, risk_details_dict)
    """
    empty_details = {"position_size_usd": 0.0, "units_to_buy": 0.0, "risk_per_unit": 0.0}
    # 1. Daily Loss Limit
    if current_daily_losses >= settings.max_daily_losses:
        return False, f"Rejected: Reached max daily losses ({current_daily_losses}).", empty_details

    # 2. Stop Distance & Logic Validation
    if payload.direction == "LONG" and payload.stop >= payload.entry:
        return False, "Rejected: Invalid stop loss placement for LONG.", empty_details
    if payload.direction == "SHORT" and payload.stop <= payload.entry:
        return False, "Rejected: Invalid stop loss placement for SHORT.", empty_details
        
    stop_distance = payload.stop_distance
    if stop_distance == 0:
        return False, "Rejected: Stop distance cannot be zero.", empty_details

    # 3. RR Validation
    if payload.rr < settings.min_rr:
        return False, f"Rejected: Conservative RR to TP1 too low ({payload.rr} < {settings.min_rr}).", empty_details
        
    # 4. Position Sizing
    # Max risk in USD based on account balance
    max_risk_usd = settings.account_balance * (settings.max_risk_percent / 100.0)
    
    # Position size = Risk_USD / Risk_per_Unit
    # Risk_per_Unit = distance from entry to stop
    # So if you buy 1 unit (e.g. 1 coin, 1 share), and price drops by stop_distance, you lose stop_distance
    # Therefore, Number of units = max_risk_usd / stop_distance
    # Position Size (USD) = Number of units * entry price
    risk_per_unit = stop_distance
    units_to_buy = max_risk_usd / risk_per_unit
    suggested_position_size = units_to_buy * payload.entry
    
    details = {
        "position_size_usd": round(suggested_position_size, 2),
        "units_to_buy": round(units_to_buy, 4),
        "risk_per_unit": round(risk_per_unit, 4)
    }
    
    return True, "Passed risk evaluation", details
