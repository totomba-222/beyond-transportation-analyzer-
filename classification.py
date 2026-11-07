"""State assignment. Precedence (highest first):
1 uploaded state-report evidence (overrides everything)  2 state hint of the main file (e.g. First Alaska)
3 BASE_DRIVER_STATE (editable)  4 Oregon school list  5 region keywords (whole-phrase)  6 Unassigned.
A driver found in two different state reports is NEEDS REVIEW, never guessed."""
import re
import pandas as pd
from config import ARIZONA_CITIES, STATE_NAMES, BASE_DRIVER_STATE, OR_SCHOOLS, REGION_KEYWORDS, STATE_FILE_HINTS, STATE_TOKEN_HINTS
from normalization import norm_name, norm_trip


def state_from_filename(name):
    base = re.sub(r"\.[^.]+$", "", str(name)).lower()
    toks = [t for t in re.split(r"[^a-z]+", base) if t]
    pairs = [a + b for a, b in zip(toks, toks[1:])]          # 'S_CA' -> 'sca', 'North CA' -> 'northca'
    for t in toks + pairs:
        if t in STATE_TOKEN_HINTS:
            return STATE_TOKEN_HINTS[t]
    compact = re.sub(r"[^a-z]", "", base)
    for kw, code in STATE_FILE_HINTS:
        if kw in compact:
            return code
    return None


def _phrase_hit(text, phrases):
    return any(re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", text) for p in phrases)


def region_hit(trip):
    t = norm_trip(trip)
    hits = [c for c, kws in REGION_KEYWORDS.items() if _phrase_hit(t, [norm_trip(k) for k in kws])]
    return hits[0] if len(hits) == 1 else None


def or_hit(trip):
    return _phrase_hit(norm_trip(trip), [norm_trip(k) for k in OR_SCHOOLS])


def base_map_normalised(extra=None):
    m = {norm_name(k): v for k, v in BASE_DRIVER_STATE.items()}
    m.update({norm_name(k): v for k, v in (extra or {}).items()})   # user-edited rows win
    return m


def driver_evidence(state_records: pd.DataFrame):
    """driver -> set(state codes) from uploaded state reports."""
    ev = {}
    for d, s in zip(state_records["driver"], state_records["state_hint"]):
        if d and s:
            ev.setdefault(d, set()).add(s)
    return ev


def classify(main: pd.DataFrame, state_records: pd.DataFrame, editable_map=None) -> pd.DataFrame:
    df = main.copy()
    ev = driver_evidence(state_records) if len(state_records) else {}
    base = base_map_normalised(editable_map)
    st, src = [], []
    for d, hint, trip in zip(df["driver"], df["state_hint"], df["trip_name"]):
        if d in ev and len(ev[d]) == 1:
            st.append(next(iter(ev[d]))); src.append("state report")
        elif d in ev:
            st.append("NEEDS REVIEW"); src.append("driver in several state reports: " + ",".join(sorted(ev[d])))
        elif hint:
            st.append(hint); src.append("main file hint")
        elif d in base:
            st.append(base[d]); src.append("driver map")
        elif or_hit(trip):
            st.append("OR"); src.append("Oregon school")
        elif region_hit(trip):
            st.append(region_hit(trip)); src.append("region keyword")
        else:
            st.append("Unassigned"); src.append("no evidence")
    df["state"], df["state_source"] = st, src
    return df


def region_label(state, trip):
    """Operational region: Arizona trips are reported under S.CA but labelled separately."""
    if state == "S.CA" and _phrase_hit(norm_trip(trip), ARIZONA_CITIES):
        return "Arizona (S.CA)"
    return STATE_NAMES.get(state, state)
