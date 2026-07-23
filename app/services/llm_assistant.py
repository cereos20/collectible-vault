import os
import httpx
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import CollectibleItem
from app.services.llm import get_ollama_host, get_active_model

logger = logging.getLogger("vault.assistant")

SYSTEM_INSTRUCTION = """You are Vault AI Assistant, a self-hosted expert on collectibles and portfolio analytics.
Use the provided Vault Context below to answer the user's question conversationally and helpfully.
Do NOT output raw context stats unless the user specifically requests numbers or a summary.
Keep answers concise, friendly, and focused on what the user asked.
If the user asks about specific items, reference them by name, value, and key status from the context.
Format currency values with $ signs and two decimal places."""


async def fetch_installed_models() -> List[str]:
    """
    Fetches the list of installed model tag names from Ollama via GET /api/tags.
    Returns list of model names like ['gemma4:12b-it-q4', 'qwen2-vl:latest', 'llama3:8b'].
    """
    url = f"{get_ollama_host()}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                raw_models = data.get("models", [])
                models_list: List[str] = []
                for m in raw_models:
                    name = m.get("name") or m.get("model")
                    if name:
                        models_list.append(name)
                return models_list
    except Exception as e:
        logger.warning(f"Could not fetch installed model tags from Ollama ({url}): {e}")
    return []


def normalize_model_tag(requested_model: str, installed_models: List[str]) -> str:
    """
    Normalizes a requested model name against Ollama's list of installed model tags:
    1. Exact match if installed_models contains requested_model.
    2. Prefix matching if requested_model is e.g. "gemma4" matching "gemma4:12b-it-q4".
    3. Fallback to the first available installed model if no match found.
    4. Return requested_model if installed_models is empty.
    """
    if not requested_model or not requested_model.strip():
        requested_model = get_active_model()

    req = requested_model.strip()
    if not installed_models:
        return req

    # 1. Exact match
    if req in installed_models:
        return req

    # 2. Prefix matching (e.g., 'gemma4' -> 'gemma4:12b-it-q4')
    prefix_colon = f"{req}:"
    for tag in installed_models:
        if tag.startswith(prefix_colon) or tag == req:
            return tag

    for tag in installed_models:
        if tag.startswith(req):
            return tag

    # 3. Fallback to first available installed model tag
    return installed_models[0]


def _build_vault_context(db: Optional[Session]) -> Dict[str, Any]:
    """Extracts portfolio summary metrics and top items from vault.db."""
    if not db:
        return {"total_items": 0, "total_value": 0.0, "total_cost": 0.0,
                "profit_loss": 0.0, "profit_pct": 0.0, "key_count": 0,
                "top_items_str": "", "key_items_str": ""}

    items = db.query(CollectibleItem).all()
    total_items = len(items)
    total_value = round(sum(i.current_market_value for i in items), 2)
    total_cost = round(sum(i.purchase_price for i in items), 2)
    key_items = [i for i in items if i.is_key_issue]
    key_count = len(key_items)
    profit_loss = round(total_value - total_cost, 2)
    profit_pct = round((profit_loss / total_cost * 100) if total_cost > 0 else 0.0, 1)

    # Top 10 by market value
    top_10 = sorted(items, key=lambda x: x.current_market_value, reverse=True)[:10]
    top_items_lines = []
    for i in top_10:
        key_flag = f" [KEY: {i.key_reasons}]" if i.is_key_issue else ""
        gain = round(i.current_market_value - i.purchase_price, 2)
        top_items_lines.append(
            f"- {i.title} ({i.category}): Value ${i.current_market_value:.2f}, "
            f"Cost ${i.purchase_price:.2f}, Gain ${gain:+.2f}, "
            f"Grade {i.condition_grade or 'Raw'}{key_flag}"
        )

    # Key issues specifically
    key_items_lines = []
    for k in sorted(key_items, key=lambda x: x.current_market_value, reverse=True)[:10]:
        gain = round(k.current_market_value - k.purchase_price, 2)
        key_items_lines.append(
            f"- {k.title}: Value ${k.current_market_value:.2f}, Gain ${gain:+.2f}, Reason: {k.key_reasons}"
        )

    return {
        "total_items": total_items,
        "total_value": total_value,
        "total_cost": total_cost,
        "profit_loss": profit_loss,
        "profit_pct": profit_pct,
        "key_count": key_count,
        "top_items_str": "\n".join(top_items_lines) or "No items in vault.",
        "key_items_str": "\n".join(key_items_lines) or "No key issues tagged."
    }


