"""Hatem's B.T. Analyzer - simple 3-page flow.  Run: streamlit run app.py
Full-featured version (filters, weekly/monthly, Alaska audit, mappings) is in app_full.py."""
import json
import pandas as pd
import streamlit as st

import app_logic as AL
import history as HI
import weekly_reports as W
import classification as C
import excel_generator as EG
import pdf_generator as PG
import ratebook as RB
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
def process(main_t, state_t, overrides_j, colmap_j, map_j):
    return AL.process_uploads(list(main_t), list(state_t), json.loads(json.dumps(DEFAULT_SETTINGS)), json.loads(overrides_j), json.loads(map_j), json.loads(colmap_j))


def pdf_button(label, key, fn):
    if st.button(f"Generate PDF: {label}", key=f"gen_{key}"):
        st.session_state[f"pdf_{key}"] = fn()
    if st.session_state.get(f"pdf_{key}"):
        st.download_button(f"⬇️ Download PDF: {label}", st.session_state[f"pdf_{key}"], f"{key}.pdf", "application/pdf", key=f"dl_{key}")


st.title("Hatem's B.T. Analyzer")
ss = st.session_state; ss.setdefault("overrides", {}); ss.setdefault("colmap", {}); ss.setdefault("editable_map", {})
with st.sidebar:
    st.subheader("1) First / EverDriven reports")
    mfiles = st.file_uploader("Upload First or EverDriven reports", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="m")
    st.subheader("2) State reports")
    sfiles = st.file_uploader("Upload state reports (optional)", type=["xlsx", "xls", "csv", "pdf"], accept_multiple_files=True, key="s")
    ak_rate = st.number_input("Official Alaska rate ($)", value=45.0, step=0.5)
    err_price = st.number_input("Price paid in error ($) - only these trips are claimed", value=42.5, step=0.5)
    st.subheader("3) Saved driver map (optional)")
    mapfile = st.file_uploader("CSV with columns driver,state", type=["csv"], key="map")
    st.subheader("4) Previous weeks history (optional)")
    histfile = st.file_uploader("weekly_history.csv saved last time", type=["csv"], key="hist")
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
main, rec = res.main, SR.apply_rate_rule(res.rec, ak_rate, err_price)     # rule applied everywhere: only the error-price trips stay REVENUE MISMATCH
has_state = bool(len(res.st))
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

_prev = None
if histfile:
    try: _prev = HI.from_csv(histfile)
    except Exception as e: st.warning(f"History CSV could not be read: {e}")
