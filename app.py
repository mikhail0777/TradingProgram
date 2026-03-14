from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime

from config import settings
from db import init_db, get_db, add_trade, update_trade_outcome, DBTrade
from models import WebhookPayload, TradeResultUpdate
from strategy import evaluate_strategy
from risk_engine import evaluate_risk
from ai_review import run_ai_review
from notifier import send_notification

app = FastAPI(title="Paper Trading Alert Server")

@app.on_event("startup")
def on_startup():
    init_db()

def verify_secret(x_algo_secret: str = Header(None)):
    if x_algo_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    return x_algo_secret

def get_daily_losses(db: Session) -> int:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(DBTrade).filter(
        DBTrade.timestamp >= today_start,
        DBTrade.status == "LOSS"
    ).count()

@app.post("/webhook")
def receive_webhook(
    payload: WebhookPayload, 
    db: Session = Depends(get_db), 
    secret: str = Depends(verify_secret)
):
    """
    Main entrypoint: Webhook -> Validation -> Strategy -> Risk -> AI Review -> Logging -> Notify
    """
    # Create an initial record structure
    trade_data = payload.model_dump(exclude={"bos_detected", "fvg_detected", "displacement_atr_mult", "active_session", "htf_bias", "liquidity_sweep"})
    trade_data["rr"] = payload.rr
    
    # 1. Strategy Filters
    strategy_passed, strat_reason = evaluate_strategy(payload)
    if not strategy_passed:
        trade_data.update({"status": "REJECTED", "reason": strat_reason})
        db_trade = add_trade(db, trade_data)
        send_notification(payload, ai_review=None, rejection_reason=strat_reason)
        return {"status": "rejected", "reason": strat_reason}
        
    # 2. Risk Engine
    daily_losses = get_daily_losses(db)
    risk_passed, risk_reason, position_size = evaluate_risk(payload, daily_losses)
    if not risk_passed:
        trade_data.update({"status": "REJECTED", "reason": risk_reason})
        db_trade = add_trade(db, trade_data)
        send_notification(payload, ai_review=None, rejection_reason=risk_reason)
        return {"status": "rejected", "reason": risk_reason}

    # 3. AI Review (Only runs if Strategy and Risk pass!)
    ai_result = run_ai_review(payload)
    trade_data.update({
        "ai_action": ai_result.action,
        "ai_grade": ai_result.grade,
        "reason": f"AI Reasons: {', '.join(ai_result.reasons)}",
        "status": "PENDING"
    })
    
    # 4. Log to DB
    db_trade = add_trade(db, trade_data)
    
    # 5. Notify
    send_notification(payload, ai_result)
    
    return {
        "status": "success",
        "trade_id": db_trade.id,
        "action": ai_result.action,
        "position_size": position_size,
        "message": "Alert processed and simulated."
    }

@app.post("/update_result")
def update_result(update: TradeResultUpdate, db: Session = Depends(get_db)):
    """
    Updates the outcome of a trade (WIN, LOSS, EXPIRED, CANCELLED).
    """
    trade = update_trade_outcome(db, update.trade_id, update.outcome)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"status": "success", "trade_id": trade.id, "new_outcome": trade.status}
