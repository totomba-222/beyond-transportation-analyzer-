"""Weekly history: one compact row per (week, month, state) so weekly / monthly comparisons work across separate uploads.
The app lets the user download the history CSV and upload it again next week (no driver-level data is kept in it).
Profit and margin exist only for states that had an uploaded state report; the comparison says so."""
import numpy as np
import pandas as pd
import financial_calculations as F

COLS = ["week_start", "month", "state", "trips", "drivers", "miles", "revenue", "state_revenue", "driver_payments", "profit", "profit_base",
        "paid_trips", "first_date", "last_date"]


def _ws(d): return d.dt.normalize() - pd.to_timedelta(d.dt.weekday, unit="D")


def weekly_rows(rec):
    r = rec.copy(); d = r.date
    ws, mo = _ws(d), d.dt.to_period("M").astype(str)
    gm = (ws.mode().iloc[0], mo.mode().iloc[0]) if d.notna().any() else (None, None)
    for st in r.state.dropna().unique():                       # undated rows (state-only rows) belong to the state's own week
        m = (r.state == st) & d.isna(); dd = d[(r.state == st) & d.notna()]
        if m.any():
            w0 = _ws(dd).mode().iloc[0] if len(dd) else gm[0]; m0 = dd.dt.to_period("M").astype(str).mode().iloc[0] if len(dd) else gm[1]
            ws[m], mo[m] = w0, m0
    r["_ws"], r["_mo"] = ws, mo; r = r[r._ws.notna()]
    rows = []
    for (w, m, st), g in r.groupby(["_ws", "_mo", "state"]):
        k = F.kpis(g); pr = g[g.profit.notna()] if "profit" in g else g.iloc[0:0]
        dd = g.date.dropna()
        pt = g.driver_payment.notna() & (g.audit_status != "MONITOR PAYMENT") if "audit_status" in g else g.driver_payment.notna()
        rows.append({"week_start": w, "month": m, "state": st, "trips": k["Trips"], "drivers": k["Drivers"], "miles": k["Miles"], "revenue": k["Revenue"],
                     "state_revenue": k["State Revenue"], "driver_payments": k["Driver Payments"], "profit": k["Profit"],
                     "profit_base": pr.state_revenue.sum(min_count=1) if len(pr) else np.nan, "paid_trips": int(pt.sum()),
                     "first_date": dd.min() if len(dd) else pd.NaT, "last_date": dd.max() if len(dd) else pd.NaT})
    return pd.DataFrame(rows, columns=COLS)


def to_csv(h): return h.sort_values(["week_start", "state"]).to_csv(index=False)


def from_csv(f):
    h = pd.read_csv(f)
    for c in ("week_start", "first_date", "last_date"): h[c] = pd.to_datetime(h[c], errors="coerce")
    return h[COLS]


def merge(prev, cur):
    """History + this session's rows; the same (week, month, state) is replaced by the fresher current value."""
    if prev is None or prev.empty: return cur.copy()
    k = ["week_start", "month", "state"]
    keep = prev.merge(cur[k].drop_duplicates(), on=k, how="left", indicator=True); keep = keep[keep._merge == "left_only"].drop(columns="_merge")
    return pd.concat([keep, cur], ignore_index=True).sort_values(k).reset_index(drop=True)


# ------------------------------------------------------------------ aggregation helpers
def _agg(h):
    pr = h.profit.sum(min_count=1)
    d = {"Trips": h.trips.sum(), "Drivers": h.drivers.sum(), "Miles": h.miles.sum(min_count=1), "Revenue": h.revenue.sum(min_count=1),
         "Driver Payments": h.driver_payments.sum(min_count=1), "Profit": pr,
         "Margin %": pr / h.profit_base.sum(min_count=1) * 100 if pd.notna(pr) and h.profit_base.sum(min_count=1) else np.nan}
    d["Avg revenue/trip"] = d["Revenue"] / d["Trips"] if d["Trips"] else np.nan
    return d


