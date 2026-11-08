"""Hatem's B.T. Analyzer - Beyond Transportation. Streamlit UI over the tested core modules.
Run:  streamlit run app.py"""
import json
import pandas as pd
import streamlit as st

import app_logic as AL
import excel_generator as EG
import financial_calculations as F
import monthly_reports as M
import pdf_generator as PG
import weekly_reports as W
from config import DEFAULT_SETTINGS, STATE_NAMES

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="🚐", layout="wide")
st.markdown("""<style>.block-container{padding-top:1.2rem;max-width:1400px}
.kpi{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:12px 14px;margin-bottom:6px}
.kpi .l{color:#94a3b8;font-size:11px;text-transform:uppercase}.kpi .v{color:#f8fafc;font-size:22px;font-weight:700}
.kpi .s{color:#64748b;font-size:11px}</style>""", unsafe_allow_html=True)

MONEY_K = ("revenue", "payment", "profit", "difference", "shortfall", "owed", "expected", "actual", "cost")


def show(df, height=None):
    """Dataframe with USD formatting; missing values stay blank (never shown as 0)."""
    if df is None or len(df) == 0:
        st.info("No records in this view."); return
    cfg = {}
    for c in df.columns:
        lc = str(c).lower()
        if pd.api.types.is_numeric_dtype(df[c]):
            if "margin" in lc or "%" in lc: cfg[c] = st.column_config.NumberColumn(format="%.1f%%")
            elif any(k in lc for k in MONEY_K): cfg[c] = st.column_config.NumberColumn(format="$%.2f")
    kw = {"height": height} if height else {}      # newer Streamlit rejects height=None
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg, **kw)


