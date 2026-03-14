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
    target = Column(Float)
    rr = Column(Float)
    
    # AI Analysis
    ai_action = Column(String)
    ai_grade = Column(String)
    
    # Status/Result tracking
    status = Column(String, default="PENDING") # PENDING, WIN, LOSS, EXPIRED, CANCELLED, REJECTED
    reason = Column(String, nullable=True)     # Reason if rejected, or notes

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
