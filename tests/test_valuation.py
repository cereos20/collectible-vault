import pytest
from app.valuation import (
    sanitize_search_query,
    build_ebay_search_query,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_sanitize_search_query_special_characters():
    title = "Silver Surfer / Warlock: Resurrection #1"
    sanitized = sanitize_search_query(title)
    assert sanitized == "Silver Surfer Warlock Resurrection 1"
    assert "/" not in sanitized
    assert ":" not in sanitized
    assert "#" not in sanitized


def test_build_ebay_search_query_raw_comic():
    query = build_ebay_search_query("Batman #423", "comic", "Near Mint")
    assert "Batman 423" in query
    assert "-lot" in query
    assert "-set" in query
    assert "-run" in query
    assert "-cgc" in query
    assert "-graded" in query
    assert "-slab" in query


def test_build_ebay_search_query_cgc_graded_comic():
    query = build_ebay_search_query("Amazing Spider-Man #300", "comic", "CGC 9.8")
    assert "Amazing Spider-Man 300" in query or "Amazing Spider Man 300" in query
    assert "-cgc" not in query
    assert "-graded" not in query


def test_filter_outliers_iqr():
    prices = [10.0, 11.0, 12.0, 10.5, 11.5, 350.0, 1.0]
    filtered = filter_outliers_iqr(prices)
    assert 350.0 not in filtered
    assert len(filtered) < len(prices)


def test_calculate_comp_fmv_uses_median():
    # Comps: [10, 12, 14, 16, 100] -> outlier 100 removed -> comps [10, 12, 14, 16] -> median 13.0
    comp_prices = [10.0, 12.0, 14.0, 16.0, 100.0]
    fmv = calculate_comp_fmv(comp_prices, category="comic", condition_grade="Near Mint", current_val=15.0)
    assert fmv == 13.0


def test_calculate_comp_fmv_zero_comps_returns_none():
    fmv = calculate_comp_fmv([], category="comic", condition_grade="Near Mint", current_val=25.0)
    assert fmv is None


def test_fetch_ebay_sold_comps_retains_existing_value_on_zero_comps():
    # When current value is $12.50, ensure valuation does not cluster around mock $57-$58
    fmv = fetch_ebay_sold_comps("Obscure Title #99", "comic", 12.50, "Raw Near Mint")
    assert isinstance(fmv, float)
    # Price should be close to 12.50 (retained or simulated around 12.50), not $57-$58
    assert 10.0 <= fmv <= 15.0
    assert fmv != 57.50
