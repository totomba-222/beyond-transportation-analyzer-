"""Hatem's B.T. Analyzer - simple 3-page flow.  Run: streamlit run app.py
Full-featured version (filters, weekly/monthly, Alaska audit, mappings) is in app_full.py."""
import json
import pandas as pd
import streamlit as st

import app_logic as AL
import history as HI
import history_store as HS
import weekly_reports as W
import classification as C
import excel_generator as EG
import pdf_generator as PG
import ratebook as RB
import pay_policy as PP
import simple_reports as SR
from config import DEFAULT_SETTINGS, STATE_NAMES

st.set_page_config(page_title="Beyond Transportation | Audit Dashboard", page_icon="🚐", layout="wide")
MONEY_K = ("revenue", "payment", "profit", "difference", "paid")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


_TBL = [0]
st.markdown("""
<style>
[data-testid='stElementToolbar']{display:none !important}
:root{--navy:#153B5B;--teal:#0F766E;--gold:#D39B2A}
.main .block-container{padding-top:2rem;max-width:1500px}
h1,h2,h3{color:var(--navy)!important;letter-spacing:-.02em}
[data-testid='stMetric']{color:#153B5B!important}
[data-testid='stMetricLabel'],[data-testid='stMetricLabel'] *{color:#35546d!important;opacity:1!important;font-weight:600!important}
[data-testid='stMetricValue'],[data-testid='stMetricValue'] *{color:#153B5B!important;opacity:1!important;font-weight:700!important}
[data-testid='stMetricDelta'],[data-testid='stMetricDelta'] *{opacity:1!important}
[data-testid='stMetric']{background:linear-gradient(135deg,#f7fafc,#eef5f7);border:1px solid #d9e4ea;border-left:4px solid var(--teal);padding:12px 14px;border-radius:10px;box-shadow:0 2px 8px rgba(21,59,91,.06)}
[data-testid='stDataFrame']{border:1px solid #d9e4ea;border-radius:10px;overflow:hidden}
section[data-testid='stSidebar']{background:linear-gradient(180deg,#153B5B 0%,#1d4d6f 100%)}
section[data-testid='stSidebar'] *{color:white}
.stButton>button,.stDownloadButton>button{border-radius:8px;border:1px solid #b8d5d2;font-weight:600}
@media (prefers-color-scheme: dark){
  h1,h2,h3{color:#8ed0ee!important}
  .main .block-container p,.main .block-container label,.main .block-container [data-testid='stCaptionContainer']{color:#d7e5ed!important}
  .main .block-container [data-testid='stExpander'] summary{color:#d7e5ed!important}
}
</style>
""", unsafe_allow_html=True)


def _display_total(df):
    """Keep the app compatible with older simple_reports.py deployments."""
    if df is None or len(df) == 0:
        return df
    helper = getattr(SR, "ensure_total", None)
    if callable(helper):
        return helper(df)
    labels = df.iloc[:, 0].astype(str).str.strip().str.upper()
    if labels.isin(["TOTAL", "GRAND TOTAL"]).any():
        return df.reset_index(drop=True)
    row = {c: None for c in df.columns}
    row[df.columns[0]] = "TOTAL"
    for c in df.columns[1:]:
        if pd.api.types.is_numeric_dtype(df[c]):
            lc = str(c).lower()
            row[c] = 100.0 if "%" in lc and (lc.endswith("%") or "share" in lc) else (None if "%" in lc else df[c].sum(min_count=1))
    return pd.concat([df.reset_index(drop=True), pd.DataFrame([row])], ignore_index=True)


def show(df, height=None, title=None):
    # Keep TOTAL rows and add one when a numeric report has none. Totals are never detail trips.
    if df is not None and len(df):
        df = _display_total(df)
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
    if title:
        _TBL[0] += 1
        try: st.download_button("⬇️ PDF: " + title[:60], PG.table_pdf(df.head(600), title, "Table"), f"{title[:40].replace(' ', '_').replace('/', '-')}.pdf", "application/pdf", key=f"tpdf_{_TBL[0]}")
        except Exception: pass


def money(v): return "n/a" if pd.isna(v) else f"${v:,.2f}"


@st.cache_data(show_spinner="Reading files...")
def process(main_t, state_t, overrides_j, colmap_j, map_j):
    return AL.process_uploads(list(main_t), list(state_t), json.loads(json.dumps(DEFAULT_SETTINGS)), json.loads(overrides_j), json.loads(map_j), json.loads(colmap_j))


def pdf_button(label, key, fn):
    if st.button(f"Generate PDF: {label}", key=f"gen_{key}"):
        st.session_state[f"pdf_{key}"] = fn()
    if st.session_state.get(f"pdf_{key}"):
        st.download_button(f"⬇️ Download PDF: {label}", st.session_state[f"pdf_{key}"], f"{key}.pdf", "application/pdf", key=f"dl_{key}")


