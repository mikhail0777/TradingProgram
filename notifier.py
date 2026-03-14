import requests
from config import settings
from models import WebhookPayload, AIReviewResult

def send_notification(payload: WebhookPayload, ai_review: AIReviewResult | None, rejection_reason: str = None):
    """
    Sends a formatted alert message to Discord and/or Telegram.
    """
    message = f"🚨 **New {payload.direction} Alert: {payload.symbol} ({payload.timeframe})** 🚨\n"
    
    if rejection_reason:
        message += f"\n❌ **REJECTED**: {rejection_reason}"
        message += f"\n- Entry: {payload.entry} | Stop: {payload.stop} | Target: {payload.target}"
    else:
        message += f"\n✅ **APPROVED BY STRATEGY**"
        message += f"\n- Entry: {payload.entry}"
        message += f"\n- Stop: {payload.stop}"
        message += f"\n- Target: {payload.target}"
        message += f"\n- R:R: {payload.rr}"
    
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
