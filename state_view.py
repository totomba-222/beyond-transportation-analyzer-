"""Professional on-screen state report layout for the Beyond Transportation analyzer."""
import html
import numpy as np
import pandas as pd
import streamlit as st
import pdf_generator as PG


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _money(v):
    if v is None or pd.isna(v):
        return "n/a"
    return f"(${abs(v):,.2f})" if v < -0.004 else f"${v:,.2f}"


def _safe(value):
    return html.escape(str(value))


def _inject_styles():
    st.markdown(
        """
        <style>
        .state-hero {
            background: linear-gradient(135deg, #102a43 0%, #1f4e79 58%, #2c7a7b 100%);
            border-radius: 18px;
            padding: 28px 32px 25px;
            color: white;
            margin: 4px 0 22px;
            box-shadow: 0 12px 30px rgba(16, 42, 67, .16);
        }
        .state-hero .eyebrow { color: #a7f3d0; text-transform: uppercase; letter-spacing: .13em; font-size: 11px; font-weight: 700; margin-bottom: 8px; }
        .state-hero h1 { color: white; font-size: 32px; line-height: 1.1; margin: 0 0 8px; font-weight: 750; }
        .state-hero p { color: #dbeafe; margin: 0; font-size: 14px; }
        .state-status { display: inline-block; margin-top: 18px; padding: 6px 11px; border-radius: 999px; font-size: 12px; font-weight: 700; background: rgba(255,255,255,.14); color: #f8fafc; }
        .state-status.good { background: #bbf7d0; color: #14532d; }
        .state-status.warn { background: #fde68a; color: #713f12; }
        .kpi-card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 16px 17px 14px; min-height: 92px; box-shadow: 0 4px 14px rgba(15, 23, 42, .05); }
        .kpi-label { color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; line-height: 1.3; }
        .kpi-value { color: #0f172a; font-size: 23px; font-weight: 750; margin-top: 8px; line-height: 1.1; }
        .report-section { border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 26px; }
        .report-section h3 { color: #102a43; font-size: 19px; margin: 0 0 4px; }
        .report-section p { color: #64748b; font-size: 13px; margin: 0 0 13px; }
        .report-note { background: #f8fafc; border-left: 4px solid #2c7a7b; padding: 12px 15px; border-radius: 0 10px 10px 0; color: #475569; font-size: 13px; margin: 10px 0 16px; }
        div[data-testid="stDownloadButton"] button { border-radius: 9px; font-weight: 650; }
        div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(D):
    ms, fp, nm = D["ms"], D["fp"], D["name"]
    k = {} if len(ms) == 0 else {
        f"{fp} trips": f"{len(ms):,}",
        "Drivers": f"{ms.driver.nunique():,}",
        "Miles": f"{ms.miles.sum(min_count=1):,.0f}",
        f"{fp} revenue (paid)": _money(ms.main_amount.sum(min_count=1)),
    }
    if D["has_rep"]:
        r = D["fin"][D["fin"].State == nm].iloc[0]
        k.update({
            "State report trips": f"{int(r['Trips']):,}",
            "State report revenue": _money(r["Revenue"]),
            "Driver payments": _money(r["Driver Payments"]),
            "Monitor payments": _money(r["Monitor payments"]),
            "Profit": _money(r["Profit"]),
            "Margin %": f"{r['Margin %']:.1f}%",
        })
    return k


def _kpi_cards(k):
    cols = st.columns(min(5, max(1, len(k))))
    for index, (label, value) in enumerate(k.items()):
        col = cols[index % len(cols)]
        col.markdown(
            f'<div class="kpi-card"><div class="kpi-label">{_safe(label)}</div><div class="kpi-value">{_safe(value)}</div></div>',
            unsafe_allow_html=True,
        )
        if (index + 1) % len(cols) == 0 and index + 1 < len(k):
            cols = st.columns(min(5, len(k) - index - 1))


def recon_row(D):
    rc, fp, nm, ms = D["recon"], D["fp"], D["name"], D["ms"]
    a, so, fo = rc["a"], rc["state_only"], rc["first_only"]
    fr = D["fin"][D["fin"].State == nm].iloc[0]
    ok = len(a) + len(so) + len(fo) + rc["review"] == 0
    return pd.DataFrame([{
        f"{fp} trips": len(ms), "State report trips": int(fr["Trips"]), "Matched trips": rc["matched"],
        f"In {fp}, NOT in state report": len(fo), f"In state report, NOT in {fp}": len(so),
        "Trips with price difference": len(a), "Manual review": rc["review"],
        f"{fp} revenue": ms.main_amount.sum(min_count=1), "State report revenue": float(fr["Revenue"]),
        "Result": "MATCHED to the cent" if ok else "DIFFERENCES - see below",
    }])


def main_table(D):
    k = kpi_row(D)
    rows = [{"KPI": a, "Value": b} for a, b in k.items()]
    if D.get("control"):
        rows.append({"KPI": "How each trip got its state (state report > school/route > driver map)", "Value": D["control"]})
    return pd.DataFrame(rows)


def match_table(D):
    fp, nm, ms = D["fp"], D["name"], D["ms"]
    rows = []

    def add(sec, typ, trips=np.nan, detail="", diff=np.nan, driver="", route="", dates=""):
        rows.append({"Section": sec, "Type": typ, "Driver": driver, "Route": route, "Trips": trips, "Dates": dates, "Detail": detail, "Difference": diff})

    if D["has_rep"] and len(ms):
        rc = D["recon"]
        a, so, fo = rc["a"], rc["state_only"], rc["first_only"]
        fr = D["fin"][D["fin"].State == nm].iloc[0]
        add("Matching", f"{fp} trips", len(ms), f"{fp} revenue {_money(ms.main_amount.sum(min_count=1))}")
        add("Matching", "State report trips", int(fr["Trips"]), f"State report revenue {_money(fr['Revenue'])}")
        add("Matching", "Matched trips", rc["matched"], "same trip on both sides")
        add("Matching", f"In {fp}, NOT in the state report", len(fo), f"{fp} revenue {_money(fo['First Revenue'].sum()) if len(fo) else _money(0)}", fo["First Revenue"].sum() if len(fo) else 0.0)
        add("Matching", "In the state report, NOT in {fp}".format(fp=fp), len(so), f"State revenue {_money(so['State Revenue'].sum()) if len(so) else _money(0)}", so["State Revenue"].sum() if len(so) else 0.0)
        add("Matching", "Trips with a price difference", len(a), f"{fp} minus state report", a["Difference (First - State)"].sum() if len(a) else 0.0)
        add("Matching", "Manual review", rc["review"], "low-confidence matches")
        add("Matching", "RESULT", np.nan, "MATCHED to the cent" if (len(a) + len(so) + len(fo) + rc["review"] == 0) else "DIFFERENCES - see the items below")
    elif D["has_rep"]:
        add("Matching", "No " + fp + " report uploaded", np.nan, f"Upload the {fp} report to reconcile {nm} trip by trip")
    else:
        add("Matching", "No state report uploaded", np.nan, f"Upload the {nm} state report")

    if D["has_rep"] and len(D["paysum"]):
        for r in D["paysum"].itertuples():
            add("Pay policy", r.Category, r.Trips, f"State report pay {_money(r._3)}", r._4)

    t = pd.DataFrame(rows)
    if D["has_rep"]:
        mt = PG.manager_table(D)
        if len(mt):
            mt = mt.assign(Section="Difference to explain")
            mt = mt[["Section", "Type", "Driver", "Route", "Trips", "Dates", "Detail", "Difference"]]
            t = pd.concat([t, mt], ignore_index=True)
    t["State manager explanation"] = ""
    return t


def claims_table(D, rate, err):
    import simple_reports as SR
    parts = [PG._claim_rows(D)]
    ak = D.get("ak")
    if ak and len(ak[3]):
        a = ak[3]
        parts.append(pd.DataFrame({
            "Date": a["Date"], "Driver": a["Driver"], "Trip ID": a["Trip ID"], "Trip Name": a["Trip Name"],
            "Agreed price": a["Official price"], "Paid": a["Price paid"], "Short": a["Shortfall"],
            "Basis": "Alaska fixed $2.50 (42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)",
        }))
    if D["has_rep"] and D["code"] != "AK":
        rr = SR.apply_rate_rule(D["rs"], rate, err)
        g = rr[(rr.state == D["code"]) & (rr.audit_status == "REVENUE MISMATCH") & (rr.revenue_difference < -0.004)]
        if len(g):
            parts.append(pd.DataFrame({
                "Date": g.date, "Driver": g.driver, "Trip ID": g.main_trip_id, "Trip Name": g.trip_name,
                "Agreed price": g.state_revenue, "Paid": g.main_revenue, "Short": -g.revenue_difference,
                "Basis": "Paid less than the state report price",
            }))
    parts = [p for p in parts if len(p)]
    cols = ["Date", "Driver", "Trip ID", "Trip Name", "Agreed price", "Paid", "Short", "Basis"]
    if not parts:
        return pd.DataFrame(columns=cols)
    t = pd.concat(parts, ignore_index=True).drop_duplicates(["Date", "Driver", "Trip Name"]).sort_values(["Short", "Date"], ascending=[False, True]).reset_index(drop=True)
    total = {c: "" for c in cols}
    total.update({"Driver": f"TOTAL ({len(t)} trips)", "Short": t.Short.sum()})
    return pd.concat([t, pd.DataFrame([total])], ignore_index=True)


def tables_workbook(D, rate, err):
    import excel_generator as EG
    return EG.build_workbook({"1 Main table": main_table(D), "2 Matching and differences": match_table(D), f"3 Claim to {D['fp']}"[:31]: claims_table(D, rate, err)})


def _xls(df, name):
    import excel_generator as EG
    return EG.build_workbook({name[:31]: df})


def _section(title, description):
    st.markdown(f'<div class="report-section"><h3>{_safe(title)}</h3><p>{_safe(description)}</p></div>', unsafe_allow_html=True)


def render(code, main, rec, hist, book, rate, err, show):
    _inject_styles()
    D = PG.state_report_data(code, main, rec, book, rate, err)
    nm, fp, ms = D["name"], D["fp"], D["ms"]
    fn = nm.replace(" ", "_").replace("(", "").replace(")", "")
    T1, T2, T3 = main_table(D), match_table(D), claims_table(D, rate, err)

    has_rep = D["has_rep"]
    reconciliation_ok = bool(len(T2) and (T2.Section == "Matching").any() and T2[T2.Type == "RESULT"].Detail.astype(str).str.startswith("MATCHED").any() and not (T2.Section == "Difference to explain").any())
    status_text = "Reconciled to the cent" if reconciliation_ok else ("State report loaded · review differences" if has_rep else "Awaiting state report")
    status_class = "good" if reconciliation_ok else "warn"

    st.markdown(
        f'<div class="state-hero"><div class="eyebrow">Beyond Transportation · State intelligence report</div>'
        f'<h1>{_safe(nm)}</h1><p>{_safe(fp)} provider report compared with the official state report</p>'
        f'<span class="state-status {status_class}">{_safe(status_text)}</span></div>',
        unsafe_allow_html=True,
    )

    _kpi_cards(kpi_row(D))
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1.15, 1, 1])
    with c1:
        st.download_button("Download 3-table workbook", tables_workbook(D, rate, err), f"{fn}_3_tables.xlsx", XLSX, key=f"sv_all_{code}", use_container_width=True, type="primary")
    with c2:
        st.download_button("Download PDF report", PG.state_full_report(code, main, rec, hist, book, rate, err), f"{fn}_report.pdf", "application/pdf", key=f"sv_pdf_{code}", use_container_width=True)
    with c3:
        st.download_button("Download trip details", PG.state_excel(code, main, rec, hist, book, rate, err), f"{fn}_details.xlsx", XLSX, key=f"sv_xls_{code}", use_container_width=True)

    if not has_rep:
        st.warning(f"No state report was uploaded for {nm}. Driver payments, profit, and reconciliation cannot be calculated yet.")
    if len(ms) == 0 and has_rep:
        st.warning(f"No {fp} report was uploaded for {nm}. Upload it to reconcile trip by trip and verify provider pricing.")

    tab1, tab2, tab3 = st.tabs(["Overview", "Reconciliation", "Claims & actions"])

    with tab1:
        _section("Executive overview", "Headline operating and financial measures for this state.")
        show(T1, title=f"{nm} - executive overview")
        st.download_button("Export overview", _xls(T1, "Executive overview"), f"{fn}_overview.xlsx", XLSX, key=f"sv_t1_{code}")
        if D.get("control"):
            st.markdown(f'<div class="report-note">State assignment evidence: {_safe(D["control"])}</div>', unsafe_allow_html=True)

    with tab2:
        _section("Reconciliation review", f"Trip matching, price differences, and pay-policy checks for {fp} versus the {nm} state report.")
        if reconciliation_ok:
            st.success(f"{fp} and the {nm} state report agree trip by trip and to the cent.")
        show(T2, title=f"{nm} - reconciliation review")
        st.download_button("Export reconciliation", _xls(T2, "Reconciliation review"), f"{fn}_matching_differences.xlsx", XLSX, key=f"sv_t2_{code}")

    with tab3:
        _section("Claims and actions", f"Trips where {fp} paid below the agreed price, with the amount and evidence needed for follow-up.")
        n_claim = len(T3) - 1 if len(T3) else 0
        if n_claim > 0:
            st.error(f"Claim to {fp}: {n_claim:,} trips · {_money(T3.iloc[-1]['Short'])}")
        else:
            st.success(f"No trip was paid below the agreed price by {fp}.")
        if len(ms) and not D["estimates"].empty:
            st.info(f"Not claimed: {len(D['estimates']):,} trips use prices estimated from similar routes. Verify before taking action.")
        show(T3, title=f"{nm} - claim to {fp}")
        st.download_button("Export claim list", _xls(T3, f"Claim to {fp}"), f"{fn}_claim.xlsx", XLSX, key=f"sv_t3_{code}")
