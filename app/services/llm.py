import os
import httpx
import logging
from typing import Dict, Any, List

logger = logging.getLogger("vault.llm")

# Global in-memory Ollama host & model configuration
_ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2-vl")
_active_model: str = DEFAULT_MODEL


def get_ollama_host() -> str:
    """Returns the currently configured Ollama base host URL (without trailing slash)."""
    global _ollama_host
    return _ollama_host.strip().rstrip("/")


def set_ollama_host(host_url: str) -> str:
    """Updates the configured Ollama base host URL."""
    global _ollama_host
    if host_url and host_url.strip():
        clean_url = host_url.strip().rstrip("/")
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = f"http://{clean_url}"
        _ollama_host = clean_url
        logger.info(f"Configured Ollama Host updated to: {_ollama_host}")
    return get_ollama_host()


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
    Pings {get_ollama_host()}/api/tags with a 3-second timeout.
    Returns status ('online' | 'offline'), active model, and list of installed full tag model names.
    """
    host = get_ollama_host()
    url = f"{host}/api/tags"
    current_model = get_active_model()

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                raw_models = data.get("models", [])
                
                # Extract full tag model names (e.g. "gemma4:12b-it-q4", "qwen2-vl:latest")
                models_list: List[str] = []
                for m in raw_models:
                    name = m.get("name") or m.get("model")
                    if name:
                        models_list.append(name)

                # Default fallback model choices if server tags list is empty
                if not models_list:
                    models_list = [current_model, "qwen2-vl:latest", "gemma4:12b-it-q4", "llama3:8b"]

                return {
                    "status": "online",
                    "active_model": current_model,
                    "models": models_list,
                    "host": host
                }
    except Exception as e:
        logger.warning(f"Ollama health check failed for host '{host}': {e}")

    return {
        "status": "offline",
        "active_model": current_model,
        "models": [current_model, "qwen2-vl:latest", "gemma4:12b-it-q4"],
        "host": host,
        "troubleshooting": "Check OLLAMA_HOST IP or OLLAMA_ORIGINS cors settings on Windows VM."
    }