hist = HI.merge(_prev, HI.weekly_rows(rec)) if len(rec) else HI.merge(_prev, pd.DataFrame(columns=HI.COLS))
st.sidebar.download_button("⬇️ Save weekly history (CSV)", HI.to_csv(hist), "weekly_history.csv", "text/csv")
page = st.sidebar.radio("Report", [f"1) {SR.provider_label(main)} report", "2) State reports (revenue, payments, profit)", "3) Discrepancy report", "4) Weekly comparison", "5) Monthly report", "6) Monthly comparison", "7) Driver pay policy review", "8) Full report per state"])
with st.sidebar:
    st.divider()
    if has_state: pdf_button("Combined report (all 3)", "combined", lambda: PG.combined_report(main, rec, rate=ak_rate, adjustments=res.adjustments, err=err_price))
    pdf_button("MASTER report (everything in one file)", "master", lambda: PG.master_report(main, rec, hist, RB.load(), rate=ak_rate, err=err_price, adjustments=res.adjustments))
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
        st.subheader("Totals by provider"); show(SR.provider_table(main))
        st.subheader("Totals by state and provider"); show(SR.state_provider_table(main))
    t = SR.first_state_table(main); st.subheader("Totals by state" + (" (all providers combined)" if main.provider.nunique() > 1 else "")); show(t)
    st.bar_chart(t[t.State != "TOTAL"].set_index("State")[["Revenue"]])
    rs, rgrp, rdrv, rdet = SR.first_rate_audit(main, ak_rate, err=err_price)
    if rs["Trips below official rate"]:
        st.subheader(f"Alaska rate check - trips paid ${err_price:,.2f} instead of the official ${ak_rate:,.2f}")
        c2 = st.columns(3); c2[0].metric(f"Trips paid ${err_price:,.2f}", f"{rs['Trips below official rate']:,}"); c2[1].metric("Total owed by the provider", money(rs["Total owed"])); c2[2].metric("Drivers affected", f"{rs['Drivers affected']:,}")
        show(rgrp)
        if rs["Other trips below the rate (not claimed)"]:
            st.info(f"{rs['Other trips below the rate (not claimed)']} other Alaska trips were paid below the rate at a different price ({rs['Other prices (not claimed)']}) - NOT part of this claim (shortfall {money(rs['Their shortfall (not claimed)'])}).")
        with st.expander("Claim by driver"): show(rdrv)
        with st.expander("Claim - trip by trip"): show(rdet, 400)
    book = RB.load(); pcs, pcd, pca = SR.price_check(main, book, err_price, ak_rate)
    st.subheader("Price check against contract prices (rate book)")
    st.caption("Contract price per route is learned from earlier state reports (same route; otherwise same state and miles). Cancelled / $0 trips are excluded. Alaska: only the error-price trips are claimed.")
    show(pcs)
    with st.expander(f"Trips paid below the contract price - trip by trip ({len(pcd):,})"): show(pcd, 400)
    st.subheader("Trip-by-trip detail")
    pick = st.selectbox("State", list(t.State[:-1])); d = SR.first_state_detail(main, names.get(pick, pick))
    st.caption(f"{len(d):,} trips - total {money(d['Revenue (trip price paid)'].sum())}"); show(d, 500)
    sheets = {"Overall": pd.DataFrame([o]), "By provider": SR.provider_table(main), "By state and provider": SR.state_provider_table(main), "By state": t, "Price check": pcs, "Price check detail": pcd, "Adjustments": res.adjustments, **({"Alaska claim": rdet, "Alaska claim by driver": rdrv} if len(rdet) else {})}
    for code in main.state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.first_state_detail(main, code)
    st.download_button("⬇️ Excel (totals + detail per state)", EG.build_workbook(sheets), "First_Report.xlsx", XLSX)
    pdf_button(f"{label} report", "first_report", lambda: PG.first_report(main, adjustments=res.adjustments, rate=ak_rate, err=err_price, with_book=True, states_with_report=set(rec[rec.state_source != ""].state)))

# ------------------------------------------------------------------ page 2
elif page.startswith("2"):
    st.header("State reports")
    _book = RB.load(); _with = set(rec[rec.state_source != ""].state)
    _est = SR.estimate_financials(main, _book, _with)
    if not has_state:
        st.info("Upload the state reports in the sidebar to see ACTUAL revenue, payments and profit.")
        if len(_est): st.subheader("ESTIMATED financial performance (no state report yet)"); st.caption("Estimate, not actual: driver payments come from earlier weeks' pay rates."); show(_est)
        st.stop()
    t = SR.state_financials(rec); show(t)
    if len(_est): st.subheader("ESTIMATED performance for states without a state report"); st.caption("Estimate, not actual: not included in the table above."); show(_est)
    if t["Monitor payments"].sum() > 0: st.caption("Monitor (MO) payments are costs: included in Driver Payments and Profit; monitors have no trip revenue of their own.")
    if (t["Trips missing revenue"] > 0).any(): st.warning("Some state-report trips have no revenue. They are kept, not counted as zero, and excluded from profit.")
    st.bar_chart(t[t.State != "TOTAL"].set_index("State")[["Revenue", "Driver Payments", "Profit"]])
    pick = st.selectbox("State detail", list(t.State[:-1])); show(SR.state_trip_detail(rec, names.get(pick, pick)), 500)
    sheets = {"States": t}
    for code in rec[rec.state_source != ""].state.unique(): sheets[STATE_NAMES.get(code, code)[:28]] = SR.state_trip_detail(rec, code)
    st.download_button("⬇️ Excel (state reports)", EG.build_workbook(sheets), "State_Reports.xlsx", XLSX)
    pdf_button("State report", "states", lambda: PG.states_financial_report(rec))

