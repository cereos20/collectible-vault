import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, init_db
from app.services.key_detector import detect_key_issue
from app.valuation import get_grade_multiplier, calculate_comp_fmv

init_db()
client = TestClient(app)


def test_detect_key_issue_logic():
    is_key, reason = detect_key_issue("The Amazing Spider-Man #300")
    assert is_key is True
    assert "Venom" in reason

    is_key, reason = detect_key_issue("Incredible Hulk #181")
    assert is_key is True
    assert "Wolverine" in reason

    is_key, reason = detect_key_issue("Random Generic Comic #12")
    assert is_key is False
    assert reason is None

    is_key, reason = detect_key_issue("Random Comic #5", notes="1st appearance of cool hero")
    assert is_key is True
    assert "1st appearance" in reason.lower()


def test_key_issue_api_endpoint():
    # 1. Create a key issue collectible
    client.post("/api/items", json={
        "title": "Amazing Spider-Man #361",
        "category": "comic",
        "purchase_price": 50.0,
        "current_market_value": 150.0,
        "condition_grade": "NM 9.4"
    })

    # 2. Query /api/items/keys
    response = client.get("/api/items/keys")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item["title"] == "Amazing Spider-Man #361" and item["is_key_issue"] is True for item in data)


def test_grade_multiplier_matrix():
    assert get_grade_multiplier("CGC 9.8") == 3.5
    assert get_grade_multiplier("9.6") == 2.2
    assert get_grade_multiplier("Near Mint 9.4") == 1.4
    assert get_grade_multiplier("Very Fine 8.0") == 1.0
    assert get_grade_multiplier("Very Good 6.0") == 0.6
    assert get_grade_multiplier("Fair 2.5") == 0.3

    # Test calculate_comp_fmv applying grade multiplier
    # Raw comps: [100.0, 100.0, 100.0] -> median 100.0 -> grade 9.8 (3.5x multiplier) -> 350.0
    fmv_98 = calculate_comp_fmv([100.0, 100.0, 100.0], category="comic", condition_grade="9.8", current_val=0.0)
    assert fmv_98 == 350.0

    fmv_60 = calculate_comp_fmv([100.0, 100.0, 100.0], category="comic", condition_grade="VG 6.0", current_val=0.0)
    assert fmv_60 == 60.0
