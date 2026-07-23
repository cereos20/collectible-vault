from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import httpx
import logging
from app.services.llm import get_ollama_host, set_ollama_host, get_active_model

router = APIRouter(prefix="/api/settings", tags=["Settings"])
logger = logging.getLogger("vault.settings")


class OllamaHostSettingsRequest(BaseModel):
    ollama_host: str


class TestHostRequest(BaseModel):
    ollama_host: str


@router.get("/ollama")
def get_ollama_settings():
    """Returns current Ollama host configuration and active model."""
    return {
        "ollama_host": get_ollama_host(),
        "active_model": get_active_model()
    }


@router.post("/ollama")
def update_ollama_settings(payload: OllamaHostSettingsRequest):
    """Updates the configured Ollama base host URL."""
    if not payload.ollama_host or not payload.ollama_host.strip():
        raise HTTPException(status_code=400, detail="Ollama host URL cannot be empty.")
    
    new_host = set_ollama_host(payload.ollama_host)
    return {
        "status": "success",
        "ollama_host": new_host
    }


@router.post("/test-host")
async def test_ollama_host_endpoint(payload: TestHostRequest):
    """
    Tests connection to a specified Ollama host URL by calling GET /api/tags.
    Returns model count and connection status message.
    """
    if not payload.ollama_host or not payload.ollama_host.strip():
        raise HTTPException(status_code=400, detail="Ollama host URL cannot be empty.")

    target = payload.ollama_host.strip().rstrip("/")
    if not target.startswith("http://") and not target.startswith("https://"):
        target = f"http://{target}"

    url = f"{target}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                raw_models = data.get("models", [])
                models = [m.get("name") or m.get("model") for m in raw_models if m.get("name") or m.get("model")]
                count = len(models)
                return {
                    "status": "success",
                    "online": True,
                    "model_count": count,
                    "models": models,
                    "message": f"Connected - {count} Models Found"
                }
            else:
                return {
                    "status": "error",
                    "online": False,
                    "model_count": 0,
                    "models": [],
                    "message": f"Server returned HTTP {resp.status_code}"
                }
    except Exception as e:
        return {
            "status": "error",
            "online": False,
            "model_count": 0,
            "models": [],
            "message": f"Connection failed: {str(e)}"
        }
