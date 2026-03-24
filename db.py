from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class DBTrade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String, index=True)
    timeframe = Column(String)
    direction = Column(String)
    entry = Column(Float)
    stop = Column(Float)
    tp1 = Column(Float)
    tp2 = Column(Float)
    rr_to_tp1 = Column(Float)
    rr_to_tp2 = Column(Float)
    stop_distance = Column(Float)
    
    # Setup context
    # Additional Analytics/Filters
    bos_direction = Column(String)
    htf_trend = Column(String)
    fvg_top = Column(Float)
    fvg_bottom = Column(Float)
    entry_zone = Column(String)
    fvg_time = Column(String, nullable=True)
    volume_ratio = Column(Float, default=1.0)
    chop_flag = Column(String, default="FALSE") # Or boolean mapped
    
    # AI Analysis
    ai_action = Column(String)
    ai_grade = Column(String)
    
    # Status/Result tracking
    status = Column(String, default="PENDING") # DETECTED, WAITING_FOR_RETRACE, ENTERED, PENDING, PARTIAL_TP1, BREAKEVEN_EXIT, TP2_HIT, WIN, LOSS, EXPIRED, CANCELLED, REJECTED, STOPPED
    reason = Column(String, nullable=True)     # Reason if rejected, or notes
    
    # Timestamps & Trade Management Tracking
    detected_at = Column(DateTime, nullable=True)
    entered_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    be_triggered = Column(String, default="FALSE") # Boolean tracked as string or bool
    trailing_active = Column(String, default="FALSE")
    units = Column(Float, default=0.0)
    tp2_rr = Column(Float, nullable=True)
    stop_buffer = Column(Float, nullable=True)
    expiry_bars = Column(Integer, nullable=True)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def add_trade(db, trade_data: dict) -> DBTrade:
    db_trade = DBTrade(**trade_data)
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade

def update_trade_outcome(db, trade_id: int, outcome: str) -> DBTrade | None:
    db_trade = db.query(DBTrade).filter(DBTrade.id == trade_id).first()
    if db_trade:
        db_trade.status = outcome
        db.commit()
        db.refresh(db_trade)
    return db_trade
