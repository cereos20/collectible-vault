import pytest
import io
from fastapi.testclient import TestClient
from app.main import app, parse_natural_language_search
from app.database import init_db, SessionLocal
from app.models import CollectibleItem
from app.services.image_healer import heal_missing_item_images, get_fallback_badge
from app.services.llm_assistant import generate_item_market_summary, generate_portfolio_insights

init_db()
client = TestClient(app)


def test_image_healer_scans_and_assigns_badges():
    db = SessionLocal()
    try:
        # Create an item missing an image
        item = CollectibleItem(
            title="Image Healer Test Comic #1",
            category="comic",
            purchase_price=10.0,
            current_market_value=15.0,
            image_url=""  # Missing
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        res = heal_missing_item_images(db)
        assert res["status"] == "success"
        assert res["healed_count"] >= 1

        db.refresh(item)
        assert item.image_url == "/static/images/badges/comic.svg"
    finally:
        db.close()


def test_admin_trigger_heal_images_endpoint():
    res = client.get("/api/admin/heal-images")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "healed_count" in data


def test_vision_intake_saves_upload_file():
    fake_img = b"FAKESUBIMAGEBYTES"
    file_obj = ("test_cover.jpg", io.BytesIO(fake_img), "image/jpeg")

    res = client.post("/api/intake/vision", files={"file": file_obj})
    assert res.status_code == 200
    data = res.json()
    assert "title" in data
    assert "category" in data
    assert "image_url" in data
    assert data["image_url"].startswith("/uploads/")


def test_generate_item_market_summary():
    db = SessionLocal()
    try:
        item = CollectibleItem(
            title="Amazing Spider-Man #300 Market Summary Test",
            category="comic",
            purchase_price=100.0,
            current_market_value=650.0,
            is_key_issue=True,
            key_reasons="1st appearance of Venom"
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        summary_res = generate_item_market_summary(item.id, db)
        assert summary_res["status"] == "success"
        assert "Amazing Spider-Man #300" in summary_res["summary"]
        assert "+550.0%" in summary_res["summary"]

        endpoint_res = client.get(f"/api/items/{item.id}/market-summary")
        assert endpoint_res.status_code == 200
        assert endpoint_res.json()["status"] == "success"
    finally:
        db.close()


def test_natural_language_search_filters():
    db = SessionLocal()
    try:
        # Seed test items
        c1 = CollectibleItem(
            title="Spider-Man High Value Comic #100",
            category="comic",
            purchase_price=50.0,
            current_market_value=250.0,
            condition_grade="CGC 9.8"
        )
        f1 = CollectibleItem(
            title="Cheap Action Figure #5",
            category="figure",
            purchase_price=10.0,
            current_market_value=20.0,
            condition_grade="Near Mint"
        )
        db.add_all([c1, f1])
        db.commit()

        # Query 1: Spider-Man comics over $100
        res1 = parse_natural_language_search("Spider-Man comics over $100", db)
        titles1 = [i.title for i in res1]
        assert "Spider-Man High Value Comic #100" in titles1
        assert "Cheap Action Figure #5" not in titles1

        # Query 2: figures under $50
        res2 = parse_natural_language_search("figures under $50", db)
        titles2 = [i.title for i in res2]
        assert "Cheap Action Figure #5" in titles2
        assert "Spider-Man High Value Comic #100" not in titles2

        # Test endpoint
        ep_res = client.get("/api/items/search/nl?q=comics%20over%20$100")
        assert ep_res.status_code == 200
        assert isinstance(ep_res.json(), list)
    finally:
        db.close()


def test_generate_portfolio_insights():
    db = SessionLocal()
    try:
        insights = generate_portfolio_insights(db)
        assert insights["status"] == "success"
        assert "headline" in insights
        assert "insights" in insights
        assert isinstance(insights["insights"], list)
        assert "advice" in insights

        endpoint_res = client.get("/api/assistant/portfolio-insights")
        assert endpoint_res.status_code == 200
        assert endpoint_res.json()["status"] == "success"
    finally:
        db.close()
