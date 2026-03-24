import os
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    webhook_secret: str = "your_super_secret_webhook_token_here"
    database_url: str = "sqlite:///./paper_trades.db"
    
    # Notifications
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    
    # Risk
    account_balance: float = 100000.0
    max_risk_percent: float = 1.0
    min_rr: float = 2.0
    max_daily_losses: int = 3
    max_open_positions: int = 5
    max_notional_exposure: float = 50000.0
    
    # Trade Management & Strategy
    tp2_rr: float = 2.0
    stop_buffer_atr: float = 0.0
    break_even_after_tp1: bool = True
    trailing_after_tp1: bool = False
    trailing_mode: Literal["SWING", "ATR"] = "SWING"
    entry_mode: Literal["FVG_TOP", "FVG_MIDPOINT", "FULL_ZONE_TOUCH"] = "FVG_MIDPOINT"
    max_bars_to_retrace: int = 8
    symbols: list[str] = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMZN"]
    
    # Session Windows (ET)
    session_primary_start: str = "09:30"
    session_primary_end: str = "11:30"
    session_secondary_start: str = "15:00"
    session_secondary_end: str = "16:00"
    
    # AI settings
    openai_api_key: str | None = None
    use_mock_ai: bool = True
    
    # Execution
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    execution_mode: Literal["PAPER", "LIVE"] = "PAPER"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
