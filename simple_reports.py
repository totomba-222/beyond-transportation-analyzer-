"""Simple 3-stage reports built on the tested engine (no new matching logic)."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import STATE_NAMES

OK = ["EXACT MATCH", "MATCHED", "STATE REPORT NOT UPLOADED"]


def _nm(c): return STATE_NAMES.get(c, c)


def first_overview(main):
    return {"Trips": len(main), "Revenue": main.main_amount.sum(min_count=1), "Drivers": main.driver.nunique(),
            "Miles": main.miles.sum(min_count=1), "States": main.state.nunique()}


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
    out = d[["date", "driver_disp", "trip_id", "trip_name", "miles", "main_amount", "flags", "src_file", "src_row"]].copy()
    out.columns = ["Date", "Driver", "Trip ID", "Trip Name", "Miles", "First Revenue", "Data flags", "Source file", "Source row"]
    return out


def state_financials(rec):
    """Only states that have an uploaded state report. Trips = rows present in the state report."""
    r = rec[rec.state_source != ""]
    rows = []
    for code, g in r.groupby("state"):
        both = g[g.state_revenue.notna() & g.driver_payment.notna()]
        profit = (both.state_revenue - both.driver_payment).sum() if len(both) else np.nan
        rev = g.state_revenue.sum(min_count=1)
        rows.append({"State": _nm(code), "Trips": len(g), "Drivers": g.driver.str.lower().nunique(), "Revenue": rev,
                     "Driver Payments": g.driver_payment.sum(min_count=1), "Profit": profit,
                     "Margin %": profit / both.state_revenue.sum() * 100 if len(both) and both.state_revenue.sum() else np.nan,
                     "Trips missing revenue": int(g.state_revenue.isna().sum())})
    t = pd.DataFrame(rows).sort_values("Revenue", ascending=False)
    if len(t):
        tp = t.Profit.sum(min_count=1); br = r[r.state_revenue.notna() & r.driver_payment.notna()].state_revenue.sum()
        t = pd.concat([t, pd.DataFrame([{"State": "TOTAL", "Trips": t.Trips.sum(), "Drivers": r.driver.str.lower().nunique(), "Revenue": t.Revenue.sum(),
                                         "Driver Payments": t["Driver Payments"].sum(), "Profit": tp, "Margin %": tp / br * 100 if br else np.nan,
                                         "Trips missing revenue": t["Trips missing revenue"].sum()}])], ignore_index=True)
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
                     "Their driver payments": mm.driver_payment.sum(min_count=1), "Their miles": mm.state_miles.sum(min_count=1)})
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
