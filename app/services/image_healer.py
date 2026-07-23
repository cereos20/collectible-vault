import os
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import CollectibleItem

logger = logging.getLogger("vault.image_healer")

CATEGORY_BADGE_MAP = {
    "comic": "/static/images/badges/comic.svg",
    "funko": "/static/images/badges/funko.svg",
    "figure": "/static/images/badges/figure.svg",
    "action_figure": "/static/images/badges/figure.svg",
    "trading_card": "/static/images/badges/trading_card.svg",
    "card": "/static/images/badges/trading_card.svg",
    "other": "/static/images/badges/other.svg"
}


def get_fallback_badge(category: str) -> str:
    """Returns the SVG badge path corresponding to the given category."""
    cat_key = (category or "other").lower().strip()
    return CATEGORY_BADGE_MAP.get(cat_key, CATEGORY_BADGE_MAP["other"])


def is_missing_image(image_url: Optional[str]) -> bool:
    """Checks whether an image_url is missing, empty, broken, or a temporary blob URL."""
    if not image_url or not str(image_url).strip():
        return True
    url_str = str(image_url).strip().lower()
    if url_str.startswith("blob:") or url_str in ["none", "null", "undefined", "placeholder.png", "/static/images/placeholder.png"]:
        return True
    return False


def purge_stored_blob_urls(db: Session) -> Dict[str, Any]:
    """
    Clears out all temporary/invalid 'blob:' image URLs stored in vault.db
    and heals affected rows with static SVG category fallback badges.
    """
    items = db.query(CollectibleItem).all()
    purged_count = 0

    for item in items:
        if is_missing_image(item.image_url):
            item.image_url = get_fallback_badge(item.category)
            purged_count += 1

    if purged_count > 0:
        db.commit()

    logger.info(f"Purged {purged_count} invalid/blob image URLs from vault.db.")
    return {
        "status": "success",
        "total_scanned": len(items),
        "purged_count": purged_count
    }


def heal_single_item_image(item: CollectibleItem) -> bool:
    """
    Attempts to resolve missing cover art for a single CollectibleItem.
    Falls back to dynamic category SVG badges if external artwork is unavailable.
    Returns True if item.image_url was updated.
    """
    if not is_missing_image(item.image_url):
        return False

    resolved_url = None

    if item.barcode:
        try:
            from app.valuation import lookup_barcode_data
            barcode_info = lookup_barcode_data(item.barcode)
            if barcode_info and barcode_info.get("cover_url"):
                resolved_url = barcode_info["cover_url"]
        except Exception as e:
            logger.debug(f"Barcode image lookup failed for item {item.id}: {e}")

    if not resolved_url:
        resolved_url = get_fallback_badge(item.category)

    item.image_url = resolved_url
    return True


def heal_missing_item_images(db: Session) -> Dict[str, Any]:
    """
    Scans vault.db for items with missing, empty, or broken image_url fields.
    Updates missing entries with cover art or category-specific SVG badges.
    """
    items = db.query(CollectibleItem).all()
    healed_count = 0

    for item in items:
        if heal_single_item_image(item):
            healed_count += 1

    if healed_count > 0:
        db.commit()

    logger.info(f"Image healer scanned {len(items)} items, healed {healed_count} missing images.")
    return {
        "status": "success",
        "total_scanned": len(items),
        "healed_count": healed_count
    }
