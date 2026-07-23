import os
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("vault.pricecharting")


def query_pricecharting_api(
    query: str,
    condition_grade: Optional[str] = None,
    barcode: Optional[str] = None
) -> float:
    """
    Queries PriceCharting API for guide FMV pricing.
    Converts prices from USD cents to float dollars.
    Returns 0.0 if API key is missing or no valid comps found.
    """
    api_key = os.getenv("PRICECHARTING_API_KEY", "").strip()
    if not api_key:
        logger.info("[PRICECHARTING] PRICECHARTING_API_KEY not configured. Skipping PriceCharting stage.")
        return 0.0

    url_base = "https://www.pricecharting.com/api"

    try:
        product_data: Optional[Dict[str, Any]] = None

        # 1. Direct UPC Lookup if barcode is provided
        if barcode and barcode.strip():
            upc_url = f"{url_base}/product"
            upc_params = {"t": api_key, "upc": barcode.strip()}
            upc_resp = requests.get(upc_url, params=upc_params, timeout=5)
            if upc_resp.status_code == 200:
                data = upc_resp.json()
                if data and isinstance(data, dict) and "id" in data:
                    product_data = data

        # 2. Product Search Query Lookup if no UPC match
        if not product_data and query and query.strip():
            search_url = f"{url_base}/products"
            search_params = {"t": api_key, "q": query.strip()}
            search_resp = requests.get(search_url, params=search_params, timeout=5)
            if search_resp.status_code == 200:
                s_data = search_resp.json()
                products = []
                if isinstance(s_data, list):
                    products = s_data
                elif isinstance(s_data, dict):
                    products = s_data.get("products", [])

                if products and len(products) > 0:
                    first_prod = products[0]
                    prod_id = first_prod.get("id")
                    # If detailed prices are in search result:
                    if "loose-price" in first_prod or "graded-price" in first_prod:
                        product_data = first_prod
                    elif prod_id:
                        # Fetch full product detail
                        det_url = f"{url_base}/product"
                        det_resp = requests.get(det_url, params={"t": api_key, "id": prod_id}, timeout=5)
                        if det_resp.status_code == 200:
                            product_data = det_resp.json()

        if not product_data:
            logger.info(f"[PRICECHARTING] 0 products found for query: '{query}'")
            return 0.0

        product_name = product_data.get("product-name") or product_data.get("product_name") or query
        cond_clean = (condition_grade or "").lower()
        is_graded = any(g in cond_clean for g in ["cgc", "cbcs", "pgx", "psa", "bgs", "slab", "9.8", "gem"])

        # Extract prices in cents
        loose_cents = product_data.get("loose-price") or product_data.get("loose_price") or 0
        cib_cents = product_data.get("cib-price") or product_data.get("cib_price") or 0
        graded_cents = product_data.get("graded-price") or product_data.get("graded_price") or 0

        chosen_cents = 0
        if is_graded and graded_cents > 0:
            chosen_cents = graded_cents
        elif cib_cents > 0:
            chosen_cents = cib_cents
        elif loose_cents > 0:
            chosen_cents = loose_cents
        else:
            chosen_cents = graded_cents or 0

        if chosen_cents > 0:
            final_usd = round(float(chosen_cents) / 100.0, 2)
            log_msg = f"[PRICECHARTING RAW RESPONSE] Query: '{query}' | Product: '{product_name}' | Price: ${final_usd:.2f}"
            logger.info(log_msg)
            print(log_msg)
            return final_usd

        return 0.0
    except Exception as e:
        err_msg = f"[PRICECHARTING API ERROR] {e}"
        logger.error(err_msg)
        print(err_msg)
        return 0.0
