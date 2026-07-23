import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

Base.metadata.create_all(bind=engine)
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