KPIS = ["Trips", "Drivers", "Miles", "Revenue", "Driver Payments", "Profit", "Margin %", "Avg revenue/trip"]


def _cmp(a, b, lab_a, lab_b):
    rows = []
    for k in KPIS:
        x, y = a.get(k, np.nan), b.get(k, np.nan); diff = x - y if pd.notna(x) and pd.notna(y) else np.nan
        rows.append({"KPI": k, lab_a: x, lab_b: y, "Difference": diff, "Change %": diff / abs(y) * 100 if pd.notna(diff) and y else np.nan})
    return pd.DataFrame(rows)


def weeks(h): return sorted(h.week_start.dropna().unique())


def week_info(h, w):
    s = h[h.week_start == w]
    if s.empty: return {"start": pd.Timestamp(w), "end": pd.Timestamp(w) + pd.Timedelta(days=6), "first": None, "last": None, "days": 0, "states": 0, "profit_states": 0}
    f, l = s.first_date.min(), s.last_date.max()
    return {"start": pd.Timestamp(w), "end": pd.Timestamp(w) + pd.Timedelta(days=6), "first": f, "last": l, "days": (l - f).days + 1 if pd.notna(f) else 0,
            "states": s.state.nunique(), "profit_states": s[s.profit.notna()].state.nunique(), "trips": int(s.trips.sum())}


def weekly_compare(h, week=None, by=None):
    ws = weeks(h)
    if not ws: return None, None, None, ["No dated trips in the history."]
    cur = pd.Timestamp(week) if week is not None else ws[-1]; prev = cur - pd.Timedelta(days=7)
    c, p = h[h.week_start == cur], h[h.week_start == prev]
    ci, pi = week_info(h, cur), week_info(h, prev); warns = []
    if p.empty: warns.append(f"No data for the previous week ({prev:%Y-%m-%d} to {prev + pd.Timedelta(days=6):%Y-%m-%d}) - upload last week's history CSV.")
    for nm, i in (("Current", ci), ("Previous", pi)):
        if i["days"] and i["days"] < 5: warns.append(f"{nm} week {i['start']:%Y-%m-%d} to {i['end']:%Y-%m-%d} looks incomplete: trips span only {i['days']} day(s) ({i['trips']} trips).")
    if not p.empty and ci["profit_states"] != pi["profit_states"]:
        warns.append(f"Profit/margin cover {ci['profit_states']} state(s) this week vs {pi['profit_states']} last week (states with an uploaded state report) - compare profit state by state.")
    if by is None: return _cmp(_agg(c), _agg(p) if not p.empty else {}, "Current week", "Previous week"), ci, pi, warns
    out = []
    for st in sorted(set(c.state) | set(p.state)):
        t = _cmp(_agg(c[c.state == st]) if (c.state == st).any() else {}, _agg(p[p.state == st]) if (p.state == st).any() else {}, "Current week", "Previous week"); t.insert(0, "State", st); out.append(t)
    return pd.concat(out, ignore_index=True), ci, pi, warns


def monthly_table(h, by=None):
    rows = []
    for key, g in h.groupby(["month"] + ([by] if by else [])):
        key = key if isinstance(key, tuple) else (key,); m = key[0]; wk = g.groupby("week_start").drivers.sum()
        a = _agg(g); a["Drivers"] = wk.mean() if len(wk) else np.nan                  # avg weekly drivers (distinct monthly drivers are not kept in the history)
        pt = g.paid_trips.sum(); a["Avg cost/trip"] = g.driver_payments.sum(min_count=1) / pt if pt else np.nan
        rows.append({"Month": m, **({by: key[1]} if by else {}), "Weeks": g.week_start.nunique(), **{("Avg weekly drivers" if k == "Drivers" else k): v for k, v in a.items()}, "Avg cost/trip": a["Avg cost/trip"]})
    t = pd.DataFrame(rows)
    if t.empty: return t
    t = t.sort_values(["Month"] + ([by] if by else [])).reset_index(drop=True)
    for c in ("Revenue", "Trips", "Profit"): t[f"{c} MoM %"] = (t.groupby(by)[c] if by else t[c]).pct_change(fill_method=None) * 100
    return t


