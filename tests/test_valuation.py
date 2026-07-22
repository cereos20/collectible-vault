import os
import pytest
from unittest.mock import patch, MagicMock
from app.valuation import (
    get_ebay_oauth_token,
    query_ebay_browse_api,
    clean_comic_title_for_search,
    build_ebay_search_query,
    build_broader_ebay_search_query,
    verify_comp_title_match,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_build_broader_ebay_search_query():
    assert build_broader_ebay_search_query("Captain Marvel #24") == "Captain Marvel"
    assert build_broader_ebay_search_query("Star Wars: Bounty Hunters (Marvel Comics) #9A") == "Star Wars Bounty Hunters"


def test_get_ebay_oauth_token_credentials_missing_logs(capsys):
    with patch.dict(os.environ, {}, clear=True):
        token = get_ebay_oauth_token()
        assert token is None

        captured = capsys.readouterr()
        assert "[EBAY ERROR] Missing EBAY_CLIENT_ID in environment" in captured.out


def test_get_ebay_oauth_token_auth_logging(capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "mock_access_token_12345",
        "expires_in": 7200
    }

    env_vars = {"EBAY_CLIENT_ID": "test_id", "EBAY_CLIENT_SECRET": "test_secret"}
    with patch.dict(os.environ, env_vars), patch("requests.post", return_value=mock_resp):
        from app.valuation import _EBAY_TOKEN_CACHE
        _EBAY_TOKEN_CACHE["token"] = None
        _EBAY_TOKEN_CACHE["expires_at"] = 0

        token = get_ebay_oauth_token()
        assert token == "mock_access_token_12345"

        captured = capsys.readouterr()
        assert "[EBAY AUTH] Requesting token..." in captured.out


def test_query_ebay_browse_api_search_logs(capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "itemSummaries": [
            {"price": {"value": "25.00"}},
            {"price": {"value": "30.00"}}
        ]
    }

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", return_value=mock_resp):
        prices = query_ebay_browse_api("Batman 101")
        assert prices == [25.0, 30.0]

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term: 'Batman 101'" in captured.out
        assert "[EBAY API RESULT] Status Code: 200 | Items Found: 2" in captured.out


def test_fetch_ebay_sold_comps_secondary_broader_search_fallback(capsys):
    def mock_get(url, headers=None, params=None, timeout=5):
        mock_r = MagicMock()
        mock_r.status_code = 200
        q = (params or {}).get("q", "")
        if q == "Unknown Series 99":
            # Primary search yields 0 items
            mock_r.json.return_value = {"itemSummaries": []}
        elif q == "Unknown Series":
            # Secondary broader search yields items!
            mock_r.json.return_value = {
                "itemSummaries": [
                    {"price": {"value": "45.00"}},
                    {"price": {"value": "50.00"}},
                    {"price": {"value": "55.00"}}
                ]
            }
        else:
            mock_r.json.return_value = {"itemSummaries": []}
        return mock_r

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", side_effect=mock_get):
        fmv = fetch_ebay_sold_comps("Unknown Series #99", "comic", 0.0, "Near Mint")
        assert fmv == 50.00

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term: 'Unknown Series 99'" in captured.out
        assert "[EBAY API SEARCH] Querying term: 'Unknown Series'" in captured.out
        assert "[VALUATION SUCCESS] Item: Unknown Series #99 | Method: eBay Browse API (Broader Title)" in captured.out
