from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class CollectibleItem(Base):
    __tablename__ = "collectibles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # comic, funko, figure, trading_card, other
    purchase_price = Column(Float, default=0.0)
    current_market_value = Column(Float, default=0.0)
    condition_grade = Column(String(50), default="Near Mint") # CGC 9.8, Mint, Ungraded, etc.
    notes = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    barcode = Column(String(100), nullable=True, index=True)
    metadata_json = Column(JSON, default=dict)  # Flexible category fields e.g., issue_number, box_number, publisher, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    valuation_history = relationship("ValuationHistory", back_populates="item", cascade="all, delete-orphan")


class ValuationHistory(Base):
    __tablename__ = "valuation_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("collectibles.id"), nullable=False)
    value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(100), default="eBay Comps")

    item = relationship("CollectibleItem", back_populates="valuation_history")