st.title("Beyond Transportation | Financial & Operations Audit")
st.caption("Professional financial and operations audit dashboard")
ss = st.session_state; ss.setdefault("overrides", {}); ss.setdefault("colmap", {}); ss.setdefault("editable_map", {})
with st.sidebar:
    st.subheader("1) First / EverDriven reports")
    mfiles = st.file_uploader("Upload First or EverDriven reports", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="m")
    st.subheader("2) State reports")
    sfiles = st.file_uploader("Upload state reports (optional)", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="s")
    ak_rate = st.number_input("Official Alaska rate ($)", value=45.0, step=0.5)
    err_price = st.number_input("Lowest price paid in error ($) - trips at/above it ending in .50 are claimed", value=42.5, step=0.5)
    st.subheader("3) Saved driver map (optional)")
    mapfile = st.file_uploader("CSV with columns driver,state", type=["csv"], key="map")
    st.subheader("4) Previous weeks history (optional)")
    histfile = st.file_uploader("Upload weekly_history.csv from the previous week", type=["csv"], key="hist")
if not mfiles:
    st.info("Upload a First or EverDriven report to begin."); st.stop()

mt = tuple((f.name, f.getvalue()) for f in mfiles); stt = tuple((f.name, f.getvalue()) for f in (sfiles or []))
csv_map = {}
if mapfile:
    try:
        _m = pd.read_csv(mapfile); csv_map = {str(r.driver): str(r.state) for r in _m.itertuples() if str(r.state) in STATE_NAMES}
    except Exception as e:
        st.warning(f"Driver map CSV could not be read: {e}")
full_map = {**csv_map, **ss["editable_map"]}            # assignments made in this session win over the saved CSV
res = process(mt, stt, json.dumps(ss["overrides"]), json.dumps(ss["colmap"]), json.dumps(full_map))
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
for _w in res.warnings:
    if "date far" in _w or "other provider" in _w or "control" in _w.lower(): st.warning(_w)
main, rec = res.main, SR.apply_rate_rule(res.rec, ak_rate, err_price)
_all_main, _all_rec = main.copy(), rec.copy()
for _df in (main, rec):                      # newer pandas keeps all-empty / mixed dates as text: always real datetimes (history, weekly and monthly reports use .dt)
    if "date" in _df.columns: _df["date"] = pd.to_datetime(_df["date"], errors="coerce")     # rule applied everywhere: only the error-price trips stay REVENUE MISMATCH
has_state = bool(len(rec) and (rec.state_source != "").any())
n_un = int(main.state.isin(["Unassigned", "NEEDS REVIEW"]).sum())
if n_un:
    sug = C.suggest_states(main, res.st)
    st.warning(f"{n_un:,} trips have no state yet. These drivers are not in any state report or in the saved driver map. "
               "Uploading the state reports assigns them automatically; or assign them below.")
    with st.expander(f"Assign {len(sug)} drivers without a state", expanded=True):
        show(sug.drop(columns="driver_key"))
        opts = ["(leave unassigned)"] + [c for c in STATE_NAMES if c != "Unassigned"]; picks = {}
        for r_ in sug.to_dict("records"):
            dflt = r_["Suggested state"] if r_["Suggested state"] in opts else opts[0]       # suggestion pre-selected, never applied without your click
            picks[r_["driver_key"]] = st.selectbox(f"{r_['Driver']} ({r_['Trips']} trips)", opts, index=opts.index(dflt), key=f"asg_{r_['driver_key']}")
        if st.button("Apply assignments"):
            for k_, v_ in picks.items():
                if v_ != opts[0]: ss["editable_map"][k_] = v_
            st.rerun()
_auto = main[main.state_source.str.startswith("trip route")]
if len(_auto):
    with st.expander(f"{_auto.driver.nunique()} new drivers were assigned automatically from the schools on their routes - please verify"):
        _t = _auto.groupby(["driver_disp", "state", "state_source"]).agg(Trips=("main_amount", "size"), Revenue=("main_amount", "sum")).reset_index()
        show(_t.rename(columns={"driver_disp": "Driver", "state": "State", "state_source": "Evidence"}))
        st.caption("Wrong? Assign the driver in the panel above (your assignment overrides this) or upload the state report, which always wins.")
if full_map:
    st.sidebar.download_button("⬇️ Save driver map (CSV)", pd.DataFrame(sorted(full_map.items()), columns=["driver", "state"]).to_csv(index=False), "driver_map.csv", "text/csv")

# Optional report filters are applied only after upload parsing and state assignment.
with st.sidebar:
    st.subheader("5) Report filters (optional)")
    _driver_options = sorted(main.driver_disp.dropna().astype(str).str.strip().unique(), key=str.casefold)
    _provider_options = sorted(main.provider.map(SR.PROVIDER_NAMES).fillna(main.provider).dropna().astype(str).unique(), key=str.casefold)
    selected_drivers = st.multiselect("Drivers", _driver_options, default=[], help="Leave empty to include every driver.")
    selected_providers = st.multiselect("Providers", _provider_options, default=[], help="Leave empty to include every provider.")

