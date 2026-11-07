"""Trip-level reconciliation: main report (First/EverDriven) vs state reports.
Match tiers (each main row and state row used at most once):
 T1 trip id | T2 driver+date+trip | T3 driver+date+miles | T4 driver+trip (order) | T5 driver+miles (order)
 T6 driver+revenue (order) | T7 driver only (order, LOW -> manual review).
Fuzzy driver names are used only for rows left over and are always NEEDS MANUAL REVIEW."""
import numpy as np
import pandas as pd
from config import DEFAULT_SETTINGS
from normalization import name_similarity

TIERS = [
    ("T1 trip id", "HIGH", lambda r: r.trip_id or None),
    ("T2 driver+date+trip", "HIGH", lambda r: (r.driver, r.date, r.trip_key) if pd.notna(r.date) and r.trip_key else None),
    ("T3 driver+date+miles", "MEDIUM-HIGH", lambda r: (r.driver, r.date, round(r.miles)) if pd.notna(r.date) and pd.notna(r.miles) else None),
    ("T4 driver+trip (sequence)", "MEDIUM", lambda r: (r.driver, r.trip_key) if r.trip_key and pd.isna(r.date) else None),
    ("T5 driver+miles (sequence)", "MEDIUM", lambda r: (r.driver, round(r.miles)) if pd.notna(r.miles) and pd.isna(r.date) else None),
    ("T6 driver+amount (sequence)", "MEDIUM", None),   # special: amount differs per side
    ("T7 driver only (sequence)", "LOW", lambda r: r.driver or None),
]


def _pair(main, st, tier, mi, si, pairs, side_main, side_state):
    name, conf, _ = tier
    gm, gs = {}, {}
    for i in mi:
        k = side_main(main.loc[i]);  gm.setdefault(k, []).append(i) if k is not None else None
    for j in si:
        k = side_state(st.loc[j]);   gs.setdefault(k, []).append(j) if k is not None else None
    used_m, used_s = set(), set()
    for k, ml in gm.items():
        for a, b in zip(ml, gs.get(k, [])):
            ta, tb = main.at[a, "trip_id"], st.at[b, "trip_id"]
            if ta and tb and ta != tb:      # conflicting trip ids: never merge on weaker keys
                continue
            pairs.append((a, b, name, conf)); used_m.add(a); used_s.add(b)
    return [i for i in mi if i not in used_m], [j for j in si if j not in used_s]


