import os
import pytest
from unittest.mock import patch, MagicMock
from app.valuation import (
    get_ebay_oauth_token,
    query_ebay_browse_api,
    clean_comic_title_for_search,
    build_ebay_search_query,
    verify_comp_title_match,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_get_ebay_oauth_token_credentials_missing():
    with patch.dict(os.environ, {}, clear=True):
        token = get_ebay_oauth_token()
        assert token is None


def test_get_ebay_oauth_token_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "mock_access_token_12345",
        "expires_in": 7200
    }

    env_vars = {"EBAY_CLIENT_ID": "test_id", "EBAY_CLIENT_SECRET": "test_secret"}
    with patch.dict(os.environ, env_vars), patch("requests.post", return_value=mock_resp):
        # Clear cache for test
        from app.valuation import _EBAY_TOKEN_CACHE
        _EBAY_TOKEN_CACHE["token"] = None
        _EBAY_TOKEN_CACHE["expires_at"] = 0

        token = get_ebay_oauth_token()
        assert token == "mock_access_token_12345"


def test_query_ebay_browse_api_returns_prices():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "itemSummaries": [
            {"price": {"value": "25.00"}},
            {"price": {"value": "30.00"}},
            {"currentBidPrice": {"value": "27.50"}}
        ]
    }

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", return_value=mock_resp):
        prices = query_ebay_browse_api("Batman 101")
        assert prices == [25.0, 30.0, 27.5]


def test_fetch_ebay_sold_comps_priority_browse_api(capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "itemSummaries": [
            {"price": {"value": "150.00"}},
            {"price": {"value": "155.00"}},
            {"price": {"value": "160.00"}}
        ]
    }

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", return_value=mock_resp):
        fmv = fetch_ebay_sold_comps("Captain Marvel #24", "comic", 0.0, "Near Mint")
        assert fmv == 155.00

        captured = capsys.readouterr()
        assert "[VALUATION SUCCESS] Item: Captain Marvel #24 | Method: eBay Browse API (Title)" in captured.out


def test_fetch_ebay_sold_comps_fallback_to_mycomicshop(capsys):
    # When Browse API returns [], fallback to MyComicShop / local index (Priority 3)
    with patch("app.valuation.get_ebay_oauth_token", return_value=None):
        fmv = fetch_ebay_sold_comps("The Amazing Spider-Man #300", "comic", 0.0, "CGC 9.6")
        assert fmv == 650.00

        captured = capsys.readouterr()
        assert "[VALUATION SUCCESS] Item: The Amazing Spider-Man #300 | Method: Title" in captured.out


def test_fetch_ebay_sold_comps_zero_comps_strict_zero_fallback(capsys):
    with patch("app.valuation.get_ebay_oauth_token", return_value=None):
        fmv = fetch_ebay_sold_comps("Obscure Unknown Title #999", "comic", 12.50, "Raw Near Mint")
        assert fmv == 0.0

        captured = capsys.readouterr()
        assert "[VALUATION NO COMPS] Item: Obscure Unknown Title #999 | Setting market_value = $0.00" in captured.out