def _filter_values(df, column, selected):
    if not selected or column not in df.columns:
        return pd.Series(True, index=df.index)
    wanted = {str(v).strip().casefold() for v in selected}
    return df[column].fillna("").astype(str).str.strip().str.casefold().isin(wanted)

if selected_drivers or selected_providers:
    _main_driver_col = "driver_disp" if "driver_disp" in main.columns else "driver"
    _rec_driver_col = "driver_disp" if "driver_disp" in rec.columns else "driver"
    _main_provider = main.provider.map(SR.PROVIDER_NAMES).fillna(main.provider).astype(str)
    _rec_provider = rec.provider.map(SR.PROVIDER_NAMES).fillna(rec.provider).astype(str) if "provider" in rec.columns else pd.Series("", index=rec.index)
    _driver_mask = _filter_values(main, _main_driver_col, selected_drivers)
    _rec_driver_mask = _filter_values(rec, _rec_driver_col, selected_drivers)
    _provider_mask = _main_provider.str.strip().str.casefold().isin({str(v).strip().casefold() for v in selected_providers}) if selected_providers else pd.Series(True, index=main.index)
    _rec_provider_mask = _rec_provider.str.strip().str.casefold().isin({str(v).strip().casefold() for v in selected_providers}) if selected_providers else pd.Series(True, index=rec.index)
    main = main.loc[_driver_mask & _provider_mask].reset_index(drop=True)
    rec = rec.loc[_rec_driver_mask & _rec_provider_mask].reset_index(drop=True)
    if len(main) == 0:
        st.warning("The selected filters returned no trips. Clear one or more filters to generate a report.")
        st.stop()
    st.sidebar.caption(f"Active filter: {len(main):,} trips selected")

_prev = HS.load()
if histfile:
    try:
        _uploaded_history = HI.from_csv(histfile)
        _prev = HI.merge(_prev, _uploaded_history)
    except Exception as e: st.warning(f"History CSV could not be read: {e}")
@st.cache_data(show_spinner="Checking prices and pay policy...")
def _week_extras(_main, _rec, _book, rate, err, key):
    import simple_pdf as _SP
    return _SP.week_extras(_main, _rec, _book, rate, err)       # per state: trips paid below the agreed price / above the pay policy (saved in the history for next week's comparison)


try:
    _history_has_state = bool(len(_all_rec) and (_all_rec.state_source != "").any())
    _ex = _week_extras(_all_main, _all_rec, RB.load(), ak_rate, err_price, (mt, stt, json.dumps(ss["overrides"]), json.dumps(ss["colmap"]), json.dumps(full_map))) if _history_has_state else {}
except Exception:
    _ex = {}
_cur_rows = HI.add_extras(HI.weekly_rows(_all_rec), _ex) if len(_all_rec) else pd.DataFrame(columns=HI.COLS)
hist = HI.merge(_prev, _cur_rows)
try:
    HS.save(hist)
except Exception as e:
    st.sidebar.warning(f"Weekly history could not be saved automatically: {e}")
st.sidebar.caption("The app saves weekly totals during normal reruns. For reliable retention after a cloud restart or redeploy, download weekly_history.csv and upload it again next week.")
st.sidebar.download_button("⬇️ Download weekly history (CSV)", HI.to_csv(hist), "weekly_history.csv", "text/csv")
page = st.sidebar.radio("Report", [f"1) {SR.provider_label(main)} report", "2) State reports (revenue, payments, profit)", "3) Discrepancy report", "4) Weekly comparison", "5) Monthly report", "6) Monthly comparison", "7) Driver pay policy review", "8) Full report per state", "9) Driver report", "10) Consolidated summary"])
with st.sidebar:
    st.divider()
    if has_state: pdf_button("Combined report (all 3)", "combined", lambda: PG.combined_report(main, rec, rate=ak_rate, adjustments=res.adjustments, err=err_price))
    pdf_button("MASTER report (everything in one file)", "master", lambda: PG.master_report(main, rec, hist, RB.load(), rate=ak_rate, err=err_price, adjustments=res.adjustments))
    pdf_button("Consolidated summary (company / provider / state)", "consolidated_summary", lambda: PG.consolidated_summary_report(main, rec, RB.load(), ak_rate, err_price))
    if has_state: pdf_button("State report - 3 tables", "state_three_tables", lambda: PG.state_three_table_report(main, rec, RB.load(), ak_rate, err_price))
names = {v: k for k, v in STATE_NAMES.items()}

