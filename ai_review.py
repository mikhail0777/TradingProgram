import json
import hashlib
from models import WebhookPayload, AIReviewResult
from config import settings

def mock_ai_review(payload: WebhookPayload) -> AIReviewResult:
    """Deterministic Mock implementation of the AI reviewer for testing."""
    # Use a deterministic hash of the setup to determine outcome without random bugs
    setup_str = f"{payload.symbol}_{payload.timeframe}_{payload.direction}_{payload.entry}"
    hash_val = int(hashlib.md5(setup_str.encode()).hexdigest(), 16) % 100
    
    # Simulate some logic based on rr and strategy inputs
    if payload.rr >= 3.0 and hash_val > 10:
        return AIReviewResult(
            action="TAKE",
            grade="A",
            confidence=90 + (hash_val % 10),
            reasons=["High R:R ratio to TP1", "Strong structural bias", "Clear invalidation point in FVG"]
        )
    elif payload.rr >= 2.0:
        if hash_val > 40:
            return AIReviewResult(
                action="TAKE",
                grade="B",
                confidence=70 + (hash_val % 20),
                reasons=["Acceptable R:R", f"Matches HTF bias ({payload.htf_trend})", "Volume profile is slightly mixed"]
            )
        else:
             return AIReviewResult(
                action="WAIT",
                grade="C",
                confidence=85,
                reasons=[f"Acceptable R:R but displacement is weak ({round(payload.displacement_atr_mult, 2)}x)", "Awaiting lower timeframe entry confirmation", "Liquidity draw is unclear"]
            )
    else:
        # Default failsafe
        return AIReviewResult(action="SKIP", grade="F", confidence=95, reasons=["R:R below acceptable minimal threshold to TP1"])


def real_ai_review(payload: WebhookPayload) -> AIReviewResult:
    """
    Placeholder for real OpenAI integration.
    You could format a prompt with the payload details and ask the model to return a structured JSON.
    """
    import openai
    # Assuming openai is configured with settings.openai_api_key
    # The real implementation would do an api call here.
    # For now, if called without real logic, fallback to mock.
    try:
        if not settings.openai_api_key:
            return mock_ai_review(payload)
            
        # Example pseudo-code for calling openai:
        # response = openai.chat.completions.create(...)
        # data = json.loads(response.choices[0].message.content)
        # return AIReviewResult(**data)
        
        return mock_ai_review(payload)
    except Exception as e:
        # If AI fails, default to WAIT, not TAKE
        return AIReviewResult(
            action="WAIT",
            grade="F",
            confidence=0,
            reasons=[f"AI review failed with error: {str(e)}", "Defaulting to WAIT as safety mechanism"]
        )

def run_ai_review(payload: WebhookPayload) -> AIReviewResult:
    """Main entrypoint for AI Review."""
    if settings.use_mock_ai:
        return mock_ai_review(payload)
    return real_ai_review(payload)
