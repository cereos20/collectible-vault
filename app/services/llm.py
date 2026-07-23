import os
import time
import json
import httpx
import logging
from typing import Dict, Any, List

logger = logging.getLogger("vault.llm")

SETTINGS_FILE = os.path.join("data", "ollama_settings.json")
_settings_loaded: bool = False
_ollama_host: str = ""
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2-vl")
_active_model: str = DEFAULT_MODEL

# In-memory status cache to prevent log spam and socket exhaustion
_status_cache: Dict[str, Any] = {}
_status_cache_time: float = 0.0
CACHE_TTL_SECONDS: float = 5.0


def _load_settings_if_needed():
    global _ollama_host, _active_model, _settings_loaded
    if _settings_loaded:
        return
    _settings_loaded = True
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                if data.get("ollama_host"):
                    _ollama_host = data["ollama_host"].strip().rstrip("/")
                if data.get("active_model"):
                    _active_model = data["active_model"].strip()
        except Exception as e:
            logger.warning(f"Failed to read disk settings file: {e}")


def get_ollama_host() -> str:
    """Returns the currently configured Ollama base host URL, checking saved runtime/disk settings first."""
    global _ollama_host
    _load_settings_if_needed()
    if not _ollama_host:
        _ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
    return _ollama_host.strip().rstrip("/")


def set_ollama_host(host_url: str) -> str:
    """Updates the configured Ollama base host URL, invalidates status cache, and persists to disk."""
    global _ollama_host, _status_cache_time, _settings_loaded
    _settings_loaded = True
    if host_url and host_url.strip():
        clean_url = host_url.strip().rstrip("/")
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = f"http://{clean_url}"
        _ollama_host = clean_url
        _status_cache_time = 0.0  # Invalidate status cache on setting update
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"ollama_host": _ollama_host, "active_model": get_active_model()}, f)
        except Exception as e:
            logger.warning(f"Could not persist Ollama host setting: {e}")

        logger.info(f"Configured Ollama Host updated to: {_ollama_host}")
    return get_ollama_host()


def get_active_model() -> str:
    """Returns the currently active LLM model name."""
    global _active_model
    return _active_model


def set_active_model(model_name: str) -> str:
    """Updates the active LLM model preference."""
    global _active_model, _status_cache_time
    if model_name and model_name.strip():
        _active_model = model_name.strip()
        _status_cache_time = 0.0  # Invalidate status cache on model update
        logger.info(f"Active LLM model changed to: {_active_model}")
    return _active_model


async def check_ollama_status(force: bool = False) -> Dict[str, Any]:
    """
    Pings {get_ollama_host()}/api/tags with a 3-second timeout.
    Caches health check results for 5.0 seconds to eliminate redundant socket connections and log spam.
    """
    global _status_cache, _status_cache_time
    now = time.time()

    if not force and _status_cache and (now - _status_cache_time < CACHE_TTL_SECONDS):
        return _status_cache

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

                result = {
                    "status": "online",
                    "active_model": current_model,
                    "models": models_list,
                    "host": host
                }
                _status_cache = result
                _status_cache_time = now
                return result
    except Exception as e:
        logger.warning(f"Ollama health check failed for host '{host}': {e}")

    result = {
        "status": "offline",
        "active_model": current_model,
        "models": [current_model, "qwen2-vl:latest", "gemma4:12b-it-q4"],
        "host": host,
        "troubleshooting": "Check OLLAMA_HOST IP or OLLAMA_ORIGINS cors settings on Windows VM."
    }
    _status_cache = result
    _status_cache_time = now
    return result
