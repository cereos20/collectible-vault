import re
from typing import Tuple, Optional

KEY_ISSUE_PATTERNS = [
    (r"spider-man.*#?300\b|amazing spider-man.*300", "1st Full Appearance of Venom"),
    (r"spider-man.*#?361\b|amazing spider-man.*361", "1st Appearance of Carnage"),
    (r"incredible hulk.*#?181\b|hulk.*181", "1st Appearance of Wolverine"),
    (r"batman.*#?423\b", "Iconic Todd McFarlane Cover"),
    (r"batman.*#?227\b", "Iconic Neal Adams Cover"),
    (r"secret wars.*#?8\b", "1st Appearance of Symbiote Black Suit"),
    (r"thor.*#?337\b", "1st Appearance of Beta Ray Bill"),
    (r"x-men.*#?266\b|uncanny x-men.*266", "1st Appearance of Gambit"),
    (r"x-men.*#?141\b|uncanny x-men.*141", "Days of Future Past"),
    (r"star wars.*#?42\b", "1st Appearance of Boba Fett"),
    (r"star wars.*#?1\b", "1st Appearance of Darth Vader in Comics"),
    (r"fantasy.*#?15\b|amazing fantasy.*15", "1st Appearance of Spider-Man"),
    (r"action comics.*#?1\b", "1st Appearance of Superman"),
    (r"detective comics.*#?27\b", "1st Appearance of Batman"),
    (r"x-force.*#?15\b", "1st Appearance of Cable / Shatterstar"),
    (r"x-force.*#?11\b|x force.*11", "1st Real Appearance of Domino"),
    (r"new mutants.*#?98\b", "1st Appearance of Deadpool"),
]


def detect_key_issue(title: str, notes: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Evaluates item title and notes against known key issue patterns.
    Returns (is_key_issue, key_reasons).
    """
    text = f"{title or ''} {notes or ''}".lower()

    for pattern, reason in KEY_ISSUE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True, reason

    # Order from longest to shortest to ensure specific key phrases take precedence
    generic_keywords = [
        "first appearance", "1st appearance", "first app", "1st app",
        "origin of", "key issue", "iconic cover", "death of"
    ]
    for kw in generic_keywords:
        if kw in text:
            return True, f"Key Feature: {kw.capitalize()}"

    return False, None