def monthly_compare(h, m1, m2):
    out = []
    for m in (m1, m2):
        g = h[h.month == m]; a = _agg(g); a["Drivers"] = g.groupby("week_start").drivers.sum().mean() if len(g) else np.nan; out.append(a)
    t = _cmp(out[1], out[0], m2, m1)[["KPI", m1, m2, "Difference", "Change %"]]
    t.loc[t.KPI == "Drivers", "KPI"] = "Avg weekly drivers"
    return t, [f"{m}: only {h[h.month == m].week_start.nunique()} week(s) of data - partial month." for m in (m1, m2) if h[h.month == m].week_start.nunique() < 4]


def like_for_like(a, b, lab_a="Current", lab_b="Previous"):
    """Compare only the states that have profit (an uploaded state report) in BOTH periods, so payments / profit are comparable."""
    sa, sb = set(a[a.profit.notna()].state), set(b[b.profit.notna()].state); both = sorted(sa & sb)
    if not both: return None, []
    return _cmp(_agg(a[a.state.isin(both)]), _agg(b[b.state.isin(both)]), lab_a, lab_b), both


def weekly_like_for_like(h, week):
    cur = pd.Timestamp(week); return like_for_like(h[h.week_start == cur], h[h.week_start == cur - pd.Timedelta(days=7)], "Current week", "Previous week")


def _state_table(a, b, la, lb):
    rows = []
    for st in sorted(set(a.state) | set(b.state)):
        x = _agg(a[a.state == st]) if (a.state == st).any() else {}; y = _agg(b[b.state == st]) if (b.state == st).any() else {}
        g = lambda d, k: d.get(k, np.nan)
        pct = lambda u, v: (u - v) / abs(v) * 100 if pd.notna(u) and pd.notna(v) and v else np.nan
        rows.append({"State": st, f"Trips {la}": g(x, "Trips"), f"Trips {lb}": g(y, "Trips"), "Trips %": pct(g(x, "Trips"), g(y, "Trips")),
                     f"Revenue {la}": g(x, "Revenue"), f"Revenue {lb}": g(y, "Revenue"), "Revenue %": pct(g(x, "Revenue"), g(y, "Revenue")),
                     f"Profit {la}": g(x, "Profit"), f"Profit {lb}": g(y, "Profit"), f"Margin % {la}": g(x, "Margin %"), f"Margin % {lb}": g(y, "Margin %")})
    return pd.DataFrame(rows)


def weekly_state_summary(h, week):
    cur = pd.Timestamp(week); return _state_table(h[h.week_start == cur], h[h.week_start == cur - pd.Timedelta(days=7)], "current", "previous")


def monthly_state_summary(h, m1, m2): return _state_table(h[h.month == m2], h[h.month == m1], m2, m1)


def fmt_table(t, value_cols):
    """KPI table as strings: each KPI row formatted by its own unit (counts, USD, miles, %)."""
    usd = lambda v: f"(${abs(v):,.2f})" if v < -0.004 else f"${v:,.2f}"
    def f(k, v, diff=False):
        if pd.isna(v): return "n/a"
        if k in ("Revenue", "Driver Payments", "Profit", "Avg revenue/trip", "Avg cost/trip"): return usd(v)
        if k == "Margin %": return f"{v:+.1f} pts" if diff else f"{v:.1f}%"
        if k == "Miles": return f"{v:,.1f}"
        return f"{v:,.0f}"
    o = t.copy().astype(object)
    for i in o.index:
        for c in value_cols: o.at[i, c] = f(t.at[i, "KPI"], t.at[i, c], diff=(c == "Difference"))
        if "Change %" in o.columns: o.at[i, "Change %"] = "n/a" if pd.isna(t.at[i, "Change %"]) else f"{t.at[i, 'Change %']:+.1f}%"
    return o
