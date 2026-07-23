from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime

class ValuationHistoryResponse(BaseModel):
    id: int
    item_id: int
    value: float
    recorded_at: datetime
    source: str

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryResponse(BaseModel):
    id: int
    item_id: int
    price: float
    source: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class CollectibleBase(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "The Amazing Spider-Man #300"})
    category: str = Field(..., json_schema_extra={"example": "comic"})  # comic, funko, figure, trading_card, other
    purchase_price: float = Field(0.0, ge=0.0)
    current_market_value: float = Field(0.0, ge=0.0)
    condition_grade: Optional[str] = "Near Mint"
    notes: Optional[str] = None
    image_url: Optional[str] = None
    barcode: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict)
    is_key_issue: Optional[bool] = False
    key_reasons: Optional[str] = None


class CollectibleCreate(CollectibleBase):
    pass


class CollectibleUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    purchase_price: Optional[float] = None
    current_market_value: Optional[float] = None
    condition_grade: Optional[str] = None
    notes: Optional[str] = None
    image_url: Optional[str] = None
    barcode: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_key_issue: Optional[bool] = None
    key_reasons: Optional[str] = None
    # Alias edit fields
    issue_number: Optional[str] = None
    grade: Optional[str] = None
    cost_basis: Optional[float] = None
    location: Optional[str] = None
    status: Optional[str] = None


class CollectibleResponse(CollectibleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    profit_loss: float = 0.0
    profit_loss_percentage: float = 0.0
    valuation_history: List[ValuationHistoryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class BarcodeIntakeRequest(BaseModel):
    barcode: str


class VisionIntakeResponse(BaseModel):
    title: str
    category: str
    publisher_or_brand: Optional[str] = None
    issue_or_box_number: Optional[str] = None
    condition_estimate: Optional[str] = "Raw / Near Mint"
    estimated_market_value: float = 0.0
    confidence_score: float = 0.85
    extracted_metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: str


class DashboardStatsResponse(BaseModel):
    total_items: int
    total_invested: float
    current_vault_value: float
    total_profit_loss: float
    profit_loss_percentage: float
    category_breakdown: Dict[str, int]
    top_valued_items: List[CollectibleResponse]


class SelectModelRequest(BaseModel):
    model: str


class WatchlistBase(BaseModel):
    title: str
    issue: Optional[str] = None
    min_grade: Optional[str] = "Near Mint"
    target_price: float = Field(0.0, ge=0.0)
    upc: Optional[str] = None


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistResponse(WatchlistBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioSnapshotResponse(BaseModel):
    id: int
    total_items: int
    total_invested: float
    current_vault_value: float
    total_profit_loss: float
    recorded_at: datetime
    date: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ValuationStatusResponse(BaseModel):
    status: str
    total_items: int
    processed_items: int
    progress_percentage: float = 0.0
    last_completed: Optional[str] = None
