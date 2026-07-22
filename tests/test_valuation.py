import os
import pytest
from unittest.mock import patch, MagicMock
from app.valuation import (
    get_ebay_oauth_token,
    query_ebay_browse_api,
    clean_comic_title_for_search,
    build_ebay_search_query,
    build_stage2_ebay_search_query,
    build_broader_ebay_search_query,
    verify_comp_title_match,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_clean_comic_title_strips_the_prefix():
    assert clean_comic_title_for_search("The Amazing Spider-Man #624") == "Amazing Spider-Man 624"
    assert clean_comic_title_for_search("The Batman, Vol. 3 #101A") == "Batman 101"
    assert clean_comic_title_for_search("Star Wars: Bounty Hunters (Marvel Comics) #9A") == "Star Wars Bounty Hunters 9"


def test_build_stage2_ebay_search_query():
    assert build_stage2_ebay_search_query("Amazing Spider-Man 624") == "Spider-Man 624"
    assert build_stage2_ebay_search_query("Uncanny X-Men 266") == "X-Men 266"


def test_query_ebay_browse_api_raw_response_logs(capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "total": 5,
        "itemSummaries": [
            {"price": {"value": "25.00"}},
            {"price": {"value": "30.00"}}
        ]
    }

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", return_value=mock_resp):
        prices = query_ebay_browse_api("Amazing Spider-Man 624")
        assert prices == [25.0, 30.0]

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term: 'Amazing Spider-Man 624'" in captured.out
        assert "[EBAY RAW RESPONSE] Status: 200 | Query: 'Amazing Spider-Man 624' | Total Results: 5" in captured.out


def test_fetch_ebay_sold_comps_multi_stage_fallback(capsys):
    def mock_get(url, headers=None, params=None, timeout=5):
        mock_r = MagicMock()
        mock_r.status_code = 200
        q = (params or {}).get("q", "")
        if q == "Amazing Spider-Man 624":
            # Stage 1 returns 0 results
            mock_r.json.return_value = {"total": 0, "itemSummaries": []}
        elif q == "Spider-Man 624":
            # Stage 2 returns valid comps!
            mock_r.json.return_value = {
                "total": 3,
                "itemSummaries": [
                    {"price": {"value": "35.00"}},
                    {"price": {"value": "40.00"}},
                    {"price": {"value": "45.00"}}
                ]
            }
        else:
            mock_r.json.return_value = {"total": 0, "itemSummaries": []}
        return mock_r

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", side_effect=mock_get):
        fmv = fetch_ebay_sold_comps("The Amazing Spider-Man #624", "comic", 0.0, "Near Mint")
        assert fmv == 40.00

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term: 'Amazing Spider-Man 624'" in captured.out
        assert "[EBAY API SEARCH] Querying term: 'Spider-Man 624'" in captured.out
        assert "[VALUATION SUCCESS] Item: The Amazing Spider-Man #624 | Method: eBay Browse API (Stage 2 Broad)" in captured.out
