import pytest
from fastapi.testclient import TestClient
from app.main import app, backfill_key_issues
from app.database import init_db, SessionLocal
from app.services.key_detector import detect_key_issue

init_db()
client = TestClient(app)


def test_detect_key_issue_iconic_books():
    # 1. Amazing Spider-Man 300 & 300A variant
    is_key, reason = detect_key_issue("The Amazing Spider-Man, Vol. 1 #300A")
    assert is_key is True
    assert "Venom" in reason

    # 2. Secret Wars 8 & 8B variant
    is_key, reason = detect_key_issue("Marvel Super Heroes Secret Wars #8B")
    assert is_key is True
    assert "Black Suit" in reason or "Symbiote" in reason

    # 3. Incredible Hulk 181
    is_key, reason = detect_key_issue("The Incredible Hulk #181A")
    assert is_key is True
    assert "Wolverine" in reason

    # 4. Batman 608
    is_key, reason = detect_key_issue("Batman, Vol. 3 #608")
    assert is_key is True
    assert "Hush" in reason

    # 5. Batman 101
    is_key, reason = detect_key_issue("Batman #101")
    assert is_key is True
    assert "Grifter" in reason

    # 6. Giant-Size X-Men 1
    is_key, reason = detect_key_issue("Giant-Size X-Men #1")
    assert is_key is True
    assert "Storm" in reason or "Nightcrawler" in reason

    # 7. Amazing Fantasy 15
    is_key, reason = detect_key_issue("Amazing Fantasy #15")
    assert is_key is True
    assert "Spider-Man" in reason

    # 8. Tales of Suspense 39
    is_key, reason = detect_key_issue("Tales of Suspense #39")
    assert is_key is True
    assert "Iron Man" in reason

    # 9. Werewolf by Night 32
    is_key, reason = detect_key_issue("Werewolf by Night #32")
    assert is_key is True
    assert "Moon Knight" in reason

    # 10. Hero for Hire 1
    is_key, reason = detect_key_issue("Hero for Hire #1")
    assert is_key is True
    assert "Luke Cage" in reason


def test_backfill_key_issues_migration():
    db = SessionLocal()
    try:
        summary = backfill_key_issues(db)
        assert "total_items" in summary
        assert "updated_items" in summary
    finally:
        db.close()


def test_backfill_keys_admin_endpoint():
    response = client.get("/api/admin/backfill-keys")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "summary" in data
