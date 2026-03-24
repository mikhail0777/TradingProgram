from pydantic import BaseModel, Field
from typing import Literal

class TradeSetupPayload(BaseModel):
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
    
    # Trade Management Rules & Extended Filters
    be_enabled: bool = Field(False, description="Move stop to BE after TP1")
    trail_enabled: bool = Field(False, description="Trailing stop logic enabled")
    tp2_rr: float = Field(2.0, description="RR target for TP2")
    stop_buffer: float = Field(0.0, description="Buffer size for stop loss")
    detected_at: str | None = Field(None, description="Timestamp when setup was detected")
    entered_at: str | None = Field(None, description="Timestamp when trade was entered")
    closed_at: str | None = Field(None, description="Timestamp when trade was closed")
    be_triggered: bool = Field(False, description="Has break-even been triggered")
    trailing_active: bool = Field(False, description="Is trailing stop actively managing price")
    volume_ratio: float = Field(1.0, description="Relative volume ratio")
    chop_flag: bool = Field(False, description="Whether the setup is in chop")
    expiry_bars: int = Field(8, description="Max bars to retrace before expiry")
    
    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.stop)
        
    @property
    def rr_to_tp1(self) -> float:
        risk = self.entry - self.stop if self.direction == "LONG" else self.stop - self.entry
        reward = self.tp1 - self.entry if self.direction == "LONG" else self.entry - self.tp1
        if risk <= 0: return 0.0
        return float(round(float(reward) / float(risk), 2))
        
    @property
    def rr_to_tp2(self) -> float:
        risk = self.entry - self.stop if self.direction == "LONG" else self.stop - self.entry
        reward = self.tp2 - self.entry if self.direction == "LONG" else self.entry - self.tp2
        if risk <= 0: return 0.0
        return float(round(float(reward) / float(risk), 2))

class AIReviewResult(BaseModel):
    action: Literal["TAKE", "WAIT", "SKIP"]
    grade: Literal["A", "B", "C", "F"]
    confidence: int  # 0 - 100
    reasons: list[str]

class TradeResultUpdate(BaseModel):
    trade_id: int
    outcome: Literal[
        "PENDING",
        "DETECTED", 
        "WAITING_FOR_RETRACE", 
        "ENTERED", 
        "PARTIAL_TP1", 
        "BREAKEVEN_EXIT", 
        "TP2_HIT", 
        "STOPPED", 
        "CANCELLED", 
        "EXPIRED", 
        "REJECTED",
        "WIN",
        "LOSS"
    ]
