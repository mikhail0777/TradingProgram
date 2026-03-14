from pydantic import BaseModel, Field
from typing import Literal

class WebhookPayload(BaseModel):
    symbol: str
    timeframe: str
    direction: Literal["LONG", "SHORT"]
    entry: float
    stop: float
    tp1: float
    tp2: float
    
    # Strategy parameters
    bos_direction: Literal["BULLISH", "BEARISH", "NONE"] = Field("NONE", description="Direction of the structural break")
    fvg_top: float = Field(0.0, description="Top price of the FVG zone")
    fvg_bottom: float = Field(0.0, description="Bottom price of the FVG zone")
    fvg_atr_mult: float = Field(0.0, description="Size of the FVG gap relative to ATR")
    displacement_atr_mult: float = Field(0.0, description="Displacement candle size relative to ATR")
    active_session: str = Field("NONE", description="Session where setup formed e.g., NY, LON")
    htf_trend: Literal["BULLISH", "BEARISH", "NEUTRAL"] = Field("NEUTRAL", description="Auto-calculated higher timeframe bias")
    liquidity_sweep: bool = Field(False, description="Whether a key liquidity level was swept before the setup")
    entry_zone: str = Field("NONE", description="Description of where entry occurred (e.g., FVG_MIDPOINT)")
    
    # Trade Management Rules
    be_enabled: bool = Field(False, description="Move stop to BE after TP1")
    trail_enabled: bool = Field(False, description="Trailing stop logic enabled")
    
    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.stop)
        
    @property
    def rr(self) -> float:
        if self.direction == "LONG":
            risk = self.entry - self.stop
            reward = self.tp1 - self.entry # Using TP1 for conservative initial R:R
        else:
            risk = self.stop - self.entry
            reward = self.entry - self.tp1
            
        if risk <= 0:
            return 0.0
        # Pylance strict type checking prefers explicit float cast before round
        val = float(reward) / float(risk)
        return float(round(val, 2))

class AIReviewResult(BaseModel):
    action: Literal["TAKE", "WAIT", "SKIP"]
    grade: Literal["A", "B", "C", "F"]
    confidence: int  # 0 - 100
    reasons: list[str]

class TradeResultUpdate(BaseModel):
    trade_id: int
    outcome: Literal["WIN", "LOSS", "EXPIRED", "CANCELLED"]
