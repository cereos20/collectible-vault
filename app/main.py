import os
import re
import csv
import io
import time
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db, init_db, SessionLocal
from app.models import CollectibleItem, ValuationHistory, PriceHistory, WatchlistItem, PortfolioSnapshot
from app.routers import assistant, settings, intake
from app.services.image_healer import (
    heal_missing_item_images,
    heal_single_item_image,
    purge_stored_blob_urls,
    is_missing_image,
    get_fallback_badge
)
from app.services.llm_assistant import generate_item_market_summary
from app.schemas import (
    CollectibleCreate,
    CollectibleUpdate,
    CollectibleResponse,
    BarcodeIntakeRequest,
    VisionIntakeResponse,
    DashboardStatsResponse,
    SelectModelRequest,
    WatchlistCreate,
    WatchlistResponse,
    PortfolioSnapshotResponse,
    ValuationStatusResponse
)
from app.vision_ai import analyze_collectible_image
from app.valuation import lookup_barcode_data, fetch_ebay_sold_comps, refresh_all_valuations, seed_sample_data_if_empty
from app.importers.xml_importer import import_comics_from_xml
from app.services.llm import check_ollama_status, set_active_model, get_active_model
from app.services.key_detector import detect_key_issue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vault")

# Global thread-safe background job state for async valuation queue
_valuation_job_state: Dict[str, Any] = {
    "status": "idle",
    "total_items": 0,
    "processed_items": 0,
    "progress_percentage": 0.0,
    "last_completed": None
}


