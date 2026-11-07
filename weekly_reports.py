"""Weekly comparison on ACTUAL trip dates (Mon-Sun weeks), never upload dates."""
import numpy as np
import pandas as pd
from financial_calculations import kpis

KPI_ORDER = ["Trips", "Drivers", "Miles", "Revenue", "Driver Payments", "Profit", "Margin %"]


def week_start(d):
    d = pd.Timestamp(d).normalize()
    return d - pd.Timedelta(days=d.weekday())


def available_weeks(rec):
    d = rec.date.dropna()
    return sorted({week_start(x) for x in d})


def week_slice(rec, ws):
    ws = pd.Timestamp(ws); we = ws + pd.Timedelta(days=6)
    s = rec[(rec.date >= ws) & (rec.date <= we + pd.Timedelta(hours=23, minutes=59))]
    return s, ws, we


def period_info(s, ws, we):
    if s.empty:
        return {"start": ws, "end": we, "first_trip": None, "last_trip": None, "days_with_trips": 0, "complete": False}
    days = s.date.dt.normalize().nunique()
    return {"start": ws, "end": we, "first_trip": s.date.min(), "last_trip": s.date.max(), "days_with_trips": days,
            "complete": days >= 5}      # a full operating week = at least Mon-Fri


def compare(cur, prev):
    kc, kp = kpis(cur), kpis(prev) if len(prev) else {k: np.nan for k in KPI_ORDER}
    rows = []
    for k in KPI_ORDER:
        c, p = kc.get(k, np.nan), kp.get(k, np.nan)
        diff = c - p if pd.notna(c) and pd.notna(p) else np.nan
        pct = diff / abs(p) * 100 if pd.notna(diff) and p not in (0, np.nan) and p else np.nan
        rows.append({"KPI": k, "Current Week": c, "Previous Week": p, "Difference": diff, "Change %": pct})
    return pd.DataFrame(rows)


def weekly_report(rec, week=None, by=None):
    """Returns (comparison, cur_info, prev_info, warnings). `by` in {None,'state','driver','provider'}."""
    weeks = available_weeks(rec)
    if not weeks:
        return None, None, None, ["No dated trips - weekly comparison impossible."]
    ws = pd.Timestamp(week) if week is not None else weeks[-1]
    cur, ws, we = week_slice(rec, ws)
    prev, pws, pwe = week_slice(rec, ws - pd.Timedelta(days=7))
    ci, pi = period_info(cur, ws, we), period_info(prev, pws, pwe)
    warns = []
    if prev.empty: warns.append(f"No trips in previous week ({pws:%Y-%m-%d} to {pwe:%Y-%m-%d}); comparison not available.")
    for nm, i in (("Current", ci), ("Previous", pi)):
        if not i["complete"] and i["days_with_trips"]: warns.append(f"{nm} week {i['start']:%Y-%m-%d} to {i['end']:%Y-%m-%d} is incomplete ({i['days_with_trips']} days with trips).")
    if by is None:
        return compare(cur, prev), ci, pi, warns
    parts = []
    for k in sorted(set(cur[by].dropna()) | set(prev[by].dropna())):
        t = compare(cur[cur[by] == k], prev[prev[by] == k]); t.insert(0, by, k); parts.append(t)
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), ci, pi, warns
