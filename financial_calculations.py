"""KPI, state/driver tables and the Alaska rate audit. Profit/margin are computed
ONLY from trips that have both a state-report revenue and a driver payment
(never from missing values treated as 0) and only when the definitions are
marked verified in settings."""
import numpy as np
import pandas as pd
from config import STATE_NAMES


def _pct(a, b):
    return a / b * 100 if b else np.nan


def kpis(rec: pd.DataFrame, verified=True) -> dict:
    mainrows = rec[rec.main_revenue.notna()]
    both = rec[rec.state_revenue.notna() & rec.driver_payment.notna()]
    out = {"Trips": len(mainrows), "Drivers": mainrows.driver.str.lower().nunique(),
           "Miles": mainrows.main_miles.sum(min_count=1), "Revenue": mainrows.main_revenue.sum(min_count=1),
           "State Revenue": rec.state_revenue.sum(min_count=1),
           "Driver Payments": rec.driver_payment.sum(min_count=1)}
    if verified and len(both):
        out["Profit"] = (both.state_revenue - both.driver_payment).sum()
        out["Margin %"] = _pct(out["Profit"], both.state_revenue.sum())
    else:
        out["Profit"] = out["Margin %"] = np.nan
    out["Rows missing revenue/payment"] = int((rec.state_revenue.isna() & rec.driver_payment.notna()).sum())
    return out


def group_table(rec, by, verified=True):
    rows = []
    for k, g in rec.groupby(by, dropna=False):
        d = kpis(g, verified); d[by if isinstance(by, str) else "key"] = k; rows.append(d)
    t = pd.DataFrame(rows)
    t["Revenue/Trip"] = t.Revenue / t.Trips.replace(0, np.nan)
    first = [by] if isinstance(by, str) else ["key"]
    return t[first + [c for c in t.columns if c not in first]]


def state_table(rec, verified=True):
    t = group_table(rec, "state", verified)
    t["State"] = t["state"].map(lambda c: STATE_NAMES.get(c, c))
    tot = kpis(rec, verified); tot.update({"state": "TOTAL", "State": "TOTAL", "Revenue/Trip": tot["Revenue"] / tot["Trips"] if tot["Trips"] else np.nan})
    return pd.concat([t, pd.DataFrame([tot])], ignore_index=True).drop(columns="state")


def driver_table(rec, state=None, verified=True):
    r = rec[rec.state == state] if state else rec
    t = group_table(r.assign(dkey=r.driver.str.lower()), "dkey", verified).rename(columns={"dkey": "Driver"})
    return t.sort_values("Revenue", ascending=False).reset_index(drop=True)


def alaska_audit(rec, main, agreed_rate=45.0, tol=0.005):
    """(a) per-trip shortfall vs the state-report contract revenue (each trip has
    its own rate); (b) screen: First paid below the configurable agreed rate."""
    ak = rec[(rec.state == "AK") & rec.main_revenue.notna() & rec.state_revenue.notna()].copy()
    ak["shortfall"] = ak.state_revenue - ak.main_revenue
    under = ak[ak.shortfall > tol]
    a = {"Affected trips (vs state contract revenue)": len(under), "Expected revenue (state report)": under.state_revenue.sum(),
         "Actual revenue (First)": under.main_revenue.sum(), "Total owed": under.shortfall.sum()}
    m = main[(main.state == "AK") & main.main_amount.notna()]
    below = m[m.main_amount < agreed_rate - tol]
    b = {"Agreed rate": agreed_rate, "Trips paid below agreed rate": len(below),
         "Actual revenue of those trips": below.main_amount.sum(),
         "Shortfall vs agreed rate (flat)": (agreed_rate - below.main_amount).sum()}
    by_rate = under.groupby(["main_revenue", "state_revenue"]).agg(Trips=("shortfall", "size"), Shortfall=("shortfall", "sum")).reset_index()
    return a, b, by_rate, under
