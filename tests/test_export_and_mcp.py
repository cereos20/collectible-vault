import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, init_db

init_db()
client = TestClient(app)


def test_export_vault_csv():
    # 1. Create a collectible item
    client.post("/api/items", json={
        "title": "Thor #337 (1st Beta Ray Bill)",
        "category": "comic",
        "purchase_price": 80.0,
        "current_market_value": 220.0,
        "condition_grade": "VF/NM 9.0",
        "notes": "1st appearance of Beta Ray Bill"
    })

    # 2. Export CSV
    response = client.get("/api/export/csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    content = response.content.decode("utf-8")
    assert "ID,Title,Category" in content
    assert "Thor #337 (1st Beta Ray Bill)" in content


def test_export_vault_json():
    response = client.get("/api/export/json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert isinstance(data, list)
    assert any(item["title"] == "Thor #337 (1st Beta Ray Bill)" for item in data)


def test_portfolio_analytics_history():
    # Fetch portfolio growth snapshots
    response = client.get("/api/analytics/portfolio-history?days=90")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    snapshot = data[0]
    assert "total_items" in snapshot
    assert "current_vault_value" in snapshot
    assert "date" in snapshot


def test_async_valuation_queue_and_status():
    # Check initial status
    status_resp = client.get("/api/valuation/status")
    assert status_resp.status_code == 200
    initial_status = status_resp.json()
    assert "status" in initial_status
    assert "progress_percentage" in initial_status

    # Trigger async valuation
    trigger_resp = client.post("/api/valuation/refresh-async")
    assert trigger_resp.status_code == 200
    res_data = trigger_resp.json()
    assert res_data["status"] in ["queued", "already_running"]

    # Poll status after trigger
    poll_resp = client.get("/api/valuation/status")
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["status"] in ["running", "completed", "idle"]
