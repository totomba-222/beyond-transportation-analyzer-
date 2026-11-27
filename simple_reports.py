"""Simple 3-stage reports built on the tested engine (no new matching logic)."""
import numpy as np
from ratebook import route_key
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import STATE_NAMES, CANCELLED_TRIPS

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
    g = _with_total(g, "State", ["Trips", "Drivers", "Miles", "Revenue"])
    if len(g):
        i = g.index[-1]; g.loc[i, "Revenue/Trip"] = g.loc[i, "Revenue"] / g.loc[i, "Trips"] if g.loc[i, "Trips"] else np.nan
        g.loc[i, "Trips %"], g.loc[i, "Revenue %"] = 100.0, 100.0
    return g.reset_index(drop=True)


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
        # profit = revenue - payments over every row that has revenue (a trip with revenue but NO driver pay counts its full revenue as profit) + monitor costs
        pr = g[g.state_revenue.notna() | (g.audit_status == "MONITOR PAYMENT")]
        profit = (pr.state_revenue.fillna(0).sum() - pr.driver_payment.fillna(0).sum()) if len(pr) else np.nan; den = pr.state_revenue.sum(min_count=1)
        return {"State": label, "Trips": len(trips), "Drivers": trips.driver.str.lower().nunique(), "Revenue": g.state_revenue.sum(min_count=1),
                "Driver Payments": g.driver_payment.sum(min_count=1), "Monitor payments": mon.driver_payment.sum(),
                "Profit": profit, "Margin %": profit / den * 100 if len(pr) and den else np.nan,
                "Trips missing revenue": int(trips.state_revenue.isna().sum())}
    for code, g in r.groupby("state"): rows.append(line(_nm(code), g))
    return pd.DataFrame(rows).sort_values("Revenue", ascending=False).reset_index(drop=True)


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
    return pd.DataFrame(rows).reset_index(drop=True)


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


def _has_total(df, label_col=None):
    if df is None or df.empty: return False
    col = label_col or df.columns[0]
    return df[col].astype(str).str.strip().str.upper().isin(["TOTAL", "GRAND TOTAL"]).any()


def _with_total(df, label_col, sums):
    """Append one auditable TOTAL row without treating it as a detail record."""
    if df is None or df.empty or _has_total(df, label_col):
        return df.reset_index(drop=True) if df is not None else df
    row = {c: np.nan for c in df.columns}; row[label_col] = "TOTAL"
    for c in sums:
        if c in df.columns:
            row[c] = df[c].sum(min_count=1)
    return pd.concat([df.reset_index(drop=True), pd.DataFrame([row])], ignore_index=True)


def ensure_total(df, label_col=None):
    """Add a total to any displayed numeric table; percentage columns are left n/a unless already calculated."""
    if df is None or len(df) == 0: return df
    label_col = label_col or df.columns[0]
    if _has_total(df, label_col): return df.reset_index(drop=True)
    row = {c: np.nan for c in df.columns}; row[label_col] = "TOTAL"
    for c in df.columns:
        if c == label_col: continue
        if pd.api.types.is_numeric_dtype(df[c]):
            lc = str(c).lower()
            if "%" in lc:
                row[c] = 100.0 if lc.endswith("%") or "share" in lc else np.nan
            else:
                row[c] = df[c].sum(min_count=1)
    return pd.concat([df.reset_index(drop=True), pd.DataFrame([row])], ignore_index=True)


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
    return t.reset_index(drop=True)


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
    if df is None or df.empty:
        return df.reset_index(drop=True) if df is not None else df
    # Use the first descriptive column as the label (usually Trips is not the first column).
    label = next((c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])), df.columns[0])
    return _with_total(df, label, [trips_col, *sum_cols])


