import os
import logging
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db, init_db
from app.models import CollectibleItem, ValuationHistory
from app.schemas import (
    CollectibleCreate,
    CollectibleUpdate,
    CollectibleResponse,
    BarcodeIntakeRequest,
    VisionIntakeResponse,
    DashboardStatsResponse
)
from app.vision_ai import analyze_collectible_image
from app.valuation import lookup_barcode_data, refresh_all_valuations, seed_sample_data_if_empty

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vault")

app = FastAPI(
    title="Universal Collectibles Vault API",
    description="Containerized open-source self-hosted collectibles tracker with camera intake, local vision AI, and FastMCP integration.",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories exist
os.makedirs("app/static/css", exist_ok=True)
os.makedirs("app/static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def on_startup():
    init_db()
    db = next(get_db())
    try:
        seed_sample_data_if_empty(db)
    finally:
        db.close()


@app.get("/")
def render_dashboard(request: Request):
    """Renders the main single-page web dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")



# --- INTAKE ENDPOINTS ---

@app.post("/api/intake/barcode")
def intake_by_barcode(payload: BarcodeIntakeRequest):
    """
    Decodes UPC/EAN barcode and returns pre-populated metadata for the confirmation modal.
    """
    data = lookup_barcode_data(payload.barcode)
    return {
        "status": "success",
        "barcode": payload.barcode,
        "preflight_data": data
    }


@app.post("/api/intake/vision", response_model=VisionIntakeResponse)
async def intake_by_vision(file: UploadFile = File(...)):
    """
    Accepts photo of box or cover, runs local Vision LLM (or smart fallback), and returns structured JSON metadata.
    """
    contents = await file.read()
    result = await analyze_collectible_image(contents, filename=file.filename or "photo.jpg")
    return VisionIntakeResponse(
        title=result.get("title", "Unknown Collectible"),
        category=result.get("category", "other"),
        publisher_or_brand=result.get("publisher_or_brand"),
        issue_or_box_number=result.get("issue_or_box_number"),
        condition_estimate=result.get("condition_estimate", "Near Mint"),
        estimated_market_value=float(result.get("estimated_market_value", 0.0)),
        confidence_score=float(result.get("confidence_score", 0.85)),
        extracted_metadata=result.get("extracted_metadata", {}),
        summary=result.get("summary", "Successfully scanned item.")
    )


# --- COLLECTIBLES CRUD ENDPOINTS ---

@app.get("/api/items", response_model=List[CollectibleResponse])
def list_collectibles(
    category: Optional[str] = Query(None, description="Filter by category (comic, funko, figure, trading_card, other)"),
    search: Optional[str] = Query(None, description="Search query for title or notes"),
    sort_by: Optional[str] = Query("newest", description="Sort by: newest, value_desc, gain_desc, title"),
    db: Session = Depends(get_db)
):
    query = db.query(CollectibleItem)

    if category and category != "all":
        query = query.filter(CollectibleItem.category == category)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(CollectibleItem.title.ilike(search_pattern) | CollectibleItem.notes.ilike(search_pattern))

    items = query.all()

    # Calculate profit/loss helper
    result = []
    for item in items:
        resp = CollectibleResponse.from_orm(item)
        resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
        resp.profit_loss_percentage = round(
            ((item.current_market_value - item.purchase_price) / item.purchase_price * 100)
            if item.purchase_price > 0 else 0.0, 1
        )
        result.append(resp)

    # Sorting
    if sort_by == "value_desc":
        result.sort(key=lambda x: x.current_market_value, reverse=True)
    elif sort_by == "gain_desc":
        result.sort(key=lambda x: x.profit_loss, reverse=True)
    elif sort_by == "title":
        result.sort(key=lambda x: x.title.lower())
    else:  # newest
        result.sort(key=lambda x: x.created_at, reverse=True)

    return result


@app.post("/api/items", response_model=CollectibleResponse, status_code=201)
def create_collectible(item_in: CollectibleCreate, db: Session = Depends(get_db)):
    """Saves a new collectible item into the vault and records initial valuation history."""
    item = CollectibleItem(**item_in.dict())
    db.add(item)
    db.commit()
    db.refresh(item)

    # Initial valuation history entry
    val_history = ValuationHistory(
        item_id=item.id,
        value=item.current_market_value,
        source="Initial Valuation"
    )
    db.add(val_history)
    db.commit()
    db.refresh(item)

    resp = CollectibleResponse.from_orm(item)
    resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
    return resp


@app.get("/api/items/{item_id}", response_model=CollectibleResponse)
def get_collectible(item_id: int, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")
    
    resp = CollectibleResponse.from_orm(item)
    resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
    resp.profit_loss_percentage = round(
        ((item.current_market_value - item.purchase_price) / item.purchase_price * 100)
        if item.purchase_price > 0 else 0.0, 1
    )
    return resp


@app.put("/api/items/{item_id}", response_model=CollectibleResponse)
def update_collectible(item_id: int, item_in: CollectibleUpdate, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")

    update_data = item_in.dict(exclude_unset=True)
    
    # Check if market value updated to log history
    if "current_market_value" in update_data and update_data["current_market_value"] != item.current_market_value:
        vh = ValuationHistory(
            item_id=item.id,
            value=update_data["current_market_value"],
            source="Manual Update"
        )
        db.add(vh)

    for field, val in update_data.items():
        setattr(item, field, val)

    db.commit()
    db.refresh(item)
    
    resp = CollectibleResponse.from_orm(item)
    resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
    return resp


@app.delete("/api/items/{item_id}")
def delete_collectible(item_id: int, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")

    db.delete(item)
    db.commit()
    return {"status": "success", "message": f"Deleted item {item_id}"}


# --- VALUATION & DASHBOARD STATS ---

@app.post("/api/valuation/refresh")
def trigger_valuation_refresh(db: Session = Depends(get_db)):
    """Triggers live market sold comps analysis across all items."""
    updates = refresh_all_valuations(db)
    return {
        "status": "success",
        "items_updated": len(updates),
        "updates": updates
    }


@app.get("/api/dashboard/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Computes high-level aggregated vault stats."""
    items = db.query(CollectibleItem).all()
    
    total_items = len(items)
    total_invested = sum(item.purchase_price for item in items)
    current_vault_value = sum(item.current_market_value for item in items)
    total_profit_loss = round(current_vault_value - total_invested, 2)
    profit_loss_pct = round((total_profit_loss / total_invested * 100) if total_invested > 0 else 0.0, 1)

    category_breakdown = {}
    for item in items:
        category_breakdown[item.category] = category_breakdown.get(item.category, 0) + 1

    top_items_models = db.query(CollectibleItem).order_by(desc(CollectibleItem.current_market_value)).limit(4).all()
    top_items = []
    for item in top_items_models:
        resp = CollectibleResponse.from_orm(item)
        resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
        top_items.append(resp)

    return DashboardStatsResponse(
        total_items=total_items,
        total_invested=round(total_invested, 2),
        current_vault_value=round(current_vault_value, 2),
        total_profit_loss=total_profit_loss,
        profit_loss_percentage=profit_loss_pct,
        category_breakdown=category_breakdown,
        top_valued_items=top_items
    )