def _format_full_prompt(user_prompt: str, ctx: Dict[str, Any]) -> str:
    """Combines system instruction, vault context, and user question into a single prompt."""
    vault_context_block = f"""Vault Context:
- Total Items: {ctx['total_items']}
- Total Market Value: ${ctx['total_value']:.2f}
- Total Capital Invested: ${ctx['total_cost']:.2f}
- Net Profit/Loss: ${ctx['profit_loss']:+.2f} ({ctx['profit_pct']:+.1f}%)
- Key Issues Count: {ctx['key_count']}

Top Valued Items:
{ctx['top_items_str']}

Key Issues:
{ctx['key_items_str']}"""

    return f"{SYSTEM_INSTRUCTION}\n\n{vault_context_block}\n\nUser: {user_prompt}\nAssistant:"


def _generate_conversational_fallback(user_prompt: str, ctx: Dict[str, Any]) -> str:
    """Generates a conversational fallback response using actual vault data when Ollama is offline."""
    user_lower = user_prompt.lower()

    preamble = ("I'm currently unable to reach the local Ollama LLM instance, "
                "but I can still help with your vault data.\n\n")

    if "spider" in user_lower or "spider-man" in user_lower:
        # Pull actual Spider-Man items from top items string
        spider_lines = [l for l in ctx["top_items_str"].split("\n") if "spider" in l.lower()]
        if spider_lines:
            return preamble + "Here are your Spider-Man items in the vault:\n" + "\n".join(spider_lines)
        return preamble + "I couldn't find any Spider-Man items in your vault right now."

    elif "growth" in user_lower or "summary" in user_lower or "portfolio" in user_lower:
        sign = "+" if ctx["profit_loss"] >= 0 else ""
        return (preamble +
                f"📊 Portfolio Summary:\n"
                f"• Total Items: {ctx['total_items']}\n"
                f"• Capital Invested: ${ctx['total_cost']:.2f}\n"
                f"• Current Market Value: ${ctx['total_value']:.2f}\n"
                f"• Net Gain/Loss: {sign}${ctx['profit_loss']:.2f} ({sign}{ctx['profit_pct']:.1f}% ROI)\n"
                f"• Key Issues Tagged: {ctx['key_count']}")

    elif "key" in user_lower or "gained" in user_lower:
        return preamble + f"🔑 Key Issues in Your Vault ({ctx['key_count']} tagged):\n{ctx['key_items_str']}"

    else:
        sign = "+" if ctx["profit_loss"] >= 0 else ""
        return (preamble +
                f"Your vault contains {ctx['total_items']} items worth ${ctx['total_value']:.2f} "
                f"(net {sign}${ctx['profit_loss']:.2f}, {sign}{ctx['profit_pct']:.1f}% ROI). "
                f"You have {ctx['key_count']} verified key issues.\n\n"
                f"Try asking about specific items, portfolio growth, or key issues!")


async def query_vault_assistant(
    user_prompt: str,
    selected_model: Optional[str] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Constructs portfolio context from vault.db, normalizes target model against installed Ollama models,
    sends a formatted prompt to Ollama, and returns Ollama's conversational response.
    Falls back gracefully if offline.
    """
    raw_requested_model = (selected_model or get_active_model()).strip()

    # 1. Fetch installed model tags from Ollama GET /api/tags
    installed_models = await fetch_installed_models()

    # 2. Normalize requested model against installed tags
    target_model = normalize_model_tag(raw_requested_model, installed_models)

    ctx = _build_vault_context(db)
    full_prompt = _format_full_prompt(user_prompt, ctx)

    context_summary = {
        "total_items": ctx["total_items"],
        "current_vault_value": ctx["total_value"],
        "key_issues_count": ctx["key_count"]
    }

    # Attempt Ollama API call with normalized model tag
    host = get_ollama_host()
    url = f"{host}/api/generate"
    payload = {
        "model": target_model,
        "prompt": full_prompt,
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                assistant_text = data.get("response", "").strip()
                if assistant_text:
                    return {
                        "status": "success",
                        "response": assistant_text,
                        "model_used": target_model,
                        "context": context_summary
                    }
                else:
                    logger.warning("Ollama returned empty response text.")
            else:
                logger.warning(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Ollama API connection failed ({host}): {e}")

    # Conversational fallback using actual vault data
    fallback_text = _generate_conversational_fallback(user_prompt, ctx)

    return {
        "status": "fallback",
        "response": fallback_text,
        "model_used": f"{target_model} (Offline — Local Fallback)",
        "context": context_summary
    }
