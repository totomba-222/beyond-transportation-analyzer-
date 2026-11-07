import numpy as np
import pandas as pd
from financial_calculations import kpis


def month_key(rec):
    return rec.date.dt.to_period("M").astype(str)


def monthly_table(rec, by=None):
    r = rec[rec.date.notna()].assign(Month=lambda x: month_key(x))
    rows = []
    for (m, *k), g in r.groupby(["Month"] + ([by] if by else [])):
        d = kpis(g); d["Month"] = m
        if by: d[by] = k[0]
        d["Avg Revenue/Trip"] = d["Revenue"] / d["Trips"] if d["Trips"] else np.nan
        both = g[g.state_revenue.notna() & g.driver_payment.notna()]
        d["Avg Cost/Trip"] = both.driver_payment.mean() if len(both) else np.nan
        rows.append(d)
    t = pd.DataFrame(rows)
    if t.empty: return t
    keys = (["Month"] + ([by] if by else []))
    t = t.sort_values(keys)
    for c in ("Revenue", "Trips", "Profit"):
        t[f"{c} MoM %"] = (t.groupby(by)[c] if by else t[c]).pct_change() * 100
    if "state" not in t.columns and by is None:
        pass
    return t.reset_index(drop=True)


def compare_months(rec, m1, m2):
    a, b = kpis(rec[month_key(rec) == m1]), kpis(rec[month_key(rec) == m2])
    return pd.DataFrame([{"KPI": k, m1: a[k], m2: b[k], "Difference": b[k] - a[k] if pd.notna(a[k]) and pd.notna(b[k]) else np.nan,
                          "Change %": (b[k] - a[k]) / abs(a[k]) * 100 if pd.notna(a[k]) and pd.notna(b[k]) and a[k] else np.nan}
                         for k in ("Trips", "Drivers", "Miles", "Revenue", "Driver Payments", "Profit", "Margin %")])
