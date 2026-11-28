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
    """Trips paid below the agreed price + a TOTAL row (the same list as the PDF: pdf_generator.claims_all)."""
    cols = ["Date", "Driver", "Trip ID", "Trip Name", "Agreed price", "Paid", "Short", "Basis"]
    t = PG.claims_all(D, rate, err)
    if t.empty:
        return pd.DataFrame(columns=cols)
    return t.reset_index(drop=True)


def tables_workbook(D, rate, err):
    import excel_generator as EG
    return EG.build_workbook({"1 Main table": main_table(D), "2 Matching and differences": match_table(D), f"3 Claim to {D['fp']}"[:31]: claims_table(D, rate, err)})


def _xls(df, name):
    import excel_generator as EG
    return EG.build_workbook({name[:31]: df})


def _section(title, description):
    st.markdown(f'<div class="report-section"><h3>{_safe(title)}</h3><p>{_safe(description)}</p></div>', unsafe_allow_html=True)


def _calm_styles():
    st.markdown(
        """
        <style>
        .kpi-card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 14px; }
        .kpi-label { color: #6b7280; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
        .kpi-value { color: #1f2937; font-size: 21px; font-weight: 650; margin-top: 6px; line-height: 1.1; }
        .calm-note { color: #6b7280; font-size: 13px; margin: 4px 0 10px; }
        div[data-testid="stDownloadButton"] button { border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _fmt_rows(rows):
    """Comparison rows of simple_pdf._compare_rows -> a table of strings (this week / last week / difference / change)."""
    import simple_pdf as SP
    out = []
    for r in rows:
        cur, prev = r["cur"], r["prev"]
        diff = (float(cur) - float(prev)) if not SP._na(cur) and not SP._na(prev) else np.nan
        pc = diff / abs(float(prev)) * 100 if not SP._na(diff) and float(prev) else np.nan
        d_txt = "n/a" if SP._na(diff) else (SP.pts(diff) if r.get("pts") else (f"{diff:+,.0f}" if r["fmt"] in (SP.num, SP.miles) else SP.usd(diff)))
        out.append({"": r["label"], "This week": r["fmt"](cur), "Last week": r["fmt"](prev), "Difference": d_txt, "Change": "n/a" if r.get("pts") else SP.chg(pc)})
    return pd.DataFrame(out)


def render(code, main, rec, hist, book, rate, err, show):
    """Simple on-screen state report: the same four parts as the PDF (summary, paid below the agreed price, pay above the policy, comparison)."""
    import simple_pdf as SP
    _calm_styles()
    D = PG.state_report_data(code, main, rec, book, rate, err)
    S = SP.state_summary(D, rate, err)
    nm, fp, ms = D["name"], D["fp"], D["ms"]
    fn = nm.replace(" ", "_").replace("(", "").replace(")", "")

    st.subheader(nm)
    st.caption(f"{fp} vs state report  |  {PG._period(ms if len(ms) else D['rs'])}")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download compact PDF report", PG.state_compact_report(code, main, rec, hist, book, rate=rate, err=err), f"{fn}_compact_report.pdf", "application/pdf", key=f"sv_pdf_{code}", use_container_width=True, type="primary")
    with c2:
        st.download_button("Download Excel (all details)", PG.state_excel(code, main, rec, hist, book, rate, err), f"{fn}_details.xlsx", XLSX, key=f"sv_xls_{code}", use_container_width=True)

    if S["has_rep"]:
        _kpi_cards({"Trips": f"{S['trips']:,}", "Revenue": _money(S["state_revenue"]), "Driver payments": _money(S["payments"]), "Profit": _money(S["profit"]),
                    "Margin": SP.pct(S["margin"])})
        if S["recon_ok"] is True:
            st.markdown(f'<div class="calm-note">Matched with the state report: {S["trips"]:,} trips, revenue equal to the cent.</div>', unsafe_allow_html=True)
        elif S["recon_ok"] is False:
            a_, so_, fo_, rv_ = S["recon_counts"]
            st.warning(f"Differences with the state report: {a_} trips with a price difference, {fo_} only in {fp}, {so_} only in the state report" + (f", {rv_} to review" if rv_ else "") + ". See the Excel file, sheet 'For state manager'.")
    else:
        st.warning(f"No state report was uploaded for {nm}. Driver payments, profit and margin cannot be calculated yet.")
        _kpi_cards({f"{fp} trips": f"{S['first_trips']:,}", f"{fp} revenue": _money(S["first_revenue"])})

    show(pd.DataFrame([
        {"": "Trips", nm: SP.num(S["first_trips"]), f"All {fp} states": SP.num(S["prov_trips"]), "Share": SP.pct(S["share_trips"])},
        {"": f"Revenue paid by {fp}", nm: SP.usd(S["first_revenue"]), f"All {fp} states": SP.usd(S["prov_revenue"]), "Share": SP.pct(S["share_revenue"])},
    ]))

    tab1, tab2, tab3 = st.tabs(["Paid below the agreed price", "Pay above the policy", "Comparison with last week"])

    with tab1:
        T3 = claims_table(D, rate, err)
        n_claim = len(T3)
        if not len(ms):
            st.info(f"No {fp} report was uploaded for {nm}, so the prices {fp} paid cannot be checked.")
        elif n_claim > 0:
            st.error(f"Claim to {fp}: {n_claim:,} trips  |  {_money(T3['Short'].sum())}")
            show(T3, 400)
            if D["code"] == "N.CA":
                st.caption("Benicia routes are listed at $45 because First cut them from $50; after the N.CA manager spoke to First, it added $5 on some Richmond routes (now $55-$60). These list prices are the agreed prices, not a claim.")
        else:
            st.success(f"No trip was paid below the agreed price by {fp}.")

    with tab2:
        if not S["has_rep"]:
            st.info("Needs the state report (it holds the driver payments).")
        elif S["above_trips"] == 0:
            st.success("All checked trips are within the pay policy. Profit and margin are unchanged.")
        else:
            st.error(f"{S['above_trips']:,} trips paid above the policy  |  excess driver pay {_money(S['above_amount'])}")
            show(pd.DataFrame([
                {"": "Actual", "Revenue": SP.usd(S["state_revenue"]), "Driver payments": SP.usd(S["payments"]), "Profit": SP.usd(S["profit"]), "Margin": SP.pct(S["margin"])},
                {"": "If the policy was applied", "Revenue": SP.usd(S["state_revenue"]), "Driver payments": SP.usd(S["payments_policy"]), "Profit": SP.usd(S["profit_policy"]), "Margin": SP.pct(S["margin_policy"])},
                {"": "Loss from not applying the policy", "Revenue": "", "Driver payments": SP.usd(S["above_amount"]), "Profit": SP.usd(S["above_amount"]),
                 "Margin": SP.pts(S["margin_policy"] - S["margin"]) if pd.notna(S["margin_policy"]) and pd.notna(S["margin"]) else "n/a"},
            ]))
            g = PG._group_pay_differences(S["above"])
            if len(g):
                show(g.drop(columns=["Miles", "Revenue", "Difference per trip", "Status"], errors="ignore"), 400)
        if S["has_rep"] and S["not_checked"]:
            st.caption(f"Not checked: {S['not_checked']:,} trips on routes that have no pay policy yet (listed in the Excel file).")

    with tab3:
        rows_c, note = SP._compare_rows(D, S, hist, None)
        show(_fmt_rows(rows_c))
        if note:
            st.caption(note)
        pick = [r for r in rows_c if r["label"] in ("Revenue", "Driver payments", "Profit") and not SP._na(r["cur"])]
        if pick:
            chart = pd.DataFrame({"This week": [float(r["cur"]) for r in pick]}, index=[r["label"] for r in pick])
            if any(not SP._na(r["prev"]) for r in pick):
                chart["Last week"] = [np.nan if SP._na(r["prev"]) else float(r["prev"]) for r in pick]
            st.bar_chart(chart)