def reconcile(main: pd.DataFrame, state: pd.DataFrame, settings=None) -> pd.DataFrame:
    S = {**DEFAULT_SETTINGS, **(settings or {})}
    main = main.reset_index(drop=True).copy(); st = state.reset_index(drop=True).copy()
    st_has_date = st["date"].notna().any()
    # duplicate trip ids inside the main set
    dup_main = set(main.index[main.trip_id.ne("") & main.duplicated("trip_id", keep="first") & main.trip_id.ne("")])
    mi, si, pairs = [i for i in main.index if i not in dup_main], list(st.index), []
    main_drivers = set(main.driver)
    for tier in TIERS:
        name, conf, fn = tier
        if tier[0].startswith("T6"):
            sm = lambda r: (r.driver, round(r.main_amount, 2)) if pd.notna(r.main_amount) else None
            ss = lambda r: (r.driver, round(r.revenue, 2)) if pd.notna(r.revenue) else None
        elif name.startswith("T7"):
            sm = fn
            ss = lambda r: (r.driver or None) if pd.notna(r.revenue) else None   # rows with no revenue never steal a match
        else:
            sm = ss = fn
        # a state report is only matched on keys it actually contains
        mi, si = _pair(main, st, tier, mi, si, pairs, sm, ss)
    rows = []
    def base(m=None, s=None):
        return {"provider": (m.provider if m is not None else ""), "state": (m.state if m is not None else (s.state_hint if s is not None else None)),
                "driver": (m.driver_disp if m is not None else s.driver_disp),
                "main_trip_id": m.trip_id if m is not None else "", "state_trip_id": s.trip_id if s is not None else "",
                "date": (m.date if m is not None else s.date), "trip_name": (m.trip_name if m is not None else s.trip_name),
                "main_miles": m.miles if m is not None else np.nan, "state_miles": s.miles if s is not None else np.nan,
                "main_revenue": m.main_amount if m is not None else np.nan,
                "state_revenue": s.revenue if s is not None else np.nan, "driver_payment": s.driver_pay if s is not None else np.nan,
                "main_source": f"{m.src_file}#{m.src_sheet}!{m.src_row}" if m is not None else "",
                "state_source": f"{s.src_file}#{s.src_sheet}!{s.src_row}" if s is not None else "",
                "main_flags": m["flags"] if m is not None else "", "state_flags": s["flags"] if s is not None else ""}
    for a, b, tname, conf in pairs:
        m, s = main.loc[a], st.loc[b]
        r = base(m, s); r.update(match_tier=tname, confidence=conf)
        rd = m.main_amount - s.revenue if pd.notna(m.main_amount) and pd.notna(s.revenue) else np.nan
        r["revenue_difference"] = rd
        r["profit"] = s.revenue - s.driver_pay if pd.notna(s.revenue) and pd.notna(s.driver_pay) else np.nan
        r["margin_pct"] = r["profit"] / s.revenue * 100 if pd.notna(r["profit"]) and s.revenue else np.nan
        note = []
        if pd.isna(s.revenue): status = "NEEDS MANUAL REVIEW"; note.append("state revenue missing")
        elif pd.isna(m.main_amount): status = "NEEDS MANUAL REVIEW"; note.append("main amount missing")
        elif abs(rd) > S["revenue_tolerance"]: status = "REVENUE MISMATCH"
        elif pd.notna(m.miles) and pd.notna(s.miles) and abs(m.miles - s.miles) > S["mileage_tolerance"]: status = "MILEAGE MISMATCH"
        elif pd.notna(s.driver_pay) and pd.notna(s.revenue) and s.driver_pay > s.revenue + S["payment_tolerance"]:
            status = "PAYMENT MISMATCH"; note.append("driver payment exceeds state revenue")
        elif pd.isna(s.driver_pay): status = "NEEDS MANUAL REVIEW"; note.append("driver payment missing")
        elif conf == "LOW": status = "NEEDS MANUAL REVIEW"; note.append("low-confidence match")
        else: status = "EXACT MATCH" if conf == "HIGH" else "MATCHED"
        r["audit_status"], r["notes"] = status, "; ".join(note); rows.append(r)
    # leftovers
    for j in si:
        s = st.loc[j]; r = base(None, s); r["match_tier"], r["confidence"] = "", ""
        if s.driver not in main_drivers:
            cand = max(((name_similarity(s.driver, d), d) for d in main_drivers), default=(0, ""))
            r["audit_status"] = "NEEDS MANUAL REVIEW" if cand[0] >= S["fuzzy_name_cutoff"] else "UNMATCHED DRIVER"
            r["notes"] = f"possible same driver as '{cand[1]}' ({cand[0]:.2f})" if cand[0] >= S["fuzzy_name_cutoff"] else "driver not in main report"
        else:
            r["audit_status"], r["notes"] = "MISSING FROM MAIN REPORT", "no main trip matched"
        r["profit"] = s.revenue - s.driver_pay if pd.notna(s.revenue) and pd.notna(s.driver_pay) else np.nan
        r["revenue_difference"] = np.nan; r["margin_pct"] = np.nan
        rows.append(r)
    for i in mi:
        m = main.loc[i]; r = base(m, None); r["match_tier"], r["confidence"] = "", ""
        r["audit_status"], r["notes"] = "MISSING FROM STATE REPORT", "no state trip matched"
        r["revenue_difference"] = r["profit"] = r["margin_pct"] = np.nan; rows.append(r)
    for i in dup_main:
        r = base(main.loc[i], None); r["match_tier"], r["confidence"] = "", ""
        r["audit_status"], r["notes"] = "DUPLICATE TRIP", "same trip id appears more than once in main reports"
        r["revenue_difference"] = r["profit"] = r["margin_pct"] = np.nan; rows.append(r)
    return pd.DataFrame(rows)


def reconcile_all(main, state_records, settings=None):
    """Main rows are reconciled against the state report of THEIR state; states
    with no uploaded report are marked STATE REPORT NOT UPLOADED (not an error)."""
    out, covered = [], set(state_records["state_hint"].dropna().unique())
    for code in sorted(covered):
        out.append(reconcile(main[main.state == code], state_records[state_records.state_hint == code], settings))
    pending = main[~main.state.isin(covered)]
    if len(pending):
        p = pd.DataFrame({"state": pending.state, "driver": pending.driver_disp, "main_trip_id": pending.trip_id, "date": pending.date,
                          "trip_name": pending.trip_name, "main_miles": pending.miles, "main_revenue": pending.main_amount,
                          "main_source": pending.src_file + "#" + pending.src_sheet + "!" + pending.src_row.astype(str),
                          "audit_status": "STATE REPORT NOT UPLOADED", "main_flags": pending["flags"]})
        p["provider"] = pending.provider; out.append(p)
    df = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return ensure_columns(df)


REC_COLS = ["provider", "state", "driver", "main_trip_id", "state_trip_id", "date", "trip_name", "main_miles", "state_miles", "main_revenue",
            "state_revenue", "driver_payment", "main_source", "state_source", "main_flags", "state_flags", "match_tier", "confidence",
            "revenue_difference", "profit", "margin_pct", "audit_status", "notes"]
_TXT = {"provider", "main_trip_id", "state_trip_id", "main_source", "state_source", "main_flags", "state_flags", "match_tier", "confidence", "notes", "driver", "trip_name"}


def ensure_columns(df):
    """Same schema whether or not state reports were uploaded (missing numbers stay NaN, never 0)."""
    for c in REC_COLS:
        if c not in df.columns:
            df[c] = "" if c in _TXT else (pd.NaT if c == "date" else np.nan)
    return df[REC_COLS + [c for c in df.columns if c not in REC_COLS]]
