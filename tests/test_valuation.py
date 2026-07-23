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


def test_build_ebay_search_query_short_generic_disambiguation():
    # Short / generic titles append ' comic'
    assert "52 1 comic" in build_ebay_search_query("52 #1")
    assert "Silk 1 comic" in build_ebay_search_query("Silk #1")
    assert "Star Wars 9 comic" in build_ebay_search_query("Star Wars #9")

    # Specific series titles do not append ' comic' if not short/generic
    assert "Amazing Spider-Man 624" in build_ebay_search_query("The Amazing Spider-Man #624")


def test_build_stage2_ebay_search_query():
    assert build_stage2_ebay_search_query("Amazing Spider-Man 624") == "Spider-Man 624"
    assert build_stage2_ebay_search_query("Uncanny X-Men 266") == "X-Men 266"


def test_query_ebay_browse_api_category_lock_and_keyword_filtering(capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "total": 5,
        "itemSummaries": [
            {"title": "Spider-Man #624 NM Raw", "price": {"value": "20.00"}},
            {"title": "Spider-Man #624 CGC 9.8 Slab", "price": {"value": "150.00"}},  # 'cgc' keyword -> excluded
            {"title": "Spider-Man #624 Statue Figure", "price": {"value": "200.00"}},  # 'statue' keyword -> excluded
            {"title": "Spider-Man #624 Lot of 5 Comics", "price": {"value": "80.00"}}, # 'lot' keyword -> excluded
            {"title": "Spider-Man #624 Very Fine", "price": {"value": "30.00"}}
        ]
    }

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", return_value=mock_resp) as mock_get:
        prices = query_ebay_browse_api("Amazing Spider-Man 624")
        
        # Verify category_ids=63 parameter was passed to eBay API
        args, kwargs = mock_get.call_args
        assert kwargs["params"].get("category_ids") == "63"
        
        # Verify keyword-excluded items were filtered out
        assert prices == [20.0, 30.0]

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term: 'Amazing Spider-Man 624'" in captured.out
        assert "[EBAY MATH DEBUG] Raw Comps: [20.0, 30.0] | Filtered Comps: [20.0, 30.0] | Median: $25.00" in captured.out


def test_calculate_comp_fmv_3x_median_outlier_removal(capsys):
    # Comps: [10, 12, 14, 15, 100] -> initial median = 14.0 -> 3x median = 42.0 -> 100.0 removed as > 42.0
    comp_prices = [10.0, 12.0, 14.0, 15.0, 100.0]
    fmv = calculate_comp_fmv(comp_prices, category="comic", condition_grade="Fine 8.0", current_val=15.0)
    assert fmv == 13.0

    captured = capsys.readouterr()
    assert "[EBAY MATH DEBUG]" in captured.out
    assert "Median: $13.00" in captured.out


def test_fetch_ebay_sold_comps_multi_stage_fallback(capsys):
    def mock_get(url, headers=None, params=None, timeout=5):
        mock_r = MagicMock()
        mock_r.status_code = 200
        q = (params or {}).get("q", "")
        if "Amazing Spider-Man 624" in q:
            # Stage 1 returns 0 results
            mock_r.json.return_value = {"total": 0, "itemSummaries": []}
        elif "Spider-Man 624" in q:
            # Stage 2 returns valid comps!
            mock_r.json.return_value = {
                "total": 3,
                "itemSummaries": [
                    {"title": "Spider-Man #624 VF", "price": {"value": "35.00"}},
                    {"title": "Spider-Man #624 NM", "price": {"value": "40.00"}},
                    {"title": "Spider-Man #624 NM+", "price": {"value": "45.00"}}
                ]
            }
        else:
            mock_r.json.return_value = {"total": 0, "itemSummaries": []}
        return mock_r

    with patch("app.valuation.get_ebay_oauth_token", return_value="mock_token"), \
         patch("requests.get", side_effect=mock_get):
        fmv = fetch_ebay_sold_comps("The Amazing Spider-Man #624", "comic", 0.0, "Fine 8.0")
        assert fmv == 40.00

        captured = capsys.readouterr()
        assert "[EBAY API SEARCH] Querying term:" in captured.out
        assert "[VALUATION SUCCESS] Item: The Amazing Spider-Man #624 | Method: eBay Browse API (Stage 2 Broad)" in captured.out
