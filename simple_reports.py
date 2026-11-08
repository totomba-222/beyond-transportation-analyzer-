"""Simple 3-stage reports built on the tested engine (no new matching logic)."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import STATE_NAMES

OK = ["EXACT MATCH", "MATCHED", "STATE REPORT NOT UPLOADED", "MONITOR PAYMENT"]


def _nm(c): return STATE_NAMES.get(c, c)


def first_overview(main, adjustments=None):
    o = {"Trips": len(main), "Revenue": main.main_amount.sum(min_count=1), "Drivers": main.driver.nunique(),
         "Miles": main.miles.sum(min_count=1), "States": main.state.nunique()}
    if adjustments is not None and len(adjustments):          # non-trip adjustments (e.g. EverDriven drug test)
        o["Adjustments"] = adjustments.Amount.sum(); o["Net revenue"] = o["Revenue"] + o["Adjustments"]
    return o


def first_state_table(main):
    g = main.groupby("state").agg(Trips=("main_amount", "size"), Drivers=("driver", "nunique"), Miles=("miles", "sum"),
                                  Revenue=("main_amount", lambda s: s.sum(min_count=1))).reset_index()
    g["State"] = g.state.map(_nm); g["Revenue/Trip"] = g.Revenue / g.Trips
    g["Trips %"] = g.Trips / g.Trips.sum() * 100; g["Revenue %"] = g.Revenue / g.Revenue.sum() * 100
    g = g.sort_values("Revenue", ascending=False)[["State", "Trips", "Drivers", "Miles", "Revenue", "Revenue/Trip", "Trips %", "Revenue %"]]
    t = {"State": "TOTAL", "Trips": int(g.Trips.sum()), "Drivers": main.driver.nunique(), "Miles": g.Miles.sum(), "Revenue": g.Revenue.sum(),
         "Revenue/Trip": g.Revenue.sum() / g.Trips.sum(), "Trips %": 100.0, "Revenue %": 100.0}
    return pd.concat([g, pd.DataFrame([t])], ignore_index=True)


def first_state_detail(main, code):
    d = main[main.state == code].sort_values(["driver", "date"])
    out = d[["provider", "date", "driver_disp", "trip_id", "trip_name", "miles", "main_amount", "flags", "src_file", "src_row"]].copy()
    out["provider"] = out.provider.map(PROVIDER_NAMES).fillna(out.provider)
    out.columns = ["Provider", "Date", "Driver", "Trip ID", "Trip Name", "Miles", "Revenue (trip price paid)", "Data flags", "Source file", "Source row"]
    return out


def state_financials(rec):
    """Only states with an uploaded state report. Trips exclude monitor (MO) rows; monitor payments are costs
    (included in Driver Payments and Profit) with no revenue of their own."""
    r = rec[rec.state_source != ""]; rows = []
    def line(label, g):
        mon, trips = g[g.audit_status == "MONITOR PAYMENT"], g[g.audit_status != "MONITOR PAYMENT"]
        pr = g[g.profit.notna()]; profit = pr.profit.sum() if len(pr) else np.nan; den = pr.state_revenue.sum(min_count=1)
        return {"State": label, "Trips": len(trips), "Drivers": trips.driver.str.lower().nunique(), "Revenue": g.state_revenue.sum(min_count=1),
                "Driver Payments": g.driver_payment.sum(min_count=1), "Monitor payments": mon.driver_payment.sum(),
                "Profit": profit, "Margin %": profit / den * 100 if len(pr) and den else np.nan,
                "Trips missing revenue": int(trips.state_revenue.isna().sum())}
    for code, g in r.groupby("state"): rows.append(line(_nm(code), g))
    t = pd.DataFrame(rows).sort_values("Revenue", ascending=False)
    if len(t): t = pd.concat([t, pd.DataFrame([line("TOTAL", r)])], ignore_index=True)
    return t


def state_trip_detail(rec, code):
    d = rec[(rec.state == code) & (rec.state_source != "")].sort_values(["driver", "date"])
    out = d[["date", "driver", "trip_name", "main_miles", "main_revenue", "state_revenue", "driver_payment", "profit", "margin_pct", "audit_status", "state_source"]].copy()
    out.columns = ["Date", "Driver", "Trip Name", "Miles", "First Revenue", "State Revenue", "Driver Payment", "Profit", "Margin %", "Status", "State source"]
    return out


def discrepancy_summary(rec):
    r = rec[rec.state_source.ne("") | rec.main_source.ne("")]; rows = []
    for code, g in r[r.audit_status != "STATE REPORT NOT UPLOADED"].groupby("state"):
        d = g[g.audit_status == "REVENUE MISMATCH"]; ms = g[g.audit_status == "MISSING FROM STATE REPORT"]
        mm = g[g.audit_status.isin(["MISSING FROM MAIN REPORT", "UNMATCHED DRIVER"])]
        rows.append({"State": _nm(code), "Trips with price difference": len(d), "Total difference (First - State)": d.revenue_difference.sum(),
                     "Trips in First but not in state report": len(ms), "Their First revenue": ms.main_revenue.sum(),
                     "Trips in state report but not in First": len(mm), "Their state revenue": mm.state_revenue.sum(min_count=1),
                     "Trips with missing state revenue": int(mm.state_revenue.isna().sum()),
                     "Their driver payments": mm.driver_payment.sum(min_count=1), "Their miles": mm.state_miles.sum(min_count=1),
                     "Monitor payments (no trip revenue)": g[g.audit_status == "MONITOR PAYMENT"].driver_payment.sum()})
    t = pd.DataFrame(rows)
    if len(t):
        s = t.drop(columns="State").sum(min_count=1); s["State"] = "TOTAL"; t = pd.concat([t, pd.DataFrame([s])], ignore_index=True)
    return t


def discrepancy_detail(rec, code):
    d = rec[(rec.state == code) & rec.audit_status.isin(["REVENUE MISMATCH", "MISSING FROM STATE REPORT", "MISSING FROM MAIN REPORT", "UNMATCHED DRIVER"])]
    out = d.sort_values(["audit_status", "driver", "date"])[["audit_status", "date", "driver", "trip_name", "main_revenue", "state_revenue", "revenue_difference", "notes", "main_source", "state_source"]].copy()
    out.columns = ["Type", "Date", "Driver", "Trip Name", "First Revenue", "State Revenue", "Difference (First - State)", "Notes", "First source", "State source"]
    return out


def share_figure(t, cols=("Trips", "Revenue", "Profit")):
    """Pie charts of each column's share by state (t = a state table; TOTAL row ignored)."""
    t = t[t.State != "TOTAL"]
    fig, axs = plt.subplots(1, len(cols), figsize=(4.3 * len(cols), 4.2))
    for ax, col in zip(np.atleast_1d(axs), cols):
        d = t[t[col] > 0]
        if d.empty: ax.axis("off"); continue
        ax.pie(d[col], labels=d.State, autopct="%1.1f%%", textprops={"fontsize": 7}, startangle=90); ax.set_title(f"{col} share by state", fontsize=10)
    plt.tight_layout(); return fig