def record_portfolio_snapshot(db: Session) -> PortfolioSnapshot:
    """Helper to compute and save a vault portfolio snapshot."""
    items = db.query(CollectibleItem).all()
    total_items = len(items)
    total_invested = round(sum(item.purchase_price for item in items), 2)
    vault_value = round(sum(item.current_market_value for item in items), 2)
    net_profit = round(vault_value - total_invested, 2)

    snapshot = PortfolioSnapshot(
        total_items=total_items,
        total_invested=total_invested,
        current_vault_value=vault_value,
        total_profit_loss=net_profit,
        recorded_at=datetime.now(timezone.utc)
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def backfill_key_issues(db: Session) -> Dict[str, Any]:
    """
    Iterates over all CollectibleItem records in vault.db, evaluates them with detect_key_issue(),
    and updates is_key_issue and key_reasons fields in place.
    """
    items = db.query(CollectibleItem).all()
    updated_count = 0
    for item in items:
        is_key, reasons = detect_key_issue(item.title, item.notes)
        if item.is_key_issue != is_key or item.key_reasons != reasons:
            item.is_key_issue = is_key
            item.key_reasons = reasons
            updated_count += 1

    if updated_count > 0:
        db.commit()

    return {"total_items": len(items), "updated_items": updated_count}


def infer_category_from_title(title: str, user_category: Optional[str] = None) -> str:
    """Dynamically detects category from title text when unspecified or misaligned."""
    t_lower = (title or "").lower()
    if any(k in t_lower for k in ["action figure", "figure", "marvel legends", "star wars black series", "hot toys", "neca"]):
        return "figure"
    elif any(k in t_lower for k in ["funko", "pop!", "pop vinyl", "bitty pop"]):
        return "funko"
    elif any(k in t_lower for k in ["trading card", "card", "charizard", "pokemon", "magic the gathering", "mtg", "yugioh"]):
        return "trading_card"
    elif any(k in t_lower for k in ["comic", "spider-man", "batman", "hulk", "x-men", "iron man", "superman", "avengers"]):
        return "comic"
    return user_category or "other"


def backfill_category_fixes(db: Session) -> Dict[str, Any]:
    """
    Scans all items in vault.db and fixes misaligned categories
    (e.g., items titled 'Action Figure' assigned to category 'funko' or 'other').
    """
    items = db.query(CollectibleItem).all()
    fixed_count = 0
    for item in items:
        t_lower = (item.title or "").lower()
        if ("action figure" in t_lower or "figure" in t_lower) and item.category != "figure":
            item.category = "figure"
            fixed_count += 1

    if fixed_count > 0:
        db.commit()

    return {"total_items": len(items), "fixed_items": fixed_count}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    db = next(get_db())
    try:
        seed_sample_data_if_empty(db)
        purge_stored_blob_urls(db)
        backfill_key_issues(db)
        backfill_category_fixes(db)
        record_portfolio_snapshot(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title="Universal Collectibles Vault API",
    description="Containerized open-source self-hosted collectibles tracker with camera intake, local vision AI, and FastMCP integration.",
    version="1.0.0",
    lifespan=lifespan
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
os.makedirs("app/static/images", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

app.include_router(assistant.router)
app.include_router(settings.router)
app.include_router(intake.router)


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


@app.post("/api/import/xml")
async def import_comics_xml(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Native XML bulk importer for comic book exports (CLZ/Collectorz, ComicBase, League of Comic Geeks).
    """
    contents = await file.read()
    if not contents:
        return {
            "status": "error",
            "imported_count": 0,
            "errors": ["Uploaded XML file is empty."]
        }

    res = import_comics_from_xml(db, contents)
    if res.get("imported_count", 0) > 0:
        record_portfolio_snapshot(db)
    return res


# --- LLM SERVICE ENDPOINTS ---

@app.get("/api/llm/status")
async def get_llm_status():
    """
    Pings Ollama server tag endpoint and returns connection status, active model, and installed models list.
    """
    return await check_ollama_status()


@app.post("/api/llm/select-model")
def select_llm_model(payload: SelectModelRequest):
    """
    Dynamically updates the active LLM model preference for vision/text processing calls.
    """
    active_model = set_active_model(payload.model)
    return {
        "status": "success",
        "active_model": active_model
    }


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
    result = [build_collectible_response(item) for item in items]

    if sort_by == "value_desc":
        result.sort(key=lambda x: x.current_market_value, reverse=True)
    elif sort_by == "gain_desc":
        result.sort(key=lambda x: x.profit_loss, reverse=True)
    elif sort_by == "title":
        result.sort(key=lambda x: x.title.lower())
    else:  # newest
        result.sort(key=lambda x: x.created_at, reverse=True)

    return result


@app.get("/api/items/keys", response_model=List[CollectibleResponse])
def get_key_issues(db: Session = Depends(get_db)):
    """Filters exclusively for key issues in the vault."""
    items = db.query(CollectibleItem).filter(CollectibleItem.is_key_issue == True).all()
    return [build_collectible_response(item) for item in items]


def build_collectible_response(item: CollectibleItem) -> CollectibleResponse:
    """
    Constructs CollectibleResponse model with automatic image sanitization
    for missing, broken, or temporary blob URLs.
    """
    resp = CollectibleResponse.model_validate(item)
    if is_missing_image(resp.image_url):
        resp.image_url = get_fallback_badge(item.category)
    resp.profit_loss = round(item.current_market_value - item.purchase_price, 2)
    resp.profit_loss_percentage = round(
        ((item.current_market_value - item.purchase_price) / item.purchase_price * 100)
        if item.purchase_price > 0 else 0.0, 1
    )
    return resp


@app.get("/api/admin/backfill-keys")
def trigger_backfill_key_issues(db: Session = Depends(get_db)):
    """Triggers an on-demand database backfill to re-evaluate and tag all key issues in vault.db."""
    summary = backfill_key_issues(db)
    return {
        "status": "success",
        "message": "Key issues backfilled successfully",
        "summary": summary
    }


@app.get("/api/admin/fix-categories")
def trigger_fix_categories(db: Session = Depends(get_db)):
    """Scans and re-aligns miscategorized vault items in vault.db."""
    summary = backfill_category_fixes(db)
    return {
        "status": "success",
        "message": "Categories re-aligned successfully",
        "summary": summary
    }


@app.get("/api/admin/heal-images")
def trigger_heal_images(db: Session = Depends(get_db)):
    """Triggers an on-demand image healing run across all vault items."""
    return heal_missing_item_images(db)


@app.get("/api/admin/purge-blobs")
def trigger_purge_blobs(db: Session = Depends(get_db)):
    """Purges invalid/blob image URLs from vault.db on demand."""
    return purge_stored_blob_urls(db)


def parse_natural_language_search(query_str: str, db: Session) -> List[CollectibleItem]:
    """
    Parses natural language search queries into structured SQL filters.
    Supports category detection, price bounds ('over $100', 'under $50'),
    key issue flags, grade keywords ('Mint', 'CGC 9.8'), and title/notes search.
    """
    if not query_str or not query_str.strip():
        return db.query(CollectibleItem).all()

    q_lower = query_str.lower().strip()
    query = db.query(CollectibleItem)

    # Category matching
    if any(k in q_lower for k in ["comic", "comics", "book"]):
        query = query.filter(CollectibleItem.category == "comic")
    elif any(k in q_lower for k in ["funko", "funkos", "pop", "pops"]):
        query = query.filter(CollectibleItem.category == "funko")
    elif any(k in q_lower for k in ["figure", "figures", "toy", "toys", "action figure"]):
        query = query.filter(CollectibleItem.category.in_(["figure", "action_figure"]))
    elif any(k in q_lower for k in ["card", "cards", "pokemon", "pokémon", "trading card"]):
        query = query.filter(CollectibleItem.category.in_(["trading_card", "card"]))

    # Key issue matching
    if "key" in q_lower or "keys" in q_lower:
        query = query.filter(CollectibleItem.is_key_issue == True)

    # Price bounds matching e.g. "over 100", "over $100", "greater than 100", "under $50"
    min_match = re.search(r'(?:over|above|greater than|>\s*)\$?\s*(\d+(?:\.\d+)?)', q_lower)
    if min_match:
        min_val = float(min_match.group(1))
        query = query.filter(CollectibleItem.current_market_value >= min_val)

    max_match = re.search(r'(?:under|below|less than|<\s*)\$?\s*(\d+(?:\.\d+)?)', q_lower)
    if max_match:
        max_val = float(max_match.group(1))
        query = query.filter(CollectibleItem.current_market_value <= max_val)

    # Condition grade matching
    if "cgc" in q_lower:
        query = query.filter(CollectibleItem.condition_grade.ilike("%CGC%"))
    elif "mint" in q_lower:
        query = query.filter(CollectibleItem.condition_grade.ilike("%Mint%"))

    # Title / notes keyword matching
    clean_str = re.sub(
        r'(?:over|above|under|below|greater than|less than|comics?|funkos?|pops?|figures?|action figures?|trading cards?|cards?|keys?|key issues?|mint|cgc|\$\d+(?:\.\d+)?)',
        '',
        q_lower
    ).strip()

    tokens = [w for w in re.findall(r'\b[a-zA-Z0-9\'-]+\b', clean_str) if len(w) > 1]
    for t in tokens:
        pattern = f"%{t}%"
        query = query.filter(
            CollectibleItem.title.ilike(pattern) |
            CollectibleItem.notes.ilike(pattern) |
            CollectibleItem.key_reasons.ilike(pattern)
        )

    return query.all()


@app.get("/api/items/search/nl", response_model=List[CollectibleResponse])
def natural_language_search(q: str = Query("", alias="q"), db: Session = Depends(get_db)):
    """
    Parses natural language query strings (e.g. 'Spider-Man comics over $100', 'Mint Funkos')
    into structured SQL queries and returns matching items.
    """
    items = parse_natural_language_search(q, db)
    return [build_collectible_response(item) for item in items]


@app.get("/api/items/{item_id}/market-summary")
def get_item_market_summary_endpoint(item_id: int, db: Session = Depends(get_db)):
    """Returns a 2-sentence market briefing for the specified item."""
    return generate_item_market_summary(item_id, db)


@app.post("/api/items", response_model=CollectibleResponse, status_code=201)
@app.post("/api/collectibles", response_model=CollectibleResponse, status_code=201)
def create_collectible(item_in: CollectibleCreate, db: Session = Depends(get_db)):
    """Saves a new collectible item into the vault and records initial valuation history & snapshot."""
    item_dict = item_in.model_dump()
    inferred_cat = infer_category_from_title(item_in.title, item_in.category)
    if ("action figure" in (item_in.title or "").lower() or "figure" in (item_in.title or "").lower()) and item_in.category != "figure":
        item_dict["category"] = "figure"
    elif inferred_cat != item_in.category and item_in.category in ["other", "funko"]:
        item_dict["category"] = inferred_cat

    is_key, key_reason = detect_key_issue(item_in.title, item_in.notes)
    item = CollectibleItem(**item_dict)
    if is_key:
        item.is_key_issue = True
        item.key_reasons = key_reason

    # Automatic image healing / fallback badge assignment
    heal_single_item_image(item)

    db.add(item)
    db.commit()
    db.refresh(item)

    val_history = ValuationHistory(
        item_id=item.id,
        value=item.current_market_value,
        source="Initial Valuation"
    )
    db.add(val_history)
    db.commit()

    record_portfolio_snapshot(db)
    db.refresh(item)

    return build_collectible_response(item)


@app.get("/api/items/{item_id}", response_model=CollectibleResponse)
def get_collectible(item_id: int, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")
    
    return build_collectible_response(item)


@app.put("/api/items/{item_id}", response_model=CollectibleResponse)
def update_collectible(item_id: int, item_in: CollectibleUpdate, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")

    update_data = item_in.model_dump(exclude_unset=True)

    if "grade" in update_data and update_data["grade"] is not None:
        update_data["condition_grade"] = update_data.pop("grade")
    if "cost_basis" in update_data and update_data["cost_basis"] is not None:
        update_data["purchase_price"] = update_data.pop("cost_basis")

    meta = dict(item.metadata_json or {})
    for meta_key in ["issue_number", "location", "status"]:
        if meta_key in update_data:
            val = update_data.pop(meta_key)
            if val is not None:
                meta[meta_key] = val
    item.metadata_json = meta

    if "current_market_value" in update_data and update_data["current_market_value"] != item.current_market_value:
        vh = ValuationHistory(
            item_id=item.id,
            value=update_data["current_market_value"],
            source="Manual Update"
        )
        db.add(vh)

    manual_key_set = "is_key_issue" in update_data and update_data["is_key_issue"] is not None

    for field, val in update_data.items():
        if hasattr(item, field) and val is not None:
            setattr(item, field, val)

    # Evaluate key issue status if user didn't explicitly set/override it
    if not manual_key_set:
        is_key, key_reason = detect_key_issue(item.title, item.notes)
        item.is_key_issue = is_key
        if is_key and not item.key_reasons:
            item.key_reasons = key_reason

    db.commit()
    record_portfolio_snapshot(db)
    db.refresh(item)
    
    return build_collectible_response(item)


@app.delete("/api/items/{item_id}")
def delete_collectible(item_id: int, db: Session = Depends(get_db)):
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Collectible item not found")

    db.delete(item)
    db.commit()
    record_portfolio_snapshot(db)
    return {"status": "success", "message": f"Deleted item {item_id}"}


# --- BULK EXPORT ENDPOINTS ---

@app.get("/api/export/csv")
def export_vault_csv(db: Session = Depends(get_db)):
    """Exports all vault items to a downloadable CSV spreadsheet."""
    items = db.query(CollectibleItem).all()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Title", "Category", "Condition Grade", "Purchase Price",
        "Current Market Value", "Net Profit/Loss", "Barcode", "Notes", "Created At"
    ])

    for i in items:
        profit = round(i.current_market_value - i.purchase_price, 2)
        created_str = i.created_at.strftime("%Y-%m-%d %H:%M:%S") if i.created_at else ""
        writer.writerow([
            i.id, i.title, i.category, i.condition_grade or "",
            f"{i.purchase_price:.2f}", f"{i.current_market_value:.2f}",
            f"{profit:.2f}", i.barcode or "", i.notes or "", created_str
        ])

    output.seek(0)
    filename = f"collectible_vault_export_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/export/json")
def export_vault_json(db: Session = Depends(get_db)):
    """Exports all vault items to a formatted JSON data backup."""
    items = db.query(CollectibleItem).all()
    data = []
    for i in items:
        data.append({
            "id": i.id,
            "title": i.title,
            "category": i.category,
            "condition_grade": i.condition_grade,
            "purchase_price": i.purchase_price,
            "current_market_value": i.current_market_value,
            "profit_loss": round(i.current_market_value - i.purchase_price, 2),
            "barcode": i.barcode,
            "notes": i.notes,
            "metadata_json": i.metadata_json or {},
            "created_at": i.created_at.isoformat() if i.created_at else None
        })

    filename = f"collectible_vault_backup_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --- PORTFOLIO ANALYTICS ENDPOINTS ---

@app.get("/api/analytics/portfolio-history", response_model=List[PortfolioSnapshotResponse])
@app.get("/api/portfolio/history", response_model=List[PortfolioSnapshotResponse])
def get_portfolio_history(days: int = Query(90, ge=1, le=365), db: Session = Depends(get_db)):
    """Returns historical daily portfolio snapshots for UI growth charts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    snapshots = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.recorded_at >= cutoff).order_by(PortfolioSnapshot.recorded_at.asc()).all()

    result = []
    for s in snapshots:
        resp = PortfolioSnapshotResponse.model_validate(s)
        resp.date = s.recorded_at.strftime("%Y-%m-%d") if s.recorded_at else ""
        result.append(resp)
    return result


# --- VALUATION & DASHBOARD STATS ---

def _run_async_valuation_task():
    global _valuation_job_state
    _valuation_job_state["status"] = "running"
    _valuation_job_state["processed_items"] = 0

    db = SessionLocal()
    try:
        items = db.query(CollectibleItem).all()
        total = len(items)
        _valuation_job_state["total_items"] = total

        for idx, item in enumerate(items):
            if idx > 0:
                time.sleep(0.5)
            new_val = fetch_ebay_sold_comps(
                title=item.title,
                category=item.category,
                current_val=item.current_market_value,
                condition_grade=item.condition_grade,
                barcode=item.barcode
            )
            item.current_market_value = new_val
            db.commit()

            processed = idx + 1
            _valuation_job_state["processed_items"] = processed
            _valuation_job_state["progress_percentage"] = round(((processed / total) * 100) if total > 0 else 100.0, 1)

        record_portfolio_snapshot(db)
        _valuation_job_state["status"] = "completed"
        _valuation_job_state["last_completed"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.error(f"[ASYNC VALUATION ERROR] {e}")
        _valuation_job_state["status"] = f"error: {str(e)}"
    finally:
        db.close()


@app.post("/api/valuation/refresh-async")
def trigger_async_valuation(background_tasks: BackgroundTasks):
    """Enqueues non-blocking batch market valuation processing in background tasks."""
    global _valuation_job_state
    if _valuation_job_state["status"] == "running":
        return {
            "status": "already_running",
            "message": "Batch valuation refresh is already running in background.",
            "job": _valuation_job_state
        }

    background_tasks.add_task(_run_async_valuation_task)
    return {
        "status": "queued",
        "message": "Background valuation refresh started successfully."
    }


@app.get("/api/valuation/status", response_model=ValuationStatusResponse)
def get_valuation_status():
    """Polls live status and progress percentage of background valuation refresh job."""
    global _valuation_job_state
    total = _valuation_job_state.get("total_items", 0)
    processed = _valuation_job_state.get("processed_items", 0)
    status_str = _valuation_job_state.get("status", "idle")
    
    if status_str == "completed":
        progress = 100.0
    elif total > 0:
        progress = round((processed / total) * 100, 1)
    else:
        progress = 0.0

    return ValuationStatusResponse(
        status=status_str,
        total_items=total,
        processed_items=processed,
        progress_percentage=progress,
        last_completed=_valuation_job_state.get("last_completed")
    )


@app.post("/api/valuation/refresh")
def trigger_valuation_refresh(db: Session = Depends(get_db)):
    """Triggers live market sold comps analysis across all items."""
    updates = refresh_all_valuations(db)
    record_portfolio_snapshot(db)
    return {
        "status": "success",
        "items_updated": len(updates),
        "updates": updates
    }


@app.get("/api/dashboard/stats", response_model=DashboardStatsResponse)
@app.get("/api/stats", response_model=DashboardStatsResponse)
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
        resp = CollectibleResponse.model_validate(item)
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


# --- WATCHLIST REST API ENDPOINTS ---

@app.get("/api/watchlist", response_model=List[WatchlistResponse])
def get_watchlist(db: Session = Depends(get_db)):
    """Fetches all items in the user's target watchlist."""
    items = db.query(WatchlistItem).order_by(desc(WatchlistItem.created_at)).all()
    return items


@app.post("/api/watchlist", response_model=WatchlistResponse, status_code=201)
def create_watchlist_item(item_in: WatchlistCreate, db: Session = Depends(get_db)):
    """Creates a new watchlist target item."""
    item = WatchlistItem(**item_in.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.delete("/api/watchlist/{watchlist_id}")
def delete_watchlist_item(watchlist_id: int, db: Session = Depends(get_db)):
    """Deletes an item from the watchlist."""
    item = db.query(WatchlistItem).filter(WatchlistItem.id == watchlist_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
    return {"status": "success", "message": f"Deleted watchlist item {watchlist_id}"}
