import re
from typing import Tuple, Optional, List

KEY_ISSUE_PATTERNS: List[Tuple[str, str]] = [
    (r"(?:amazing\s+)?spider\s*man.*?\b300\b", "1st full appearance of Venom"),
    (r"(?:amazing\s+)?spider\s*man.*?\b361\b", "1st appearance of Carnage"),
    (r"(?:marvel\s+super\s+heroes\s+)?secret\s+wars.*?\b8\b", "1st appearance of Alien Symbiote Black Suit"),
    (r"(?:incredible\s+)?hulk.*?\b181\b", "1st full appearance of Wolverine"),
    (r"batman.*?\b608\b", "Iconic Jim Lee Hush cover / arc"),
    (r"batman.*?\b101\b", "1st appearance of Grifter in main DCU"),
    (r"batman.*?\b423\b", "Iconic Todd McFarlane Cover"),
    (r"batman.*?\b227\b", "Iconic Neal Adams Cover"),
    (r"giant\s*size\s*x\s*men.*?\b1\b", "1st appearance of Storm, Nightcrawler, Colossus"),
    (r"amazing\s+fantasy.*?\b15\b", "1st appearance of Spider-Man"),
    (r"tales\s+of\s+suspense.*?\b39\b", "1st appearance of Iron Man"),
    (r"werewolf\s+by\s+night.*?\b32\b", "1st appearance of Moon Knight"),
    (r"hero\s+for\s+hire.*?\b1\b", "1st appearance of Luke Cage"),
    (r"thor.*?\b337\b", "1st appearance of Beta Ray Bill"),
    (r"(?:uncanny\s+)?x\s*men.*?\b266\b", "1st appearance of Gambit"),
    (r"(?:uncanny\s+)?x\s*men.*?\b141\b", "Days of Future Past"),
    (r"star\s+wars.*?\b42\b", "1st appearance of Boba Fett"),
    (r"star\s+wars.*?\b1\b", "1st appearance of Darth Vader in Comics"),
    (r"action\s+comics.*?\b1\b", "1st appearance of Superman"),
    (r"detective\s+comics.*?\b27\b", "1st appearance of Batman"),
    (r"x\s*force.*?\b15\b", "1st appearance of Cable / Shatterstar"),
    (r"x\s*force.*?\b11\b", "1st real appearance of Domino"),
    (r"new\s+mutants.*?\b98\b", "1st appearance of Deadpool"),
]


def normalize_key_text(text: Optional[str]) -> str:
    """
    Strips volume info, leading 'The', punctuation, and extra whitespace
    to ensure robust key issue matching regardless of formatting.
    """
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r",?\s*vol\.?\s*\d+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^the\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[/:,#\"'\-\.]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_key_issue(title: str, notes: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Evaluates item title and notes against known key issue patterns after string normalization.
    Returns (is_key_issue, key_reasons).
    """
    raw_text = f"{title or ''} {notes or ''}"
    norm_text = f"{normalize_key_text(title)} {normalize_key_text(notes)}"

    # Match against normalized text first
    for pattern, reason in KEY_ISSUE_PATTERNS:
        if re.search(pattern, norm_text, flags=re.IGNORECASE) or re.search(pattern, raw_text, flags=re.IGNORECASE):
            return True, reason

    # Order from longest to shortest to ensure specific key phrases take precedence
    generic_keywords = [
        "first appearance", "1st appearance", "first app", "1st app",
        "origin of", "key issue", "iconic cover", "death of"
    ]
    for kw in generic_keywords:
        if kw in norm_text or kw in raw_text.lower():
            return True, f"Key Feature: {kw.capitalize()}"

    return False, None