# ------------------------------------------------------------------ page 1
if page.startswith("1"):
    label = SR.provider_label(main)
    st.header(f"{label} report")
    o = SR.first_overview(main, res.adjustments); c = st.columns(6 if "Adjustments" in o else 4)
    c[0].metric("Total trips", f"{o['Trips']:,}"); c[1].metric("Total revenue", money(o["Revenue"])); c[2].metric("Drivers", f"{o['Drivers']:,}"); c[3].metric("Miles", f"{o['Miles']:,.0f}")
    if "Adjustments" in o:
        c[4].metric("Adjustments", money(o["Adjustments"])); c[5].metric("Net revenue received", money(o["Net revenue"]))
        with st.expander("Non-trip adjustments"): show(res.adjustments)
    if main.provider.nunique() > 1:
        st.subheader("Totals by provider"); show(SR.provider_table(main), title="Totals by provider")
        st.subheader("Totals by state and provider"); show(SR.state_provider_table(main), title="Totals by state and provider")
    t = SR.first_state_table(main); st.subheader("Totals by state" + (" (all providers combined)" if main.provider.nunique() > 1 else "")); show(t, title="Totals by state")
    st.bar_chart(t.set_index("State")[["Revenue"]])
    rs, rgrp, rdrv, rdet = SR.first_rate_audit(main, ak_rate, err=err_price)
    if rs["Trips below official rate"]:
        st.subheader(f"Alaska rate check - trips short by the fixed ${ak_rate-err_price:,.2f} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)")
        c2 = st.columns(3); c2[0].metric(f"Trips paid ${err_price:,.2f}", f"{rs['Trips below official rate']:,}"); c2[1].metric("Total owed by the provider", money(rs["Total owed"])); c2[2].metric("Drivers affected", f"{rs['Drivers affected']:,}")
        show(rgrp, title="Alaska claim by price")
        if rs["Other trips below the rate (not claimed)"]:
            st.info(f"{rs['Other trips below the rate (not claimed)']} other Alaska trips were paid below the rate at a different price ({rs['Other prices (not claimed)']}) - NOT part of this claim (shortfall {money(rs['Their shortfall (not claimed)'])}).")
        with st.expander("Claim by driver"): show(rdrv, title="Alaska claim by driver")
        with st.expander("Claim - trip by trip"): show(rdet, 400)
    book = RB.load(); pcs, pcd, pca = SR.price_check(main, book, err_price, ak_rate)
    st.subheader("Price check against contract prices (rate book)")
    st.caption("Contract price per route is learned from earlier state reports (same route; otherwise same state and miles). Cancelled / $0 trips are excluded. Alaska: only the error-price trips are claimed.")
    show(pcs, title="Price check against contract prices")
    _policy_prices, _policy_price_detail = PP.price_list_check(main)
    if len(_policy_prices):
        st.subheader("Provider price vs official policy price (by state)")
        st.caption("The summary is grouped by state, not city. Exception detail keeps city, route, miles, Spiff, and a reason-to-review so a changed address/district or route is not mistaken for a pricing error.")
        show(_policy_prices, title="Provider price vs official policy price")
        if len(_policy_price_detail): show(_policy_price_detail, 400, title="Provider price differences vs official policy")
    # Claims metrics must use unique detail trips only; TOTAL is a display row, never a trip.
    _claim_detail = pcd.copy() if pcd is not None else pd.DataFrame()
    if len(_claim_detail) and "State" in _claim_detail.columns:
        _claim_detail = _claim_detail[_claim_detail.State.astype(str).str.upper().ne("TOTAL")].copy()
        _dedupe = [c for c in ["State", "Date", "Driver", "Trip ID", "Trip Name", "Miles", "Paid", "Contract price", "Source file", "Source row"] if c in _claim_detail.columns]
        if _dedupe:
            _claim_detail = _claim_detail.drop_duplicates(_dedupe, keep="first").reset_index(drop=True)
    _cl_states = sorted(_claim_detail.State.dropna().unique()) if len(_claim_detail) else []
    st.subheader("CLAIMS to First / EverDriven - trips paid below the contract price" + (": " + ", ".join(_cl_states) if _cl_states else ""))
    st.caption("Basis per trip: same route paid more in earlier weeks, same state + miles, or the Alaska fixed rule. Each state has the claim by price, by driver and trip by trip.")
    _tot_n, _tot_amt = int((-_claim_detail["Difference"] > 0).sum()), float(-_claim_detail["Difference"].sum()) if len(_claim_detail) else 0.0
    cc = st.columns(2); cc[0].metric("Trips to claim", f"{_tot_n:,}"); cc[1].metric("Total to claim", money(_tot_amt))
    for stn in _cl_states:
        dd = _claim_detail[_claim_detail.State == stn]
        if dd.empty: continue
        gp, gd = SR.claim_tables(dd)
        with st.expander(f"{stn}: {len(dd):,} trips, {money(-dd['Difference'].sum())}", expanded=False):
            show(gp, title=f"{stn} - claim by price"); show(gd, title=f"{stn} - claim by driver"); show(dd, 400, title=f"{stn} - claim trip by trip")
    st.subheader("Trip-by-trip detail")
    pick = st.selectbox("State", list(t.State)); d = SR.first_state_detail(main, names.get(pick, pick))
    st.caption(f"{len(d):,} trips - total {money(d['Revenue (trip price paid)'].sum())}"); show(d, 500)
    sheets = {"Overall": pd.DataFrame([o]), "By provider": SR.provider_table(main), "By state and provider": SR.state_provider_table(main), "By state": t, "Price check": pcs, "Price check detail": _claim_detail, "Official policy prices": _policy_prices, "Policy price detail": _policy_price_detail, "Adjustments": res.adjustments, **({"Alaska claim": rdet, "Alaska claim by driver": rdrv} if len(rdet) else {})}
    for code in main.state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.first_state_detail(main, code)
    st.download_button("⬇️ Excel (totals + detail per state)", EG.build_workbook(sheets), "First_Report.xlsx", XLSX)
    pdf_button(f"{label} report", "first_report", lambda: PG.first_report(main, adjustments=res.adjustments, rate=ak_rate, err=err_price, with_book=True, states_with_report=set(rec[rec.state_source != ""].state), rec=rec))

