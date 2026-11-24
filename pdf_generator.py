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
EXP = ParagraphStyle("exp", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#4B5563"))
BODY = ParagraphStyle("b", parent=SS["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11)
MONEY_K = ("revenue", "payment", "profit", "difference", "shortfall", "owed", "expected", "actual", "cost", "spent", "price", "paid", "adjust", "pay", "short", "total")

EXPLAIN = [
    ("=Summary by state", "One row per state for driver payments. 'Trips with a pay policy' = trips whose route has a stable usual pay; only those are judged. 'Trips paid above policy' and 'Total excess pay' show overpayment; 'above trip revenue' shows trips where the driver was paid more than the trip earns."),
    ("Totals by state and provider", "The same numbers split by state, with First and EverDriven side by side. Each state normally belongs to one company (Nebraska and Kansas are EverDriven; the others are First)."),
    ("Totals by provider", "How many trips and how much money each company (First or EverDriven) paid Beyond. Revenue/Trip = revenue divided by trips. Revenue % = that company's share of all revenue."),
    ("Totals by state", "One row per state for everything uploaded. Drivers = different drivers, Miles = total miles, Revenue = money paid by First / EverDriven. Trips % and Revenue % = the state's share of the company total."),
    ("Claim: trips short", "Trips where the provider paid the official price minus a fixed $2.50 (42.50 instead of 45, 47.50 instead of 50, 82.50 instead of 85). Shortfall per trip = official minus paid. Total owed = trips x shortfall: this is the amount to claim from the provider."),
    ("CLAIM TO FIRST", "Trips that the provider paid at the wrong (error) price instead of the official price. Total owed = trips x shortfall per trip: this is the amount to claim."),
    ("claim by driver", "The same claim split by driver, so every driver's trips and amount can be checked."),
    ("Paid price vs contract price", "Compares what the provider paid for each trip with the contract price learned from earlier state reports for the same route. 'Below' = possible underpayment, 'above' = paid more than usual. Coverage = share of trips whose contract price is known."),
    ("Trips paid below the contract price", "The individual trips behind the 'below contract price' count: the price paid, the contract price and the difference. Check them with the provider."),
    ("Estimated profit by state", "ESTIMATE for states without a state report: provider revenue minus driver pay estimated from earlier weeks. It is not actual and is replaced by real numbers when the state report arrives."),
    ("Financial performance", "Actual money for this state from its state report. Revenue = what Beyond earns. Driver Payments = paid to drivers. Monitor payments = cost of monitors (no trip revenue). Profit = revenue minus payments. Margin = profit divided by revenue."),
    ("=All states", "Actual money per state from the state reports. Revenue = what Beyond earns, Driver Payments = paid to drivers, Monitor payments = cost of monitors who ride with drivers (no trip revenue). Profit = revenue minus payments; Margin % = profit divided by revenue. n/a = no state report uploaded yet."),
    ("Driver performance", "One row per driver: trips, miles, revenue, payments, profit and margin. Use it to see which drivers earn more or less for the company."),
    ("Revenue bridge", "Explains the gap between what the provider paid and what the state report says Beyond should receive, line by line. The last column must be $0.00; any other number means part of the gap is unexplained."),
    ("Summary by state (difference", "Counts of differences per state: trips with a price difference, trips missing on one side, and monitor payments. Difference = provider revenue minus state revenue (negative = the provider paid less than the state report)."),
    ("trips in the state report but NOT in First", "Trips that appear in the state report but have no matching trip in the provider report. Check whether they were really driven and whether Beyond should claim them or remove them."),
    ("monitor (MO) payments", "Payments to monitors who ride beside the driver. They are costs with no trip revenue of their own, so they are information only, not a discrepancy."),
    ("trips in First but NOT in the state report", "Trips the provider paid Beyond for that are missing from the state report. They may be unrecorded trips or a driver listed under another state."),
    ("price differences by driver", "Price differences grouped by driver, with trips, miles and the amount."),
    ("trips paid above the pay policy", "Trips where the driver was paid more than the usual pay for the same route. Excess pay = driver pay minus the policy. Review for mistakes or approved exceptions."),
    ("paid more than the trip revenue", "Trips where the driver's pay is higher than the trip's own revenue, so Beyond loses money on that trip."),
    ("=Company - all states", "Two periods for the whole company. Difference = current minus previous; Change % = difference divided by the previous value. Payments and profit only include states that have a state report, so also read the like-for-like table."),
    ("Like-for-like", "The same comparison using only the states that have a state report in BOTH periods, so payments, profit and margin are truly comparable."),
    ("State ranking", "States ranked by revenue for the latest month (1 = highest revenue)."),
    ("=Company by month", "One row per month: trips, revenue, payments, profit, margin and averages. MoM % = change versus the previous month. Months with fewer than 4 weeks are partial."),
    ("=State by month", "The same monthly figures for each state."),
    ("=By state", "Each state's trips, revenue, profit and margin for the periods compared; the % columns show the change between them."),
]


def explain_for(title):
    t = str(title or "").lower()
    for key, text in EXPLAIN:
        if (key[1:].lower() == t) if key.startswith("=") else (key.lower() in t): return text
    return None


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
    lens = [max(11, max([len(str(c)) * 0.8] + [min(len(fmt_cell(c, v)), 28) for v in df[c].head(150)]) + 2) for c in df.columns]
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
    def table(self, df, title=None, wide=True, font=None, note=None):
        (self.land if wide else self.portrait)()
        if title: self.h2(title)
        if df is None or len(df) == 0: self.p("No records in this scope."); return
        self.story.append(df_table(df, self.width, font or (6.5 if len(df.columns) > 9 else 7.5)))
        txt = note if note is not None else explain_for(title)
        if txt: self.story += [Spacer(1, 2), Paragraph("<i>What this table shows:</i> " + txt, EXP), Spacer(1, 4)]
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
        doc.build(self.story); self.pages = doc.page; return buf.getvalue()



def table_pdf(df, title, subtitle="Table", period=""):
    """One table as a PDF (used by the 'Download PDF' button under every table of the app)."""
    R_ = Report(subtitle, period); R_.land(); R_.h1(title)
    if df is None or len(df) == 0: R_.p("No records.")
    else: R_.story.append(df_table(df, R_.width, 6.5 if len(df.columns) > 9 else 7.5))
    return R_.build()


# ---------------------------------------------------------------- report builders
TRIP_COLS = {"date": "Date", "driver": "Driver", "main_trip_id": "Trip ID", "trip_name": "Trip Name", "main_miles": "Miles",
             "main_revenue": "Main Revenue", "state_revenue": "State Revenue", "driver_payment": "Driver Payment",
             "profit": "Profit", "revenue_difference": "Difference", "audit_status": "Status"}
EXC_OK = ["EXACT MATCH", "MATCHED", "STATE REPORT NOT UPLOADED", "MONITOR PAYMENT"]


def _period(rec):
    d = rec.date.dropna() if "date" in rec else []
    if len(d) > 5: d = d[(d - d.median()).abs() <= pd.Timedelta(days=45)]       # a typo'd date (e.g. 2029) must not stretch the period
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


def _add_first(R_, main, label, adjustments=None, rate=None, err=None, with_book=False, states_with_report=()):
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
            R_.p(f"{s['Trips below official rate']} Alaska trips of {s['Alaska trips in report']} were short by the fixed ${rate-SR._err(err):,.2f} each (price ending in .50, at least ${SR._err(err):,.2f}). "
                 f"Total owed by the provider: <b>{usd(s['Total owed'])}</b>. Trip-by-trip detail is in the Excel file.")
            R_.table(grp, f"Claim: trips short by the fixed ${rate-SR._err(err):,.2f} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)", font=8); R_.table(drv, "Claim by driver", font=7)
            if s["Other trips below the rate (not claimed)"]:
                R_.p(f"Note: {s['Other trips below the rate (not claimed)']} other Alaska trips were paid below the rate at a different price ({s['Other prices (not claimed)']}); "
                     f"they are not part of this claim (shortfall {usd(s['Their shortfall (not claimed)'])}).")
    if with_book:
        import ratebook as RB
        book = RB.load(); pc, _, acc = SR.price_check(main, book, SR._err(err), rate or 45.0)
        if pc.iloc[-1]["Trips paid below contract price"]:
            R_.section("L"); R_.h1("Price check against contract prices (rate book)")
            R_.p("Contract price per route learned from earlier state reports (same route, otherwise same state and miles). Alaska: only trips paid exactly the error price are claimed.")
            R_.table(pc, "Paid price vs contract price, by state", font=7)
            _, cdet, _x = SR.price_check(main, book, SR._err(err), rate or 45.0)
            for st_ in [x for x in pc.State if x != "TOTAL"]:
                dd = cdet[cdet.State == st_]
                if st_ == "Alaska" or dd.empty: continue                      # Alaska has its own claim section above
                gp, gd = SR.claim_tables(dd)
                R_.table(gp, f"{st_} - CLAIM: trips paid below the contract price (by price)", font=7.5, note="")
                R_.table(gd, f"{st_} - claim by driver (trip-by-trip detail is in the Excel file)", font=7, note="")
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
            R_.table(claim, f"{nm} - CLAIM TO FIRST: trips short by the fixed ${rate-SR._err(err):,.2f} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)", font=8)
            d = SR.claim_by_driver(rec, code, rate, err)
            if len(d): R_.table(d, f"{nm} - claim by driver (trip-by-trip detail is in the Excel file)", font=7)
        so = SR.state_only_by_driver(rec, code)
        if len(so): R_.table(so, f"{nm} - trips in the state report but NOT in First/EverDriven, by driver (detail is in the Excel file)", font=7)
        mo = SR.monitor_by_driver(rec, code)
        if len(mo): R_.table(mo, f"{nm} - monitor (MO) payments: monitors ride next to the driver, so there is no separate trip revenue (information only, not a discrepancy)", font=7)
        n_acc, amt_acc = SR.accepted_summary(rec[rec.state == code])
        if n_acc: R_.p(f"Note: {n_acc} {nm} trips with other price differences (total {usd(abs(amt_acc))}) are treated as correct and are not part of the claim; only trips short by the fixed ${rate-SR._err(err):,.2f} are claimed.")
        if len(f): R_.table(f, f"{nm} - trips in First but NOT in the state report", font=6.5)


def first_report(main, label=None, adjustments=None, rate=None, err=None, with_book=False, states_with_report=()):
    label = label or SR.provider_label(main)
    R_ = Report(f"{label} Report", _period(main)); _add_first(R_, main, label, adjustments, rate, err, with_book, states_with_report); return R_.build()


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


# ---------------------------------------------------------------- weekly / monthly / pay-policy sections (used standalone AND inside the master / per-state reports)
import zipfile
import history as HI


def _kpi_pdf(R_, t, vcols, title, font=8):
    R_.table(HI.fmt_table(t, vcols), title, wide=False, font=font)


def _chart2(R_, df, x, ys, title):
    d = df[df[x] != "TOTAL"].copy()
    if len(d): R_.chart(d, x, ys, title)


def _add_weekly(R_, h, week=None):
    R_.h1("Weekly performance comparison")
    ws = HI.weeks(h)
    if not ws: R_.p("No dated trips in the history."); return
    wk = pd.Timestamp(week) if week is not None else ws[-1]
    t, ci, pi, warns = HI.weekly_compare(h, wk)
    R_.p((f"Current week: {ci['start']:%Y-%m-%d} to {ci['end']:%Y-%m-%d} (trips dated {ci['first']:%Y-%m-%d} to {ci['last']:%Y-%m-%d}). "
          f"Previous week: {pi['start']:%Y-%m-%d} to {pi['end']:%Y-%m-%d}.") if (ci["first"] is not None and pd.notna(ci["first"]) and pd.notna(ci["last"])) else
          (f"Current week: {ci['start']:%Y-%m-%d} to {ci['end']:%Y-%m-%d} (this state's report has no trip dates, so it is placed in the week of the other uploaded reports)." if ci["first"] is not None else "No trips in the selected week."))
    for w in warns: R_.p(f"<b>Warning:</b> {w}")
    R_.p("Revenue = amount paid by First / EverDriven. Driver payments, profit and margin exist only for states with an uploaded state report.")
    _kpi_pdf(R_, t, ["Current week", "Previous week", "Difference"], "Company - all states")
    lf, both = HI.weekly_like_for_like(h, wk)
    if lf is not None: _kpi_pdf(R_, lf, ["Current week", "Previous week", "Difference"], f"Like-for-like: states with a state report in both weeks ({', '.join(STATE_NAMES.get(s, s) for s in both)})")
    s = HI.weekly_state_summary(h, wk); R_.table(s, "By state")
    if len(s) > 0:
        rv = s[["State", "Revenue current", "Revenue previous"]].rename(columns={"Revenue current": "Current week", "Revenue previous": "Previous week"}); rv["State"] = rv.State.map(lambda c: STATE_NAMES.get(c, c))
        R_.chart(rv, "State", ["Current week", "Previous week"], "Revenue by state: current vs previous week")


def weekly_comparison_report(h, week=None):
    ws = HI.weeks(h); wk = pd.Timestamp(week) if week is not None else (ws[-1] if ws else None)
    period = f"{pd.Timestamp(wk):%Y-%m-%d} to {pd.Timestamp(wk) + pd.Timedelta(days=6):%Y-%m-%d}" if wk is not None else "n/a"
    R_ = Report("Weekly Comparison Report", period); _add_weekly(R_, h, week); return R_.build()


def _add_monthly(R_, h):
    R_.h1("Monthly financial report")
    t = HI.monthly_table(h)
    if t.empty: R_.p("No dated trips in the history."); return
    for m, w in zip(t.Month, t.Weeks):
        if w < 4: R_.p(f"<b>Note:</b> {m} has {w} week(s) of data - partial month.")
    R_.p("Revenue = paid by First / EverDriven. Payments, profit and margin cover only states with an uploaded state report. Drivers = average of the weekly driver counts.")
    R_.table(t.drop(columns=[c for c in t.columns if c.endswith("MoM %") and t[c].isna().all()]), "Company by month")
    R_.chart(t, "Month", ["Revenue", "Driver Payments", "Profit"], "Monthly revenue, driver payments and profit")
    s = HI.monthly_table(h, by="state"); s["State"] = s.state.map(lambda c: STATE_NAMES.get(c, c))
    R_.table(s[["Month", "State", "Weeks", "Trips", "Revenue", "Driver Payments", "Profit", "Margin %", "Avg revenue/trip"]], "State by month")
    if s.State.nunique() > 1:
        last = s[s.Month == s.Month.max()].sort_values("Revenue", ascending=False)[["State", "Trips", "Revenue", "Profit", "Margin %"]].reset_index(drop=True)
        last.insert(0, "Rank", range(1, len(last) + 1)); R_.table(last, f"State ranking by revenue - {s.Month.max()}", wide=False)


def monthly_report_pdf(h):
    R_ = Report("Monthly Financial Report", "all months in the history"); _add_monthly(R_, h); return R_.build()


def _add_mcomp(R_, h, m1, m2):
    R_.h1(f"Monthly comparison: {m2} vs {m1}")
    t, warns = HI.monthly_compare(h, m1, m2)
    for w in warns: R_.p(f"<b>Warning:</b> {w}")
    R_.p(f"Difference = {m2} minus {m1}. Payments, profit and margin cover only states with an uploaded state report.")
    _kpi_pdf(R_, t, [m1, m2, "Difference"], "Company - all states")
    lf, both = HI.like_for_like(h[h.month == m2], h[h.month == m1], m2, m1)
    if lf is not None:
        lf = lf[["KPI", m1, m2, "Difference", "Change %"]]; _kpi_pdf(R_, lf, [m1, m2, "Difference"], f"Like-for-like: states with a state report in both months ({', '.join(STATE_NAMES.get(s, s) for s in both)})")
    R_.table(HI.monthly_state_summary(h, m1, m2), "By state")


def monthly_comparison_report(h, m1, m2):
    R_ = Report("Monthly Comparison Report", f"{m1} vs {m2}"); _add_mcomp(R_, h, m1, m2); return R_.build()


def _add_paypol(R_, rec, book):
    R_.h1("Driver pay policy review: payments above the usual pay for the same route")
    s, over, loss = SR.pay_check(rec, book)
    if s.empty: R_.p("No state reports with driver payments uploaded."); return
    R_.p("Policy = the pay that was paid for the same route in at least 80% of earlier trips (minimum 3). The route of each trip comes from the First / EverDriven report. "
         "Trips whose route has no stable policy yet are not judged.")
    R_.table(s, "Summary by state", font=7)
    for code in over.State.unique():
        d = over[over.State == code].drop(columns=["State", "State source"]); R_.table(d, f"{code} - trips paid above the pay policy ({len(d)} trips, excess {usd(d['Excess pay'].sum())})", font=6.5)
    if len(loss): R_.table(loss.drop(columns=["State source", "Pay policy"]).rename(columns={"Excess pay": "Pay above revenue"}), "Trips where the driver was paid more than the trip revenue", font=6.5)
    import pay_policy as PP
    bs, bd = PP.band_check(rec, book)
    if len(bs):
        R_.h1("Driver pay vs the official mile-band policy (Northern / Southern California, New Mexico, Oregon)")
        R_.p("Bands per city come from the price PDFs. A different pay that is listed in the price list is an approved exception; long trips and Sacramento are approved per trip by management.")
        R_.table(PP.bands_table(), "Mile bands", wide=False, font=8, note="Driver pay per trip by miles for each city. Richmond's bands are inferred from its trips.")
        R_.table(bs, "Driver pay against the mile bands, by city", font=7, note="Matches band = paid exactly the band pay. ABOVE / BELOW band = paid differently with no approval in the price list. Long trip: needs management approval = beyond the last band with no approved pay.")
        bad = bd[bd.Status.str.startswith(("ABOVE", "BELOW", "Long trip: needs", "ZERO", "Sacramento: pay NOT", "City not"))]
        if len(bad): R_.table(bad.drop(columns=["State"]).head(120), f"Trips that need review ({len(bad)}; first {min(len(bad), 120)})", font=6.5)


def pay_policy_report(rec, book):
    R_ = Report("Driver Pay Policy Review", _period(rec)); _add_paypol(R_, rec, book); return R_.build()


# ---------------------------------------------------------------- full report of ONE state, master report, all-states zip
def state_full_report_long(code, main, rec, hist, book, rate=45.0, err=None, week=None):
    """(long version, 10+ pages, kept unchanged) Everything about one state: financial performance, price check, price + trip differences, pay policy, weekly and monthly."""
    import financial_calculations as FC
    nm = STATE_NAMES.get(code, code); ms, rs = main[main.state == code], rec[rec.state == code]
    hs = hist[hist.state == code] if hist is not None and len(hist) else None
    has_rep = bool(len(rs)) and bool((rs.state_source != "").any())
    R_ = Report(f"{nm} - Full State Report", _period(ms if len(ms) else rs)); R_.h1(f"{nm}: full report")
    k = {"Trips (provider report)": len(ms), "Drivers": ms.driver.nunique(), "Miles": ms.miles.sum(min_count=1), "Provider revenue (paid)": ms.main_amount.sum(min_count=1)}
    if has_rep:
        f = SR.state_financials(rs); row = f[f.State == nm].iloc[0]; pt = rs[rs.driver_payment.notna() & (rs.audit_status != "MONITOR PAYMENT")]
        k.update({"Trips (state report)": int(row["Trips"]), "State-report revenue": row["Revenue"], "Driver payments": row["Driver Payments"], "Monitor payments": row["Monitor payments"], "Profit": row["Profit"], "Margin %": row["Margin %"],
                  "Avg revenue/trip": k["Provider revenue (paid)"] / len(ms) if len(ms) else np.nan, "Avg driver payment/trip": pt.driver_payment.sum() / len(pt) if len(pt) else np.nan})
    R_.kpis(k)
    R_.p("This report has six parts: financial performance, price check, price and trip differences against the state report, driver pay policy, weekly comparison and monthly report."
         if has_rep else "<b>No state report was uploaded for this state yet</b>, so driver payments, profit and the differences below cannot be calculated. The estimate and the price check use earlier weeks' rates.")
    R_.section("L"); R_.h1("1. Financial performance")
    if has_rep:
        R_.table(f[f.State == nm], "Financial performance (state report)")
        nopay = rs[rs.state_revenue.notna() & rs.driver_payment.isna() & (rs.audit_status != "MONITOR PAYMENT")]
        if len(nopay): R_.p(f"<b>Note:</b> {len(nopay)} trips with revenue {usd(nopay.state_revenue.sum())} have no driver payment in the state report; their revenue is counted fully as profit.")
        d = FC.driver_table(rs, code).drop(columns=["Rows missing revenue/payment"], errors="ignore"); R_.table(d, "Driver performance", font=7)
    elif len(ms):
        est = SR.estimate_financials(ms, book, ()); R_.table(est[est.State == nm] if len(est) else est, "Estimated profit by state")
    else:
        R_.p("No trips for this state in the uploaded reports.")
    R_.section("L"); R_.h1("2. Price check against contract prices")
    if len(ms):
        pc, det, _ = SR.price_check(ms, book, SR._err(err), rate)
        R_.table(pc[pc.State == nm] if (pc.State == nm).any() else pc.iloc[-1:], "Paid price vs contract price, by state")
        if code in ("N.CA", "NM", "KS", "NE"):
            import pay_policy as PP
            pls, pld = PP.price_list_check(ms)
            if len(pls):
                R_.table(pls, "Price paid by First vs the agreed price list (city price PDFs, or the agreed rule of the state)", note="Below list = First paid less than the listed price for the same route (shortfall to claim). Above list = paid more than listed.")
                if len(pld): R_.table(pld.head(80), f"Trips not at the list price (first {min(len(pld), 80)} of {len(pld)})", font=6.5)
        if len(det): R_.table(det.drop(columns=["State", "Source file", "Source row"], errors="ignore").head(80), f"Trips paid below the contract price (trip by trip, first {min(len(det), 80)} of {len(det)}; full list in Excel)", font=6.5)
        if code == "AK":
            s, grp, drv, _ = SR.first_rate_audit(ms, rate, err=err)
            if s["Trips below official rate"]:
                R_.p(f"Alaska claim: {s['Trips below official rate']} trips of {s['Alaska trips in report']} were short by the fixed ${rate-SR._err(err):,.2f} each (price ending in .50, at least ${SR._err(err):,.2f}). Total owed: <b>{usd(s['Total owed'])}</b>.")
                R_.table(grp, f"Claim: trips short by the fixed ${rate-SR._err(err):,.2f} (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)", font=8); R_.table(drv, "Claim by driver", font=7)
    else:
        R_.p("No trips for this state in the uploaded reports.")
    R_.section("L")
    if has_rep: _add_disc(R_, rs, rate, err)
    else: R_.h1("3. Differences against the state report"); R_.p("No state report uploaded for this state.")
    R_.section("L")
    if has_rep: _add_paypol(R_, rs, book)
    else: R_.h1("4. Driver pay policy review"); R_.p("Needs the state report (it holds the driver payments).")
    if hs is not None and len(hs):
        R_.section("P"); _add_weekly(R_, hs, week); R_.section("P"); _add_monthly(R_, hs)
    return R_.build()



# ---------------------------------------------------------------- compact 2-page state report (long version kept as state_full_report_long)
def provider_of(code):
    """The company that pays Beyond in this state: EverDriven (NE, KS) or First (all others)."""
    from config import EVERDRIVEN_STATES
    return "EverDriven" if code in EVERDRIVEN_STATES else "First"


_PAY_OK = ("Matches", "Approved", "Allowed")
_EXPLAIN = "state manager to explain"


def _pay_category(status):
    s = str(status)
    if s.startswith("Matches route policy (differs"): return "Negotiated route: equals the route's usual pay"
    if s.startswith(_PAY_OK) or s.startswith("Sacramento: management-approved"): return "Matches the pay policy"
    if s.startswith("Long trip (>16 mi): management-set"): return "Long trip: pay set by management"
    if s.startswith("ABOVE"): return "ABOVE policy - " + _EXPLAIN
    if s.startswith("BELOW"): return "BELOW policy - " + _EXPLAIN
    if s.startswith("ZERO") or s.startswith("No driver pay"): return "ZERO pay - " + _EXPLAIN
    if s.startswith(("Long trip: needs", "Sacramento: pay NOT")): return "Needs management approval - " + _EXPLAIN
    return "Not checked (no pay policy for this route)"



NEGOTIATED_CAT = "Negotiated with the driver (approved list)"


def _apply_negotiated(bd, diffs):
    """Trips whose driver pay was negotiated (negotiated_pay.py) leave the 'to explain' list and get their own category."""
    try:
        from negotiated_pay import NEGOTIATED
        from normalization import norm_name
        from ratebook import route_key
    except Exception:
        return bd, diffs
    if not NEGOTIATED: return bd, diffs
    def hit(state, driver, trip, pay):
        for st, dr, rt, pv, note in NEGOTIATED:
            if st not in ("*", state) or (dr != "*" and norm_name(dr) != norm_name(driver)): continue
            if pv is not None and abs(float(pv) - float(pay)) > 0.005: continue
            if rt in ("*", None) or route_key(rt).split() == route_key(trip).split()[:len(route_key(rt).split())] or route_key(rt) in route_key(trip): return note or "negotiated"
        return None
    for df in (bd, diffs):
        if df.empty: continue
        inv = {v: k for k, v in STATE_NAMES.items()}
        notes = [hit(inv.get(s, s), d, t, p) for s, d, t, p in zip(df["State"], df.Driver, df["Trip Name"], df["Driver pay"])]
        m = pd.Series([n is not None for n in notes], index=df.index)
        df.loc[m & ~df.Category.str.startswith("Matches"), "Category"] = NEGOTIATED_CAT
        df.loc[m, "Source"] = ["Negotiated: " + n for n in notes if n is not None]
    diffs = diffs[diffs.Category != NEGOTIATED_CAT].copy()
    return bd, diffs


def state_pay_differences(rs, book):
    """Driver pay in the STATE REPORT vs the agreed pay policy. Returns (summary by category, trip-level differences).
    Differences = band/rule policy + trips paid above the route's usual pay (learned from earlier weeks). Nothing from the old checks is dropped."""
    import pay_policy as PP
    bs, bd = PP.band_check(rs, book)
    if bd.empty: return pd.DataFrame(), pd.DataFrame()
    bd = bd.copy(); bd["Category"] = bd.Status.map(_pay_category); bd["Source"] = "Agreed pay policy"
    diffs = bd[bd.Category.str.endswith(_EXPLAIN)].copy()
    try:
        _, over, _ = SR.pay_check(rs, book)
        if len(over):
            o = over.rename(columns={"Pay policy": "Policy pay", "Excess pay": "Difference"}).copy()
            key = set(zip(diffs.Date, diffs.Driver, diffs["Trip Name"]))
            o = o[[(a, b, c) not in key for a, b, c in zip(o.Date, o.Driver, o["Trip Name"])]]
            o = o[[PP.route_info(t)[0] != "San Leandro" for t in o["Trip Name"]]]      # San Leandro exceptions: all approved by Mr. Abdoun
            if len(o):
                oset = set(zip(o.Date, o.Driver, o["Trip Name"]))
                o["Status"] = "ABOVE the route's usual pay"; o["Category"] = "ABOVE policy - " + _EXPLAIN; o["Source"] = "Route's usual pay (earlier weeks)"
                o["Driver pay"] = o["Driver pay"].astype(float); o["Pay % of revenue"] = np.nan; o["City"] = ""
                diffs = pd.concat([diffs, o[[c for c in diffs.columns if c in o.columns]]], ignore_index=True)
                m = pd.Series([(a, b, c) in oset for a, b, c in zip(bd.Date, bd.Driver, bd["Trip Name"])], index=bd.index) & (bd.Category != "Not checked (no pay policy for this route)")
                bd.loc[m & bd.Category.str.startswith(("Matches", "Negotiated")), "Category"] = "ABOVE policy - " + _EXPLAIN
                bd.loc[bd.Category.eq("Not checked (no pay policy for this route)") & pd.Series([(a, b, c) in oset for a, b, c in zip(bd.Date, bd.Driver, bd["Trip Name"])], index=bd.index), "Category"] = "ABOVE policy - " + _EXPLAIN
    except Exception:
        pass
    bd, diffs = _apply_negotiated(bd, diffs)
    nck = bd[bd.Category.str.startswith("Not checked")]
    if len(nck): diffs = pd.concat([diffs, nck], ignore_index=True)
    s = bd.groupby("Category").agg(Trips=("Driver pay", "size"), **{"State report pay": ("Driver pay", "sum"), "Difference vs policy": ("Difference", "sum")}).reset_index()
    order = {"Matches the pay policy": 0, "Negotiated route": 1, "Long trip": 2}
    s["_o"] = s.Category.map(lambda c: next((v for k, v in order.items() if c.startswith(k)), 3)); s = s.sort_values(["_o", "Category"]).drop(columns="_o")
    return s, diffs


def _group_pay_differences(diffs):
    """Same driver + same route + same pay + same policy -> ONE row with the number of trips (state manager explains once per row)."""
    if diffs.empty: return diffs
    from ratebook import route_key
    d = diffs.copy(); d["_rk"] = d["Trip Name"].map(route_key); d["Policy pay"] = d["Policy pay"].astype(float)
    gk = ["Driver", "_rk", "Driver pay", "Policy pay", "Status"]
    out = d.groupby(gk, dropna=False).agg(Route=("Trip Name", "first"), Miles=("Miles", "first"), Trips=("Driver pay", "size"), Revenue=("Trip revenue", "first"),
                                       Total=("Difference", "sum"), Dates=("Date", lambda x: ", ".join(sorted({pd.Timestamp(v).strftime("%m-%d") for v in x if pd.notna(v)})))).reset_index()
    out["Difference per trip"] = out["Driver pay"] - out["Policy pay"]
    out = out.rename(columns={"Driver pay": "State report pay", "Total": "Total difference"})
    out["Abs"] = out["Total difference"].abs().fillna(0); out = out.sort_values("Abs", ascending=False)
    return out[["Driver", "Route", "Miles", "Trips", "Dates", "Revenue", "State report pay", "Policy pay", "Difference per trip", "Total difference", "Status"]].reset_index(drop=True)


def _state_control(main_state, code):
    """How every trip of this state got its state: proves nothing was guessed silently (state report > route/school > driver map)."""
    g = main_state[main_state.state == code]
    if g.empty: return ""
    c = g.state_source.fillna("").map(lambda s: "state report" if s == "state report" else ("school / route" if s.startswith("trip route") or s in ("Oregon school", "region keyword") else ("main file" if s == "main file hint" else "driver map"))).value_counts()
    return "; ".join(f"{k}: {v}" for k, v in c.items())


def state_report_data(code, main, rec, book, rate=45.0, err=None):
    """Every number of the compact state report (and of the state Excel) in one place."""
    import pay_policy as PP
    nm = STATE_NAMES.get(code, code); fp = provider_of(code)
    ms, rs = main[main.state == code], rec[rec.state == code]
    has_rep = bool(len(rs)) and bool((rs.state_source != "").any())
    D = {"name": nm, "fp": fp, "has_rep": has_rep, "ms": ms, "rs": rs, "code": code, "control": _state_control(main, code)}
    D["fin"] = SR.state_financials(rs) if has_rep else pd.DataFrame()
    D["pclaim"] = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if has_rep:
        rr = SR.apply_rate_rule(rs, rate, err); D["pclaim"] = SR.price_diff_claim(rr, code, rate, err)
        a, s_only, f_only = SR.discrepancy_sections(rr, code)
        _nt = lambda d: d[~d.iloc[:, 0].astype(str).str.upper().eq("TOTAL") & ~d.iloc[:, 1].astype(str).str.upper().eq("TOTAL")] if len(d) else d   # drop the TOTAL rows: they are not trips
        a, s_only, f_only = _nt(a), _nt(s_only), _nt(f_only)
        D["recon"] = {"a": a, "state_only": s_only, "first_only": f_only, "bridge": SR.revenue_bridge(rr, rate, err), "claim": SR.claim_split(rr, code, rate, err)[0],
                      "matched": int(rr.audit_status.isin(["EXACT MATCH", "MATCHED"]).sum()), "review": int((rr.audit_status == "NEEDS MANUAL REVIEW").sum()),
                      "monitors": SR.monitor_by_driver(rr, code)}
        D["paysum"], D["paydiff"] = state_pay_differences(rs, book)
    claims, est = [], pd.DataFrame()
    if len(ms):
        pc, det, _ = SR.price_check(ms, book, SR._err(err), rate)
        D["pc"] = pc[pc.State == nm] if (pc.State == nm).any() else pc.iloc[-1:]
        if len(det):
            by_route = det[det["Price source"].astype(str).str.lower().isin(["route", "miles"])]; est = pd.DataFrame()
            if len(by_route): claims.append(by_route.assign(Basis=by_route["Price source"].map({"route": "Same route, earlier weeks", "miles": "Same state + miles (earlier weeks)"})).rename(columns={"Contract price": "Agreed price"}))
        if code in ("N.CA", "NM", "KS", "NE"):
            pls, pld = PP.price_list_check(ms)
            if len(pld):
                below = pld[pld.Status.astype(str).str.startswith("BELOW")]
                if len(below): claims.append(below.rename(columns={"List price": "Agreed price", "Paid by First": "Paid"}).assign(Basis="Agreed price list / rule", Difference=lambda x: -x["Shortfall"]))
        if code == "AK":
            s, grp, drv, adet = SR.first_rate_audit(ms, rate, err=err); D["ak"] = (s, grp, drv, adet)
    D["claims"] = claims; D["estimates"] = est
    return D


def _claim_rows(D):
    """Flat table of every trip to claim from First/EverDriven: date, driver, trip, agreed price, paid, short, basis. No trip appears twice."""
    rows = []
    for c in D.get("claims", []):
        for r in c.to_dict("records"):
            agreed, paid = r.get("Agreed price"), r.get("Paid")
            try: agreed = float(str(agreed).split("/")[0].replace("$", "").replace(",", ""))
            except Exception: agreed = np.nan
            short = (agreed - paid) if (pd.notna(agreed) and pd.notna(paid)) else abs(r.get("Difference", np.nan))
            rows.append({"Date": r.get("Date"), "Driver": r.get("Driver"), "Trip ID": r.get("Trip ID", ""), "Trip Name": r.get("Trip Name"), "Agreed price": agreed, "Paid": paid, "Short": short, "Basis": r["Basis"]})
    out = pd.DataFrame(rows, columns=["Date", "Driver", "Trip ID", "Trip Name", "Agreed price", "Paid", "Short", "Basis"])
    if len(out):
        out = out[out.Short.notna() & (out.Short > 0.004)].copy()
        out["_b"] = out.Basis.map(lambda b: 0 if "list" in str(b) else 1)      # the agreed list/rule wins over the route history for the same trip
        out = out.sort_values(["_b", "Short"], ascending=[True, False]).drop_duplicates(["Date", "Driver", "Trip Name"]).drop(columns="_b")
        out = out.sort_values(["Short", "Date"], ascending=[False, True]).reset_index(drop=True)
    return out



def manager_table(D):
    """ONE table with EVERY difference the state manager must explain before payroll: trips missing on either side, price differences,
    driver pay vs policy, routes that could not be checked. The last column is left empty for the manager's explanation."""
    fp = D["fp"]; rows = []
    def add(typ, df, drv, route, n, dates, detail, diff):
        for r in df.itertuples(): rows.append({"Type": typ, "Driver": drv(r), "Route": route(r), "Trips": n(r), "Dates": dates(r), "Detail": detail(r), "Difference": diff(r)})
    def grp(df, cols):  # group a recon frame by driver (+route) with count and dates
        if df is None or df.empty: return []
        return df
    if D["has_rep"]:
        rc = D["recon"]; fo, so, a = rc["first_only"], rc["state_only"], rc["a"]
        if len(fo):
            for (dr, rt), x in fo.groupby(["Driver", "Trip Name"]):
                rows.append({"Type": f"In {fp}, NOT in state report", "Driver": dr, "Route": rt, "Trips": len(x), "Dates": ", ".join(sorted({pd.Timestamp(v).strftime("%m-%d") for v in x["Date"] if pd.notna(v)})),
                             "Detail": f"{fp} paid {usd(x['First Revenue'].sum())}", "Difference": x["First Revenue"].sum()})
        if len(so):
            for dr, x in so.groupby("Driver"):
                rows.append({"Type": f"In state report, NOT in {fp}", "Driver": dr, "Route": "", "Trips": len(x), "Dates": "", "Detail": f"State report revenue {usd(x['State Revenue'].sum())}, driver pay {usd(x['Driver Payment'].sum())}",
                             "Difference": x["State Revenue"].sum()})
        if len(a):
            for (dr, rt), x in a.groupby(["Driver", "Trip Name"]):
                rows.append({"Type": f"Price differs: {fp} vs state report", "Driver": dr, "Route": rt, "Trips": len(x), "Dates": ", ".join(sorted({pd.Timestamp(v).strftime("%m-%d") for v in x["Date"] if pd.notna(v)})),
                             "Detail": f"{fp} {usd(x['First Revenue'].sum())} vs state {usd(x['State Revenue'].sum())}", "Difference": x["Difference (First - State)"].sum()})
        pg = _group_pay_differences(D["paydiff"])
        for r in pg.itertuples():
            nck = str(r.Status).startswith(("City not", "No policy", "No driver"))
            rows.append({"Type": "Route not checked (no pay policy)" if nck else "Driver pay vs pay policy", "Driver": r.Driver, "Route": r.Route, "Trips": r.Trips, "Dates": r.Dates,
                         "Detail": (f"Paid {usd(r._7)}/trip; no policy for this route" if nck else f"Paid {usd(r._7)} vs policy {usd(r._8)} per trip ({r.Status})"), "Difference": np.nan if nck else r._10})
    out = pd.DataFrame(rows, columns=["Type", "Driver", "Route", "Trips", "Dates", "Detail", "Difference"])
    if len(out):
        out["_a"] = out.Difference.abs().fillna(0); out = out.sort_values(["Type", "_a"], ascending=[True, False]).drop(columns="_a").reset_index(drop=True)
    return out


def _build_state_pdf(D, rate, err, rows_pay=16, rows_other=8, hs=None, week=None):
    nm, fp, ms, rs, code_ = D["name"], D["fp"], D["ms"], D["rs"], D.get("code")
    R_ = Report(f"{nm} - weekly report", _period(ms if len(ms) else rs)); R_.land()
    R_.h1(f"{nm}: weekly report  ({fp} vs state report)")
    no_first = len(ms) == 0
    k = {} if no_first else {f"{fp} trips": len(ms), "Drivers": ms.driver.nunique(), "Miles": ms.miles.sum(min_count=1), f"{fp} revenue (paid)": ms.main_amount.sum(min_count=1)}
    if D["has_rep"]:
        row = D["fin"][D["fin"].State == nm].iloc[0]
        k.update({"State report trips": int(row["Trips"]), "State report revenue": row["Revenue"], "Driver payments": row["Driver Payments"], "Monitor payments": row["Monitor payments"],
                  "Profit": row["Profit"], "Margin %": row["Margin %"]})
    R_.table(pd.DataFrame([k]), None, font=7.5, note="")
    if D.get("control"): R_.p(f"<b>How each trip got its state</b> (state report > school/route > driver map; nothing unassigned is counted): {D['control']}.")
    if not D["has_rep"]:
        R_.p(f"<b>No state report was uploaded for {nm}</b>: driver payments, profit and the comparison with the state report cannot be calculated.")
    if no_first and D["has_rep"]:
        R_.p(f"<b>No {fp} report was uploaded for {nm}.</b> Upload it to reconcile trip by trip and to check the prices {fp} paid. Below: the state report payments against the pay policy.")
    elif D["has_rep"]:
        rc = D["recon"]; a, so, fo = rc["a"], rc["state_only"], rc["first_only"]
        R_.h2(f"1. {fp} vs the {nm} state report - trip by trip")
        fr = D["fin"][D["fin"].State == nm].iloc[0]
        ok = (len(a) + len(so) + len(fo) + rc["review"] == 0)
        t = pd.DataFrame([{f"{fp} trips": len(ms), "State report trips": int(fr["Trips"]), "Matched trips": rc["matched"], f"In {fp}, NOT in state report": len(fo),
                           f"In state report, NOT in {fp}": len(so), "Trips with price difference": len(a), "Manual review": rc["review"],
                           f"{fp} revenue": ms.main_amount.sum(min_count=1), "State report revenue": float(fr["Revenue"]), "Result": "MATCHED to the cent" if ok else "DIFFERENCES - see below"}])
        R_.table(t, None, font=7.5, note="")
    cl = _claim_rows(D) if not no_first else pd.DataFrame(); est = D["estimates"] if not no_first else pd.DataFrame(); ak = D.get("ak")
    if not no_first:
        R_.h2(f"{2 if D['has_rep'] else 1}. Prices paid by {fp} vs the agreed price")
        parts = []
        if len(cl): parts.append(f"<b>Claim to {fp} (agreed price, same route or agreed list): {len(cl)} trips, {usd(cl.Short.sum())}</b>")
        if ak and ak[0].get("Trips below official rate"): parts.append(f"<b>Alaska fixed $2.50 claim: {ak[0]['Trips below official rate']} of {ak[0]['Alaska trips in report']} trips, {usd(ak[0]['Total owed'])}</b> (paid 42.50 vs 45, 47.50 vs 50, 82.50 vs 85...)")
        if len(est): parts.append(f"Not claimed (price estimated from other routes with similar miles - verify first): {len(est)} trips, {usd(est['Difference'].abs().sum() if 'Difference' in est.columns else np.nan)}")
        R_.p("; ".join(parts) if parts else f"No trip was paid below the agreed price by {fp}.")
        if code_ == "N.CA": R_.p("<i>Note: Benicia routes are listed at $45 because First cut them from $50; after the N.CA manager spoke to First, it added $5 on some Richmond routes (now $55-$60). These list prices are the agreed prices, not a claim.</i>")
        if len(cl): R_.table(cl.head(rows_other), f"Trips to claim from {fp}" + (f"  [first {rows_other} of {len(cl)}; all in Excel]" if len(cl) > rows_other else ""), font=6.5, note="")
        if ak and len(ak[1]): R_.table(ak[1], "Alaska claim by price", font=7, note="")
        pcl = D["pclaim"][0]
        if len(pcl): R_.table(pcl, f"Claim to {fp}: trips paid LESS than the state report price ({int(pcl.iloc[-1]['Trips'])} trips, {usd(pcl.iloc[-1]['Total owed'])})", font=7, note="")
    if D["has_rep"]:
        R_.section("L"); R_.h2("3. Driver pay: state report vs the agreed pay policy - summary")
        ps, pdiff = D["paysum"], D["paydiff"]
        if ps.empty: R_.p("No driver payments to check.")
        else:
            nc = ps[ps.Category.str.startswith("Not checked")]["Trips"].sum()
            import pay_policy as _PP
            if code_ == "N.CA" and getattr(_PP, "NC_LOAD_ERROR", None): R_.p(f"<b>Warning:</b> the North California price list (nc_policy.py) could not be loaded: {_PP.NC_LOAD_ERROR}")
            R_.table(ps, None, font=7.5, note="")
            if nc and nc >= 0.5 * ps.Trips.sum():
                R_.p(f"<b>Warning:</b> {int(nc)} of {int(ps.Trips.sum())} trips could not be checked because their route has no pay policy loaded. Make sure the price list module (nc_policy.py for North California) is deployed with the app.")
    if D["has_rep"]:
        mt = manager_table(D)
        R_.h2("4. DIFFERENCES FOR THE STATE MANAGER TO EXPLAIN BEFORE PAYROLL")
        if mt.empty: R_.p("<b>No difference between this report and the state report.</b>")
        else:
            R_.table(mt.head(rows_pay), f"{len(mt)} items to explain" + (f"  [largest {rows_pay} shown; all in the Excel file, sheet 'For state manager']" if len(mt) > rows_pay else ""), font=6.5, note="")
    if hs is not None and len(hs):                      # weekly review / comparison and monthly report of THIS state (after the 2 core pages)
        R_.section("P"); _add_weekly(R_, hs, week); R_.section("P"); _add_monthly(R_, hs)
    return R_


def state_full_report(code, main, rec, hist, book, rate=45.0, err=None, week=None, max_pages=2):
    """ONE state: 2 core pages (provider vs state report, prices, pay policy, differences for the state manager), then the weekly
    review/comparison and the monthly report of that state when history exists. The previous long report is state_full_report_long."""
    D = state_report_data(code, main, rec, book, rate, err)
    hs = hist[hist.state == code] if hist is not None and len(hist) else None
    chosen = (2, 1)
    for rp, ro in ((16, 8), (12, 6), (9, 4), (6, 3), (4, 2), (2, 1)):
        chosen = (rp, ro); R_ = _build_state_pdf(D, rate, err, rp, ro); R_.build()
        if R_.pages <= max_pages: break
    R_ = _build_state_pdf(D, rate, err, chosen[0], chosen[1], hs, week)
    return R_.build()


def state_excel(code, main, rec, hist, book, rate=45.0, err=None):
    """Full detail behind the compact report: every trip, difference and claim."""
    import excel_generator as EG, financial_calculations as FC
    D = state_report_data(code, main, rec, book, rate, err); fp = D["fp"]; fr = {}
    if D["has_rep"]:
        mt = manager_table(D); fr["For state manager"] = mt if len(mt) else pd.DataFrame({"Result": ["No difference between the provider report and the state report"]})
        fr["Summary"] = D["fin"]; rc = D["recon"]; fr["Reconciliation"] = rc["bridge"]
        for nm_, df in (("In state only", rc["state_only"]), (f"In {fp} only", rc["first_only"]), ("Price differences", rc["a"])):
            if len(df): fr[nm_] = df
        if len(D["paydiff"]): fr["Pay vs policy (trips)"] = D["paydiff"].drop(columns=["Category", "Source"], errors="ignore")
        g = _group_pay_differences(D["paydiff"])
        if len(g): fr["Pay differences (grouped)"] = g
        if len(D["paysum"]): fr["Pay summary"] = D["paysum"]
        try: fr["Drivers"] = FC.driver_table(D["rs"], code).drop(columns=["Rows missing revenue/payment"], errors="ignore")
        except Exception: pass
    if len(D["pclaim"][0]): fr[f"Price claim to {fp}"] = D["pclaim"][0]
    if len(D["pclaim"][1]): fr["Price claim by driver"] = D["pclaim"][1]
    if len(D["pclaim"][2]): fr[f"{fp} paid more (info)"] = D["pclaim"][2]
    cl = _claim_rows(D)
    if len(cl): fr[f"Claim to {fp}"] = cl
    if len(D["estimates"]): fr["Not claimed (estimated)"] = D["estimates"]
    if D.get("ak") is not None and len(D["ak"][3]): fr["Alaska claim detail"] = D["ak"][3]
    return EG.build_workbook({k[:31]: v for k, v in fr.items()})


def master_report(main, rec, hist, book, label=None, rate=45.0, err=None, adjustments=None, week=None):
    """All combined reports in ONE file: provider + state totals, price check, state financials, differences, pay policy, weekly, monthly."""
    label = label or SR.provider_label(main); has = (rec.state_source != "").any()
    R_ = Report("Master Report - all combined reports", _period(main))
    _add_first(R_, main, label, adjustments, rate, err, True, set(rec[rec.state_source != ""].state))
    if has:
        R_.section("L"); _add_states(R_, rec); R_.section("L"); _add_disc(R_, rec, rate, err); R_.section("L"); _add_paypol(R_, rec, book)
    if hist is not None and len(hist):
        R_.section("P"); _add_weekly(R_, hist, week); R_.section("P"); _add_monthly(R_, hist)
        ms = sorted(hist.month.dropna().unique())
        if len(ms) >= 2: R_.section("P"); _add_mcomp(R_, hist, ms[-2], ms[-1])
    return R_.build()


def report_states(main, rec):
    """Every state that has a provider (First/EverDriven) report OR a state report: each one gets its own full report."""
    s = set(main.state.dropna().unique()) | set(rec[rec.state_source != ""].state.dropna().unique()) if len(rec) else set(main.state.dropna().unique())
    return sorted(c for c in s if c not in ("Unassigned", "NEEDS REVIEW", ""))


def all_states_zip(main, rec, hist, book, rate=45.0, err=None, week=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for code in report_states(main, rec):
            fn = STATE_NAMES.get(code, code).replace(' ', '_').replace('(', '').replace(')', '')
            z.writestr(f"{fn}_report.pdf", state_full_report(code, main, rec, hist, book, rate, err, week))
            try: z.writestr(f"{fn}_details.xlsx", state_excel(code, main, rec, hist, book, rate, err))
            except Exception as e: z.writestr(f"{fn}_details_ERROR.txt", str(e))
    return buf.getvalue()
