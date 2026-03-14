from pydantic import BaseModel, Field
from typing import Literal

class WebhookPayload(BaseModel):
    symbol: str
    timeframe: str
    direction: Literal["LONG", "SHORT"]
    entry: float
    stop: float
    target: float
    
    # Strategy parameters
    bos_detected: bool = Field(False, description="Break of Structure detected")
    fvg_detected: bool = Field(False, description="Fair Value Gap detected")
    displacement_atr_mult: float = Field(0.0, description="Displacement candle size relative to ATR")
    active_session: str = Field("NONE", description="Session where setup formed e.g., NY, LON")
    htf_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = Field("NEUTRAL", description="Higher timeframe bias")
    
    @property
    def rr(self) -> float:
        if self.direction == "LONG":
            risk = self.entry - self.stop
            reward = self.target - self.entry
        else:
            risk = self.stop - self.entry
            reward = self.entry - self.target
            
        if risk <= 0:
            return 0.0
        return round(reward / risk, 2)

class AIReviewResult(BaseModel):
    action: Literal["TAKE", "WAIT", "SKIP"]
    grade: Literal["A", "B", "C", "F"]
    confidence: int  # 0 - 100
    reasons: list[str]

class TradeResultUpdate(BaseModel):
    trade_id: int
    outcome: Literal["WIN", "LOSS", "EXPIRED", "CANCELLED"]
