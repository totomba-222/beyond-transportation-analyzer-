"""Professional PDF reports (reportlab). Portrait pages for summaries, landscape for wide tables,
repeating table headers, page numbers, USD formatting with negatives in red parentheses.
Missing values print as 'n/a' (never 0). Nothing is invented: an empty scope prints a notice."""
import io
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, BaseDocTemplate, Frame, Image, LongTable, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, TableStyle)
import financial_calculations as F, weekly_reports as W, monthly_reports as M
from config import STATE_NAMES

BRAND, TITLE = "Beyond Transportation", "Beyond Transportation – Financial & Operations Audit Report"
NAVY, GREY = colors.HexColor("#1F3A5F"), colors.HexColor("#F2F5F9")
SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontName="Helvetica-Bold", fontSize=15, textColor=NAVY, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("b", parent=SS["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11)
MONEY_K = ("revenue", "payment", "profit", "difference", "shortfall", "owed", "expected", "actual", "cost", "spent", "price", "paid", "adjust")


def usd(v):
    return "n/a" if pd.isna(v) else (f"(${abs(v):,.2f})" if v < -0.004 else f"${abs(v) if abs(v) < 0.005 else v:,.2f}")


def fmt_cell(col, v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "n/a"
    low = str(col).lower()
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (int, float, np.integer, np.floating)):
        if low.startswith("trips") and "%" not in low:
            return f"{v:,.0f}"
        if "%" in low or "margin" in low or "change" in low:
            return f"{v:,.1f}%"
        if any(k in low for k in MONEY_K):
            return usd(float(v))
        if "miles" in low:
            return f"{v:,.1f}"
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return str(v)


def df_table(df, width, font=7):
    df = df.reset_index(drop=True)
    data = [[Paragraph(f"<b>{c}</b>", ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=font, textColor=colors.white, leading=font + 2)) for c in df.columns]]
    for _, r in df.iterrows():
        data.append([Paragraph(fmt_cell(c, r[c]).replace("&", "&amp;").replace("<", "&lt;"), ParagraphStyle("td", fontName="Helvetica", fontSize=font, leading=font + 2,
                     alignment=2 if isinstance(r[c], (int, float, np.number)) else 0)) for c in df.columns])
    lens = [max([len(str(c)) * 0.8] + [min(len(fmt_cell(c, v)), 28) for v in df[c].head(150)]) + 2 for c in df.columns]
    tot = sum(lens)
    t = LongTable(data, colWidths=[width * l / tot for l in lens], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D1DC")),
          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY])]
    t.setStyle(TableStyle(st))
    return t


def _chart(df, x, ys, title):
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 2.8)); d = df.set_index(x)[ys]
    d.plot(kind="bar", ax=ax, color=["#1F3A5F", "#2E8B57", "#C9A227"][:len(ys)], width=0.75)
    ax.set_title(title, fontsize=9); ax.set_xlabel(""); ax.tick_params(labelsize=7); ax.legend(fontsize=7)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    plt.xticks(rotation=20); plt.tight_layout(); b = io.BytesIO(); fig.savefig(b, format="png", dpi=160); plt.close(fig); b.seek(0)
    return Image(b, width=170 * mm, height=63 * mm)


