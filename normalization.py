"""Normalisation helpers: names, trip names, dates, money, file hashes."""
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

_TOTAL_WORDS = {"total", "totals", "grand total", "subtotal", "sub total"}


def is_total_label(s) -> bool:
    return re.sub(r"[^a-z ]", "", str(s).strip().lower()) in _TOTAL_WORDS


def norm_name(s) -> str:
    """Canonical driver key: ascii-fold, lowercase, strip punctuation, collapse
    spaces. '(MO)' is kept as the token 'mo' because it is part of how the
    AK report distinguishes those driver rows."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_variants(key: str) -> set:
    """Spelling variants for lookup in the (old-format) base map, which keeps
    punctuation such as '(mo)' and hyphens."""
    return {key, key.replace(" mo", " (mo)")}


def norm_trip(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()


def norm_trip_id(x) -> str:
    """'10671013', 10671013.0, ' 10671013 ' -> '10671013'. Empty if missing."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return "" if s.lower() in ("nan", "none", "-") else s


def parse_date(x):
    """Return a normalised Timestamp or NaT. Never raises. Years outside 2000-2100
    are rejected (pandas reads 'Oct 21,2026' as year 0001, so that format is
    parsed explicitly first)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return pd.NaT
    if isinstance(x, str):
        m = re.match(r"\s*([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,\s*(\d{4})\s*$", x)
        if m:
            d = pd.to_datetime(f"{m.group(1)} {m.group(2)} {m.group(3)}", errors="coerce")
            return d if (not pd.isna(d) and 2000 <= d.year <= 2100) else pd.NaT
    try:
        d = pd.to_datetime(x, errors="coerce")
    except Exception:
        return pd.NaT
    return d if (not pd.isna(d) and 2000 <= d.year <= 2100) else pd.NaT


def to_number(x):
    """Numeric value or NaN. '$1,234.50', '(12.00)' -> -12. Blank stays NaN
    (never silently 0)."""
    if x is None:
        return float("nan")
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s in ("", "-", "nan", "None"):
        return float("nan")
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        v = float(s)
    except ValueError:
        return float("nan")
    return -v if neg else v


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
