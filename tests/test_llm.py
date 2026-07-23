import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm import get_active_model, set_active_model

client = TestClient(app)


def test_llm_status_endpoint():
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["online", "offline"]
    assert "active_model" in data
    assert "models" in data
    assert isinstance(data["models"], list)


def test_select_llm_model_endpoint():
    response = client.post(
        "/api/llm/select-model",
        json={"model": "gemma4"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["active_model"] == "gemma4"
    assert get_active_model() == "gemma4"

    # Reset back to default for other tests
    set_active_model("qwen2-vl")


import asyncio
from app.services.llm import check_ollama_status, set_ollama_host

def test_check_ollama_status_caching():
    set_ollama_host("http://localhost:11434")
    res1 = asyncio.run(check_ollama_status())
    res2 = asyncio.run(check_ollama_status())
    assert res1 == res2