# ------------------------------------------------------------------ page 2
elif page.startswith("2"):
    st.header("State reports")
    _book = RB.load(); _with = set(rec[rec.state_source != ""].state)
    _est = SR.estimate_financials(main, _book, _with)
    if not has_state:
        st.info("Upload the state reports in the sidebar to see ACTUAL revenue, payments and profit.")
        if len(_est): st.subheader("ESTIMATED financial performance (no state report yet)"); st.caption("Estimate, not actual: driver payments come from earlier weeks' pay rates."); show(_est)
        st.stop()
    t = SR.state_financials(rec); show(t[["State", "Trips", "Revenue", "Driver Payments", "Profit", "Margin %"]])
    if len(_est): st.subheader("ESTIMATED performance for states without a state report"); st.caption("Estimate, not actual: not included in the table above."); show(_est)
    if t["Monitor payments"].sum() > 0: st.caption("Monitor (MO) payments are costs: included in Driver Payments and Profit; monitors have no trip revenue of their own.")
    st.bar_chart(t.set_index("State")[["Revenue", "Driver Payments", "Profit"]])
    st.caption("This page is summary-only. Trip-level detail is kept in the Excel download and can be opened below only when needed.")
    with st.expander("Optional trip-level detail (not included in the summary report)"):
        pick = st.selectbox("State detail", list(t.State))
        show(SR.state_trip_detail(rec, names.get(pick, pick)), 500, title="State trip-level detail")
    # The general state summary stays on the agreed-price financial view;
    # Alaska's paid/agreed comparison is available only in its state detail.
    sheets = {"States": t[["State", "Trips", "Revenue", "Driver Payments", "Profit", "Margin %"]]}
    for code in rec[rec.state_source != ""].state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.state_trip_detail(rec, code)
    st.download_button("⬇️ Excel (state reports)", EG.build_workbook(sheets), "State_Reports.xlsx", XLSX)
    pdf_button("State Financial Report - 3 tables", "states", lambda: PG.states_financial_report(rec, main))

