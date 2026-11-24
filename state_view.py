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



def main_table(D):
    """Table 1 - the main table: the headline numbers of the state (First/EverDriven side and state-report side) + how each trip got its state."""
    k = kpi_row(D); rows = [{"KPI": a, "Value": b} for a, b in k.items()]
    if D.get("control"): rows.append({"KPI": "How each trip got its state (state report > school/route > driver map)", "Value": D["control"]})
    return pd.DataFrame(rows)


def match_table(D):
    """Table 2 - matching and differences between First/EverDriven and the state report (trip counts and dollars first, then every item to explain)."""
    fp, nm, ms = D["fp"], D["name"], D["ms"]; rows = []
    def add(sec, typ, trips=np.nan, detail="", diff=np.nan, driver="", route="", dates=""):
        rows.append({"Section": sec, "Type": typ, "Driver": driver, "Route": route, "Trips": trips, "Dates": dates, "Detail": detail, "Difference": diff})
    if D["has_rep"] and len(ms):
        rc = D["recon"]; a, so, fo = rc["a"], rc["state_only"], rc["first_only"]; fr = D["fin"][D["fin"].State == nm].iloc[0]
        add("Matching", f"{fp} trips", len(ms), f"{fp} revenue {_money(ms.main_amount.sum(min_count=1))}")
        add("Matching", "State report trips", int(fr["Trips"]), f"State report revenue {_money(fr['Revenue'])}")
        add("Matching", "Matched trips", rc["matched"], "same trip on both sides")
        add("Matching", f"In {fp}, NOT in the state report", len(fo), f"{fp} revenue {_money(fo['First Revenue'].sum()) if len(fo) else _money(0)}", fo["First Revenue"].sum() if len(fo) else 0.0)
        add("Matching", f"In the state report, NOT in {fp}", len(so), f"State revenue {_money(so['State Revenue'].sum()) if len(so) else _money(0)}", so["State Revenue"].sum() if len(so) else 0.0)
        add("Matching", "Trips with a price difference", len(a), f"{fp} minus state report", a["Difference (First - State)"].sum() if len(a) else 0.0)
        add("Matching", "Manual review", rc["review"], "low-confidence matches")
        add("Matching", "RESULT", np.nan, "MATCHED to the cent" if (len(a) + len(so) + len(fo) + rc["review"] == 0) else "DIFFERENCES - see the items below")
    elif D["has_rep"]:
        add("Matching", "No " + fp + " report uploaded", np.nan, f"Upload the {fp} report to reconcile {nm} trip by trip")
    else:
        add("Matching", "No state report uploaded", np.nan, f"Upload the {nm} state report")
    if D["has_rep"] and len(D["paysum"]):
        for r in D["paysum"].itertuples(): add("Pay policy", r.Category, r.Trips, f"State report pay {_money(r._3)}", r._4)
    t = pd.DataFrame(rows)
    if D["has_rep"]:
        mt = PG.manager_table(D)
        if len(mt):
            mt = mt.assign(Section="Difference to explain"); mt = mt[["Section", "Type", "Driver", "Route", "Trips", "Dates", "Detail", "Difference"]]
            t = pd.concat([t, mt], ignore_index=True)
    t["State manager explanation"] = ""
    return t


def claims_table(D, rate, err):
    """Table 3 - claim to First/EverDriven: every trip they paid below the agreed price (trip, agreed, paid, short, basis) + TOTAL."""
    import simple_reports as SR
    parts = [PG._claim_rows(D)]
    ak = D.get("ak")
    if ak and len(ak[3]):
        a = ak[3]; parts.append(pd.DataFrame({"Date": a["Date"], "Driver": a["Driver"], "Trip ID": a["Trip ID"], "Trip Name": a["Trip Name"], "Agreed price": a["Official price"], "Paid": a["Price paid"],
                                              "Short": a["Shortfall"], "Basis": "Alaska fixed $2.50 (42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)"}))
    if D["has_rep"] and D["code"] != "AK":
        rr = SR.apply_rate_rule(D["rs"], rate, err); g = rr[(rr.state == D["code"]) & (rr.audit_status == "REVENUE MISMATCH") & (rr.revenue_difference < -0.004)]
        if len(g): parts.append(pd.DataFrame({"Date": g.date, "Driver": g.driver, "Trip ID": g.main_trip_id, "Trip Name": g.trip_name, "Agreed price": g.state_revenue, "Paid": g.main_revenue,
                                              "Short": -g.revenue_difference, "Basis": "Paid less than the state report price"}))
    parts = [p for p in parts if len(p)]
    cols = ["Date", "Driver", "Trip ID", "Trip Name", "Agreed price", "Paid", "Short", "Basis"]
    if not parts: return pd.DataFrame(columns=cols)
    t = pd.concat(parts, ignore_index=True).drop_duplicates(["Date", "Driver", "Trip Name"]).sort_values(["Short", "Date"], ascending=[False, True]).reset_index(drop=True)
    tot = {c: "" for c in cols}; tot.update({"Driver": f"TOTAL ({len(t)} trips)", "Short": t.Short.sum()})
    return pd.concat([t, pd.DataFrame([tot])], ignore_index=True)


