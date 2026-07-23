import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app
from app.services.llm import get_ollama_host, set_ollama_host

client = TestClient(app)


def test_get_ollama_settings_endpoint():
    res = client.get("/api/settings/ollama")
    assert res.status_code == 200
    data = res.json()
    assert "ollama_host" in data
    assert "active_model" in data


def test_update_ollama_settings_endpoint():
    original_host = get_ollama_host()
    try:
        new_test_host = "http://192.168.86.100:11434"
        res = client.post("/api/settings/ollama", json={"ollama_host": new_test_host})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["ollama_host"] == new_test_host
        assert get_ollama_host() == new_test_host
    finally:
        set_ollama_host(original_host)


def test_update_ollama_settings_empty_validation():
    res = client.post("/api/settings/ollama", json={"ollama_host": "  "})
    assert res.status_code == 400


def test_test_ollama_host_endpoint_success():
    mock_resp = httpx.Response(
        200,
        json={
            "models": [
                {"name": "gemma4:12b-it-q4"},
                {"name": "qwen2-vl:latest"},
                {"name": "llama3:8b"}
            ]
        }
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = client.post("/api/settings/test-host", json={"ollama_host": "http://192.168.86.54:11434"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["online"] is True
        assert data["model_count"] == 3
        assert "gemma4:12b-it-q4" in data["models"]
        assert "Connected - 3 Models Found" in data["message"]


def test_test_ollama_host_endpoint_failure():
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        res = client.post("/api/settings/test-host", json={"ollama_host": "http://invalid-host:11434"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "error"
        assert data["online"] is False
        assert "Connection failed" in data["message"]