def _with_total(df, label_col, sums):
    if df.empty: return df
    row = {c: "" for c in df.columns}; row[label_col] = "TOTAL"
    for c in sums: row[c] = df[c].sum(min_count=1)
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def discrepancy_sections(rec, code):
    """(price differences, in state report but not in First, in First but not in state report) - each with a TOTAL row."""
    g = rec[rec.state == code]
    a = g[g.audit_status == "REVENUE MISMATCH"].sort_values(["driver", "date"])[["date", "driver", "trip_name", "main_miles", "main_revenue", "state_revenue", "revenue_difference"]]
    a.columns = ["Date", "Driver", "Trip Name", "Miles", "First Revenue", "State Revenue", "Difference (First - State)"]
    s = g[g.audit_status.isin(["MISSING FROM MAIN REPORT", "UNMATCHED DRIVER"])].sort_values(["driver"])[["driver", "state_miles", "state_revenue", "driver_payment", "notes"]]
    s.columns = ["Driver", "Miles", "State Revenue", "Driver Payment", "Notes"]
    f = g[g.audit_status == "MISSING FROM STATE REPORT"].sort_values(["driver", "date"])[["date", "driver", "trip_name", "main_miles", "main_revenue"]]
    f.columns = ["Date", "Driver", "Trip Name", "Miles", "First Revenue"]
    return (_with_total(a, "Driver", ["Miles", "First Revenue", "State Revenue", "Difference (First - State)"]),
            _with_total(s, "Driver", ["Miles", "State Revenue", "Driver Payment"]),
            _with_total(f, "Driver", ["Miles", "First Revenue"]))


