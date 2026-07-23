import os
import pytest
from unittest.mock import patch, MagicMock
from app.services.pricecharting import query_pricecharting_api
from app.valuation import fetch_ebay_sold_comps, fetch_item_valuation


def test_pricecharting_missing_api_key():
    with patch.dict(os.environ, {"PRICECHARTING_API_KEY": ""}):
        price = query_pricecharting_api("Amazing Spider-Man 300")
        assert price == 0.0


def test_pricecharting_api_success_cents_conversion():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "12345",
        "product-name": "Amazing Spider-Man 300",
        "loose-price": 1500,     # $15.00
        "cib-price": 4500,       # $45.00
        "graded-price": 25000    # $250.00
    }

    with patch.dict(os.environ, {"PRICECHARTING_API_KEY": "test_token_123"}), \
         patch("requests.get", return_value=mock_response):
        # 1. Raw / ungraded query
        raw_price = query_pricecharting_api("Amazing Spider-Man 300", condition_grade="Fine 8.0")
        assert raw_price == 45.0  # CIB / mid-grade price

        # 2. Graded slab query
        graded_price = query_pricecharting_api("Amazing Spider-Man 300", condition_grade="CGC 9.8")
        assert graded_price == 250.0  # Graded slab price


def test_pricecharting_api_no_match():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"products": []}

    with patch.dict(os.environ, {"PRICECHARTING_API_KEY": "test_token_123"}), \
         patch("requests.get", return_value=mock_response):
        price = query_pricecharting_api("Nonexistent Book #999")
        assert price == 0.0


def test_valuation_waterfall_pricecharting_success():
    with patch("app.valuation.query_pricecharting_api", return_value=125.00):
        val = fetch_item_valuation("Amazing Spider-Man #300", "comic")
        assert val == 125.00


def test_valuation_waterfall_fallback_to_ebay(capsys):
    # PriceCharting returns 0.0 -> fallback to eBay / MyComicShop
    with patch("app.valuation.query_pricecharting_api", return_value=0.0):
        val = fetch_item_valuation("The Amazing Spider-Man #624", "comic")
        assert val == 650.0  # Falls back to MyComicShop simulation benchmark
        captured = capsys.readouterr()
        assert "[VALUATION SUCCESS]" in captured.out