class Report:
    def __init__(self, subtitle, period):
        self.subtitle, self.period, self.story = subtitle, period, []
        self.pw, self.ph = A4; self.lw, self.lh = landscape(A4); self.mode = "P"; self.start = "P"
        self.generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _deco(self, c, doc):
        w, h = c._pagesize
        c.saveState(); c.setFillColor(NAVY); c.rect(0, h - 16 * mm, w, 16 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 10); c.drawString(12 * mm, h - 8 * mm, TITLE)
        c.setFont("Helvetica", 8); c.drawString(12 * mm, h - 12.5 * mm, f"{self.subtitle}  |  Period: {self.period}")
        c.setFillColor(colors.grey); c.setFont("Helvetica", 7)
        c.drawString(12 * mm, 7 * mm, f"{BRAND} - generated {self.generated} - all amounts in USD")
        c.drawRightString(w - 12 * mm, 7 * mm, f"Page {doc.page}"); c.restoreState()

    def portrait(self):
        if self.mode != "P": self.story += [NextPageTemplate("P"), PageBreak()]; self.mode = "P"
    def land(self):
        if self.mode != "L":
            only_text = not any(isinstance(x, (LongTable, Image, PageBreak)) for x in self.story)
            if only_text:                      # nothing but headings so far: start the document in landscape (no blank page)
                self.start = "L"
            else:
                self.story += [NextPageTemplate("L"), PageBreak()]
            self.mode = "L"
    @property
    def width(self): return (self.pw if self.mode == "P" else self.lw) - 24 * mm

    def section(self, mode):
        self.story += [NextPageTemplate(mode), PageBreak()]; self.mode = mode
    def h1(self, t): self.story.append(Paragraph(t, H1))
    def h2(self, t): self.story.append(Paragraph(t, H2))
    def p(self, t): self.story.append(Paragraph(t, BODY))
    def kpis(self, d):
        rows = [[k, fmt_cell(k, v)] for k, v in d.items()]
        t = df_table(pd.DataFrame(rows, columns=["KPI", "Value"]).astype(object), 90 * mm, 8)
        self.story += [t, Spacer(1, 6)]
    def table(self, df, title=None, wide=True, font=None):
        (self.land if wide else self.portrait)()
        if title: self.h2(title)
        if df is None or len(df) == 0: self.p("No records in this scope."); return
        self.story.append(df_table(df, self.width, font or (6.5 if len(df.columns) > 9 else 7.5)))
    def chart(self, df, x, ys, title):
        img = _chart(df, x, ys, title)
        if img is not None: self.story += [img, Spacer(1, 6)]

    def build(self) -> bytes:
        buf = io.BytesIO()
        doc = BaseDocTemplate(buf, pagesize=A4, title=f"{TITLE} - {self.subtitle}", author=BRAND)
        fp = Frame(12 * mm, 12 * mm, self.pw - 24 * mm, self.ph - 32 * mm, id="fp")
        fl = Frame(12 * mm, 12 * mm, self.lw - 24 * mm, self.lh - 32 * mm, id="fl")
        tp = [PageTemplate("P", [fp], onPage=self._deco, pagesize=A4), PageTemplate("L", [fl], onPage=self._deco, pagesize=landscape(A4))]
        doc.addPageTemplates(tp if self.start == "P" else tp[::-1])
        self.story += [Spacer(1, 26), KeepTogether([Paragraph("_______________________________", BODY),
                       Paragraph("<b>Hatem Elalfy</b><br/>CFO", BODY)])]
        doc.build(self.story); return buf.getvalue()


# ---------------------------------------------------------------- report builders
TRIP_COLS = {"date": "Date", "driver": "Driver", "main_trip_id": "Trip ID", "trip_name": "Trip Name", "main_miles": "Miles",
             "main_revenue": "Main Revenue", "state_revenue": "State Revenue", "driver_payment": "Driver Payment",
             "profit": "Profit", "revenue_difference": "Difference", "audit_status": "Status"}
EXC_OK = ["EXACT MATCH", "MATCHED", "STATE REPORT NOT UPLOADED", "MONITOR PAYMENT"]


def _period(rec):
    d = rec.date.dropna() if "date" in rec else []
    return "n/a" if len(d) == 0 else f"{d.min():%Y-%m-%d} to {d.max():%Y-%m-%d}"


def _trip_table(r):
    t = r.sort_values(["driver", "date"])[list(TRIP_COLS)].rename(columns=TRIP_COLS)
    return t


def _status_counts(rec):
    return rec.audit_status.value_counts().rename_axis("Audit Status").reset_index(name="Trips")