def price_diff_grouped(rec, code):
    """One row per (official state price, price First paid): trips, difference per trip, total difference."""
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if g.empty: return pd.DataFrame()
    t = g.groupby(["state_revenue", "main_revenue"]).agg(Trips=("revenue_difference", "size"), Total=("revenue_difference", "sum")).reset_index()
    t["Diff"] = t.main_revenue - t.state_revenue
    t = t.rename(columns={"state_revenue": "Official price (state report)", "main_revenue": "Price paid by First", "Diff": "Difference per trip", "Total": "Total difference"})
    t = t[["Trips", "Official price (state report)", "Price paid by First", "Difference per trip", "Total difference"]]
    return _with_total(t, "Trips", ["Total difference"]).assign(Trips=lambda d: d.Trips).pipe(lambda d: d.assign(Trips=d.Trips.where(d.Trips != "TOTAL", int(t.Trips.sum()))))


def price_diff_by_driver(rec, code):
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if g.empty: return pd.DataFrame()
    t = g.groupby("driver").agg(Trips=("revenue_difference", "size"), Miles=("main_miles", "sum"), Total=("revenue_difference", "sum")).reset_index()
    t.columns = ["Driver", "Trips", "Miles", "Total difference"]
    return _with_total(t, "Driver", ["Trips", "Miles", "Total difference"])


def state_only_by_driver(rec, code):
    g = rec[(rec.state == code) & rec.audit_status.isin(["MISSING FROM MAIN REPORT", "UNMATCHED DRIVER"])]
    if g.empty: return pd.DataFrame()
    t = g.groupby("driver").agg(Trips=("driver_payment", "size"), Miles=("state_miles", lambda x: x.sum(min_count=1)),
                                **{"State Revenue": ("state_revenue", lambda x: x.sum(min_count=1)), "Driver Payment": ("driver_payment", lambda x: x.sum(min_count=1))}).reset_index()
    t.columns = ["Driver", "Trips", "Miles", "State Revenue", "Driver Payment"]
    return _with_total(t, "Driver", ["Trips", "Miles", "State Revenue", "Driver Payment"])


