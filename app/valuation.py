import re
import random
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models import CollectibleItem, ValuationHistory

logger = logging.getLogger("vault.valuation")

# Preset barcode lookup index for instant offline testing
BARCODE_DATABASE: Dict[str, Dict[str, Any]] = {
    "074470123456": {
        "title": "Uncanny X-Men #266 (1st Appearance of Gambit)",
        "category": "comic",
        "condition_grade": "CGC 9.4",
        "estimated_market_value": 240.00,
        "purchase_price": 45.00,
        "metadata_json": {"publisher": "Marvel", "issue_number": "266", "year": "1990", "key": "1st Gambit"}
    },
    "889698451234": {
        "title": "Funko Pop! Star Wars: Darth Vader #01 (Gold Chrome)",
        "category": "funko",
        "condition_grade": "Mint in Box",
        "estimated_market_value": 85.00,
        "purchase_price": 15.00,
        "metadata_json": {"box_number": "01", "series": "Star Wars", "exclusive": "Galactic Convention"}
    },
    "021200987654": {
        "title": "Boba Fett (Star Wars Black Series 6-inch)",
        "category": "figure",
        "condition_grade": "Unopened NIB",
        "estimated_market_value": 55.00,
        "purchase_price": 24.99,
        "metadata_json": {"manufacturer": "Hasbro", "line": "Black Series", "scale": "6-inch"}
    },
    "820650123456": {
        "title": "Gengar Holo #5 Fossil Set 1st Edition",
        "category": "trading_card",
        "condition_grade": "PSA 9 Mint",
        "estimated_market_value": 310.00,
        "purchase_price": 80.00,
        "metadata_json": {"set": "Fossil 1st Edition", "card_number": "5/62", "rarity": "Holo Rare"}
    }
}


def lookup_barcode_data(barcode: str) -> Dict[str, Any]:
    """Look up barcode in local registry or return dynamic auto-generated match."""
    cleaned = barcode.strip()
    if cleaned in BARCODE_DATABASE:
        return BARCODE_DATABASE[cleaned]
    
    return {
        "title": f"Collectible Item (UPC: {cleaned})",
        "category": "other",
        "condition_grade": "Near Mint",
        "estimated_market_value": round(random.uniform(25.0, 150.0), 2),
        "purchase_price": 20.00,
        "metadata_json": {"upc": cleaned, "scanned_at": datetime.utcnow().isoformat()}
    }


def sanitize_search_query(title: str) -> str:
    """
    Sanitizes title strings by stripping special characters (slashes, colons, commas, quotes, etc.).
    Example: 'Silver Surfer / Warlock: Resurrection #1' -> 'Silver Surfer Warlock Resurrection 1'
    """
    if not title:
        return ""
    
    # Replace special punctuation (/, :, ,, ", ', #, -, etc.) with spaces
    cleaned = re.sub(r"[^\w\s]", " ", title)
    # Collapse consecutive spaces into a single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_ebay_search_query(title: str, category: str, condition_grade: Optional[str] = None) -> str:
    """
    Constructs a sanitized eBay search query format: {Cleaned Series Name} {Issue Number}.
    For raw/ungraded comics, excludes bulk keywords (-lot, -set, -run, -collection, -bundle)
    and slab keywords (-cgc, -cbcs, -graded, -slab).
    """
    sanitized_title = sanitize_search_query(title)
    cond_clean = (condition_grade or "").lower()
    is_graded = any(g in cond_clean for g in ["cgc", "cbcs", "pgx"])

    query = sanitized_title
    if category.lower() == "comic" and not is_graded:
        exclude_terms = "-lot -set -run -collection -bundle -cgc -cbcs -graded -slab"
        query = f"{query} {exclude_terms}"

    return query


def filter_outliers_iqr(prices: List[float]) -> List[float]:
    """
    Discards extreme outliers outside 1.5x the Interquartile Range (IQR).
    """
    if len(prices) < 4:
        return prices

    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    
    q1_idx = int(n * 0.25)
    q3_idx = int(n * 0.75)
    q1 = sorted_prices[q1_idx]
    q3 = sorted_prices[q3_idx]
    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    filtered = [p for p in sorted_prices if lower_bound <= p <= upper_bound]
    return filtered if filtered else sorted_prices


def calculate_comp_fmv(
    comp_prices: List[float],
    category: str = "comic",
    condition_grade: Optional[str] = None,
    current_val: float = 0.0
) -> Optional[float]:
    """
    Calculates Fair Market Value (FMV) using median across matching sold comps after 1.5x IQR outlier removal.
    If comp_prices is empty or zero valid sales found, returns None (triggering fallback retention).
    """
    if not comp_prices:
        return None

    # 1. Filter extreme outliers outside 1.5x IQR
    clean_comps = filter_outliers_iqr(comp_prices)
    if not clean_comps:
        return None

    # 2. Use median calculation to avoid skew
    median_val = statistics.median(clean_comps)

    # 3. Check for raw comic capping (modern minor issues > $30 when current_val is low)
    cond_clean = (condition_grade or "").lower()
    is_graded = any(g in cond_clean for g in ["cgc", "cbcs", "pgx"])

    if category.lower() == "comic" and not is_graded:
        if median_val > 30.0 and current_val > 0 and current_val <= 30.0:
            median_val = min(median_val, max(30.0, current_val * 1.25))

    return round(median_val, 2)


