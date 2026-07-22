import os
import httpx
import logging
from typing import Dict, Any, List

logger = logging.getLogger("vault.llm")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2-vl")

# Global in-memory active model preference
_active_model: str = DEFAULT_MODEL


def get_active_model() -> str:
    """Returns the currently active LLM model name."""
    global _active_model
    return _active_model


def set_active_model(model_name: str) -> str:
    """Updates the active LLM model preference."""
    global _active_model
    if model_name and model_name.strip():
        _active_model = model_name.strip()
        logger.info(f"Active LLM model changed to: {_active_model}")
    return _active_model


async def check_ollama_status() -> Dict[str, Any]:
    """
    Pings {OLLAMA_HOST}/api/tags with a 3-second timeout.
    Returns status ('online' | 'offline'), active model, and list of installed models.
    """
    url = f"{OLLAMA_HOST}/api/tags"
    current_model = get_active_model()

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                raw_models = data.get("models", [])
                
                # Extract model names
                models_list: List[str] = []
                for m in raw_models:
                    name = m.get("name") or m.get("model")
                    if name:
                        # Clean tag if e.g. "qwen2-vl:latest" -> "qwen2-vl" or keep name
                        models_list.append(name)

                # Default fallback model choices if server tags list is empty
                if not models_list:
                    models_list = [current_model, "qwen2-vl", "gemma4", "llama3"]

                return {
                    "status": "online",
                    "active_model": current_model,
                    "models": models_list,
                    "host": OLLAMA_HOST
                }
    except Exception as e:
        logger.warning(f"Ollama health check failed for host '{OLLAMA_HOST}': {e}")

    return {
        "status": "offline",
        "active_model": current_model,
        "models": [current_model, "qwen2-vl", "gemma4"],
        "host": OLLAMA_HOST,
        "troubleshooting": "Check OLLAMA_HOST IP or OLLAMA_ORIGINS cors settings on Windows VM."
    }