def consolidated(rec, main=None, verified=True):
    R_ = Report("Consolidated Company Report", _period(rec))
    R_.h1("Executive Summary"); k = F.kpis(rec, verified); R_.kpis(k)
    R_.p("Revenue = main-company report amount. Driver payments and profit come only from uploaded state reports and only for trips having both a state revenue and a driver payment; missing values are reported, never treated as zero.")
    st = F.state_table(rec, verified); R_.chart(st[st.State != "TOTAL"], "State", ["Revenue", "Driver Payments", "Profit"], "Revenue, payments and profit by state")
    R_.table(st.drop(columns=["Rows missing revenue/payment"], errors="ignore"), "State comparison")
    if "provider" in rec:
        R_.table(F.group_table(rec[rec.provider != ""], "provider").drop(columns=["Rows missing revenue/payment"]), "Revenue by transportation provider")
    R_.table(_status_counts(rec), "Audit status summary", wide=False)
    return R_.build()


def provider_audit(rec, provider, label):
    r = rec[rec.provider == provider]; R_ = Report(f"{label} Audit Report", _period(r))
    R_.h1(f"{label} Audit")
    if r.empty:
        R_.p(f"No {label} records were uploaded. No figures are shown."); return R_.build()
    R_.kpis(F.kpis(r)); R_.table(F.state_table(r).drop(columns=["Rows missing revenue/payment"]), "By state")
    R_.table(_status_counts(r), "Audit status summary", wide=False)
    R_.table(_trip_table(r[~r.audit_status.isin(EXC_OK)]), "Exceptions"); return R_.build()


def state_report(rec, code, trips=True):
    r = rec[rec.state == code]; name = STATE_NAMES.get(code, code)
    R_ = Report(f"{name} - {'Trip Details' if trips else 'Financial Report'}", _period(r))
    R_.h1(name)
    if r.empty:
        R_.p("No records for this state."); return R_.build()
    k = F.kpis(r); R_.kpis({**k, "Avg revenue/trip": k["Revenue"] / k["Trips"] if k["Trips"] else np.nan,
                            "Avg driver payment/trip": (r.driver_payment.sum(min_count=1) / r.driver_payment.notna().sum()) if r.driver_payment.notna().any() else np.nan})
    if not trips:
        R_.table(F.driver_table(r).drop(columns=["Rows missing revenue/payment"]), "Driver performance")
        R_.table(_status_counts(r), "Audit findings", wide=False)
        R_.table(_trip_table(r[~r.audit_status.isin(EXC_OK)]), "Discrepancies and exceptions")
    else:
        R_.table(_trip_table(r), "Individual trip details")
    return R_.build()


def driver_report(rec, state=None):
    r = rec[rec.state == state] if state else rec; R_ = Report("Driver Performance Report", _period(r))
    R_.h1("Driver performance"); R_.table(F.driver_table(r).drop(columns=["Rows missing revenue/payment"]), "Drivers ranked by revenue")
    return R_.build()


def weekly(rec, week=None):
    R_ = Report("Weekly Comparison Report", _period(rec)); R_.h1("Weekly performance comparison")
    t, ci, pi, warns = W.weekly_report(rec, week)
    if t is None: R_.p(warns[0]); return R_.build()
    R_.p(f"Current week: {ci['start']:%Y-%m-%d} to {ci['end']:%Y-%m-%d} (trips {ci['first_trip']:%Y-%m-%d} to {ci['last_trip']:%Y-%m-%d}). "
         f"Previous week: {pi['start']:%Y-%m-%d} to {pi['end']:%Y-%m-%d}.")
    for w in warns: R_.p(f"<b>Warning:</b> {w}")
    R_.table(t, "Company", wide=False)
    for by, lab in (("state", "By state"), ("provider", "By provider")):
        x, *_ = W.weekly_report(rec, week, by=by)
        if x is not None and len(x): R_.table(x, lab)
    return R_.build()


def monthly(rec):
    R_ = Report("Monthly Financial Report", _period(rec)); R_.h1("Monthly financial report")
    t = M.monthly_table(rec); R_.chart(t, "Month", ["Revenue", "Driver Payments", "Profit"], "Monthly revenue, payments and profit")
    R_.table(t.drop(columns=["Rows missing revenue/payment"], errors="ignore"), "Company by month")
    s = M.monthly_table(rec, by="state"); R_.table(s.drop(columns=["Rows missing revenue/payment"], errors="ignore"), "State by month")
    return R_.build()


