import pytest
from app.valuation import (
    clean_comic_title_for_search,
    sanitize_search_query,
    build_ebay_search_query,
    verify_comp_title_match,
    filter_outliers_iqr,
    calculate_comp_fmv,
    fetch_ebay_sold_comps
)


def test_clean_comic_title_for_search_transformations():
    # 1. Star Wars: Bounty Hunters (Marvel Comics) #9A -> Star Wars Bounty Hunters 9
    res1 = clean_comic_title_for_search("Star Wars: Bounty Hunters (Marvel Comics) #9A")
    assert "Marvel Comics" not in res1
    assert "9" in res1
    assert "9A" not in res1

    # 2. The Amazing Spider-Man, Vol. 5 #61G -> The Amazing Spider-Man 61
    res2 = clean_comic_title_for_search("The Amazing Spider-Man, Vol. 5 #61G")
    assert "Vol" not in res2
    assert "61" in res2
    assert "61G" not in res2

    # 3. X-Force, Vol. 1 #25A1 -> X-Force 25
    res3 = clean_comic_title_for_search("X-Force, Vol. 1 #25A1")
    assert "Vol" not in res3
    assert "25" in res3
    assert "25A1" not in res3

    # 4. Batman, Vol. 3 #101A -> Batman 101
    res4 = clean_comic_title_for_search("Batman, Vol. 3 #101A")
    assert "Vol" not in res4
    assert "101" in res4
    assert "101A" not in res4

    # 5. Decimal preservation: Spider-Man #700.1
    res5 = clean_comic_title_for_search("Spider-Man #700.1")
    assert "700.1" in res5


def test_build_ebay_search_query_log_output(capsys):
    query = build_ebay_search_query("Batman, Vol. 3 #101A", "comic", "Near Mint")
    assert "Batman 101" in query
    assert "-lot" in query

    captured = capsys.readouterr()
    assert '[VALUATION QUERY] Original: "Batman, Vol. 3 #101A"' in captured.out


def test_verify_comp_title_match():
    # Single comic vs trade paperback / lot
    assert verify_comp_title_match("Batman #101 Near Mint", "101") is True
    assert verify_comp_title_match("Batman Vol 3 TPB Trade Paperback", "101") is False
    assert verify_comp_title_match("Batman Lot of 10 Comics", "101") is False
    assert verify_comp_title_match("Batman #102 NM", "101") is False


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