# ------------------------------------------------------------------ page 3
elif page.startswith("3"):
    st.header("Differences between First and the state reports")
    if not has_state: st.info("Upload the state reports to see the differences."); st.stop()
    n_acc, amt_acc = SR.accepted_summary(rec)
    if n_acc: st.caption(f"{n_acc} Alaska trips with other price differences (total ${abs(amt_acc):,.2f}) are treated as correct and excluded from the claim; only trips paid ${err_price:,.2f} are claimed.")
    _match = rec.copy()
    _match["Provider"] = _match.provider.map(SR.PROVIDER_NAMES).fillna(_match.provider) if "provider" in _match.columns else "Unknown"
    _match["State"] = _match.state.map(lambda c: STATE_NAMES.get(c, c))
    _match = _match.groupby(["Provider", "State", "audit_status"], dropna=False).size().reset_index(name="Trips")
    _match = _match.rename(columns={"audit_status": "Matching result"})
    st.subheader("First / EverDriven to state-report matching")
    st.caption("Every uploaded trip is classified once: matched, price/payment difference, missing on one side, duplicate, or manual review.")
    show(_match, title="Matching results by provider and state")
    st.subheader("Revenue bridge: First/EverDriven to state report"); show(SR.revenue_bridge(rec, ak_rate, err_price), title="Revenue bridge")
    t = SR.discrepancy_summary(rec); show(t, title="Summary of differences by state")
    if len(t): st.metric("Total price difference (First - State)", money(t["Total difference (First - State)"].sum()))
    sheets = {"Matching results": _match, "Revenue bridge": SR.revenue_bridge(rec, ak_rate, err_price), "Summary": t}
    for code in rec[rec.state_source != ""].state.unique():
        a, s, f = SR.discrepancy_sections(rec, code); nm = STATE_NAMES.get(code, code)
        if not (len(a) or len(s) or len(f)): continue
        with st.expander(f"{nm}: {len(a)} price differences, {len(s)} state-only trips, {len(f)} First-only trips"):
            cl, ot = SR.claim_split(rec, code, ak_rate, err_price)
            if len(cl): st.markdown(f"**Claim to First: trips short by the fixed ${ak_rate-err_price:,.2f} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)**"); show(cl)
            pp_, pd_, po_ = SR.price_diff_claim(rec, code, ak_rate, err_price)
            if len(pp_): st.markdown("**Claim to First/EverDriven: trips paid LESS than the state report price**"); show(pp_, title=f"{nm} - claim by price"); show(pd_, title=f"{nm} - claim by driver"); sheets[f"{code} claim"[:31]] = pp_
            if len(po_): st.markdown("**Provider paid MORE than the state report (no claim - information)**"); show(po_)
            mo = SR.monitor_by_driver(rec, code)
            if len(mo): st.markdown("**Monitor (MO) payments - costs with no trip revenue (information only)**"); show(mo); sheets[f"{code} monitors"[:31]] = mo
            for ttl, df, sh in (("Trips with a different price", a, "price"), ("In the state report but not in First", s, "state-only"), ("In First but not in the state report", f, "First-only")):
                if len(df): st.markdown(f"**{ttl}**"); show(df); sheets[f"{code} {sh}"[:31]] = df
    st.download_button("⬇️ Excel (discrepancies)", EG.build_workbook(sheets), "Discrepancies.xlsx", XLSX)
    pdf_button("Discrepancy report", "disc", lambda: PG.discrepancy_report(rec, ak_rate, err_price))


# ------------------------------------------------------------------ page 10: consolidated summary
elif page.startswith("10"):
    st.header("Consolidated company, provider, and state summary")
    st.caption("Company-wide financial summary. First and EverDriven are separate provider reports. Each state row shows trips, revenue, driver payments, profit, margin, amount to request, and the state's trip/revenue share of its provider total. Weekly comparisons are available in the Weekly comparison report.")
    if has_state:
        pdf_button("State report - exactly 3 tables", "state_three_tables_page", lambda: PG.state_three_table_report(main, rec, RB.load(), ak_rate, err_price))
    _sum_tabs = PG.consolidated_summary_tables(main, rec, RB.load(), ak_rate, err_price)
    st.subheader("Company total - First + EverDriven")
    show(_sum_tabs["company"], title="Company consolidated summary")
    st.subheader("Provider reports - First and EverDriven")
    show(_sum_tabs["providers"], title="First and EverDriven totals")
    st.subheader("State totals under each provider")
    show(_sum_tabs["states"], title="State totals by provider")
    if len(_sum_tabs["providers"]):
        _pchart = _sum_tabs["providers"][["Provider", "Amount to request from provider"]].dropna().set_index("Provider")
        if len(_pchart):
            st.subheader("Amount to request from each provider")
            st.bar_chart(_pchart)
    if len(_sum_tabs["states"]):
        _schart = _sum_tabs["states"].copy()
        _schart["Provider / State"] = _schart["Provider"].astype(str) + " / " + _schart["State"].astype(str)
        _schart = _schart[["Provider / State", "Policy loss"]].dropna().set_index("Provider / State")
        if len(_schart):
            st.subheader("Potential lost profit from paying above policy")
            st.bar_chart(_schart)
    st.download_button("⬇️ Excel (summary only)", EG.build_workbook({"Company total": _sum_tabs["company"], "Provider totals": _sum_tabs["providers"], "State totals": _sum_tabs["states"]}), "Consolidated_Summary.xlsx", XLSX)

# ------------------------------------------------------------------ page 4: weekly comparison
elif page.startswith("4"):
    st.header("Weekly comparison")
    st.caption("Previous weeks come from the history CSV you upload in the sidebar plus this session. Revenue = paid by First / EverDriven; payments, profit and margin exist only for states with a state report.")
    ws = HI.weeks(hist)
    if not ws: st.info("No dated trips."); st.stop()
    wk = pd.Timestamp(st.selectbox("Reporting week (Mon-Sun)", ws[::-1], format_func=lambda d: f"{pd.Timestamp(d):%Y-%m-%d} to {pd.Timestamp(d) + pd.Timedelta(days=6):%Y-%m-%d}"))
    t, ci, pi, warns = HI.weekly_compare(hist, wk)
    for w_ in warns: st.warning(w_)
    show(HI.fmt_table(t, ["Current week", "Previous week", "Difference"]))
    lf, both = HI.weekly_like_for_like(hist, wk)
    if lf is not None:
        st.subheader("Like-for-like: states with a state report in both weeks (" + ", ".join(STATE_NAMES.get(s, s) for s in both) + ")"); show(HI.fmt_table(lf, ["Current week", "Previous week", "Difference"]))
    ss_ = HI.weekly_state_summary(hist, wk); st.subheader("By state"); show(ss_)
    st.bar_chart(ss_.set_index("State")[["Revenue current", "Revenue previous"]])
    with st.expander("By driver (needs both weeks in this session)"):
        try:
            dt_, _, _, dw_ = W.weekly_report(rec, wk, by="driver"); show(dt_) if dt_ is not None and len(dt_) else st.caption("Upload both weeks together to compare drivers.")
        except Exception as e: st.caption(f"Driver comparison not available: {e}")
    pdf_button("Weekly comparison report", "weekly_cmp", lambda: PG.weekly_comparison_report(hist, wk))

