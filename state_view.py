"""On-screen state report: the same content as the 2-page PDF, shown in the app (KPIs, First/EverDriven vs state report, prices,
pay vs policy, and the single table of differences for the state manager), plus PDF / Excel download buttons."""
import numpy as np
import pandas as pd
import streamlit as st
import pdf_generator as PG


def _money(v):
    return "n/a" if v is None or pd.isna(v) else (f"(${abs(v):,.2f})" if v < -0.004 else f"${v:,.2f}")


def kpi_row(D):
    ms, fp, nm = D["ms"], D["fp"], D["name"]
    k = {} if len(ms) == 0 else {f"{fp} trips": f"{len(ms):,}", "Drivers": f"{ms.driver.nunique():,}", "Miles": f"{ms.miles.sum(min_count=1):,.0f}", f"{fp} revenue (paid)": _money(ms.main_amount.sum(min_count=1))}
    if D["has_rep"]:
        r = D["fin"][D["fin"].State == nm].iloc[0]
        k.update({"State report trips": f"{int(r['Trips']):,}", "State report revenue": _money(r["Revenue"]), "Driver payments": _money(r["Driver Payments"]),
                  "Monitor payments": _money(r["Monitor payments"]), "Profit": _money(r["Profit"]), "Margin %": f"{r['Margin %']:.1f}%"})
    return k


def recon_row(D):
    rc, fp, nm, ms = D["recon"], D["fp"], D["name"], D["ms"]
    a, so, fo = rc["a"], rc["state_only"], rc["first_only"]; fr = D["fin"][D["fin"].State == nm].iloc[0]
    ok = (len(a) + len(so) + len(fo) + rc["review"] == 0)
    return pd.DataFrame([{f"{fp} trips": len(ms), "State report trips": int(fr["Trips"]), "Matched trips": rc["matched"], f"In {fp}, NOT in state report": len(fo),
                          f"In state report, NOT in {fp}": len(so), "Trips with price difference": len(a), "Manual review": rc["review"],
                          f"{fp} revenue": ms.main_amount.sum(min_count=1), "State report revenue": float(fr["Revenue"]), "Result": "MATCHED to the cent" if ok else "DIFFERENCES - see below"}])


def render(code, main, rec, hist, book, rate, err, show):
    D = PG.state_report_data(code, main, rec, book, rate, err)
    nm, fp, ms = D["name"], D["fp"], D["ms"]; no_first = len(ms) == 0
    st.subheader(f"{nm}: weekly report ({fp} vs state report)")
    # ---- downloads (PDF = 2 pages for management, Excel = every trip)
    c1, c2, _ = st.columns([1, 1, 3])
    try: c1.download_button("⬇️ PDF (2 pages)", PG.state_full_report(code, main, rec, hist, book, rate, err), f"{nm.replace(' ', '_')}_report.pdf", "application/pdf", key=f"sv_pdf_{code}", use_container_width=True)
    except Exception as e: c1.warning(f"PDF failed: {e}")
    try: c2.download_button("⬇️ Excel (all details)", PG.state_excel(code, main, rec, hist, book, rate, err), f"{nm.replace(' ', '_')}_details.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"sv_xls_{code}", use_container_width=True)
    except Exception as e: c2.warning(f"Excel failed: {e}")
    # ---- headline numbers
    k = kpi_row(D); items = list(k.items())
    for i in range(0, len(items), 5):
        cols = st.columns(5)
        for col, (lab, val) in zip(cols, items[i:i + 5]): col.metric(lab, val)
    if D.get("control"): st.caption(f"How each trip got its state (state report > school/route > driver map): {D['control']}")
    if not D["has_rep"]:
        st.warning(f"No state report was uploaded for {nm}: driver payments, profit and the comparison with the state report cannot be calculated.")
    if no_first and D["has_rep"]:
        st.warning(f"No {fp} report was uploaded for {nm}. Upload it to reconcile trip by trip and to check the prices {fp} paid. Below: the state report payments against the pay policy.")
    # ---- 1 reconciliation
    if D["has_rep"] and not no_first:
        rc = D["recon"]
        st.markdown(f"#### 1. {fp} vs the {nm} state report - trip by trip")
        rr = recon_row(D); show(rr)
        if rr.iloc[0]["Result"].startswith("MATCHED"): st.success(f"{fp} and the {nm} state report agree trip by trip and to the cent.")
        for lab, df in ((f"Trips in {fp} but NOT in the state report", rc["first_only"]), (f"Trips in the state report but NOT in {fp}", rc["state_only"]), (f"Price differences {fp} vs state report", rc["a"])):
            if len(df):
                with st.expander(f"{lab}: {len(df)} trips", expanded=True): show(df)
        with st.expander("Revenue bridge: every dollar explained"): show(rc["bridge"])
    # ---- 2 prices paid by First/EverDriven
    if not no_first:
        st.markdown(f"#### {2 if D['has_rep'] else 1}. Prices paid by {fp} vs the agreed price")
        cl = PG._claim_rows(D); est = D["estimates"]; ak = D.get("ak"); pcl = D["pclaim"][0]; any_claim = False
        if len(cl): st.error(f"Claim to {fp} (agreed price, same route or agreed list): {len(cl)} trips, {_money(cl.Short.sum())}"); any_claim = True
        if ak and ak[0].get("Trips below official rate"): st.error(f"Alaska fixed $2.50 claim: {ak[0]['Trips below official rate']} of {ak[0]['Alaska trips in report']} trips, {_money(ak[0]['Total owed'])} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)"); any_claim = True
        if len(pcl): st.error(f"Trips paid LESS than the state report price: {int(pcl.iloc[-1]['Trips'])} trips, {_money(pcl.iloc[-1]['Total owed'])}"); any_claim = True
        if len(est): st.info(f"Not claimed (price estimated from other routes with similar miles - verify first): {len(est)} trips")
        if not any_claim: st.success(f"No trip was paid below the agreed price by {fp}.")
        if len(cl): show(cl, title=f"{nm} - trips to claim from {fp}")
        if ak and len(ak[1]): show(ak[1])
        if len(pcl): show(pcl)
    # ---- 3 pay policy
    if D["has_rep"]:
        import pay_policy as PP
        st.markdown("#### 3. Driver pay: state report vs the agreed pay policy")
        ps = D["paysum"]
        if ps.empty: st.info("No driver payments to check.")
        else:
            if code == "N.CA" and getattr(PP, "NC_LOAD_ERROR", None): st.error(f"The North California price list (nc_policy.py) could not be loaded: {PP.NC_LOAD_ERROR}")
            nc = ps[ps.Category.str.startswith("Not checked")]["Trips"].sum()
            if nc and nc >= 0.5 * ps.Trips.sum(): st.error(f"{int(nc)} of {int(ps.Trips.sum())} trips could not be checked: their route has no pay policy loaded (is nc_policy.py deployed?).")
            show(ps)
        # ---- 4 the single table for the state manager
        st.markdown("#### 4. DIFFERENCES FOR THE STATE MANAGER TO EXPLAIN BEFORE PAYROLL")
        mt = PG.manager_table(D)
        if mt.empty: st.success("No difference between this report and the state report.")
        else:
            mt = mt.assign(**{"State manager explanation": ""})
            st.caption(f"{len(mt)} items. The last column is for the manager's explanation (it is also in the Excel file, sheet 'For state manager').")
            show(mt, title=f"{nm} - differences for the state manager")
