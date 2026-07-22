import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base, engine
from sqlalchemy.orm import sessionmaker

# Create test DB tables
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def test_create_and_edit_item():
    # 1. Create a collectible item
    create_resp = client.post("/api/items", json={
        "title": "Uncanny X-Men #141",
        "category": "comic",
        "purchase_price": 50.0,
        "current_market_value": 150.0,
        "condition_grade": "VF/NM 9.0",
        "notes": "Days of Future Past part 1"
    })
    assert create_resp.status_code == 201
    item_data = create_resp.json()
    item_id = item_data["id"]

    # 2. Edit item using PUT /api/items/{item_id}
    edit_resp = client.put(f"/api/items/{item_id}", json={
        "title": "Uncanny X-Men #141 (Days of Future Past)",
        "grade": "CGC 9.4",
        "cost_basis": 60.0,
        "current_market_value": 180.0,
        "location": "Box A-12",
        "status": "In Vault",
        "notes": "Key Days of Future Past storyline"
    })
    assert edit_resp.status_code == 200
    updated = edit_resp.json()

    assert updated["title"] == "Uncanny X-Men #141 (Days of Future Past)"
    assert updated["condition_grade"] == "CGC 9.4"
    assert updated["purchase_price"] == 60.0
    assert updated["current_market_value"] == 180.0
    assert updated["metadata_json"]["location"] == "Box A-12"
    assert updated["metadata_json"]["status"] == "In Vault"


def test_watchlist_crud_endpoints():
    # 1. Create watchlist item
    create_resp = client.post("/api/watchlist", json={
        "title": "Secret Wars #8",
        "issue": "8",
        "min_grade": "CGC 9.6",
        "target_price": 200.00
    })
    assert create_resp.status_code == 201
    w_item = create_resp.json()
    w_id = w_item["id"]
    assert w_item["title"] == "Secret Wars #8"

    # 2. Get watchlist items
    get_resp = client.get("/api/watchlist")
    assert get_resp.status_code == 200
    items = get_resp.json()
    assert any(i["id"] == w_id for i in items)

    # 3. Delete watchlist item
    del_resp = client.delete(f"/api/watchlist/{w_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"