# ------------------------------------------------------------------ page 5: monthly report
elif page.startswith("5"):
    st.header("Monthly report")
    mt_ = HI.monthly_table(hist)
    if mt_.empty: st.info("No dated trips."); st.stop()
    for m_, w_ in zip(mt_.Month, mt_.Weeks):
        if w_ < 4: st.warning(f"{m_} has {w_} week(s) of data - partial month.")
    show(mt_); st.bar_chart(mt_.set_index("Month")[["Revenue", "Driver Payments", "Profit"]])
    sm_ = HI.monthly_table(hist, by="state"); sm_["State"] = sm_.state.map(lambda c: STATE_NAMES.get(c, c)); st.subheader("State by month")
    show(sm_[["Month", "State", "Weeks", "Trips", "Revenue", "Driver Payments", "Profit", "Margin %", "Avg revenue/trip"]])
    pdf_button("Monthly report", "monthly", lambda: PG.monthly_report_pdf(hist))

# ------------------------------------------------------------------ page 6: monthly comparison
elif page.startswith("6"):
    st.header("Monthly comparison")
    months = sorted(hist.month.dropna().unique())
    if len(months) < 2: st.info("Needs two months in the history (upload the saved history CSV)."); st.stop()
    m1 = st.selectbox("Month A", months, index=len(months) - 2); m2 = st.selectbox("Month B", months, index=len(months) - 1)
    t, warns = HI.monthly_compare(hist, m1, m2)
    for w_ in warns: st.warning(w_)
    show(HI.fmt_table(t, [m1, m2, "Difference"]))
    lf, both = HI.like_for_like(hist[hist.month == m2], hist[hist.month == m1], m2, m1)
    if lf is not None: st.subheader("Like-for-like: states with a state report in both months (" + ", ".join(STATE_NAMES.get(s, s) for s in both) + ")"); show(HI.fmt_table(lf[["KPI", m1, m2, "Difference", "Change %"]], [m1, m2, "Difference"]))
    st.subheader("By state"); show(HI.monthly_state_summary(hist, m1, m2))
    pdf_button("Monthly comparison", "monthly_cmp", lambda: PG.monthly_comparison_report(hist, m1, m2))

# ------------------------------------------------------------------ page 7: driver pay policy review
elif page.startswith("7"):
    st.header("Driver pay policy review")
    if not has_state: st.info("Upload the state reports to review driver payments."); st.stop()
    _book = RB.load()
    _policy_detail, _policy_summary, _pk = SR.policy_compliance_report(rec, _book)
    st.caption("One rule is used everywhere: COMPLIANT requires a known policy price and an equal Net Pay. NON_COMPLIANT means a real difference. NOT_VERIFIABLE means the policy or required route/mileage input is missing; it is never counted as compliant. Gross Pay = state-report revenue; Net Pay = current driver payment.")
    _c = st.columns(7)
    _c[0].metric("Trips checked", f"{_pk['Trips']:,}")
    _c[1].metric("Compliant", f"{_pk['Compliant']:,}")
    _c[2].metric("Non-compliant", f"{_pk['Non-compliant']:,}")
    _c[3].metric("Not verifiable", f"{_pk['Not verifiable']:,}")
    _c[4].metric("Loss from non-compliance", money(_pk['Loss']))
    _c[5].metric("Actual margin", f"{_pk.get('Actual margin %', float('nan')):.1f}%" if pd.notna(_pk.get('Actual margin %')) else "n/a")
    _c[6].metric("Projected margin", f"{_pk.get('Projected margin %', float('nan')):.1f}%" if pd.notna(_pk.get('Projected margin %')) else "n/a")
    st.subheader("Policy compliance by state")
    show(_policy_summary, title="Policy compliance by state")
    st.subheader("Trip-by-trip policy decision")
    show(_policy_detail, 500, title="Trip-by-trip policy compliance")
    _non = _policy_detail[_policy_detail.Status == "NON_COMPLIANT"] if len(_policy_detail) else _policy_detail
    if len(_non):
        with st.expander(f"Non-compliant trips ({len(_non):,})", expanded=True): show(_non, 500)
    _nv = _policy_detail[_policy_detail.Status == "NOT_VERIFIABLE"] if len(_policy_detail) else _policy_detail
    if len(_nv):
        with st.expander(f"Not verifiable - not counted as compliant ({len(_nv):,})"): show(_nv, 500)
    with st.expander("Pay policy table (every route with a stable policy)"): show(SR.pay_policy_table(_book), 400)
    _bs, _bd = PP.band_check(rec, _book)
    if len(_bs):
        st.subheader("Driver pay vs the official mile-band policy (Northern / Southern California, New Mexico, Oregon)")
        st.caption("Bands per city come from the price PDFs. Trips with a different pay that is listed in the price list are approved exceptions; long trips and Sacramento are approved per trip by management.")
        show(_bs)
        _bad = _bd[_bd.Status.str.startswith(("ABOVE", "BELOW", "Long trip: needs", "ZERO", "Sacramento: pay NOT", "City not"))]
        with st.expander(f"Trips that need review ({len(_bad):,})", expanded=len(_bad) > 0): show(_bad, 400)
        with st.expander("Mile bands"): show(PP.bands_table())
    st.download_button("⬇️ Excel (pay policy review)", EG.build_workbook({"Policy compliance": _policy_summary, "Trip decisions": _policy_detail, "Non-compliant": _non, "Not verifiable": _nv, "Pay policy": SR.pay_policy_table(_book), "N.CA mile bands": _bs, "N.CA band detail": _bd}), "Pay_Policy_Review.xlsx", XLSX)
    pdf_button("Driver pay policy review", "paypol", lambda: PG.pay_policy_report(rec, _book))


