import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal
from app.services.llm_assistant import query_vault_assistant

init_db()
client = TestClient(app)


def test_assistant_chat_endpoint_empty_prompt():
    res = client.post("/api/assistant/chat", json={"prompt": "", "model": "qwen2-vl"})
    assert res.status_code == 400


import asyncio

def test_query_vault_assistant_service():
    db = SessionLocal()
    try:
        result = asyncio.run(query_vault_assistant(
            user_prompt="What are my top Spider-Man comics?",
            selected_model="qwen2-vl",
            db=db
        ))
        assert result["status"] in ["success", "fallback"]
        assert "response" in result
        assert len(result["response"]) > 0
        assert "context" in result
    finally:
        db.close()


def test_assistant_chat_endpoint_valid_prompt():
    res = client.post("/api/assistant/chat", json={
        "prompt": "Show portfolio growth summary",
        "model": "gemma4:12b-it-q4"
    })
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert "model_used" in data


def test_manual_key_issue_override():
    # 1. Create item that is NOT a key issue
    create_res = client.post("/api/items", json={
        "title": "Random Test Book #1",
        "category": "comic",
        "purchase_price": 5.0,
        "current_market_value": 5.0,
        "condition_grade": "Very Fine"
    })
    assert create_res.status_code == 201
    item_id = create_res.json()["id"]
    assert create_res.json()["is_key_issue"] is False

    # 2. Manually override is_key_issue = True via PUT /api/items/{item_id}
    update_res = client.put(f"/api/items/{item_id}", json={
        "is_key_issue": True,
        "key_reasons": "Manual Collector Custom Key Override"
    })
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["is_key_issue"] is True
    assert updated_data["key_reasons"] == "Manual Collector Custom Key Override"


from app.services.llm_assistant import normalize_model_tag

def test_normalize_model_tag_exact_match():
    installed = ["gemma4:12b-it-q4", "qwen2-vl:latest", "llama3:8b"]
    assert normalize_model_tag("gemma4:12b-it-q4", installed) == "gemma4:12b-it-q4"

def test_normalize_model_tag_prefix_match():
    installed = ["gemma4:12b-it-q4", "qwen2-vl:latest", "llama3:8b"]
    assert normalize_model_tag("gemma4", installed) == "gemma4:12b-it-q4"
    assert normalize_model_tag("llama3", installed) == "llama3:8b"

def test_normalize_model_tag_fallback():
    installed = ["gemma4:12b-it-q4", "qwen2-vl:latest"]
    assert normalize_model_tag("nonexistent_model", installed) == "gemma4:12b-it-q4"
    assert normalize_model_tag("custom", []) == "custom"


from app.services.llm_assistant import _build_vault_context, _format_full_prompt

def test_intent_aware_context_retrieval():
    db = SessionLocal()
    try:
        # Create a specific action figure item
        client.post("/api/items", json={
            "title": "TMNT The Last Ronin Armored Action Figure",
            "category": "figure",
            "purchase_price": 35.0,
            "current_market_value": 45.0,
            "condition_grade": "Mint in Box",
            "notes": "NECA Comic Convention Exclusive"
        })

        # Test context retrieval with keyword query "Last Ronin"
        ctx = _build_vault_context("Show me my Last Ronin action figures", db)
        assert "category_summary_str" in ctx
        assert len(ctx["category_summary_str"]) > 0
        assert "relevant_items_str" in ctx
        assert "Last Ronin" in ctx["relevant_items_str"]

        # Test full prompt formatting includes Category Breakdown and Relevant Items
        full_prompt = _format_full_prompt("Show me my Last Ronin action figures", ctx)
        assert "Category Breakdown:" in full_prompt
        assert "Relevant Vault Items Matching Query:" in full_prompt
        assert "TMNT The Last Ronin" in full_prompt
    finally:
        db.close()