def kpi(col, label, value, sub=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def money(v): return "n/a" if pd.isna(v) else f"${v:,.2f}"


@st.cache_data(show_spinner="Reading and reconciling files...")
def process(main_t, state_t, settings_j, overrides_j, map_j, colmap_j):
    return AL.process_uploads(list(main_t), list(state_t), json.loads(settings_j), json.loads(overrides_j),
                              json.loads(map_j), json.loads(colmap_j))


@st.cache_data(show_spinner=False)
def workbook(rec, main, excluded, control, rate):
    a, b, by_rate, under = F.alaska_audit(rec, main, rate)
    ex = rec[~rec.audit_status.isin(["EXACT MATCH", "MATCHED", "STATE REPORT NOT UPLOADED", "MONITOR PAYMENT"])]
    return EG.build_workbook({"State Summary": F.state_table(rec), "Drivers": F.driver_table(rec), "Reconciliation": rec,
                              "Exceptions": ex, "Alaska Shortfall": under, "Excluded Rows": excluded, "Control Totals": control,
                              "Monthly": M.monthly_table(rec)})


# ------------------------------------------------------------------ sidebar
st.title("Hatem's B.T. Analyzer")
st.caption("Beyond Transportation - Financial & Operations Audit")
with st.sidebar:
    st.subheader("1 · Main company reports")
    st.caption("First Student / EverDriven (xlsx, xls, csv, pdf)")
    mfiles = st.file_uploader("Main reports", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="m")
    st.subheader("2 · State reports")
    sfiles = st.file_uploader("State reports", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="s")
    st.subheader("Settings")
    rate = st.number_input("Alaska agreed rate ($)", value=float(DEFAULT_SETTINGS["alaska_agreed_rate"]), step=0.5)
    verified = st.checkbox("Revenue/payment definitions verified (enables profit)", value=True)
    st.caption("State 'Revenue' equals First NET PAY on every non-Alaska trip checked; Alaska differs by the underpayment.")

if not mfiles:
    st.info("Upload at least one main-company report (First Student or EverDriven) to begin. State reports can be added afterwards.")
    st.stop()

ss = st.session_state
ss.setdefault("overrides", {}); ss.setdefault("editable_map", {}); ss.setdefault("colmap", {})
mt = tuple((f.name, f.getvalue()) for f in mfiles)
stt = tuple((f.name, f.getvalue()) for f in (sfiles or []))
res = process(mt, stt, json.dumps(DEFAULT_SETTINGS), json.dumps(ss["overrides"]), json.dumps(ss["editable_map"]), json.dumps(ss["colmap"]))

# ---- resolve uncertain state / mapping problems (never silently ignored)
for fname, sugg in res.unresolved_state_files:
    st.warning(f"State of '{fname}' could not be detected. Suggestion from drivers: {sugg or 'none'}.")
    opts = [c for c in STATE_NAMES if c != "Unassigned"]
    ch = st.selectbox(f"State for {fname}", opts, index=opts.index(sugg) if sugg in opts else 0, key=f"st_{fname}")
    if st.button(f"Apply state for {fname}", key=f"ap_{fname}"):
        ss["overrides"][fname] = ch; st.rerun()
for fname, fields in res.needs_mapping:
    heads = AL.peek_headers(dict(mt + stt)[fname], fname)
    st.error(f"'{fname}': cannot identify {fields}. Map the columns manually.")
    for fld in fields:
        pick = st.selectbox(f"{fname}: column for '{fld}'", heads, key=f"cm_{fname}_{fld}")
        ss["colmap"].setdefault(fname, {})[fld] = pick
    if st.button(f"Apply mapping for {fname}", key=f"cmb_{fname}"): st.rerun()
for a, b in res.duplicate_uploads:
    st.warning(f"Duplicate upload ignored: '{a}' has identical content to '{b}'.")
if res.rec is None or res.rec.empty:
    st.error("No trips could be read."); [st.write(w) for w in res.warnings]; st.stop()

rec_all = res.rec
# ------------------------------------------------------------------ filters
with st.sidebar:
    st.subheader("Filters")
    dmin, dmax = rec_all.date.min(), rec_all.date.max()
    dr = st.date_input("Trip date range", value=(dmin.date(), dmax.date())) if pd.notna(dmin) else None
    f_state = st.multiselect("State", sorted(rec_all.state.dropna().unique()))
    f_region = st.multiselect("Region", sorted(rec_all.region.dropna().unique()))
    f_driver = st.multiselect("Driver", sorted(rec_all.driver.dropna().unique()))
    f_status = st.multiselect("Audit status", sorted(rec_all.audit_status.unique()))
    f_prov = st.multiselect("Main source", sorted(x for x in rec_all.provider.dropna().unique() if x))
rec = AL.apply_filters(rec_all, dr, f_state, f_region, f_driver, f_status, f_prov)
st.sidebar.caption(f"Showing {len(rec):,} of {len(rec_all):,} reconciliation rows")

tabs = st.tabs(["Dashboard", "States & Regions", "Drivers", "Reconciliation", "Exceptions", "Weekly", "Monthly", "Alaska audit", "Downloads", "Data quality & mappings"])

# ---------------------------------------------------------------- Dashboard
with tabs[0]:
    k = F.kpis(rec, verified)
    UNM = ["MISSING FROM STATE REPORT", "MISSING FROM MAIN REPORT", "UNMATCHED DRIVER"]
    masks = {
        "Trips (main report)": rec.main_revenue.notna(), "Company revenue (main)": rec.main_revenue.notna(),
        "State-report revenue": rec.state_revenue.notna(), "Driver payments": rec.driver_payment.notna(),
        "Profit rows (state revenue AND payment present)": rec.state_revenue.notna() & rec.driver_payment.notna(),
        "Unmatched trips": rec.audit_status.isin(UNM), "Duplicate trips": rec.audit_status.eq("DUPLICATE TRIP"),
        "Revenue discrepancies": rec.audit_status.eq("REVENUE MISMATCH"), "Payment discrepancies": rec.audit_status.eq("PAYMENT MISMATCH"),
        "Unassigned state": rec.state.isin(["Unassigned", "NEEDS REVIEW"]), "Needs manual review": rec.audit_status.eq("NEEDS MANUAL REVIEW"),
        "Missing revenue (state report)": rec.audit_status.isin(UNM) & rec.state_revenue.isna() & rec.driver_payment.notna()}
    c = st.columns(5)
    kpi(c[0], "Trips", f"{k['Trips']:,}"); kpi(c[1], "Drivers", f"{k['Drivers']:,}"); kpi(c[2], "Company revenue", money(k["Revenue"]), "main report")
    kpi(c[3], "State-report revenue", money(k["State Revenue"])); kpi(c[4], "Driver payments", money(k["Driver Payments"]), "state reports")
    c = st.columns(5)
    kpi(c[0], "Gross profit", money(k["Profit"]) if verified else "n/a", "state revenue - driver payment")
    kpi(c[1], "Profit margin", "n/a" if pd.isna(k["Margin %"]) else f"{k['Margin %']:.1f}%", "profit / state revenue")
    kpi(c[2], "Miles", f"{k['Miles']:,.0f}"); kpi(c[3], "Unmatched trips", f"{int(masks['Unmatched trips'].sum()):,}"); kpi(c[4], "Duplicate trips", f"{int(masks['Duplicate trips'].sum()):,}")
    c = st.columns(4)
    kpi(c[0], "Revenue discrepancies", f"{int(masks['Revenue discrepancies'].sum()):,}", money(rec[masks['Revenue discrepancies']].revenue_difference.sum()) + " net")
    kpi(c[1], "Payment discrepancies", f"{int(masks['Payment discrepancies'].sum()):,}"); kpi(c[2], "Unassigned state", f"{int(masks['Unassigned state'].sum()):,}")
    kpi(c[3], "Rows missing revenue", f"{int(masks['Missing revenue (state report)'].sum()):,}", "kept, not zeroed")
    if (rec.audit_status == "STATE REPORT NOT UPLOADED").any():
        n = int((rec.audit_status == "STATE REPORT NOT UPLOADED").sum())
        st.warning(f"{n:,} trips belong to states with no uploaded state report: driver payments and profit are unavailable for them (not estimated).")
    stt_ = F.state_table(rec, verified); st.markdown("#### By state")
    show(stt_.drop(columns=["Rows missing revenue/payment"]))
    ch = stt_[stt_.State != "TOTAL"].set_index("State")[["Revenue", "Driver Payments", "Profit"]]
    st.bar_chart(ch)
    with st.expander("Traceability - show the source rows behind a figure"):
        which = st.selectbox("Figure", list(masks))
        show(rec[masks[which]][["state", "driver", "date", "trip_name", "main_revenue", "state_revenue", "driver_payment", "audit_status", "main_source", "state_source"]])

# ---------------------------------------------------------------- States
with tabs[1]:
    reg = F.group_table(rec, "region", verified).drop(columns=["Rows missing revenue/payment"])
    st.markdown("#### Regions (Arizona is an operational assignment to S.CA)"); show(reg)
    code = st.selectbox("State detail", sorted(rec.state.dropna().unique()), format_func=lambda c: STATE_NAMES.get(c, c))
    r = rec[rec.state == code]; kk = F.kpis(r, verified)
    c = st.columns(5); kpi(c[0], "Trips", f"{kk['Trips']:,}"); kpi(c[1], "Revenue", money(kk["Revenue"])); kpi(c[2], "Driver payments", money(kk["Driver Payments"]))
    kpi(c[3], "Profit", money(kk["Profit"])); kpi(c[4], "Margin", "n/a" if pd.isna(kk["Margin %"]) else f"{kk['Margin %']:.1f}%")
    st.markdown("Reconciliation status"); show(r.audit_status.value_counts().rename_axis("Status").reset_index(name="Trips"))
    show(r[["date", "driver", "main_trip_id", "trip_name", "main_miles", "main_revenue", "state_revenue", "driver_payment", "profit", "revenue_difference", "audit_status"]])

# ---------------------------------------------------------------- Drivers
with tabs[2]:
    dstate = st.selectbox("State", ["All"] + sorted(rec.state.dropna().unique()), key="dst")
    dt = F.driver_table(rec, None if dstate == "All" else dstate, verified).drop(columns=["Rows missing revenue/payment"])
    sort = st.selectbox("Sort by", ["Revenue", "Profit", "Margin %", "Trips"]); show(dt.sort_values(sort, ascending=False))

# ---------------------------------------------------------------- Reconciliation
with tabs[3]:
    st.caption("Revenue Difference = main revenue - state revenue. Profit = state revenue - driver payment. Margin = profit / state revenue x 100.")
    cols = ["state", "region", "driver", "date", "trip_name", "main_trip_id", "state_trip_id", "main_miles", "state_miles", "main_revenue", "state_revenue",
            "driver_payment", "revenue_difference", "profit", "margin_pct", "match_tier", "confidence", "audit_status", "notes", "main_source", "state_source"]
    show(rec[[c for c in cols if c in rec.columns]], height=600)

# ---------------------------------------------------------------- Exceptions
with tabs[4]:
    exc_cols = ["state", "driver", "date", "trip_name", "main_revenue", "state_revenue", "driver_payment", "revenue_difference", "audit_status", "notes", "main_source", "state_source"]
    for title, sts in (("Missing from state report", ["MISSING FROM STATE REPORT"]), ("Missing from main report", ["MISSING FROM MAIN REPORT"]), ("Duplicate trips", ["DUPLICATE TRIP"]),
                       ("Unmatched drivers", ["UNMATCHED DRIVER"]), ("Revenue mismatches", ["REVENUE MISMATCH"]), ("Payment mismatches", ["PAYMENT MISMATCH"]),
                       ("Mileage mismatches", ["MILEAGE MISMATCH"]), ("Needs manual review", ["NEEDS MANUAL REVIEW"])):
        d = rec[rec.audit_status.isin(sts)]
        with st.expander(f"{title} ({len(d):,})", expanded=len(d) > 0 and len(d) < 60):
            show(d[exc_cols])

# ---------------------------------------------------------------- Weekly
with tabs[5]:
    weeks = W.available_weeks(rec_all)
    if not weeks: st.info("No dated trips.")
    else:
        wk = st.selectbox("Reporting week (Mon-Sun)", weeks[::-1], format_func=lambda d: f"{d:%Y-%m-%d} to {d + pd.Timedelta(days=6):%Y-%m-%d}")
        by = st.selectbox("Compare by", ["Company", "state", "provider", "driver"])
        t, ci, pi, warns = W.weekly_report(rec, wk, None if by == "Company" else by)
        st.write(f"Current: **{ci['start']:%Y-%m-%d} - {ci['end']:%Y-%m-%d}** ({ci['days_with_trips']} days with trips) | Previous: {pi['start']:%Y-%m-%d} - {pi['end']:%Y-%m-%d}")
        for w in warns: st.warning(w)
        show(t)

# ---------------------------------------------------------------- Monthly
with tabs[6]:
    mt_ = M.monthly_table(rec)
    if mt_.empty: st.info("No dated trips.")
    else:
        show(mt_.drop(columns=["Rows missing revenue/payment"], errors="ignore")); st.line_chart(mt_.set_index("Month")[["Revenue", "Driver Payments", "Profit"]])
        months = list(mt_.Month)
        if len(months) >= 2:
            m1 = st.selectbox("Month A", months, index=0); m2 = st.selectbox("Month B", months, index=len(months) - 1); show(M.compare_months(rec, m1, m2))
        else: st.caption("Only one month in the data - month-over-month comparison needs a second month.")
        show(M.monthly_table(rec, by="state").drop(columns=["Rows missing revenue/payment"], errors="ignore"))

# ---------------------------------------------------------------- Alaska
with tabs[7]:
    a, b, by_rate, under = F.alaska_audit(rec_all, res.main, rate)
    st.markdown("#### A. Per-trip shortfall vs the contract revenue in the Alaska state report")
    c = st.columns(4); kpi(c[0], "Affected trips", f"{a['Affected trips (vs state contract revenue)']:,}"); kpi(c[1], "Expected revenue", money(a["Expected revenue (state report)"]))
    kpi(c[2], "Actual (First)", money(a["Actual revenue (First)"])); kpi(c[3], "Total owed", money(a["Total owed"]))
    show(by_rate)
    st.markdown(f"#### B. Screen against the configured agreed rate (${rate:,.2f})")
    st.write({k_: (round(float(v), 2) if not isinstance(v, int) else v) for k_, v in b.items()})
    st.caption("Section A uses each trip's own contract rate from the state report; B assumes one flat rate and can understate the amount.")
    show(under[["driver", "date", "trip_name", "main_revenue", "state_revenue", "shortfall", "main_source", "state_source"]] if len(under) else under)

# ---------------------------------------------------------------- Downloads
with tabs[8]:
    st.download_button("⬇️ Excel workbook (all sections)", workbook(rec, res.main, res.excluded, res.control, rate), "BT_Audit_Report.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    kinds = {"Consolidated Company Report": lambda: PG.consolidated(rec, res.main, verified), "First Student Audit Report": lambda: PG.provider_audit(rec, "FIRST", "First Student"),
             "EverDriven Audit Report": lambda: PG.provider_audit(rec, "EVERDRIVEN", "EverDriven"),
             "State Financial Report": lambda: PG.state_report(rec, pcode, False), "State Trip Details": lambda: PG.state_report(rec, pcode, True),
             "Driver Performance Report": lambda: PG.driver_report(rec), "Weekly Comparison Report": lambda: PG.weekly(rec_all),
             "Monthly Financial Report": lambda: PG.monthly(rec), "Revenue Reconciliation Report": lambda: PG.reconciliation(rec),
             "Exceptions and Discrepancies Report": lambda: PG.exceptions(rec, res.excluded, res.control), "Alaska Rate Audit": lambda: PG.alaska(rec_all, res.main, rate)}
    kind = st.selectbox("PDF report", list(kinds))
    pcode = st.selectbox("State (for state reports)", sorted(rec.state.dropna().unique()), format_func=lambda c: STATE_NAMES.get(c, c))
    if st.button("Generate PDF"):
        ss["pdf"] = (kind, kinds[kind]())
    if ss.get("pdf"):
        st.download_button(f"⬇️ Download PDF: {ss['pdf'][0]}", ss["pdf"][1], f"{ss['pdf'][0].replace(' ', '_')}.pdf", "application/pdf")

# ---------------------------------------------------------------- Data quality
with tabs[9]:
    st.markdown("#### Import warnings"); [st.write("• " + w) for w in res.warnings] or st.caption("none")
    st.markdown("#### Rows excluded from trips (totals / sub-totals / blank-driver rows)"); show(res.excluded)
    st.markdown("#### Control totals that disagree with their own detail rows"); show(res.control[res.control.difference.abs() > 0.005] if len(res.control) else res.control)
    st.markdown("#### Editable driver → state mapping (your edits override the built-in map; uploaded state reports override both)")
    ed = st.data_editor(AL.editable_map_frame(ss["editable_map"]), num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("Apply mapping edits"):
        ss["editable_map"] = {r.driver: r.state for r in ed.itertuples() if r.driver and r.state}; st.rerun()
    st.markdown("#### Classification evidence"); show(res.main.groupby(["state", "state_source"]).size().reset_index(name="Trips"))