# ------------------------------------------------------------------ page 8: full report per state
elif page.startswith("8"):
    st.header("Full report per state")
    st.caption("One report per state, shown on the screen and downloadable as a 2-page PDF or an Excel file: First/EverDriven vs the state report, prices paid, pay policy, and the differences for the state manager. States without a state report get the estimate and the price check only.")
    import state_view as SV
    codes_ = PG.report_states(main, rec); _b8 = RB.load()
    if ss.get("state_pick") not in codes_: ss["state_pick"] = codes_[0] if codes_ else None
    st.caption("Click a state: its report opens on the screen (and can be downloaded as PDF or Excel).")
    _cols = st.columns(max(len(codes_), 1))
    for _c, _code in zip(_cols, codes_):
        if _c.button(STATE_NAMES.get(_code, _code), key=f"stbtn_{_code}", use_container_width=True, type="primary" if ss.get("state_pick") == _code else "secondary"): ss["state_pick"] = _code
    if ss.get("state_pick"):
        st.divider(); SV.render(ss["state_pick"], main, rec, hist, _b8, ak_rate, err_price, show)
    st.divider()
    if st.button("Generate ZIP with all states", key="gen_zip"): ss["zip_all"] = PG.all_states_zip(main, rec, hist, _b8, ak_rate, err_price)
    if ss.get("zip_all"): st.download_button("⬇️ Download ZIP: all states", ss["zip_all"], "All_States_Full_Reports.zip", "application/zip", key="dl_zip")

elif page.startswith("9"):
    st.header("Driver report")
    st.caption("Pick a driver: every trip of his from the uploaded reports (provider price, state-report revenue and pay, differences, pay policy), as a PDF or Excel file.")
    import excel_generator as EG
    _rs = rec[rec.driver.fillna("").ne("")]
    _stp = st.selectbox("State", ["All states"] + sorted({STATE_NAMES.get(c, c) for c in _rs.state.dropna().unique()}))
    _pool = _rs if _stp == "All states" else _rs[_rs.state.map(lambda c: STATE_NAMES.get(c, c)) == _stp]
    _names = sorted({str(x).strip() for x in _pool.driver}, key=lambda x: x.lower())
    _drv = st.selectbox("Driver", _names)
    if _drv:
        _b9 = RB.load(); _t, _k = PG.driver_trips(rec, main, _drv, _b9, ak_rate, err_price)
        if _t.empty: st.info("No trips for this driver.")
        else:
            _c = st.columns(5)
            for _col, _lab in zip(_c, ["Trips", "Provider paid", "State report revenue", "Driver pay", "Profit"]):
                _v = _k.get(_lab); _col.metric(_lab, f"{int(_v):,}" if _lab == "Trips" else money(_v))
            show(_t, 500)
            _fn = "driver_" + "".join(ch if ch.isalnum() else "_" for ch in _drv)[:40]
            _d1, _d2 = st.columns(2)
            _d1.download_button("⬇️ Download PDF", PG.driver_trip_report(rec, main, _drv, _b9, ak_rate, err_price), f"{_fn}.pdf", "application/pdf", key="drv_pdf", use_container_width=True, type="primary")
            _d2.download_button("⬇️ Download Excel", EG.build_workbook({"Driver trips": _t}), f"{_fn}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="drv_xls", use_container_width=True)
