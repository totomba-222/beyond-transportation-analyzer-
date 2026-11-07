"""Hatem's B.T. Analyzer - simple 3-page flow.  Run: streamlit run app.py
Full-featured version (filters, weekly/monthly, Alaska audit, mappings) is in app_full.py."""
import json
import pandas as pd
import streamlit as st

import app_logic as AL
import excel_generator as EG
import pdf_generator as PG
import simple_reports as SR
from config import DEFAULT_SETTINGS, STATE_NAMES

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="🚐", layout="wide")
MONEY_K = ("revenue", "payment", "profit", "difference", "paid")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def show(df, height=None):
    if df is None or len(df) == 0:
        st.info("No records."); return
    cfg = {}
    for c in df.columns:
        lc = str(c).lower()
        if pd.api.types.is_numeric_dtype(df[c]):
            if "%" in lc: cfg[c] = st.column_config.NumberColumn(format="%.1f%%")
            elif any(k in lc for k in MONEY_K) and not lc.startswith("trips"): cfg[c] = st.column_config.NumberColumn(format="$%.2f")
    kw = {"height": height} if height else {}      # newer Streamlit rejects height=None
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg, **kw)


def money(v): return "n/a" if pd.isna(v) else f"${v:,.2f}"


@st.cache_data(show_spinner="Reading files...")
def process(main_t, state_t, overrides_j, colmap_j):
    return AL.process_uploads(list(main_t), list(state_t), json.loads(json.dumps(DEFAULT_SETTINGS)), json.loads(overrides_j), None, json.loads(colmap_j))


def pdf_button(label, key, fn):
    if st.button(f"Generate PDF: {label}", key=f"gen_{key}"):
        st.session_state[f"pdf_{key}"] = fn()
    if st.session_state.get(f"pdf_{key}"):
        st.download_button(f"⬇️ Download PDF: {label}", st.session_state[f"pdf_{key}"], f"{key}.pdf", "application/pdf", key=f"dl_{key}")


st.title("Hatem's B.T. Analyzer")
ss = st.session_state; ss.setdefault("overrides", {}); ss.setdefault("colmap", {})
with st.sidebar:
    st.subheader("1) First / EverDriven reports")
    mfiles = st.file_uploader("Upload First or EverDriven reports", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="m")
    st.subheader("2) State reports")
    sfiles = st.file_uploader("Upload state reports (optional)", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="s")
    ak_rate = st.number_input("Official Alaska rate ($) used for the claim", value=45.0, step=0.5)
if not mfiles:
    st.info("Upload a First or EverDriven report to begin."); st.stop()

mt = tuple((f.name, f.getvalue()) for f in mfiles); stt = tuple((f.name, f.getvalue()) for f in (sfiles or []))
res = process(mt, stt, json.dumps(ss["overrides"]), json.dumps(ss["colmap"]))
for fname, sugg in res.unresolved_state_files:
    st.warning(f"The state of '{fname}' could not be detected (suggestion: {sugg or 'none'}). Choose it:")
    opts = [c for c in STATE_NAMES if c != "Unassigned"]
    ch = st.selectbox(f"State of {fname}", opts, index=opts.index(sugg) if sugg in opts else 0, key=f"st_{fname}")
    if st.button(f"Confirm {fname}", key=f"ap_{fname}"): ss["overrides"][fname] = ch; st.rerun()
for fname, fields in res.needs_mapping:
    heads = AL.peek_headers(dict(mt + stt)[fname], fname)
    st.error(f"'{fname}': could not identify the columns {fields}. Select them manually:")
    for fld in fields: ss["colmap"].setdefault(fname, {})[fld] = st.selectbox(f"{fname}: column for '{fld}'", heads, key=f"cm_{fname}_{fld}")
    if st.button(f"Apply {fname}", key=f"cmb_{fname}"): st.rerun()
for a, b in res.duplicate_uploads: st.warning(f"Duplicate file ignored: '{a}' is identical to '{b}'")
if res.main is None or res.main.empty:
    st.error("No trips found in the First/EverDriven files."); [st.write(w) for w in res.warnings]; st.stop()
main, rec = res.main, res.rec
has_state = bool(len(res.st))
n_un = int(main.state.isin(["Unassigned", "NEEDS REVIEW"]).sum())
if n_un: st.warning(f"{n_un:,} trips have no state assigned - shown under 'Unassigned'.")

