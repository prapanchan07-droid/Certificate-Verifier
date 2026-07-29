import re

_SESSIONS = r"(APR|MAR|OCT|NOV|DEC|JAN|FEB)"

_BOARD_NOISE = [
    "STATE BOARD OF SCHOOL EXAMINATIONS",
    "DEPARTMENT OF GOVERNMENT EXAMINATIONS",
    "SECONDARY SCHOOL LEAVING CERTIFICATE",
    "HIGHER SECONDARY COURSE",
    "ISSUED UNDER THE AUTHORITY",
    "GOVERNMENT OF TAMILNADU",
    "GOVERNMENT OF TAMIL NADU",
    "PROVISIONAL CERTIFICATE",
    "X STANDARD",
]

_SCHOOL_KEYWORDS = [
    "GOVT", "GOVERNMENT", "HR SEC", "HIGH SCHOOL",
    "MATRICULATION", "AIDED", "SCHOOL", "COLLEGE",
    "GHSS", "GHNS", "MHSS",
]

_SENTENCE_WORDS = re.compile(
    r'\b(THE|AND|OF|FOR|IN|TO|WITH|IS|ARE|WAS|OBTAINED|FOLLOWING'
    r'|CERTIFIED|APPEARED|MARKS|SUBJECT|PRACTICAL|THEORY|PASS|FAIL'
    r'|ABOVE|MENTIONED|SECONDARY|LEAVING|CERTIFICATE|PUBLIC|EXAMINATION'
    r'|ISSUED|UNDER|AUTHORITY|DEPARTMENT|GOVERNMENT|TAMILNADU|SESSION'
    r'|FATHER|FATHERS|GUARDIAN|GUARDIANS|MOTHER|MOTHERS|NAME)\b'
)

# Short OCR noise tokens seen bleeding in before the real name text
# (column-border/watermark bleed-through, e.g. "IS VARSHINI G" or
# "XI வர்ஷினி..."). Stripped rather than used to reject the whole
# candidate, since rejecting on them throws away the real name too.
_NOISE_PREFIXES = {"IS", "AL", "XI", "PE", "KJ", "BH", "BP", "SS", "PY", "RY", "OY", "IT", "AY"}


def _strip_noise_prefix(text: str) -> str:
    words = text.split()
    if len(words) >= 2 and words[0] in _NOISE_PREFIXES:
        return " ".join(words[1:])
    return text


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 3 or len(text) > 60:
        return False
    if not _is_english(text):
        return False
    if _SENTENCE_WORDS.search(text):
        return False
    if not re.match(r'^[A-Z][A-Z\s\.]+$', text):
        return False
    words = [w for w in text.split() if w]
    if len(words) < 2:
        return False
    if any(len(w) > 20 for w in words):
        return False
    if not any(len(w) >= 3 for w in words):
        return False
    return True


def _validate_name(text: str):
    """Try the text as-is, then retry after stripping a leading noise
    token, before giving up."""
    text = text.strip()
    if _looks_like_name(text):
        return text
    stripped = _strip_noise_prefix(text)
    if stripped != text and _looks_like_name(stripped):
        return stripped
    return None


def _is_english(text: str) -> bool:
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.7


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 3 or len(text) > 60:
        return False
    if not _is_english(text):
        return False
    if _SENTENCE_WORDS.search(text):
        return False
    if not re.match(r'^[A-Z][A-Z\s\.]+$', text):
        return False
    words = [w for w in text.split() if w]
    if len(words) < 2:
        return False
    if any(len(w) > 20 for w in words):
        return False
    if not any(len(w) >= 3 for w in words):   # NEW — rejects noise like "XI A"
        return False
    return True