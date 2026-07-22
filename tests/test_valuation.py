import pytest
from app.valuation import (
    build_ebay_search_query,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_build_ebay_search_query_raw_comic():
    query = build_ebay_search_query("Batman #423", "comic", "Near Mint")
    assert "Batman #423" in query
    assert "-lot" in query
    assert "-set" in query
    assert "-run" in query
    assert "-cgc" in query
    assert "-graded" in query
    assert "-slab" in query


def test_build_ebay_search_query_cgc_graded_comic():
    query = build_ebay_search_query("Amazing Spider-Man #300", "comic", "CGC 9.8")
    assert "Amazing Spider-Man #300" in query
    assert "-cgc" not in query
    assert "-graded" not in query


def test_filter_outliers_iqr():
    prices = [10.0, 11.0, 12.0, 10.5, 11.5, 350.0, 1.0]
    filtered = filter_outliers_iqr(prices)
    assert 350.0 not in filtered
    assert len(filtered) < len(prices)


def test_calculate_comp_fmv_raw_comic_capping():
    # Modern minor raw comic with base value $15
    comp_prices = [12.0, 15.0, 14.0, 16.0, 250.0]  # $250 lot sale outlier
    fmv = calculate_comp_fmv(comp_prices, category="comic", condition_grade="Near Mint", base_val=15.0)
    assert fmv <= 30.0
    assert fmv > 10.0


def test_fetch_ebay_sold_comps():
    fmv = fetch_ebay_sold_comps("X-Men #1", "comic", 25.0, "Raw Near Mint")
    assert isinstance(fmv, float)
    assert fmv > 0
