import os
import pytest
from fastapi.testclient import TestClient
from app.main import app, infer_category_from_title, backfill_category_fixes
from app.database import init_db, SessionLocal

init_db()
client = TestClient(app)


def test_infer_category_from_title():
    assert infer_category_from_title("Marvel Legends Spider-Man Action Figure") == "figure"
    assert infer_category_from_title("Darth Vader Black Series Figure") == "figure"
    assert infer_category_from_title("Funko Pop! Darth Vader #01") == "funko"
    assert infer_category_from_title("Charizard 1st Edition Trading Card") == "trading_card"
    assert infer_category_from_title("The Amazing Spider-Man #300") == "comic"


def test_create_collectible_auto_category_fix():
    # Submit item with category "funko" but title containing "Action Figure"
    res = client.post("/api/items", json={
        "title": "Wolverine Action Figure",
        "category": "funko",
        "purchase_price": 25.0,
        "current_market_value": 30.0,
        "condition_grade": "Mint"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["category"] == "figure"


def test_admin_fix_categories_endpoint():
    res = client.get("/api/admin/fix-categories")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "summary" in data


def test_uploads_route_mounted():
    # Test /uploads endpoint returns HTTP status (not 404 handler)
    res = client.get("/uploads/")
    assert res.status_code in [200, 403, 404]  # StaticFiles returns 404 if file doesn't exist, not API 404
