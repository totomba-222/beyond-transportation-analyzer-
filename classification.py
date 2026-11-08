"""State assignment. Precedence (highest first):
1 uploaded state-report evidence (overrides everything)  2 state hint of the main file (e.g. First Alaska)
3 BASE_DRIVER_STATE (editable)  4 Oregon school list  5 region keywords (whole-phrase)  6 Unassigned.
A driver found in two different state reports is NEEDS REVIEW, never guessed."""
import re
import pandas as pd
from config import LEARNED_DRIVER_STATE, ARIZONA_CITIES, STATE_NAMES, BASE_DRIVER_STATE, OR_SCHOOLS, REGION_KEYWORDS, STATE_FILE_HINTS, STATE_TOKEN_HINTS
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
    m = {norm_name(k): v for k, v in LEARNED_DRIVER_STATE.items()}      # learned from earlier state reports
    m.update({norm_name(k): v for k, v in BASE_DRIVER_STATE.items()})    # original map wins on conflict
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


def _school_stem(trip_key):
    """Route -> school: 'shaver es ib 01 er 110226 01' -> 'shaver es'; 'linc culler ms 04 pm' -> 'linc culler ms'."""
    toks = re.split(r"\b(?:ib|ob|am|pm)\b", str(trip_key))[0].split()
    while toks and re.fullmatch(r"\d+", toks[-1]): toks.pop()
    return " ".join(toks)


def _add_votes(votes, states, trip_keys):
    for s, k in zip(states, trip_keys):
        k = _school_stem(k)
        if k and s and s not in ("Unassigned", "NEEDS REVIEW"):
            votes.setdefault(k, {}); votes[k][s] = votes[k].get(s, 0) + 1


def route_votes(main_trusted, state_records=None):
    """school stem -> {state: trips}. Built-in table (from earlier weeks) + trusted trips of the current upload
    + trip names inside uploaded state reports."""
    from school_routes import SCHOOL_STATE
    votes = {k: dict(v) for k, v in SCHOOL_STATE.items()}
    _add_votes(votes, main_trusted.state, main_trusted.trip_key)
    if state_records is not None and len(state_records):
        sr = state_records[state_records.trip_key.ne("")]
        _add_votes(votes, sr.state_hint, sr.trip_key)
    return votes


def infer_state(trip_keys, votes, min_trips=3, min_share=0.8):
    """Driver-level inference from the distinct schools on his routes. Returns (state, share, n) or None."""
    tot = {}
    for k in {_school_stem(t) for t in trip_keys}:
        for s, n in votes.get(k, {}).items(): tot[s] = tot.get(s, 0) + n
    n = sum(tot.values())
    if n < min_trips: return None
    top = max(tot, key=tot.get)
    return (top, tot[top] / n, n) if tot[top] / n >= min_share else None


def classify(main: pd.DataFrame, state_records: pd.DataFrame, editable_map=None) -> pd.DataFrame:
    """1 uploaded state report  2 main-file hint  3 driver map (user edits > original > learned)  4 Oregon school list
    5 TRIP ROUTE (school -> state knowledge, drivers new to us)  6 whole-phrase region keywords  7 Unassigned."""
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
        else:
            st.append("Unassigned"); src.append("no evidence")
    df["state"], df["state_source"] = st, src
    # pass 2: new drivers -> state from the schools on their routes
    unk = df.state == "Unassigned"
    if unk.any():
        trusted = df[df.state_source.isin(["state report", "main file hint", "driver map", "Oregon school"])]
        votes = route_votes(trusted, state_records)
        for d, g in df[unk].groupby("driver"):
            r = infer_state(g.trip_key, votes)
            if r:
                df.loc[g.index, "state"] = r[0]
                df.loc[g.index, "state_source"] = f"trip route (auto: {r[1]:.0%} of {r[2]} known trips on the same schools) - verify"
    # pass 3: region keywords for what is still unknown
    for i in df.index[df.state == "Unassigned"]:
        rg = region_hit(df.at[i, "trip_name"])
        if rg: df.at[i, "state"], df.at[i, "state_source"] = rg, "region keyword"
    return df


def suggest_states(main: pd.DataFrame, state_records=None) -> pd.DataFrame:
    """Drivers still without a state: weak evidence is shown as a suggestion only (never applied automatically)."""
    un = main[main.state == "Unassigned"]
    cols = ["driver_key", "Driver", "Trips", "Revenue", "Example trip", "Suggested state", "Evidence"]
    if un.empty: return pd.DataFrame(columns=cols)
    known = main[~main.state.isin(["Unassigned", "NEEDS REVIEW"])]
    votes = route_votes(known, state_records); rows = []
    for d, g in un.groupby("driver"):
        tot = {}
        for k in {_school_stem(t) for t in g.trip_key}:
            for s, n in votes.get(k, {}).items(): tot[s] = tot.get(s, 0) + n
        top = max(tot, key=tot.get) if tot else None
        rows.append({"driver_key": d, "Driver": g.driver_disp.iloc[0], "Trips": len(g), "Revenue": g.main_amount.sum(), "Example trip": g.trip_name.iloc[0],
                     "Suggested state": top, "Evidence": f"same schools on known routes: {tot}" if tot else "no evidence - choose manually"})
    return pd.DataFrame(rows).sort_values("Revenue", ascending=False).reset_index(drop=True)