def claim_split(rec, code, rate=45.0, err=None):
    """(claim, other): claim = trips whose OFFICIAL price equals the agreed rate (Alaska) but First paid less
    -> amount owed by First; other = every remaining price difference (needs review)."""
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if g.empty: return pd.DataFrame(), pd.DataFrame()
    t = g.groupby(["state_revenue", "main_revenue"]).agg(Trips=("revenue_difference", "size"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
    t["Shortfall per trip"] = t.state_revenue - t.main_revenue
    t = t.rename(columns={"state_revenue": "Official price", "main_revenue": "Price paid by First", "Owed": "Total owed"})[["Trips", "Official price", "Price paid by First", "Shortfall per trip", "Total owed"]]
    is_claim = ak_claim_mask(t["Price paid by First"], t["Official price"], rate, err).set_axis(t.index) if code == "AK" else pd.Series(False, index=t.index)
    c, o = t[is_claim], t[~is_claim]
    return (_tot(c, sum_cols=["Total owed"]) if len(c) else c), (_tot(o, sum_cols=["Total owed"]) if len(o) else o)


def price_diff_claim(rec, code, rate=45.0, err=None):
    """Any state (Alaska rule kept for AK): trips where First/EverDriven paid LESS than the state report says Beyond should receive.
    Returns (by price: trips / state price / paid / shortfall per trip / total owed, by driver, trips over-paid by First (info, no claim))."""
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if code == "AK" or g.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    low = g[g.revenue_difference < -0.004]; high = g[g.revenue_difference > 0.004]
    by_price = pd.DataFrame(); by_drv = pd.DataFrame()
    if len(low):
        t = low.groupby(["state_revenue", "main_revenue"]).agg(Trips=("revenue_difference", "size"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
        t["Shortfall per trip"] = t.state_revenue - t.main_revenue
        t = t.rename(columns={"state_revenue": "State report price", "main_revenue": "Price paid by provider", "Owed": "Total owed"})[["Trips", "State report price", "Price paid by provider", "Shortfall per trip", "Total owed"]]
        by_price = _tot(t, sum_cols=["Total owed"])
        d = low.groupby("driver").agg(Trips=("revenue_difference", "size"), Miles=("main_miles", "sum"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
        d.columns = ["Driver", "Trips", "Miles", "Total owed"]; by_drv = _with_total(d, "Driver", ["Trips", "Miles", "Total owed"])
    over = high[["date", "driver", "trip_name", "main_miles", "main_revenue", "state_revenue", "revenue_difference"]].copy() if len(high) else pd.DataFrame()
    if len(over): over.columns = ["Date", "Driver", "Trip Name", "Miles", "Provider paid", "State report", "Difference"]
    return by_price, by_drv, over


def claim_by_driver(rec, code, rate=45.0, err=None):
    g = rec[(rec.state == code) & (rec.audit_status == "REVENUE MISMATCH")]
    if code == "AK": g = g[ak_claim_mask(g.main_revenue, g.state_revenue, rate, err).set_axis(g.index)]
    else: return pd.DataFrame()
    if g.empty: return pd.DataFrame()
    t = g.groupby("driver").agg(Trips=("revenue_difference", "size"), Miles=("main_miles", "sum"), Owed=("revenue_difference", lambda x: -x.sum())).reset_index()
    t.columns = ["Driver", "Trips", "Miles", "Total owed"]
    return _with_total(t, "Driver", ["Trips", "Miles", "Total owed"])


def is_cancel_fee(state, amount, tol=0.05):
    """True when `amount` is the fee the provider pays for a cancelled trip of this state (config.CANCELLED_TRIPS)."""
    spec = CANCELLED_TRIPS.get(state)
    return bool(spec) and pd.notna(amount) and any(abs(float(amount) - x) < tol for x in spec["revenue"])


def cancel_mask(df, state_col="state", amount_col="main_amount", pay_col=None):
    """Rows that are cancelled trips by the rule above (provider fee amount, and, when pay_col is given, the fixed driver pay)."""
    m = pd.Series([is_cancel_fee(s_, a_) for s_, a_ in zip(df[state_col], df[amount_col])], index=df.index)
    if pay_col is not None:
        m &= pd.Series([pd.notna(p_) and abs(float(p_) - CANCELLED_TRIPS[s_]["driver_pay"]) < 0.005 if s_ in CANCELLED_TRIPS else False for s_, p_ in zip(df[state_col], df[pay_col])], index=df.index)
    return m


def apply_rate_rule(rec, rate=45.0, err=None):
    """Management rule: in Alaska only trips short by exactly the fixed $2.50 (paid 42.50/47.50/82.50 vs 45/50/85) are errors.
    Other Alaska price differences are ACCEPTED (relabelled MATCHED, note kept). The original rec is untouched."""
    r = rec.copy()
    claim = ak_claim_mask(r.main_revenue, r.state_revenue, rate, err).set_axis(r.index)
    m = (r.state == "AK") & (r.audit_status == "REVENUE MISMATCH") & ~claim
    r.loc[m, "notes"] = "ACCEPTED: price differs from state report, treated as correct (management decision)"
    r.loc[m, "audit_status"] = "MATCHED"
    # cancelled trips (Nebraska: provider pays 18, driver gets 15): accepted, revenue = what the provider really paid, profit = revenue - driver pay
    cm = cancel_mask(r, "state", "main_revenue", "driver_payment") & r.audit_status.isin(["REVENUE MISMATCH", "MATCHED", "EXACT MATCH", "PAYMENT MISMATCH", "MILEAGE MISMATCH"])
    if cm.any():
        r.loc[cm, "state_revenue"] = r.loc[cm, "main_revenue"]
        r.loc[cm, "revenue_difference"] = 0.0
        r.loc[cm, "profit"] = r.loc[cm, "state_revenue"] - r.loc[cm, "driver_payment"]
        r.loc[cm, "margin_pct"] = r.loc[cm, "profit"] / r.loc[cm, "state_revenue"] * 100
        r.loc[cm & r.audit_status.isin(["REVENUE MISMATCH", "PAYMENT MISMATCH", "MILEAGE MISMATCH"]), "audit_status"] = "MATCHED"
        r.loc[cm, "notes"] = "CANCELLED TRIP: provider fee paid to Beyond, fixed driver pay (not a price difference, not a claim)"
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
    g = _with_total(g, "Provider", ["Trips", "Drivers", "Miles", "Revenue"])
    if len(g):
        i = g.index[-1]; g.loc[i, "Revenue/Trip"] = g.loc[i, "Revenue"] / g.loc[i, "Trips"] if g.loc[i, "Trips"] else np.nan; g.loc[i, "Revenue %"] = 100.0
    return g.reset_index(drop=True)


def state_provider_table(main):
    """One row per state; trips and revenue for each provider side by side, then the combined total."""
    m = main.assign(P=main.provider.map(PROVIDER_NAMES).fillna(main.provider)); provs = _order(m.P.unique()); rows = []
    for code, g in m.groupby("state"):
        row = {"State": _nm(code)}
        for p in provs:
            gp = g[g.P == p]; row[f"{p} Trips"] = len(gp); row[f"{p} Revenue"] = gp.main_amount.sum()
        row["Total Trips"] = len(g); row["Total Revenue"] = g.main_amount.sum(min_count=1); rows.append(row)
    out = pd.DataFrame(rows).sort_values("Total Revenue", ascending=False).reset_index(drop=True)
    return _with_total(out, "State", [c for c in out.columns if c != "State"])


def revenue_bridge(rec, rate=45.0, err=None):
    """Per state: First/EverDriven revenue -> state-report revenue, explaining every dollar of the difference.
    Check must be 0.00. Works on raw or rate-rule-adjusted rec (differences are recomputed from the amounts)."""
    rows = []
    for code, g in rec[rec.audit_status != "STATE REPORT NOT UPLOADED"].groupby("state"):
        if not (g.state_source != "").any(): continue
        first_total = g.main_revenue.sum()
        first_only = g[(g.audit_status == "MISSING FROM STATE REPORT")].main_revenue.sum()
        both = g[g.main_revenue.notna() & g.state_revenue.notna()]
        diff = (both.state_revenue - both.main_revenue).round(2); nz = diff.abs() > 0.005
        claim_m = nz & (code == "AK") & ak_claim_mask(both.main_revenue, both.state_revenue, rate, err).set_axis(both.index)
        claim, other = diff[claim_m].sum(), diff[nz & ~claim_m].sum()
        state_only = g[g.main_revenue.isna() & g.state_revenue.notna()].state_revenue.sum()
        state_total = g.state_revenue.sum()
        rows.append({"State": _nm(code), "First/EverDriven revenue": first_total, "Less: First revenue not in state report": 0.0 - first_only + 0.0,
                     "Plus: price differences claimed": claim, "Plus: other price differences (accepted)": other,
                     "Plus: state-only revenue": state_only, "State report revenue": state_total,
                     "Check difference (must be 0)": round(first_total - first_only + claim + other + state_only - state_total, 2)})
    return pd.DataFrame(rows).reset_index(drop=True)


# ---------------------------------------------------------------- rate check from the main report ALONE (no state report needed)
ERROR_PRICE = 42.5          # the price First paid in error (official 45.00); only trips paid exactly this are claimed
OFFICIAL_RATES = {"AK": 45.0}        # state -> official per-trip price; extend when the full rate list is available


def first_rate_audit(main, rate=45.0, state="AK", err=None):
    """Claim = `state` trips paid at least `paid` ($42.50) ending in .50, i.e. missing the fixed $2.50 (42.50/45, 47.50/50, 82.50/85). Other trips paid below
    the rate are NOT part of the claim; they are only reported in the summary. Returns (summary, grouped, by driver, detail)."""
    paid = _err(err)
    s_all = main[(main.state == state) & main.main_amount.notna()]
    delta = round(rate - paid, 2)
    # a claim = price paid >= 42.50 and ending in .50 (the fixed $2.50 is missing): 42.50->45, 47.50->50, 82.50->85
    is_c = (s_all.main_amount >= paid - 0.005) & ((s_all.main_amount % 1 - 0.5).abs() < 0.005)
    g = s_all[is_c].copy()
    oth = s_all[(s_all.main_amount < rate - 0.005) & ~is_c]
    empty = pd.DataFrame()
    other = {"Other trips below the rate (not claimed)": len(oth), "Their shortfall (not claimed)": (rate - oth.main_amount).sum() if len(oth) else 0.0,
             "Other prices (not claimed)": ", ".join(f"${p:,.2f} x{n}" for p, n in oth.main_amount.value_counts().sort_index().items())}
    if g.empty: return {"Trips below official rate": 0, "Total owed": 0.0, "Alaska trips in report": len(s_all), **other}, empty, empty, empty
    g["official"] = g.main_amount + delta; g["short"] = delta
    grp = g.groupby("main_amount").agg(Trips=("short", "size"), Owed=("short", "sum")).reset_index()
    grp["Official price"] = grp.main_amount + delta; grp["Shortfall per trip"] = delta
    grp = grp.rename(columns={"main_amount": "Price paid", "Owed": "Total owed"})[["Trips", "Official price", "Price paid", "Shortfall per trip", "Total owed"]]
    drv = g.groupby("driver_disp").agg(Trips=("short", "size"), Miles=("miles", "sum"), Owed=("short", "sum")).reset_index()
    drv.columns = ["Driver", "Trips", "Miles", "Total owed"]
    det = g.sort_values(["driver", "date"])[["date", "driver_disp", "trip_id", "trip_name", "miles", "main_amount", "short", "src_file", "src_row"]].copy()
    det.insert(5, "Official price", g.sort_values(["driver", "date"]).official.values)
    det.columns = ["Date", "Driver", "Trip ID", "Trip Name", "Miles", "Official price", "Price paid", "Shortfall", "Source file", "Source row"]
    summary = {"Trips below official rate": len(g), "Shortfall per trip": delta, "Total owed": g.short.sum(), "Drivers affected": g.driver.nunique(),
               "Alaska trips in report": len(s_all), **other}
    return summary, grp.reset_index(drop=True), drv.reset_index(drop=True), det


def _err(err): return ERROR_PRICE if err is None else err


def ak_claim_mask(paid, official, rate=45.0, err=None):
    """Alaska rule (management): the price First pays is the true price minus a fixed $2.50 (45 -> 42.50, 50 -> 47.50, 85 -> 82.50 ...).
    A trip is a claim when the price paid is at least `err` (42.50) and the official price is exactly paid + (rate - err)."""
    paid = pd.Series(paid); official = pd.Series(official); delta = round(rate - _err(err), 2)
    return (paid >= _err(err) - 0.005) & ((official - paid - delta).abs() < 0.005)


# ---------------------------------------------------------------- rate book: price check + estimated financials (before the state reports arrive)
def price_check(main, book, err=42.5, rate=45.0):
    """First/EverDriven price per trip vs the contract price learned from earlier state reports (same route, else same state+miles).
    Returns (summary by state, detail of trips paid BELOW contract, accepted-info dict). Alaska keeps the management rule:
    only trips paid exactly `err` against the official `rate` are claimed; other Alaska differences are listed as not claimed."""
    import ratebook as RB
    # A duplicated upload row must never become two claims. Prefer the provider's
    # trip ID; for rows without an ID use the stable trip signature.
    _m = main.copy()
    if "trip_id" in _m.columns:
        _has_id = _m.trip_id.fillna("").astype(str).str.strip().ne("")
        _with_id = _m[_has_id].drop_duplicates([c for c in ["provider", "trip_id"] if c in _m.columns], keep="first")
        _no_id = _m[~_has_id]
        _sig = [c for c in ["provider", "state", "date", "driver", "driver_disp", "trip_name", "miles", "main_amount"] if c in _no_id.columns]
        _no_id = _no_id.drop_duplicates(_sig, keep="first") if _sig else _no_id
        _m = pd.concat([_with_id, _no_id], ignore_index=True)
    a = RB.annotate(_m, book); a["diff"] = (a.main_amount - a.exp_revenue).round(2)
    zero = a.main_amount.fillna(0).abs() < 0.005
    if "cancelled" in a.columns: zero = zero | a.cancelled.fillna(False).astype(bool)
    zero = zero | cancel_mask(a, "state", "main_amount")          # cancelled trips (Nebraska fee) are not price errors
    a = a[~zero]                                                  # cancelled / $0 trips are not price errors
    known = a[a.exp_revenue.notna() & a.main_amount.notna()]
    under = known[(known["diff"] < -0.005) & (known.state != "AK")]
    # CLAIM = the SAME route was paid more in earlier weeks. A price only estimated from OTHER routes with similar miles is NOT a claim
    # (e.g. Oregon trips whose state report price equals the paid price): it is kept apart and never added to the amount owed.
    claim_route = under[under.exp_rev_src.astype(str).str.lower().eq("route")]
    mil = under[under.exp_rev_src.astype(str).str.lower().eq("miles")]
    # A price estimated from state + miles is accepted EXCEPT when it is simply the price of ANOTHER route of the same school with the same miles in the same
    # report (e.g. an IB route priced 73.75 used for the OB route that really is 66.25): then the estimate is not this route's price and it is not claimed.
    from classification import _school_stem
    def _borrowed(r):
        stem = _school_stem(route_key(r.trip_name)); mi = round(float(r.miles)) if pd.notna(r.miles) else None
        if mi is None: return False
        sib = a[(a.state == r.state) & (a.trip_name != r.trip_name) & (a.miles.round() == mi) & ((a.main_amount - r.exp_revenue).abs() < 0.005)]
        return any(_school_stem(route_key(t)) == stem for t in sib.trip_name.unique())
    borrowed = mil[[bool(_borrowed(r)) for r in mil.itertuples()]] if len(mil) else mil
    claim = pd.concat([claim_route, mil[~mil.index.isin(borrowed.index)]])
    verify = borrowed
    def _det(x):
        d = x.sort_values(["state", "driver", "date"])[["state", "date", "driver_disp", "trip_id", "trip_name", "miles", "exp_revenue", "exp_rev_src", "main_amount", "diff", "src_file", "src_row"]].copy()
        def explain(r):
            src = str(r.exp_rev_src).lower()
            if src == "miles":
                return "Same-state mileage-band estimate; verify route/district/address change"
            if src == "route":
                e = book.get("routes", {}).get(f"{r.state}|{route_key(r.trip_name)}", {})
                ref = e.get("mi") if isinstance(e, dict) else None
                if pd.notna(ref) and pd.notna(r.miles) and abs(float(r.miles) - float(ref)) > 0.51:
                    return f"Same route history, mileage changed ({float(ref):g} reference vs {float(r.miles):g} current)"
                return "Same route/mileage basis; provider price differs"
            return "No route/mileage basis available"
        d["Explanation"] = [explain(r) for r in d.itertuples()]
        d["state"] = d.state.map(_nm)
        d.columns = ["State", "Date", "Driver", "Trip ID", "Trip Name", "Miles", "Contract price", "Price source", "Paid", "Difference", "Source file", "Source row", "Explanation"]
        return d
    det, ver = _det(claim), _det(verify)
    # Alaska: ONE number everywhere = the fixed-rule claim (price paid ends in .50, official = paid + 2.50). It does not need a known contract price.
    ak_s, _, _, ak_det = first_rate_audit(_m, rate, err=err)
    if len(ak_det):
        akd = pd.DataFrame({"State": _nm("AK"), "Date": ak_det["Date"], "Driver": ak_det["Driver"], "Trip ID": ak_det["Trip ID"], "Trip Name": ak_det["Trip Name"], "Miles": ak_det["Miles"],
                            "Contract price": ak_det["Official price"], "Price source": "Alaska fixed rule", "Paid": ak_det["Price paid"], "Difference": -ak_det["Shortfall"],
                            "Source file": ak_det["Source file"], "Source row": ak_det["Source row"]})
        det = pd.concat([det, akd], ignore_index=True)
    rows = []
    for code, g in a.groupby("state"):
        k = known[known.state == code]
        if code == "AK": nu, su, nv, sv = int(ak_s["Trips below official rate"]), float(ak_s["Total owed"]), 0, 0.0
        else:
            u = claim[claim.state == code]; v = verify[verify.state == code]
            nu, su, nv, sv = len(u), (-u["diff"].sum() if len(u) else 0.0), len(v), (-v["diff"].sum() if len(v) else 0.0)
        rows.append({"State": _nm(code), "Trips": len(g), "Trips with a known contract price": len(k), "Coverage %": len(k) / len(g) * 100 if len(g) else np.nan,
                     "Trips paid below contract price": nu, "Total shortfall": su})
    # Start from every state in the uploaded provider report; filtering zero/cancelled rows
    # must not make an uploaded state disappear from the by-state report.
    state_codes = [x for x in main.state.dropna().unique() if str(x) not in ("Unassigned", "NEEDS REVIEW")]
    by_state = {r["State"]: r for r in rows}
    for code in state_codes:
        label = _nm(code); eligible = int((a.state == code).sum()); matched = int((known.state == code).sum())
        if label not in by_state:
            by_state[label] = {"State": label, "Trips": eligible, "Trips with a known contract price": matched,
                               "Coverage %": matched / eligible * 100 if eligible else np.nan,
                               "Trips paid below contract price": 0, "Total shortfall": 0.0}
    t = pd.DataFrame(list(by_state.values())).sort_values("Trips", ascending=False).reset_index(drop=True)
    total = {"State":"TOTAL", "Trips":int(t.Trips.sum()), "Trips with a known contract price":int(t["Trips with a known contract price"].sum()),
             "Coverage %":t["Trips with a known contract price"].sum() / t.Trips.sum() * 100 if t.Trips.sum() else np.nan,
             "Trips paid below contract price":int(t["Trips paid below contract price"].sum()), "Total shortfall":t["Total shortfall"].sum()}
    t = pd.concat([t, pd.DataFrame([total])], ignore_index=True)
    return t, det, {"accepted_trips": len(verify), "accepted_amount": -verify["diff"].sum() if len(verify) else 0.0, "verify": ver}


def estimate_financials(main, book, states_with_report=()):
    """ESTIMATE for states WITHOUT an uploaded state report: First revenue (actual) minus driver pay estimated from the rate book,
    on the trips where a pay estimate exists. Clearly labelled; never added to actual state-report totals."""
    import ratebook as RB
    a = RB.annotate(main, book); a = a[~a.state.isin(list(states_with_report)) & ~a.state.isin(["Unassigned", "NEEDS REVIEW"])]
    rows = []
    for code, g in a.groupby("state"):
        c = g[g.exp_pay.notna() & g.main_amount.notna()]
        rev, pay = c.main_amount.sum(), c.exp_pay.sum()
        rows.append({"State": _nm(code), "Trips": len(g), "First/EverDriven revenue": g.main_amount.sum(min_count=1), "Trips with a pay estimate": len(c),
                     "Coverage %": len(c) / len(g) * 100 if len(g) else np.nan, "Est. driver payments": pay, "Est. profit": rev - pay if len(c) else np.nan,
                     "Est. margin %": (rev - pay) / rev * 100 if len(c) and rev else np.nan})
    return pd.DataFrame(rows).reset_index(drop=True)


# ---------------------------------------------------------------- driver pay policy (learned) and the overpayment review
def pay_policy_table(book):
    """One row per state+route with a STABLE driver-pay policy (the same pay in >=80% of >=3 earlier trips) and its contract price."""
    import ratebook as RB
    rows = []
    for k, e in book["routes"].items():
        st, rt = k.split("|", 1); pm = RB._mode(e["pay"], 0.8, 3)
        if not pm: continue
        rv = RB._mode(e["rev"], 0.8, 2)
        rows.append({"State": _nm(st), "Route": rt, "Earlier trips": sum(e["pay"].values()), "Contract price": rv[0] if rv else np.nan,
                     "Driver pay policy": pm[0], "Policy share %": pm[1] * 100, "Miles": e["mi"]})
    return pd.DataFrame(rows).sort_values(["State", "Route"]).reset_index(drop=True)


def pay_check(rec, book, tol=0.005):
    """State-report driver payments vs the pay policy of the SAME route (First/EverDriven give the route of every trip).
    Returns (summary by state, trips paid ABOVE the policy, trips paid ABOVE their own contract revenue)."""
    import ratebook as RB
    r = rec[(rec.state_source != "") & rec.driver_payment.notna() & (rec.audit_status != "MONITOR PAYMENT") & rec.trip_name.fillna("").ne("")].copy()
    pol, src = [], []
    for st, t in zip(r.state, r.trip_name):
        e = book["routes"].get(f"{st}|{RB.route_key(t)}"); m = RB._mode(e["pay"], 0.8, 3) if e else None
        pol.append(m[0] if m else np.nan); src.append("route policy" if m else "")
    r["policy"], r["excess"] = pol, r.driver_payment - pd.Series(pol, index=r.index)
    over = r[r.policy.notna() & (r.excess > tol)]
    loss = r[r.state_revenue.notna() & (r.driver_payment > r.state_revenue + tol)]
    rows = []
    for code, g in r.groupby("state"):
        o, l = over[over.state == code], loss[loss.state == code]
        rows.append({"State": _nm(code), "Trips with driver pay": len(g), "Trips with a pay policy": int(g.policy.notna().sum()), "Coverage %": g.policy.notna().mean() * 100,
                     "Trips paid above policy": len(o), "Total excess pay": o.excess.sum(), "Trips paid above trip revenue": len(l),
                     "Their loss": (l.driver_payment - l.state_revenue).sum()})
    t = pd.DataFrame(rows, columns=["State", "Trips with driver pay", "Trips with a pay policy", "Coverage %", "Trips paid above policy", "Total excess pay", "Trips paid above trip revenue", "Their loss"])
    total = {"State":"TOTAL", "Trips with driver pay":t["Trips with driver pay"].sum(), "Trips with a pay policy":t["Trips with a pay policy"].sum(),
             "Coverage %": t["Trips with a pay policy"].sum() / t["Trips with driver pay"].sum() * 100 if t["Trips with driver pay"].sum() else np.nan,
             "Trips paid above policy":t["Trips paid above policy"].sum(), "Total excess pay":t["Total excess pay"].sum(),
             "Trips paid above trip revenue":t["Trips paid above trip revenue"].sum(), "Their loss":t["Their loss"].sum()}
    t = pd.concat([t.sort_values("Trips with driver pay", ascending=False).reset_index(drop=True), pd.DataFrame([total])], ignore_index=True)
    cols = ["state", "date", "driver", "trip_name", "main_miles", "state_revenue", "driver_payment", "policy", "excess", "match_tier", "state_source"]
    names = ["State", "Date", "Driver", "Trip Name", "Miles", "Trip revenue", "Driver pay", "Pay policy", "Excess pay", "Trip matched by", "State source"]
    mk = lambda d: d.sort_values(["state", "excess"], ascending=[True, False])[cols].rename(columns=dict(zip(cols, names))).assign(State=lambda x: x.State.map(_nm)).reset_index(drop=True)
    return t, mk(over), mk(loss.assign(excess=loss.driver_payment - loss.state_revenue))


def policy_compliance_report(rec, book, tol=0.005):
    """One auditable pricing-policy decision for every checkable driver-payment trip.

    Missing policy inputs are NOT_VERIFIABLE, never COMPLIANT. Gross Pay is
    state-report revenue, Net Pay is the current driver payment, and the
    difference is Net Pay minus Policy Trip Price.
    """
    import pay_policy as PP
    cols = ["State", "Date", "Driver", "Trip Name", "Gross Pay", "Net Pay", "Policy Trip Price", "Difference", "Status", "Reason"]
    base = rec[(rec.state_source != "") & rec.driver_payment.notna() &
               (rec.audit_status != "MONITOR PAYMENT") & rec.trip_name.fillna("").ne("")].copy()
    _, raw = PP.band_check(base, book)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=cols), pd.DataFrame(), {"Trips": 0, "Compliant": 0, "Non-compliant": 0, "Not verifiable": 0, "Loss": 0.0}
    d = raw.copy()
    d["Gross Pay"] = pd.to_numeric(d["Trip revenue"], errors="coerce")
    d["Net Pay"] = pd.to_numeric(d["Driver pay"], errors="coerce")
    d["Policy Trip Price"] = pd.to_numeric(d["Policy pay"], errors="coerce")
    d["Difference"] = d["Net Pay"] - d["Policy Trip Price"]
    old = d["Status"].astype(str)
    approved = old.str.startswith(("Approved exception", "Allowed exception", "Matches policy", "Matches route policy", "Matches band", "Matches route", "Matches"))
    no_policy = old.str.startswith(("No policy", "City not", "Long trip: needs", "ZERO", "No driver", "Sacramento: pay NOT"))
    comparable = d["Policy Trip Price"].notna() & d["Net Pay"].notna()
    equal = comparable & d["Difference"].abs().le(tol)
    d["Status"] = np.where(no_policy | ~comparable, "NOT_VERIFIABLE", np.where(equal | approved, "COMPLIANT", "NON_COMPLIANT"))
    d["Reason"] = np.select(
        [d.Status.eq("COMPLIANT") & approved & ~equal, d.Status.eq("COMPLIANT"), d.Status.eq("NON_COMPLIANT"), d.Status.eq("NOT_VERIFIABLE")],
        ["Approved exception in policy", "Net Pay equals Policy Trip Price", "Net Pay differs from Policy Trip Price", "Policy price or required route/mileage input is missing"], default="")
    d["State"] = d["State"].map(_nm)
    detail = d[cols].sort_values(["State", "Status", "Date", "Driver"], na_position="last").reset_index(drop=True)
    rows = []
    for state, g in detail.groupby("State", dropna=False):
        non = g[g.Status == "NON_COMPLIANT"]
        loss = non["Difference"].clip(lower=0).sum()
        gross = g["Gross Pay"].sum(min_count=1)
        rows.append({"State": state, "Trips checked": len(g), "Compliant": int((g.Status == "COMPLIANT").sum()),
                     "Non-compliant": int((g.Status == "NON_COMPLIANT").sum()), "Not verifiable": int((g.Status == "NOT_VERIFIABLE").sum()),
                     "Coverage %": (g.Status != "NOT_VERIFIABLE").mean() * 100, "Non-compliant %": (g.Status == "NON_COMPLIANT").mean() * 100,
                     "Gross Pay": gross, "Net Pay": g["Net Pay"].sum(min_count=1), "Policy Pay": g["Policy Trip Price"].sum(min_count=1),
                     "Difference": g["Difference"].sum(min_count=1), "Loss from non-compliance": loss,
                     "Loss % of Gross Pay": loss / gross * 100 if gross else np.nan})
    summary = pd.DataFrame(rows)
    if len(summary):
        gross = summary["Gross Pay"].sum(); loss = summary["Loss from non-compliance"].sum(); n = summary["Trips checked"].sum()
        total = {"State": "TOTAL", "Trips checked": summary["Trips checked"].sum(), "Compliant": summary.Compliant.sum(), "Non-compliant": summary["Non-compliant"].sum(), "Not verifiable": summary["Not verifiable"].sum(),
                 "Coverage %": (summary.Compliant.sum() + summary["Non-compliant"].sum()) / n * 100 if n else np.nan, "Non-compliant %": summary["Non-compliant"].sum() / n * 100 if n else np.nan,
                 "Gross Pay": gross, "Net Pay": summary["Net Pay"].sum(), "Policy Pay": summary["Policy Pay"].sum(), "Difference": summary["Difference"].sum(),
                 "Loss from non-compliance": loss, "Loss % of Gross Pay": loss / gross * 100 if gross else np.nan}
        summary = pd.concat([summary.sort_values("Gross Pay", ascending=False), pd.DataFrame([total])], ignore_index=True)
    gross_all = pd.to_numeric(rec.state_revenue, errors="coerce").sum(min_count=1)
    pay_all = pd.to_numeric(rec.driver_payment, errors="coerce").sum(min_count=1)
    actual = gross_all - pay_all if pd.notna(gross_all) and pd.notna(pay_all) else np.nan
    loss = detail.loc[detail.Status == "NON_COMPLIANT", "Difference"].clip(lower=0).sum()
    kpis = {"Trips": len(detail), "Compliant": int((detail.Status == "COMPLIANT").sum()), "Non-compliant": int((detail.Status == "NON_COMPLIANT").sum()), "Not verifiable": int((detail.Status == "NOT_VERIFIABLE").sum()),
            "Loss": float(loss), "Gross Pay": gross_all, "Actual profit": actual, "Projected profit": actual + loss if pd.notna(actual) else np.nan,
            "Actual margin %": actual / gross_all * 100 if gross_all else np.nan, "Projected margin %": (actual + loss) / gross_all * 100 if gross_all else np.nan,
            "Loss % of Gross Pay": loss / gross_all * 100 if gross_all else np.nan}
    return detail, summary, kpis


def claim_tables(det):
    """Alaska-style claim for ONE state from the price-check detail: (by price, by driver). Same columns as the Alaska claim."""
    if det is None or det.empty: return pd.DataFrame(), pd.DataFrame()
    d = det.copy(); d["short"] = -d["Difference"]
    g = d.groupby(["Contract price", "Paid"]).agg(Trips=("short", "size"), Owed=("short", "sum")).reset_index()
    g["Shortfall per trip"] = g["Contract price"] - g["Paid"]
    g = g.rename(columns={"Contract price": "Official price", "Paid": "Price paid", "Owed": "Total owed"})[["Trips", "Official price", "Price paid", "Shortfall per trip", "Total owed"]].sort_values("Total owed", ascending=False)
    v = d.groupby("Driver").agg(Trips=("short", "size"), Miles=("Miles", "sum"), Owed=("short", "sum")).reset_index().rename(columns={"Owed": "Total owed"}).sort_values("Total owed", ascending=False)
    return _tot(g, sum_cols=["Total owed"]), _with_total(v, "Driver", ["Trips", "Miles", "Total owed"])
