import os
import re
import httpx
import logging
from typing import Dict, Any, Optional, List, Set
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


def _extract_search_tokens(user_prompt: str) -> List[str]:
    """Extracts search keywords and tokens from the user prompt."""
    prompt_lower = user_prompt.lower()
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "over", "after",
        "what", "where", "when", "how", "who", "which", "why", "show", "list",
        "my", "me", "i", "your", "are", "is", "was", "were", "be", "have", "has",
        "had", "do", "does", "did", "top", "all", "get", "find", "tell", "give",
        "many", "much", "valuable", "items", "item", "vault", "collection"
    }

    words = re.findall(r'\b[a-zA-Z0-9\'-]+\b', prompt_lower)
    return [w for w in words if w not in stop_words and len(w) > 1]


def _build_vault_context(user_prompt: str = "", db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Extracts portfolio summary metrics, category totals breakdown, and
    intent-aware matching items from vault.db based on keywords in user_prompt.
    """
    if not db:
        return {
            "total_items": 0, "total_value": 0.0, "total_cost": 0.0,
            "profit_loss": 0.0, "profit_pct": 0.0, "key_count": 0,
            "category_summary_str": "No categories available.",
            "top_items_str": "No items in vault.",
            "key_items_str": "No key issues tagged.",
            "relevant_items_str": "No matching items found."
        }

    items = db.query(CollectibleItem).all()
    total_items = len(items)
    total_value = round(sum(i.current_market_value for i in items), 2)
    total_cost = round(sum(i.purchase_price for i in items), 2)
    key_items = [i for i in items if i.is_key_issue]
    key_count = len(key_items)
    profit_loss = round(total_value - total_cost, 2)
    profit_pct = round((profit_loss / total_cost * 100) if total_cost > 0 else 0.0, 1)

    # Category totals breakdown
    cat_counts: Dict[str, int] = {}
    cat_values: Dict[str, float] = {}
    for i in items:
        cat = (i.category or "other").lower()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        cat_values[cat] = round(cat_values.get(cat, 0.0) + (i.current_market_value or 0.0), 2)

    cat_labels = {
        "comic": "Comics",
        "funko": "Funko Pops",
        "figure": "Figures",
        "action_figure": "Action Figures",
        "trading_card": "Trading Cards",
        "card": "Trading Cards",
        "other": "Other Collectibles"
    }

    cat_parts = []
    for cat_key, count in cat_counts.items():
        label = cat_labels.get(cat_key, cat_key.capitalize())
        val = cat_values.get(cat_key, 0.0)
        cat_parts.append(f"{label}: {count} (${val:.2f})")

    category_summary_str = ", ".join(cat_parts) if cat_parts else "No items in vault."

    # Intent-aware item matching
    prompt_lower = user_prompt.lower() if user_prompt else ""
    tokens = _extract_search_tokens(user_prompt) if user_prompt else []

    # Category keyword mapping
    category_keywords = {
        "comic": ["comic", "comics", "book", "books"],
        "funko": ["funko", "funkos", "pop", "pops"],
        "figure": ["figure", "figures", "action figure", "action figures", "toy", "toys"],
        "action_figure": ["figure", "figures", "action figure", "action figures", "toy", "toys"],
        "trading_card": ["card", "cards", "trading card", "pokemon", "pokémon", "tcg"]
    }

    matched_categories: Set[str] = set()
    for cat, kw_list in category_keywords.items():
        if any(kw in prompt_lower for kw in kw_list):
            matched_categories.add(cat)

    matching_items = []
    for item in items:
        item_title_lower = (item.title or "").lower()
        item_cat_lower = (item.category or "").lower()
        item_notes_lower = (item.notes or "").lower()
        item_keys_lower = (item.key_reasons or "").lower()

        # Check category match
        is_cat_match = item_cat_lower in matched_categories

        # Check token match across title, notes, key_reasons, category
        is_token_match = any(
            t in item_title_lower or t in item_notes_lower or t in item_keys_lower or t in item_cat_lower
            for t in tokens
        )

        if is_cat_match or is_token_match:
            matching_items.append(item)

    # Sort matching items by market value descending
    matching_items = sorted(matching_items, key=lambda x: x.current_market_value, reverse=True)[:25]

    # If no specific matches found (or prompt is generic summary request), fallback to top valued items
    if not matching_items:
        matching_items = sorted(items, key=lambda x: x.current_market_value, reverse=True)[:15]

    relevant_lines = []
    for i in matching_items:
        key_flag = f" [KEY: {i.key_reasons}]" if i.is_key_issue else ""
        gain = round(i.current_market_value - i.purchase_price, 2)
        relevant_lines.append(
            f"- {i.title} ({i.category}): Value ${i.current_market_value:.2f}, "
            f"Cost ${i.purchase_price:.2f}, Gain ${gain:+.2f}, "
            f"Grade {i.condition_grade or 'Raw'}{key_flag}"
        )

    relevant_items_str = "\n".join(relevant_lines) or "No items found."

    # Top 10 overall for general context
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

    # Key issues
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
        "category_summary_str": category_summary_str,
        "top_items_str": "\n".join(top_items_lines) or "No items in vault.",
        "key_items_str": "\n".join(key_items_lines) or "No key issues tagged.",
        "relevant_items_str": relevant_items_str
    }


def _format_full_prompt(user_prompt: str, ctx: Dict[str, Any]) -> str:
    """Combines system instruction, vault context, category overview, and user question into a single prompt."""
    vault_context_block = f"""Vault Context:
- Total Items: {ctx['total_items']}
- Total Market Value: ${ctx['total_value']:.2f}
- Total Capital Invested: ${ctx['total_cost']:.2f}
- Net Profit/Loss: ${ctx['profit_loss']:+.2f} ({ctx['profit_pct']:+.1f}%)
- Key Issues Count: {ctx['key_count']}
- Category Breakdown: {ctx['category_summary_str']}

Relevant Vault Items Matching Query:
{ctx['relevant_items_str']}

Top Valued Items in Vault:
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
        spider_lines = [l for l in ctx["relevant_items_str"].split("\n") if "spider" in l.lower()]
        if spider_lines:
            return preamble + "Here are your Spider-Man items in the vault:\n" + "\n".join(spider_lines)
        return preamble + "I couldn't find any Spider-Man items in your vault right now."

    elif "figure" in user_lower or "action figure" in user_lower or "toy" in user_lower:
        fig_lines = [l for l in ctx["relevant_items_str"].split("\n") if "figure" in l.lower() or "kenner" in l.lower() or "boba" in l.lower()]
        if fig_lines:
            return preamble + "Here are your action figures in the vault:\n" + "\n".join(fig_lines)
        return preamble + f"Here are relevant items in your vault:\n{ctx['relevant_items_str']}"

    elif "growth" in user_lower or "summary" in user_lower or "portfolio" in user_lower:
        sign = "+" if ctx["profit_loss"] >= 0 else ""
        return (preamble +
                f"📊 Portfolio Summary:\n"
                f"• Total Items: {ctx['total_items']}\n"
                f"• Capital Invested: ${ctx['total_cost']:.2f}\n"
                f"• Current Market Value: ${ctx['total_value']:.2f}\n"
                f"• Net Gain/Loss: {sign}${ctx['profit_loss']:.2f} ({sign}{ctx['profit_pct']:.1f}% ROI)\n"
                f"• Key Issues Tagged: {ctx['key_count']}\n"
                f"• Category Breakdown: {ctx['category_summary_str']}")

    elif "key" in user_lower or "gained" in user_lower:
        return preamble + f"🔑 Key Issues in Your Vault ({ctx['key_count']} tagged):\n{ctx['key_items_str']}"

    else:
        sign = "+" if ctx["profit_loss"] >= 0 else ""
        return (preamble +
                f"Your vault contains {ctx['total_items']} items worth ${ctx['total_value']:.2f} "
                f"(net {sign}${ctx['profit_loss']:.2f}, {sign}{ctx['profit_pct']:.1f}% ROI). "
                f"Categories: {ctx['category_summary_str']}.\n\n"
                f"Here are relevant items matching your prompt:\n{ctx['relevant_items_str']}")


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

    ctx = _build_vault_context(user_prompt, db)
    full_prompt = _format_full_prompt(user_prompt, ctx)

    context_summary = {
        "total_items": ctx["total_items"],
        "current_vault_value": ctx["total_value"],
        "key_issues_count": ctx["key_count"],
        "category_summary": ctx["category_summary_str"]
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


def generate_item_market_summary(item_id: int, db: Session) -> Dict[str, Any]:
    """
    Generates a concise market briefing for a single item based on
    its valuation history, sold comps, purchase price, and market trajectory.
    """
    item = db.query(CollectibleItem).filter(CollectibleItem.id == item_id).first()
    if not item:
        return {"status": "error", "message": f"Item #{item_id} not found."}

    val_history = item.valuation_history
    val_points = [v.value for v in val_history] if val_history else []
    
    current_val = item.current_market_value or 0.0
    cost = item.purchase_price or 0.0
    profit = round(current_val - cost, 2)
    profit_pct = round((profit / cost * 100) if cost > 0 else 0.0, 1)

    key_text = f" Driven by '{item.key_reasons}' key status." if item.is_key_issue and item.key_reasons else ""

    if val_points and len(val_points) > 1:
        min_comp = min(val_points)
        max_comp = max(val_points)
        avg_comp = round(sum(val_points) / len(val_points), 2)
        briefing = (
            f"{item.title} demonstrates solid market liquidity with recent comps ranging from ${min_comp:.2f} to ${max_comp:.2f} (avg ${avg_comp:.2f})."
            f"{key_text} Currently valued at ${current_val:.2f}, representing a net ROI of {profit_pct:+.1f}% over purchase cost."
        )
    else:
        briefing = (
            f"{item.title} ({item.category}) is currently valued at ${current_val:.2f} based on fair market comps."
            f"{key_text} Capital cost basis is ${cost:.2f}, yielding a net gain of ${profit:+.2f} ({profit_pct:+.1f}% ROI)."
        )

    return {
        "status": "success",
        "item_id": item_id,
        "title": item.title,
        "current_market_value": current_val,
        "summary": briefing
    }


def generate_portfolio_insights(db: Session) -> Dict[str, Any]:
    """
    Analyzes overall vault composition, category distribution, top gains, and yields proactive AI insights.
    """
    items = db.query(CollectibleItem).all()
    if not items:
        return {
            "status": "success",
            "headline": "Empty Vault Inventory",
            "insights": ["Add items to your vault to generate AI portfolio analytics."],
            "advice": "Snap photos or import XML catalogs to start tracking asset value."
        }

    total_items = len(items)
    total_val = round(sum(i.current_market_value for i in items), 2)
    total_cost = round(sum(i.purchase_price for i in items), 2)
    total_gain = round(total_val - total_cost, 2)
    overall_roi = round((total_gain / total_cost * 100) if total_cost > 0 else 0.0, 1)

    cat_values: Dict[str, float] = {}
    for i in items:
        cat = i.category or "other"
        cat_values[cat] = cat_values.get(cat, 0.0) + i.current_market_value

    top_cat = max(cat_values.items(), key=lambda x: x[1]) if cat_values else ("other", 0.0)
    top_cat_pct = round((top_cat[1] / total_val * 100) if total_val > 0 else 0.0, 1)

    key_items = [i for i in items if i.is_key_issue]
    key_count = len(key_items)
    key_val = sum(k.current_market_value for k in key_items)
    key_pct = round((key_val / total_val * 100) if total_val > 0 else 0.0, 1)

    cat_display_map = {"comic": "Comic Books", "funko": "Funko Pops", "figure": "Action Figures", "trading_card": "Trading Cards"}
    top_cat_name = cat_display_map.get(top_cat[0], top_cat[0].capitalize())

    headline = f"Portfolio Insight: {top_cat_name} Lead Vault at {top_cat_pct}% Concentration (${top_cat[1]:,.2f})"

    insights = [
        f"Vault holds {total_items} items with a total Fair Market Value of ${total_val:,.2f} (Net Gain ${total_gain:+,.2f}, {overall_roi:+.1f}% ROI).",
        f"Top category '{top_cat_name}' represents ${top_cat[1]:,.2f} ({top_cat_pct}% of total asset value).",
        f"{key_count} verified key issues represent ${key_val:,.2f} ({key_pct}% of total portfolio valuation)."
    ]

    advice = "Consider grading high-value raw key issues or balancing portfolio exposure across underrepresented categories."

    return {
        "status": "success",
        "headline": headline,
        "total_items": total_items,
        "total_value": total_val,
        "total_gain": total_gain,
        "overall_roi": overall_roi,
        "top_category": top_cat_name,
        "top_category_percentage": top_cat_pct,
        "key_issues_count": key_count,
        "insights": insights,
        "advice": advice
    }

