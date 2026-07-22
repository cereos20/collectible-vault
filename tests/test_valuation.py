import pytest
from app.valuation import (
    clean_comic_title_for_search,
    build_ebay_search_query,
    verify_comp_title_match,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_build_ebay_search_query_simplified_without_inline_negatives(capsys):
    query = build_ebay_search_query("Captain Marvel #24", "comic", "Near Mint")
    assert query == "Captain Marvel 24"
    assert "-lot" not in query
    assert "-set" not in query
    assert "-cgc" not in query

    captured = capsys.readouterr()
    assert '[VALUATION QUERY] Original: "Captain Marvel #24" -> Cleaned: "Captain Marvel 24"' in captured.out


def test_verify_comp_title_match_python_post_filtering():
    # Raw comic post-filtering in Python
    assert verify_comp_title_match("Captain Marvel #24 NM", "24", is_graded=False) is True
    assert verify_comp_title_match("Captain Marvel #24 CGC 9.8", "24", is_graded=False) is False
    assert verify_comp_title_match("Captain Marvel #24 Lot of 5", "24", is_graded=False) is False
    assert verify_comp_title_match("Captain Marvel Complete Run Set", "24", is_graded=False) is False
    assert verify_comp_title_match("Captain Marvel Slabbed Comic", "24", is_graded=False) is False

    # Graded comic permits graded terms
    assert verify_comp_title_match("Captain Marvel #24 CGC 9.8", "24", is_graded=True) is True


def test_clean_comic_title_for_search_transformations():
    assert clean_comic_title_for_search("Star Wars: Bounty Hunters (Marvel Comics) #9A") == "Star Wars Bounty Hunters 9"
    assert clean_comic_title_for_search("The Amazing Spider-Man, Vol. 5 #61G") == "The Amazing Spider-Man 61"
    assert clean_comic_title_for_search("X-Force, Vol. 1 #25A1") == "X-Force 25"


def test_filter_outliers_iqr():
    prices = [10.0, 11.0, 12.0, 10.5, 11.5, 350.0, 1.0]
    filtered = filter_outliers_iqr(prices)
    assert 350.0 not in filtered
    assert len(filtered) < len(prices)


def test_calculate_comp_fmv_uses_median():
    comp_prices = [10.0, 12.0, 14.0, 16.0, 100.0]
    fmv = calculate_comp_fmv(comp_prices, category="comic", condition_grade="Near Mint", current_val=15.0)
    assert fmv == 13.0


def test_fetch_ebay_sold_comps_zero_comps_strict_zero_fallback(capsys):
    fmv = fetch_ebay_sold_comps("Obscure Unknown Title #999", "comic", 12.50, "Raw Near Mint")
    assert fmv == 0.0

    captured = capsys.readouterr()
    assert "[VALUATION NO COMPS] Item: Obscure Unknown Title #999 | Setting market_value = $0.00" in captured.out


def test_fetch_ebay_sold_comps_upc_priority(capsys):
    fmv = fetch_ebay_sold_comps("Uncanny X-Men #266", "comic", 0.0, "CGC 9.4", barcode="074470123456")
    assert fmv == 240.00

    captured = capsys.readouterr()
    assert "[VALUATION SUCCESS] Item: Uncanny X-Men #266 | Method: UPC" in captured.out
