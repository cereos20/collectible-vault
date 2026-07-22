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
    comp_prices = [10.0, 12.0, 14.0, 16.0, 100.0]
    fmv = calculate_comp_fmv(comp_prices, category="comic", condition_grade="Near Mint", current_val=15.0)
    assert fmv == 13.0


def test_calculate_comp_fmv_zero_comps_returns_zero():
    fmv = calculate_comp_fmv([], category="comic", condition_grade="Near Mint", current_val=25.0)
    assert fmv == 0.0


def test_fetch_ebay_sold_comps_zero_comps_strict_zero_fallback(capsys):
    # When 0 comp sales are found, setting market_value = $0.00 strictly
    fmv = fetch_ebay_sold_comps("Obscure Unknown Title #999", "comic", 12.50, "Raw Near Mint")
    assert fmv == 0.0

    captured = capsys.readouterr()
    assert "[VALUATION NO COMPS] Item: Obscure Unknown Title #999 | Setting market_value = $0.00" in captured.out


def test_fetch_ebay_sold_comps_upc_priority(capsys):
    # Valid barcode "074470123456" uses UPC method priority
    fmv = fetch_ebay_sold_comps("Uncanny X-Men #266", "comic", 0.0, "CGC 9.4", barcode="074470123456")
    assert fmv == 240.00

    captured = capsys.readouterr()
    assert "[VALUATION SUCCESS] Item: Uncanny X-Men #266 | Method: UPC" in captured.out


def test_fetch_ebay_sold_comps_title_fallback(capsys):
    # Title "The Amazing Spider-Man #300" falls back to Title method when no UPC barcode provided
    fmv = fetch_ebay_sold_comps("The Amazing Spider-Man #300", "comic", 0.0, "CGC 9.6")
    assert fmv == 650.00

    captured = capsys.readouterr()
    assert "[VALUATION SUCCESS] Item: The Amazing Spider-Man #300 | Method: Title" in captured.out
