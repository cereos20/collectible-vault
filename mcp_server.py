import json
import logging
from typing import Dict, Any, Optional, List
from fastmcp import FastMCP
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import CollectibleItem, ValuationHistory
from app.valuation import refresh_all_valuations, fetch_ebay_sold_comps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vault.mcp")

# Initialize FastMCP Server
mcp = FastMCP("Universal Collectibles Vault")

# Ensure DB initialized
init_db()

@mcp.tool()
def get_vault_summary() -> str:
    """
    Get a high-level summary of the collector's vault including total items, total invested, 
    current market value, total net gain/loss, and category breakdown.
    """
    db: Session = SessionLocal()
    try:
        items = db.query(CollectibleItem).all()
        total_items = len(items)
        total_invested = sum(item.purchase_price for item in items)
        vault_value = sum(item.current_market_value for item in items)
        net_profit = round(vault_value - total_invested, 2)
        roi_pct = round((net_profit / total_invested * 100) if total_invested > 0 else 0.0, 1)

        categories = {}
        for item in items:
            categories[item.category] = categories.get(item.category, 0) + 1

        summary = {
            "total_items": total_items,
            "total_invested": f"${total_invested:,.2f}",
            "current_vault_value": f"${vault_value:,.2f}",
            "net_gain_loss": f"${net_profit:+,.2f} ({roi_pct:+.1f}%)",
            "categories": categories,
            "top_item": max(items, key=lambda x: x.current_market_value).title if items else None
        }
        return json.dumps(summary, indent=2)
    finally:
        db.close()


@mcp.tool()
def add_item(
    title: str,
    category: str,
    purchase_price: float = 0.0,
    current_market_value: float = 0.0,
    condition_grade: str = "Near Mint",
    notes: Optional[str] = None,
    issue_or_box_number: Optional[str] = None,
    publisher_or_brand: Optional[str] = None
) -> str:
    """
    Add a new collectible item into the vault.
    Categories: comic, funko, figure, trading_card, other.
    """
    db: Session = SessionLocal()
    try:
        metadata = {}
        if issue_or_box_number:
            metadata["issue_or_box_number"] = issue_or_box_number
        if publisher_or_brand:
            metadata["publisher_or_brand"] = publisher_or_brand

        item = CollectibleItem(
            title=title,
            category=category.lower(),
            purchase_price=purchase_price,
            current_market_value=current_market_value if current_market_value > 0 else purchase_price,
            condition_grade=condition_grade,
            notes=notes,
            metadata_json=metadata
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        # Log initial valuation
        vh = ValuationHistory(
            item_id=item.id,
            value=item.current_market_value,
            source="FastMCP Agent Intake"
        )
        db.add(vh)
        db.commit()

        return f"Successfully added '{item.title}' (ID: {item.id}) to vault with Market Value ${item.current_market_value:,.2f}."
    finally:
        db.close()


@mcp.tool()
def query_item_market_value(query: str) -> str:
    """
    Search for a collectible by title, keyword, or ID and return its valuation, purchase price, profit/loss, and history.
    """
    db: Session = SessionLocal()
    try:
        if query.isdigit():
            item = db.query(CollectibleItem).filter(CollectibleItem.id == int(query)).first()
        else:
            item = db.query(CollectibleItem).filter(CollectibleItem.title.ilike(f"%{query}%")).first()

        if not item:
            return f"No collectible found matching search query '{query}'."

        profit = round(item.current_market_value - item.purchase_price, 2)
        pct = round((profit / item.purchase_price * 100) if item.purchase_price > 0 else 0.0, 1)

        history = [
            {"date": h.recorded_at.strftime("%Y-%m-%d"), "value": f"${h.value:,.2f}", "source": h.source}
            for h in item.valuation_history
        ]

        result = {
            "id": item.id,
            "title": item.title,
            "category": item.category,
            "condition": item.condition_grade,
            "purchase_price": f"${item.purchase_price:,.2f}",
            "current_market_value": f"${item.current_market_value:,.2f}",
            "profit_loss": f"${profit:+,.2f} ({pct:+.1f}%)",
            "metadata": item.metadata_json,
            "notes": item.notes,
            "valuation_history": history
        }
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
def list_top_collectibles(by: str = "value", limit: int = 5) -> str:
    """
    List top collectibles ranked by 'value' (current market value) or 'gain' (net profit/loss).
    """
    db: Session = SessionLocal()
    try:
        items = db.query(CollectibleItem).all()
        if not items:
            return "Vault is empty."

        item_list = []
        for item in items:
            gain = item.current_market_value - item.purchase_price
            item_list.append({
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "market_value": item.current_market_value,
                "purchase_price": item.purchase_price,
                "net_gain": round(gain, 2)
            })

        if by == "gain":
            item_list.sort(key=lambda x: x["net_gain"], reverse=True)
        else:
            item_list.sort(key=lambda x: x["market_value"], reverse=True)

        top_list = item_list[:limit]
        formatted = [
            f"#{i+1}: {x['title']} [{x['category'].upper()}] - Value: ${x['market_value']:,.2f} (Gain: ${x['net_gain']:+,.2f})"
            for i, x in enumerate(top_list)
        ]
        return "\n".join(formatted)
    finally:
        db.close()


@mcp.tool()
def refresh_vault_valuations() -> str:
    """
    Triggers live market valuation refresh across all items in the vault using sold comps.
    """
    db: Session = SessionLocal()
    try:
        results = refresh_all_valuations(db)
        return f"Successfully refreshed market valuations for {len(results)} items."
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run()