# ------------------------------------------------------------------ page 3
elif page.startswith("3"):
    st.header("Differences between First and the state reports")
    if not has_state: st.info("Upload the state reports to see the differences."); st.stop()
    n_acc, amt_acc = SR.accepted_summary(rec)
    if n_acc: st.caption(f"{n_acc} Alaska trips with other price differences (total ${abs(amt_acc):,.2f}) are treated as correct and excluded from the claim; only trips paid ${err_price:,.2f} are claimed.")
    st.subheader("Revenue bridge: First/EverDriven to state report"); show(SR.revenue_bridge(rec, ak_rate, err_price))
    t = SR.discrepancy_summary(rec); show(t)
    if len(t): st.metric("Total price difference (First - State)", money(t[t.State == "TOTAL"].iloc[0]["Total difference (First - State)"]))
    sheets = {"Revenue bridge": SR.revenue_bridge(rec, ak_rate, err_price), "Summary": t}
    for code in rec[rec.state_source != ""].state.unique():
        a, s, f = SR.discrepancy_sections(rec, code); nm = STATE_NAMES.get(code, code)
        if not (len(a) or len(s) or len(f)): continue
        with st.expander(f"{nm}: {max(len(a) - 1, 0)} price differences, {max(len(s) - 1, 0)} state-only trips, {max(len(f) - 1, 0)} First-only trips"):
            cl, ot = SR.claim_split(rec, code, ak_rate, err_price)
            if len(cl): st.markdown(f"**Claim to First: trips paid ${err_price:,.2f} instead of the official ${ak_rate:,.2f}**"); show(cl)
            mo = SR.monitor_by_driver(rec, code)
            if len(mo): st.markdown("**Monitor (MO) payments - costs with no trip revenue (information only)**"); show(mo); sheets[f"{code} monitors"[:31]] = mo
            for ttl, df, sh in (("Trips with a different price", a, "price"), ("In the state report but not in First", s, "state-only"), ("In First but not in the state report", f, "First-only")):
                if len(df): st.markdown(f"**{ttl}**"); show(df); sheets[f"{code} {sh}"[:31]] = df
    st.download_button("⬇️ Excel (discrepancies)", EG.build_workbook(sheets), "Discrepancies.xlsx", XLSX)
    pdf_button("Discrepancy report", "disc", lambda: PG.discrepancy_report(rec, ak_rate, err_price))


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
    _book = RB.load(); ps, pover, ploss = SR.pay_check(rec, _book)
    st.caption("Policy = the pay paid for the same route in >=80% of earlier trips (minimum 3). The route of each trip comes from the First / EverDriven report.")
    show(ps)
    if len(ps): st.metric("Total excess pay above policy", money(ps.iloc[-1]["Total excess pay"]))
    for code in pover.State.unique():
        d_ = pover[pover.State == code]
        with st.expander(f"{code}: {len(d_)} trips paid above the pay policy (excess {money(d_['Excess pay'].sum())})"): show(d_.drop(columns=["State"]))
    if len(ploss):
        with st.expander(f"Trips where the driver was paid more than the trip revenue ({len(ploss)})"): show(ploss.drop(columns=["State source"]))
    with st.expander("Pay policy table (every route with a stable policy)"): show(SR.pay_policy_table(_book), 400)
    st.download_button("⬇️ Excel (pay policy review)", EG.build_workbook({"Summary": ps, "Above policy": pover, "Above revenue": ploss, "Pay policy": SR.pay_policy_table(_book)}), "Pay_Policy_Review.xlsx", XLSX)
    pdf_button("Driver pay policy review", "paypol", lambda: PG.pay_policy_report(rec, _book))


# ------------------------------------------------------------------ page 8: full report per state
else:
    st.header("Full report per state")
    st.caption("One PDF per state: financial performance, price check, price and trip differences, driver pay policy, weekly comparison and monthly report. States without a state report get the estimate and the price check only.")
    codes_ = [c for c in sorted(main.state.dropna().unique()) if c not in ("Unassigned", "NEEDS REVIEW")]
    pick_ = st.selectbox("State", codes_, format_func=lambda c: STATE_NAMES.get(c, c)); _b8 = RB.load()
    pdf_button(f"{STATE_NAMES.get(pick_, pick_)} full report", f"state_{pick_}", lambda: PG.state_full_report(pick_, main, rec, hist, _b8, ak_rate, err_price))
    if st.button("Generate ZIP with all states", key="gen_zip"): ss["zip_all"] = PG.all_states_zip(main, rec, hist, _b8, ak_rate, err_price)
    if ss.get("zip_all"): st.download_button("⬇️ Download ZIP: all states", ss["zip_all"], "All_States_Full_Reports.zip", "application/zip", key="dl_zip")