def _tot(df, trips_col="Trips", sum_cols=()):
    row = {c: "" for c in df.columns}; row[trips_col] = int(df[trips_col].sum())
    for c in sum_cols: row[c] = df[c].sum()
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def claim_split(rec, code, rate=45.0):
    """(claim, other): claim = trips whose OFFICIAL price equals the agreed rate (Alaska) but First paid less
    -> amount owed by First; other = every remaining price difference (needs review)."""
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if g.empty: return pd.DataFrame(), pd.DataFrame()
    t = g.groupby(["state_revenue", "main_revenue"]).agg(Trips=("revenue_difference", "size"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
    t["Shortfall per trip"] = t.state_revenue - t.main_revenue
    t = t.rename(columns={"state_revenue": "Official price", "main_revenue": "Price paid by First", "Owed": "Total owed"})[["Trips", "Official price", "Price paid by First", "Shortfall per trip", "Total owed"]]
    is_claim = (t["Official price"].round(2) == round(rate, 2)) if code == "AK" else pd.Series(False, index=t.index)
    c, o = t[is_claim], t[~is_claim]
    return (_tot(c, sum_cols=["Total owed"]) if len(c) else c), (_tot(o, sum_cols=["Total owed"]) if len(o) else o)


def claim_by_driver(rec, code, rate=45.0):
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if code == "AK": g = g[g.state_revenue.round(2) == round(rate, 2)]
    else: return pd.DataFrame()
    if g.empty: return pd.DataFrame()
    t = g.groupby("driver").agg(Trips=("revenue_difference", "size"), Miles=("main_miles", "sum"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
    t.columns = ["Driver", "Trips", "Miles", "Total owed"]
    return _with_total(t, "Driver", ["Trips", "Miles", "Total owed"])


def apply_rate_rule(rec, rate=45.0):
    """Management rule: in Alaska only trips whose official price equals the agreed rate (45) are errors.
    Other Alaska price differences are ACCEPTED (relabelled MATCHED, note kept). The original rec is untouched."""
    r = rec.copy()
    m = (r.state == "AK") & (r.audit_status == "REVENUE MISMATCH") & (r.state_revenue.round(2) != round(rate, 2))
    r.loc[m, "notes"] = "ACCEPTED: price differs from state report, treated as correct (management decision)"
    r.loc[m, "audit_status"] = "MATCHED"
    return r


def accepted_summary(rec):
    a = rec[rec.notes.astype(str).str.startswith("ACCEPTED")]
    return len(a), (a.main_revenue - a.state_revenue).sum() if len(a) else 0.0


def monitor_by_driver(rec, code):
    g = rec[(rec.state == code) & (rec.audit_status == "MONITOR PAYMENT")]
    if g.empty: return pd.DataFrame()
    t = g.groupby("driver").agg(Entries=("driver_payment", "size"), Payment=("driver_payment", "sum")).reset_index()
    t.columns = ["Monitor", "Entries", "Driver Payment"]
    return _with_total(t, "Monitor", ["Entries", "Driver Payment"])


PROVIDER_NAMES = {"FIRST": "First", "EVERDRIVEN": "EverDriven"}


def _order(provs):
    """First before EverDriven, anything else after, alphabetically."""
    return sorted(provs, key=lambda p: (list(PROVIDER_NAMES.values()).index(p) if p in PROVIDER_NAMES.values() else 99, p))


def provider_label(main):
    """'First', 'EverDriven' or 'First + EverDriven' depending on what was uploaded."""
    ps = _order([PROVIDER_NAMES.get(p, p) for p in main.provider.dropna().unique() if p])
    return " + ".join(ps) if ps else "Main report"


def provider_table(main):
    g = main.assign(Provider=main.provider.map(PROVIDER_NAMES).fillna(main.provider)).groupby("Provider").agg(
        Trips=("main_amount", "size"), Drivers=("driver", "nunique"), Miles=("miles", "sum"), Revenue=("main_amount", lambda s: s.sum(min_count=1))).reset_index()
    g["Revenue/Trip"] = g.Revenue / g.Trips; g["Revenue %"] = g.Revenue / g.Revenue.sum() * 100
    g = g.set_index("Provider").loc[_order(g.Provider)].reset_index()
    t = {"Provider": "TOTAL", "Trips": int(g.Trips.sum()), "Drivers": main.driver.nunique(), "Miles": g.Miles.sum(), "Revenue": g.Revenue.sum(),
         "Revenue/Trip": g.Revenue.sum() / g.Trips.sum(), "Revenue %": 100.0}
    return pd.concat([g, pd.DataFrame([t])], ignore_index=True)


def state_provider_table(main):
    """One row per state; trips and revenue for each provider side by side, then the combined total."""
    m = main.assign(P=main.provider.map(PROVIDER_NAMES).fillna(main.provider)); provs = _order(m.P.unique()); rows = []
    for code, g in m.groupby("state"):
        row = {"State": _nm(code)}
        for p in provs:
            gp = g[g.P == p]; row[f"{p} Trips"] = len(gp); row[f"{p} Revenue"] = gp.main_amount.sum()
        row["Total Trips"] = len(g); row["Total Revenue"] = g.main_amount.sum(min_count=1); rows.append(row)
    t = pd.DataFrame(rows).sort_values("Total Revenue", ascending=False)
    tot = {c: t[c].sum() for c in t.columns if c != "State"}; tot["State"] = "TOTAL"
    return pd.concat([t, pd.DataFrame([tot])], ignore_index=True)


def revenue_bridge(rec, rate=45.0):
    """Per state: First/EverDriven revenue -> state-report revenue, explaining every dollar of the difference.
    Check must be 0.00. Works on raw or rate-rule-adjusted rec (differences are recomputed from the amounts)."""
    rows = []
    for code, g in rec[rec.audit_status != "STATE REPORT NOT UPLOADED"].groupby("state"):
        if not (g.state_source != "").any(): continue
        first_total = g.main_revenue.sum()
        first_only = g[(g.audit_status == "MISSING FROM STATE REPORT")].main_revenue.sum()
        both = g[g.main_revenue.notna() & g.state_revenue.notna()]
        diff = (both.state_revenue - both.main_revenue).round(2); nz = diff.abs() > 0.005
        claim_m = nz & (code == "AK") & (both.state_revenue.round(2) == round(rate, 2))
        claim, other = diff[claim_m].sum(), diff[nz & ~claim_m].sum()
        state_only = g[g.main_revenue.isna() & g.state_revenue.notna()].state_revenue.sum()
        state_total = g.state_revenue.sum()
        rows.append({"State": _nm(code), "First/EverDriven revenue": first_total, "Less: First revenue not in state report": 0.0 - first_only + 0.0,
                     "Plus: price differences claimed": claim, "Plus: other price differences (accepted)": other,
                     "Plus: state-only revenue": state_only, "State report revenue": state_total,
                     "Check difference (must be 0)": round(first_total - first_only + claim + other + state_only - state_total, 2)})
    t = pd.DataFrame(rows)
    if len(t):
        tot = {c: t[c].sum() for c in t.columns if c != "State"}; tot["State"] = "TOTAL"; t = pd.concat([t, pd.DataFrame([tot])], ignore_index=True)
    return t


# ---------------------------------------------------------------- rate check from the main report ALONE (no state report needed)
OFFICIAL_RATES = {"AK": 45.0}        # state -> official per-trip price; extend when the full rate list is available


def first_rate_audit(main, rate=45.0, state="AK"):
    """Trips of `state` that First/EverDriven paid BELOW the official rate (Alaska: $42.50 vs $45.00).
    Returns (summary dict, grouped table, by-driver table, trip detail)."""
    g = main[(main.state == state) & main.main_amount.notna() & (main.main_amount < rate - 0.005)].copy()
    empty = pd.DataFrame()
    if g.empty: return {"Trips below official rate": 0, "Total owed": 0.0}, empty, empty, empty
    g["short"] = rate - g.main_amount
    grp = g.groupby("main_amount").agg(Trips=("short", "size"), Owed=("short", "sum")).reset_index()
    grp["Official price"] = rate; grp["Shortfall per trip"] = rate - grp.main_amount
    grp = grp.rename(columns={"main_amount": "Price paid", "Owed": "Total owed"})[["Trips", "Official price", "Price paid", "Shortfall per trip", "Total owed"]]
    drv = g.groupby("driver_disp").agg(Trips=("short", "size"), Miles=("miles", "sum"), Owed=("short", "sum")).reset_index()
    drv.columns = ["Driver", "Trips", "Miles", "Total owed"]
    det = g.sort_values(["driver", "date"])[["date", "driver_disp", "trip_id", "trip_name", "miles", "main_amount", "short", "src_file", "src_row"]].copy()
    det.insert(5, "Official price", rate)
    det.columns = ["Date", "Driver", "Trip ID", "Trip Name", "Miles", "Official price", "Price paid", "Shortfall", "Source file", "Source row"]
    summary = {"Trips below official rate": len(g), "Official price": rate, "Total owed": g.short.sum(), "Drivers affected": g.driver.nunique(),
               "Alaska trips in report": int(((main.state == state)).sum())}
    return summary, _tot(grp, sum_cols=["Total owed"]), _with_total(drv, "Driver", ["Trips", "Miles", "Total owed"]), det
