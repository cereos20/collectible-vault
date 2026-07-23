from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

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
    metadata_json = Column(JSON, default=dict)  # Flexible category fields e.g., issue_number, box_number, publisher, location, status, etc.
    is_key_issue = Column(Boolean, default=False)
    key_reasons = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    valuation_history = relationship("ValuationHistory", back_populates="item", cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="item", cascade="all, delete-orphan")


class ValuationHistory(Base):
    __tablename__ = "valuation_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("collectibles.id"), nullable=False)
    value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=utc_now)
    source = Column(String(100), default="eBay Comps")

    item = relationship("CollectibleItem", back_populates="valuation_history")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("collectibles.id"), nullable=False)
    price = Column(Float, nullable=False)
    source = Column(String(100), default="eBay Sold Comps")
    timestamp = Column(DateTime, default=utc_now)

    item = relationship("CollectibleItem", back_populates="price_history")


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    issue = Column(String(50), nullable=True)
    min_grade = Column(String(50), default="Near Mint")
    target_price = Column(Float, default=0.0)
    upc = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    total_items = Column(Integer, nullable=False)
    total_invested = Column(Float, nullable=False)
    current_vault_value = Column(Float, nullable=False)
    total_profit_loss = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=utc_now)
