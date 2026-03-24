import requests
from config import settings
from models import TradeSetupPayload, AIReviewResult

def send_notification(payload: TradeSetupPayload, ai_review: AIReviewResult | None, rejection_reason: str = None):
    """
    Sends a formatted alert message to Discord and/or Telegram.
    """
    message = f"🚨 **New {payload.direction} Alert: {payload.symbol} ({payload.timeframe})** 🚨\n"
    
    if rejection_reason:
        message += f"\n❌ **REJECTED**: {rejection_reason}"
        message += f"\n- Entry: {payload.entry} (Zone: {payload.entry_zone}) | Stop: {payload.stop} | TP1: {payload.tp1} | TP2: {payload.tp2}"
    else:
        message += f"\n✅ **APPROVED BY STRATEGY**"
        message += f"\n- Entry: {payload.entry} (Zone: {payload.entry_zone})"
        message += f"\n- Stop: {payload.stop} (Dist: {round(payload.stop_distance, 2)})"
        message += f"\n- Target 1: {payload.tp1} (RR: {payload.rr})"
        message += f"\n- Target 2: {payload.tp2}"
        message += f"\n- Management: BE={payload.be_enabled}, Trail={payload.trail_enabled}"
        message += f"\n- Context: BOS {payload.bos_direction}, HTF {payload.htf_trend}"
    
    if ai_review:
        message += f"\n\n🤖 **AI Review**: {ai_review.action} (Grade: {ai_review.grade}, Conf: {ai_review.confidence}%)"
        message += "\nReasons:"
        for r in ai_review.reasons:
            message += f"\n - {r}"
            
    # Send to Discord
    if settings.discord_webhook_url:
        try:
            requests.post(
                settings.discord_webhook_url,
                json={"content": message},
                timeout=5
            )
        except Exception as e:
            print(f"Failed to send Discord notification: {e}")
            
    # Send to Telegram
    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            requests.post(
                url,
                json={"chat_id": settings.telegram_chat_id, "text": message},
                timeout=5
            )
        except Exception as e:
            print(f"Failed to send Telegram notification: {e}")