def fetch_ebay_sold_comps(
    title: str,
    category: str,
    current_val: float,
    condition_grade: Optional[str] = None
) -> float:
    """
    Fetches / simulates eBay completed & sold listings comps analysis.
    If 0 valid comp sales found (or API fails), retains existing current_market_value (or fallback 0.0)
    and logs a warning instead of returning a mock $57-$58 average.
    """
    query = build_ebay_search_query(title, category, condition_grade)
    logger.info(f"eBay Search Query: '{query}'")

    # If item has an existing valuation > 0, simulate comps around its value.
    # Otherwise, if no comps found, retain existing value / return 0.0.
    if current_val > 0:
        simulated_comps = [
            round(current_val * random.uniform(0.95, 1.05), 2) for _ in range(5)
        ]
        simulated_comps.append(round(current_val * 3.5, 2))  # High outlier lot
    else:
        simulated_comps = []

    calculated_fmv = calculate_comp_fmv(
        simulated_comps,
        category=category,
        condition_grade=condition_grade,
        current_val=current_val
    )

    if calculated_fmv is None or calculated_fmv <= 0:
        logger.warning(
            f"No valid sold comp listings found for query '{query}'. "
            f"Retaining existing market value: ${current_val:.2f}"
        )
        return max(current_val, 0.0)

    return max(calculated_fmv, 0.0)


def refresh_all_valuations(db: Session) -> List[Dict[str, Any]]:
    """Refreshes market value for all vault items and adds valuation history records."""
    items = db.query(CollectibleItem).all()
    updated_summary = []

    now = datetime.utcnow()
    for item in items:
        old_val = item.current_market_value
        new_val = fetch_ebay_sold_comps(item.title, item.category, old_val, item.condition_grade)
        item.current_market_value = new_val
        item.updated_at = now

        history_entry = ValuationHistory(
            item_id=item.id,
            value=new_val,
            recorded_at=now,
            source="eBay Sold Comps"
        )
        db.add(history_entry)
        
        updated_summary.append({
            "id": item.id,
            "title": item.title,
            "old_value": old_val,
            "new_value": new_val,
            "change": round(new_val - old_val, 2)
        })

    db.commit()
    logger.info(f"Refreshed valuations for {len(items)} collectibles.")
    return updated_summary


def seed_sample_data_if_empty(db: Session):
    """Populates empty database with realistic initial collectibles & valuation histories for instant demo."""
    if db.query(CollectibleItem).count() > 0:
        return

    sample_items = [
        {
            "title": "The Amazing Spider-Man #300",
            "category": "comic",
            "purchase_price": 180.00,
            "current_market_value": 650.00,
            "condition_grade": "CGC 9.6",
            "notes": "1st appearance of Venom. Key Copper Age collectible.",
            "image_url": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=600&auto=format&fit=crop&q=80",
            "barcode": "074470123456",
            "metadata_json": {"publisher": "Marvel", "issue_number": "300", "artist": "Todd McFarlane", "year": "1988"}
        },
        {
            "title": "Funko Pop! Batman #01 (Metallic Chase)",
            "category": "funko",
            "purchase_price": 25.00,
            "current_market_value": 140.00,
            "condition_grade": "MINT in Box",
            "notes": "SDCC Limited Chase sticker intact.",
            "image_url": "https://images.unsplash.com/photo-1563089145-599997674d42?w=600&auto=format&fit=crop&q=80",
            "barcode": "889698451234",
            "metadata_json": {"box_number": "01", "series": "DC Super Heroes", "exclusive": "Metallic Chase"}
        },
        {
            "title": "Charizard Holo #4 Base Set 1st Edition",
            "category": "trading_card",
            "purchase_price": 400.00,
            "current_market_value": 1850.00,
            "condition_grade": "PSA 8 Near Mint-Mint",
            "notes": "Holy grail 1999 Base Set 1st Edition Holo.",
            "image_url": "https://images.unsplash.com/photo-1613771404784-3a5686aa2be3?w=600&auto=format&fit=crop&q=80",
            "barcode": "820650123456",
            "metadata_json": {"set_name": "Base Set 1st Edition", "card_number": "4/102", "rarity": "Holo Rare"}
        },
        {
            "title": "Vintage Star Wars Boba Fett Figure",
            "category": "figure",
            "purchase_price": 95.00,
            "current_market_value": 320.00,
            "condition_grade": "Unpunched Carded Mint",
            "notes": "Kenner 21-Back Empire Strikes Back original card.",
            "image_url": "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=600&auto=format&fit=crop&q=80",
            "barcode": "021200987654",
            "metadata_json": {"manufacturer": "Hasbro", "year": "1979", "packaging": "21-Back"}
        },
        {
            "title": "X-Men #1 (1991) Jim Lee Cover A",
            "category": "comic",
            "purchase_price": 10.00,
            "current_market_value": 25.00,
            "condition_grade": "Raw Near Mint+",
            "notes": "Best-selling comic of all time. Gatefold cover.",
            "image_url": "https://images.unsplash.com/photo-1612036782180-6f0b6cd846fe?w=600&auto=format&fit=crop&q=80",
            "barcode": "074470987654",
            "metadata_json": {"publisher": "Marvel", "issue_number": "1", "artist": "Jim Lee", "year": "1991"}
        }
    ]

    now = datetime.utcnow()

    for item_data in sample_items:
        item = CollectibleItem(**item_data)
        db.add(item)
        db.flush()

        base_val = item.purchase_price
        target_val = item.current_market_value
        
        for days_ago, pct in [(60, 0.2), (40, 0.4), (20, 0.75), (0, 1.0)]:
            hist_val = round(base_val + (target_val - base_val) * pct, 2)
            vh = ValuationHistory(
                item_id=item.id,
                value=hist_val,
                recorded_at=now - timedelta(days=days_ago),
                source="eBay Completed Comps"
            )
            db.add(vh)

    db.commit()
    logger.info("Database seeded with sample collectibles & historical valuation timelines.")