def tables_workbook(D, rate, err):
    import excel_generator as EG
    return EG.build_workbook({"1 Main table": main_table(D), "2 Matching and differences": match_table(D), f"3 Claim to {D['fp']}"[:31]: claims_table(D, rate, err)})


def _xls(df, name):
    import excel_generator as EG
    return EG.build_workbook({name[:31]: df})


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render(code, main, rec, hist, book, rate, err, show):
    D = PG.state_report_data(code, main, rec, book, rate, err)
    nm, fp, ms = D["name"], D["fp"], D["ms"]; fn = nm.replace(" ", "_").replace("(", "").replace(")", "")
    T1, T2, T3 = main_table(D), match_table(D), claims_table(D, rate, err)
    st.subheader(f"{nm}: weekly report ({fp} vs state report)")
    c1, c2, c3, _ = st.columns([1.3, 1, 1, 1.5])
    try: c1.download_button("⬇️ Excel: the 3 tables", tables_workbook(D, rate, err), f"{fn}_3_tables.xlsx", XLSX, key=f"sv_all_{code}", use_container_width=True, type="primary")
    except Exception as e: c1.warning(f"Excel failed: {e}")
    try: c2.download_button("⬇️ PDF (2 pages)", PG.state_full_report(code, main, rec, hist, book, rate, err), f"{fn}_report.pdf", "application/pdf", key=f"sv_pdf_{code}", use_container_width=True)
    except Exception as e: c2.warning(f"PDF failed: {e}")
    try: c3.download_button("⬇️ Excel (every trip)", PG.state_excel(code, main, rec, hist, book, rate, err), f"{fn}_details.xlsx", XLSX, key=f"sv_xls_{code}", use_container_width=True)
    except Exception as e: c3.warning(f"Excel failed: {e}")
    if not D["has_rep"]: st.warning(f"No state report was uploaded for {nm}: driver payments, profit and the comparison with the state report cannot be calculated.")
    if len(ms) == 0 and D["has_rep"]: st.warning(f"No {fp} report was uploaded for {nm}: upload it to reconcile trip by trip and to check the prices {fp} paid.")
    # ---- table 1
    st.markdown("#### Table 1 - Main table")
    show(T1, title=f"{nm} - main table")
    st.download_button("⬇️ Excel: main table", _xls(T1, "Main table"), f"{fn}_main_table.xlsx", XLSX, key=f"sv_t1_{code}")
    # ---- table 2
    st.markdown(f"#### Table 2 - Matching and differences ({fp} vs state report; pay vs pay policy)")
    if len(T2) and (T2.Section == "Matching").any() and T2[T2.Type == "RESULT"].Detail.astype(str).str.startswith("MATCHED").any() and not (T2.Section == "Difference to explain").any():
        st.success(f"{fp} and the {nm} state report agree trip by trip and to the cent.")
    show(T2, title=f"{nm} - matching and differences")
    st.download_button("⬇️ Excel: matching and differences", _xls(T2, "Matching and differences"), f"{fn}_matching_differences.xlsx", XLSX, key=f"sv_t2_{code}")
    # ---- table 3
    st.markdown(f"#### Table 3 - Claim to {fp}")
    n_claim = len(T3) - 1 if len(T3) else 0
    if n_claim > 0: st.error(f"Claim to {fp}: {n_claim} trips, {_money(T3.iloc[-1]['Short'])}")
    else: st.success(f"No trip was paid below the agreed price by {fp}.")
    if len(ms) and not D["estimates"].empty: st.info(f"Not claimed (price estimated from other routes with similar miles - verify first): {len(D['estimates'])} trips")
    show(T3, title=f"{nm} - claim to {fp}")
    st.download_button("⬇️ Excel: claim", _xls(T3, f"Claim to {fp}"), f"{fn}_claim.xlsx", XLSX, key=f"sv_t3_{code}")