def reconciliation(rec):
    R_ = Report("Revenue Reconciliation Report", _period(rec)); R_.h1("Revenue reconciliation")
    R_.table(pd.crosstab(rec.state, rec.audit_status).reset_index(), "Audit status by state")
    R_.table(_trip_table(rec[rec.revenue_difference.abs() > 0.005]), "Trips with a revenue difference"); return R_.build()


def exceptions(rec, excluded=None, control=None):
    R_ = Report("Exceptions and Discrepancies Report", _period(rec)); R_.h1("Exceptions and discrepancies")
    ex = rec[~rec.audit_status.isin(EXC_OK)]; R_.table(_status_counts(ex), "Exceptions by status", wide=False)
    cols = {**TRIP_COLS, "notes": "Notes", "main_source": "Main source", "state_source": "State source"}
    R_.table(ex.sort_values(["audit_status", "state"])[list(cols)].rename(columns=cols), "All exceptions (with source file#sheet!row)", font=6)
    if control is not None and len(control):
        c = control[control.difference.abs() > 0.005]
        R_.table(c.rename(columns={"src_file": "File", "src_row": "Row"}), "Source-report totals that do not match their own detail rows")
    return R_.build()


def alaska(rec, main, rate):
    R_ = Report("Alaska Rate Audit", _period(rec[rec.state == "AK"])); R_.h1("Alaska rate audit")
    a, b, by_rate, under = F.alaska_audit(rec, main, rate)
    R_.kpis(a); R_.kpis(b); R_.table(by_rate, "Shortfall by rate", wide=False)
    R_.table(_trip_table(under.assign(revenue_difference=-under.shortfall)), "Affected trips"); return R_.build()


# ---------------------------------------------------------------- simple 3-stage reports
import simple_reports as SR


def _fig_img(fig, w=250):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=150); plt.close(fig); b.seek(0)
    return Image(b, width=w * mm, height=w * mm * 0.33)


def _add_first(R_, main, label, adjustments=None, rate=None, err=None):
    R_.h1(f"{label}: overall and by state")
    o = SR.first_overview(main, adjustments); k = {"Total trips": o["Trips"], "Total revenue (trip price paid)": o["Revenue"], "Drivers": o["Drivers"], "Miles": o["Miles"]}
    if "Adjustments" in o: k.update({"Adjustments (non-trip, e.g. drug test)": o["Adjustments"], "Net revenue received": o["Net revenue"]})
    R_.kpis(k)
    if main.provider.nunique() > 1:
        R_.table(SR.provider_table(main), "Totals by provider")
        R_.table(SR.state_provider_table(main), "Totals by state and provider")
    t = SR.first_state_table(main); R_.table(t, "Totals by state (all providers combined)")
    R_.land(); R_.story.append(_fig_img(SR.share_figure(t, ("Trips", "Revenue"))))
    if rate:
        s, grp, drv, _ = SR.first_rate_audit(main, rate, err=err)
        if s["Trips below official rate"]:
            R_.section("L"); R_.h1(f"Alaska rate check ({label} report only)")
            R_.p(f"{s['Trips below official rate']} Alaska trips of {s['Alaska trips in report']} were paid ${SR._err(err):,.2f} instead of the official ${rate:,.2f}. "
                 f"Total owed by the provider: <b>{usd(s['Total owed'])}</b>. Trip-by-trip detail is in the Excel file.")
            R_.table(grp, f"Claim: trips paid ${SR._err(err):,.2f} instead of the official ${rate:,.2f}", font=8); R_.table(drv, "Claim by driver", font=7)
            if s["Other trips below the rate (not claimed)"]:
                R_.p(f"Note: {s['Other trips below the rate (not claimed)']} other Alaska trips were paid below the rate at a different price ({s['Other prices (not claimed)']}); "
                     f"they are not part of this claim (shortfall {usd(s['Their shortfall (not claimed)'])}).")
    un = main[main.state == "Unassigned"]
    if len(un): R_.p(f"<b>Note:</b> {len(un)} trips ({usd(un.main_amount.sum())}) of {un.driver.nunique()} drivers have no state yet (new drivers not found in any state report). "
                     "They are shown as 'Unassigned' - upload the state reports or assign the drivers in the app.")