page = st.sidebar.radio("Report", ["1) First / EverDriven report", "2) State reports (revenue, payments, profit)", "3) Discrepancy report"])
if has_state:
    with st.sidebar:
        st.divider(); pdf_button("Combined report (all 3)", "combined", lambda: PG.combined_report(main, rec, rate=ak_rate))
names = {v: k for k, v in STATE_NAMES.items()}

# ------------------------------------------------------------------ page 1
if page.startswith("1"):
    st.header("First / EverDriven report")
    o = SR.first_overview(main); c = st.columns(4)
    c[0].metric("Total trips", f"{o['Trips']:,}"); c[1].metric("Total revenue", money(o["Revenue"])); c[2].metric("Drivers", f"{o['Drivers']:,}"); c[3].metric("Miles", f"{o['Miles']:,.0f}")
    t = SR.first_state_table(main); st.subheader("Totals by state"); show(t)
    st.bar_chart(t[t.State != "TOTAL"].set_index("State")[["Revenue"]])
    st.subheader("Trip-by-trip detail")
    pick = st.selectbox("State", list(t.State[:-1])); d = SR.first_state_detail(main, names.get(pick, pick))
    st.caption(f"{len(d):,} trips - total {money(d['First Revenue'].sum())}"); show(d, 500)
    sheets = {"Overall": pd.DataFrame([o]), "By state": t}
    for code in main.state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.first_state_detail(main, code)
    st.download_button("⬇️ Excel (totals + detail per state)", EG.build_workbook(sheets), "First_Report.xlsx", XLSX)
    pdf_button("First / EverDriven report", "first_report", lambda: PG.first_report(main))

# ------------------------------------------------------------------ page 2
elif page.startswith("2"):
    st.header("State reports")
    if not has_state: st.info("Upload the state reports in the sidebar to see revenue, payments and profit."); st.stop()
    t = SR.state_financials(rec); show(t)
    if (t["Trips missing revenue"] > 0).any(): st.warning("Some state-report trips have no revenue. They are kept, not counted as zero, and excluded from profit.")
    st.bar_chart(t[t.State != "TOTAL"].set_index("State")[["Revenue", "Driver Payments", "Profit"]])
    pick = st.selectbox("State detail", list(t.State[:-1])); show(SR.state_trip_detail(rec, names.get(pick, pick)), 500)
    sheets = {"States": t}
    for code in rec[rec.state_source != ""].state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.state_trip_detail(rec, code)
    st.download_button("⬇️ Excel (state reports)", EG.build_workbook(sheets), "State_Reports.xlsx", XLSX)
    pdf_button("State report", "states", lambda: PG.states_financial_report(rec))

# ------------------------------------------------------------------ page 3
else:
    st.header("Differences between First and the state reports")
    if not has_state: st.info("Upload the state reports to see the differences."); st.stop()
    rec = SR.apply_rate_rule(rec, ak_rate)
    n_acc, amt_acc = SR.accepted_summary(rec)
    if n_acc: st.caption(f"{n_acc} Alaska trips paid at other rates (total ${abs(amt_acc):,.2f}) are treated as correct and excluded from the claim.")
    t = SR.discrepancy_summary(rec); show(t)
    if len(t): st.metric("Total price difference (First - State)", money(t[t.State == "TOTAL"].iloc[0]["Total difference (First - State)"]))
    sheets = {"Summary": t}
    for code in rec[rec.state_source != ""].state.unique():
        a, s, f = SR.discrepancy_sections(rec, code); nm = STATE_NAMES.get(code, code)
        if not (len(a) or len(s) or len(f)): continue
        with st.expander(f"{nm}: {max(len(a) - 1, 0)} price differences, {max(len(s) - 1, 0)} state-only trips, {max(len(f) - 1, 0)} First-only trips"):
            cl, ot = SR.claim_split(rec, code, ak_rate)
            if len(cl): st.markdown(f"**Claim to First: trips paid below the official ${ak_rate:,.2f} rate**"); show(cl)
            for ttl, df, sh in (("Trips with a different price", a, "price"), ("In the state report but not in First", s, "state-only"), ("In First but not in the state report", f, "First-only")):
                if len(df): st.markdown(f"**{ttl}**"); show(df); sheets[f"{code} {sh}"[:31]] = df
    st.download_button("⬇️ Excel (discrepancies)", EG.build_workbook(sheets), "Discrepancies.xlsx", XLSX)
    pdf_button("Discrepancy report", "disc", lambda: PG.discrepancy_report(rec, ak_rate))
