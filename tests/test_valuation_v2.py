import pytest
from app.valuation import (
    sanitize_and_disambiguate_query,
    calculate_robust_fmv_v2,
    fetch_ebay_sold_comps
)


def test_sanitize_and_disambiguate_query_short_title():
    # 1. Short comic title "52 #38"
    info = sanitize_and_disambiguate_query("52 #38", category="comic", condition_grade="Near Mint")
    assert info["is_short_title"] is True
    assert info["category_id"] == "259104"
    assert "comic book issue" in info["api_query"]
    assert "-lot" in info["api_query"]
    assert "-cgc" in info["api_query"]

    # 2. Graded comic title "Amazing Spider-Man #300"
    info_graded = sanitize_and_disambiguate_query("The Amazing Spider-Man #300", category="comic", condition_grade="CGC 9.8")
    assert info_graded["is_graded"] is True
    assert info_graded["category_id"] == "259104"
    assert "-cgc" not in info_graded["api_query"]  # Should NOT exclude CGC when graded


def test_sanitize_and_disambiguate_query_strips_variant_letters():
    info_618a = sanitize_and_disambiguate_query("The Amazing Spider-Man #618A", category="comic")
    assert info_618a["cleaned_title"] == "Amazing Spider-Man 618"
    assert "Amazing Spider-Man 618 comic" in info_618a["api_query"]

    info_615a = sanitize_and_disambiguate_query("Amazing Spider-Man 615A", category="comic")
    assert info_615a["cleaned_title"] == "Amazing Spider-Man 615"

    info_620a = sanitize_and_disambiguate_query("The Amazing Spider-Man #620A", category="comic")
    assert info_620a["cleaned_title"] == "Amazing Spider-Man 620"


def test_sanitize_and_disambiguate_query_categories():
    # Trading Card
    tc_info = sanitize_and_disambiguate_query("Charizard Holo", category="trading_card")
    assert tc_info["category_id"] == "183454"
    assert "card" in tc_info["api_query"]

    # Funko Pop
    funko_info = sanitize_and_disambiguate_query("Darth Vader #01", category="funko")
    assert funko_info["category_id"] == "262334"
    assert "Funko Pop" in funko_info["api_query"]

    # Action Figure
    fig_info = sanitize_and_disambiguate_query("Boba Fett 6-inch", category="figure")
    assert fig_info["category_id"] == "220"


def test_calculate_robust_fmv_v2_4stage_pipeline():
    # Raw comps with extreme outliers: [5.0, 10.0, 10.0, 12.0, 12.0, 15.0, 500.0]
    # Gross lot filter (3x median ~36) drops 500.0
    # Ungraded Raw Condition: Near Mint 9.8 (3.5x multiplier on raw comps)
    fmv_98 = calculate_robust_fmv_v2([5.0, 10.0, 10.0, 12.0, 12.0, 15.0, 500.0], category="comic", condition_grade="Near Mint 9.8")
    # Base median after trimming 12.0 * 3.5 = 42.0
    assert fmv_98 == 42.0

    # Fine 8.0 (1.0x baseline multiplier)
    fmv_80 = calculate_robust_fmv_v2([10.0, 10.0, 12.0, 12.0, 14.0], category="comic", condition_grade="Fine 8.0")
    assert fmv_80 == 12.0