def _add_states(R_, rec):
    R_.h1("State reports: revenue, payments, profit and margin")
    t = SR.state_financials(rec)
    if t.empty: R_.p("No state reports uploaded."); return
    R_.table(t, "All states")
    if t["Monitor payments"].sum() > 0: R_.p("Monitor (MO) payments are costs: they are included in Driver Payments and in Profit; monitors have no trip revenue of their own.")
    R_.chart(t[t.State != "TOTAL"], "State", ["Revenue", "Driver Payments", "Profit"], "Revenue, driver payments and profit by state")


def _add_disc(R_, rec, rate=45.0, err=None):
    rec = SR.apply_rate_rule(rec, rate, err)
    R_.h1("Differences between First and the state reports")
    t = SR.discrepancy_summary(rec)
    if t.empty: R_.p("No state reports uploaded."); return
    R_.table(SR.revenue_bridge(rec, rate, err), "Revenue bridge: First/EverDriven revenue to state-report revenue (every dollar explained)", font=7)
    R_.table(t, "Summary by state (difference = First revenue - state revenue)", font=6.5)
    for code in rec[rec.state_source != ""].state.unique():
        nm = STATE_NAMES.get(code, code); a, s, f = SR.discrepancy_sections(rec, code)
        claim, other = SR.claim_split(rec, code, rate, err)
        if len(claim):
            R_.table(claim, f"{nm} - CLAIM TO FIRST: trips paid ${SR._err(err):,.2f} instead of the official ${rate:,.2f}", font=8)
            d = SR.claim_by_driver(rec, code, rate, err)
            if len(d): R_.table(d, f"{nm} - claim by driver (trip-by-trip detail is in the Excel file)", font=7)
        so = SR.state_only_by_driver(rec, code)
        if len(so): R_.table(so, f"{nm} - trips in the state report but NOT in First/EverDriven, by driver (detail is in the Excel file)", font=7)
        mo = SR.monitor_by_driver(rec, code)
        if len(mo): R_.table(mo, f"{nm} - monitor (MO) payments: monitors ride next to the driver, so there is no separate trip revenue (information only, not a discrepancy)", font=7)
        n_acc, amt_acc = SR.accepted_summary(rec[rec.state == code])
        if n_acc: R_.p(f"Note: {n_acc} {nm} trips with other price differences (total {usd(abs(amt_acc))}) are treated as correct and are not part of the claim; only trips paid ${SR._err(err):,.2f} are claimed.")
        if len(f): R_.table(f, f"{nm} - trips in First but NOT in the state report", font=6.5)


def first_report(main, label=None, adjustments=None, rate=None, err=None):
    label = label or SR.provider_label(main)
    R_ = Report(f"{label} Report", _period(main)); _add_first(R_, main, label, adjustments, rate, err); return R_.build()


def states_financial_report(rec):
    R_ = Report("State Financial Report", _period(rec)); _add_states(R_, rec); return R_.build()


def discrepancy_report(rec, rate=45.0, err=None):
    R_ = Report("Price Discrepancy Report", _period(rec)); _add_disc(R_, rec, rate, err); return R_.build()


def combined_report(main, rec, label=None, rate=45.0, adjustments=None, err=None):
    label = label or SR.provider_label(main)
    R_ = Report("Combined Report", _period(main)); _add_first(R_, main, label, adjustments)
    if (rec.state_source != "").any():
        R_.section("L"); _add_states(R_, rec); R_.section("L"); _add_disc(R_, rec, rate, err)
    return R_.build()
