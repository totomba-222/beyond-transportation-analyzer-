"""Simple, calm PDF reports (portrait A4, white page, thin lines, muted colours, few words).

state_report_pdf(D, ...)  one state, 2 pages at most:
    1. summary (trips, revenue, driver payments, profit, margin) + the state's share of the First/EverDriven total
    2. trips paid below the agreed price (claim to First / EverDriven)
    3. driver pay ABOVE the pay policy (profit and margin if the policy had been applied, loss, trips list)
    4. comparison with last week (+ chart)
first_report_pdf(main, ...)  First / EverDriven: totals, by state, trips paid below the agreed price.

Nothing is invented: a missing value prints 'n/a'.
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle)

import history as HI
import simple_reports as SR
import pdf_generator as PG

BRAND = "Beyond Transportation"
INK, MUTED, LINE = "#1F2937", "#6B7280", "#E5E7EB"
HEAD_BG, RULE = "#F3F4F6", "#CBD5E1"
BLUE, GREY, GREEN, AMBER, RED = "#4A6A8A", "#A3AAB5", "#6BA292", "#C9A25A", "#B25B5B"

LM = 18 * mm                                    # left / right margin
PAGE_W = A4[0] - 2 * LM

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor(INK), spaceAfter=2)
SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor(MUTED), spaceAfter=8)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=colors.HexColor(INK), spaceBefore=12, spaceAfter=4)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor(INK), spaceAfter=4)
NOTE = ParagraphStyle("note", fontName="Helvetica", fontSize=7.8, leading=10, textColor=colors.HexColor(MUTED), spaceAfter=3)
TH_L = ParagraphStyle("thl", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor(MUTED))
TH_R = ParagraphStyle("thr", parent=TH_L, alignment=2)
TD_L = ParagraphStyle("tdl", fontName="Helvetica", fontSize=8.6, leading=11, textColor=colors.HexColor(INK))
TD_R = ParagraphStyle("tdr", parent=TD_L, alignment=2)


# ------------------------------------------------------------------ formatting
def _na(v): return v is None or (not isinstance(v, str) and pd.isna(v))
def usd(v): return "n/a" if _na(v) else PG.usd(float(v))
def num(v): return "n/a" if _na(v) else f"{float(v):,.0f}"
def miles(v): return "n/a" if _na(v) else f"{float(v):,.0f}"
def pct(v): return "n/a" if _na(v) else f"{float(v):.1f}%"
def pts(v): return "n/a" if _na(v) else f"{float(v):+.1f} pts"
def chg(v): return "n/a" if _na(v) else f"{float(v):+.1f}%"
def sdate(v): return "" if _na(v) else pd.Timestamp(v).strftime("%m-%d")
def _tr(n): return f"{int(n):,} trip" + ("" if int(n) == 1 else "s")
def _share(a, b): return float(a) / float(b) * 100 if (not _na(a) and not _na(b) and float(b)) else np.nan


def _p(text, style): return Paragraph(escape(str(text)), style)


def table(header, rows, widths, aligns=None, bold_last=False, bold_rows=()):
    """header: list of str; rows: list of lists of str; widths: relative column widths; aligns: 'L'/'R' per column."""
    n = len(header); aligns = aligns or ["L"] + ["R"] * (n - 1); tot = float(sum(widths))
    data = [[Paragraph(escape(h), TH_R if a == "R" else TH_L) for h, a in zip(header, aligns)]]
    for i, r in enumerate(rows):
        bold = (bold_last and i == len(rows) - 1) or i in bold_rows
        row = []
        for c, a in zip(r, aligns):
            t = escape(str(c)); t = f"<b>{t}</b>" if bold else t
            row.append(Paragraph(t, TD_R if a == "R" else TD_L))
        data.append(row)
    t = Table(data, colWidths=[PAGE_W * w / tot for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_BG)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(RULE)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


# ------------------------------------------------------------------ charts (muted, no borders)
def _style_ax(ax):
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(LINE); ax.tick_params(colors=MUTED, labelsize=7.5, length=0)
    ax.set_axisbelow(True)


def _img(fig, width_mm):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=200, bbox_inches="tight", facecolor="white"); plt.close(fig); b.seek(0)
    w, h = ImageReader(b).getSize(); b.seek(0)
    return Image(b, width=width_mm * mm, height=width_mm * mm * h / w)


def _money_k(v): return f"${v:,.0f}"


def chart_state_summary(S):
    """Left: revenue, driver payments, profit. Right: the state's share of the First / EverDriven total (trips, revenue)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 2.5), gridspec_kw={"width_ratios": [1.25, 1]})
    if S["has_rep"]:
        labs, vals, cols = ["Revenue", "Driver payments", "Profit"], [S["state_revenue"], S["payments"], S["profit"]], [BLUE, GREY, GREEN]
    else:
        labs, vals, cols = [f"{S['fp']} revenue"], [S["first_revenue"]], [BLUE]
    vals = [0 if _na(v) else float(v) for v in vals]
    bars = a1.bar(labs, vals, color=cols, width=0.55)
    top = max(vals + [1]); a1.set_ylim(min(0, min(vals)) * 1.2, top * 1.18)
    for b_, v in zip(bars, vals): a1.text(b_.get_x() + b_.get_width() / 2, v + top * 0.02 if v >= 0 else v - top * 0.02, _money_k(v), ha="center", va="bottom" if v >= 0 else "top", fontsize=7.5, color=INK)
    a1.yaxis.set_visible(False); _style_ax(a1); a1.set_title("Revenue, driver payments, profit" if S["has_rep"] else f"{S['fp']} revenue", fontsize=8.5, color=INK, loc="left")
    sh = [S["share_trips"], S["share_revenue"]]; sh = [0 if _na(v) else float(v) for v in sh]
    b2 = a2.barh(["Revenue", "Trips"], [sh[1], sh[0]], color=[BLUE, GREY], height=0.5)
    a2.set_xlim(0, 100); a2.xaxis.set_visible(False); _style_ax(a2); a2.spines["bottom"].set_visible(False)
    for bar, v in zip(b2, [sh[1], sh[0]]): a2.text(max(v, 0) + 1.5, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%", va="center", fontsize=8, color=INK)
    a2.barh(["Revenue", "Trips"], [100, 100], color="#F3F4F6", height=0.5, zorder=0)
    a2.set_title(f"Share of all {S['fp']} states", fontsize=8.5, color=INK, loc="left")
    fig.tight_layout(w_pad=3)
    return _img(fig, 170)


def chart_compare(rows):
    """Grouped bars: this week vs last week for revenue, driver payments, profit."""
    pick = [r for r in rows if r["label"] in ("Revenue", "Driver payments", "Profit") and not _na(r["cur"])]      # n/a is never drawn as a $0 bar
    if not pick: return None
    fig, ax = plt.subplots(figsize=(7.4, 2.3)); x = np.arange(len(pick)); w = 0.34
    cur = [float(r["cur"]) for r in pick]; prev = [np.nan if _na(r["prev"]) else float(r["prev"]) for r in pick]
    has_prev = any(not np.isnan(v) for v in prev); top = max([abs(v) for v in cur] + [abs(v) for v in prev if not np.isnan(v)] + [1])
    pos = x - w / 2 if has_prev else x
    bc = ax.bar(pos, cur, w, color=BLUE, label="This week")
    for b_, v in zip(bc, cur): ax.text(b_.get_x() + b_.get_width() / 2, v + top * 0.02, _money_k(v), ha="center", va="bottom", fontsize=7.2, color=INK)
    if has_prev:
        bp = ax.bar([xi + w / 2 for xi, v in zip(x, prev) if not np.isnan(v)], [v for v in prev if not np.isnan(v)], w, color=GREY, label="Last week")
        for b_, v in zip(bp, [v for v in prev if not np.isnan(v)]): ax.text(b_.get_x() + b_.get_width() / 2, v + top * 0.02, _money_k(v), ha="center", va="bottom", fontsize=7.2, color=INK)
        ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    ax.set_xticks(x); ax.set_xticklabels([r["label"] for r in pick]); ax.yaxis.set_visible(False); ax.set_ylim(min(0, min(cur)) * 1.2, top * 1.2); _style_ax(ax)
    fig.tight_layout()
    return _img(fig, 170)


# ------------------------------------------------------------------ document
class _Doc:
    def __init__(self, title, subtitle):
        self.title, self.subtitle, self.story = title, subtitle, []
        self.generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _deco(self, c, doc):
        w, h = A4
        c.saveState()
        c.setFont("Helvetica", 7.5); c.setFillColor(colors.HexColor(MUTED))
        c.drawString(LM, h - 11 * mm, BRAND); c.drawRightString(w - LM, h - 11 * mm, "Weekly report")
        c.setStrokeColor(colors.HexColor(LINE)); c.setLineWidth(0.5); c.line(LM, h - 13.5 * mm, w - LM, h - 13.5 * mm)
        c.drawString(LM, 9 * mm, f"Generated {self.generated}  |  all amounts in USD"); c.drawRightString(w - LM, 9 * mm, f"Page {doc.page}")
        c.restoreState()

    def add(self, *items): self.story.extend(items)
    def keep(self, fn):
        """Run fn (which calls self.add) and keep everything it added on ONE page (moves to the next page instead of splitting a section)."""
        start = len(self.story); fn(); items = self.story[start:]; del self.story[start:]
        if items: self.story.append(KeepTogether(items))
    def h2(self, t): return Paragraph(escape(t), H2)
    def p(self, t, style=BODY): return Paragraph(t, style)            # t may carry <b> tags: callers escape what they insert

    def build(self):
        buf = io.BytesIO()
        doc = BaseDocTemplate(buf, pagesize=A4, title=f"{self.title} - {BRAND}", author=BRAND, leftMargin=LM, rightMargin=LM, topMargin=19 * mm, bottomMargin=16 * mm)
        doc.addPageTemplates([PageTemplate("p", [Frame(LM, 16 * mm, PAGE_W, A4[1] - 35 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=self._deco)])
        story = [Paragraph(escape(self.title), H1), Paragraph(escape(self.subtitle), SUB)] + self.story
        story += [Spacer(1, 14), KeepTogether([Paragraph("_______________________________", NOTE), Paragraph("<b>Hatem Elalfy</b><br/>CFO", NOTE)])]
        doc.build(story)
        return buf.getvalue(), doc.page


def _bold(t): return f"<b>{escape(str(t))}</b>"


# ------------------------------------------------------------------ one state: numbers
def state_summary(D, rate=45.0, err=None):
    """Every number of the simple state report (also used for the on-screen view and the weekly history)."""
    ms, rs, has, fp = D["ms"], D["rs"], D["has_rep"], D["fp"]
    pt = D.get("prov_total") or {}
    S = {"has_rep": has, "fp": fp, "name": D["name"], "code": D.get("code"),
         "first_trips": int(len(ms)), "first_revenue": float(ms.main_amount.sum(min_count=1)) if len(ms) and ms.main_amount.notna().any() else np.nan,
         "drivers": int(ms.driver.nunique()) if len(ms) else np.nan, "miles": float(ms.miles.sum(min_count=1)) if len(ms) and ms.miles.notna().any() else np.nan,
         "prov_trips": pt.get("trips", np.nan), "prov_revenue": pt.get("revenue", np.nan)}
    S["share_trips"] = _share(S["first_trips"], S["prov_trips"]); S["share_revenue"] = _share(S["first_revenue"], S["prov_revenue"])
    cl = PG.claims_all(D, rate, err) if len(ms) else pd.DataFrame(columns=["Date", "Driver", "Trip ID", "Trip Name", "Agreed price", "Paid", "Short", "Basis"])
    S["claims"], S["claim_trips"], S["claim_amount"] = cl, int(len(cl)), float(cl.Short.sum()) if len(cl) else 0.0
    S["cancelled"] = None
    if has:
        _c = rs[rs.notes.astype(str).str.startswith("CANCELLED TRIP")] if "notes" in rs.columns else rs.iloc[0:0]
        if len(_c): S["cancelled"] = {"trips": int(len(_c)), "revenue": float(_c.state_revenue.sum()), "pay": float(_c.driver_payment.sum())}
    S.update(trips=np.nan, state_revenue=np.nan, payments=np.nan, monitor=0.0, profit=np.nan, margin=np.nan, margin_base=np.nan, recon_ok=None, recon_counts=None,
             above=pd.DataFrame(), above_trips=0, above_amount=0.0, profit_policy=np.nan, margin_policy=np.nan, payments_policy=np.nan, not_checked=0)
    if not has: return S
    row = D["fin"][D["fin"].State == D["name"]].iloc[0]
    S.update(trips=int(row["Trips"]), state_revenue=float(row["Revenue"]), payments=float(row["Driver Payments"]), monitor=float(row["Monitor payments"]) if pd.notna(row["Monitor payments"]) else 0.0,
             profit=float(row["Profit"]), margin=float(row["Margin %"]) if pd.notna(row["Margin %"]) else np.nan)
    r = rs[rs.state_source != ""]; prr = r[r.state_revenue.notna() | (r.audit_status == "MONITOR PAYMENT")]
    base = prr.state_revenue.sum(min_count=1) if len(prr) else np.nan; S["margin_base"] = float(base) if pd.notna(base) else np.nan
    if "recon" in D:
        rc = D["recon"]; a, so, fo = len(rc["a"]), len(rc["state_only"]), len(rc["first_only"])
        S["recon_counts"] = (a, so, fo, rc["review"]); S["recon_ok"] = (a + so + fo + rc["review"]) == 0
    pdf = D.get("paydiff")
    if pdf is not None and len(pdf):
        ab = pdf[pdf.Category.astype(str).str.startswith("ABOVE") & (pd.to_numeric(pdf.Difference, errors="coerce") > 0.004)].copy()
        S["above"], S["above_trips"], S["above_amount"] = ab, int(len(ab)), float(pd.to_numeric(ab.Difference, errors="coerce").sum()) if len(ab) else 0.0
    ps = D.get("paysum")
    if ps is not None and len(ps): S["not_checked"] = int(ps[ps.Category.astype(str).str.startswith("Not checked")].Trips.sum())
    ex = S["above_amount"]
    S["payments_policy"] = S["payments"] - ex if pd.notna(S["payments"]) else np.nan
    S["profit_policy"] = S["profit"] + ex if pd.notna(S["profit"]) else np.nan
    S["margin_policy"] = S["profit_policy"] / S["margin_base"] * 100 if pd.notna(S["profit_policy"]) and pd.notna(S["margin_base"]) and S["margin_base"] else np.nan
    return S


def week_extras(main, rec, book, rate=45.0, err=None):
    """{state code: {short_trips, short_amount, above_trips, above_amount}} for the weekly history (so next week's comparison has them)."""
    out = {}
    for code in PG.report_states(main, rec):
        try:
            D = PG.state_report_data(code, main, rec, book, rate, err)
            S = state_summary(D, rate, err)
            out[code] = {"short_trips": S["claim_trips"], "short_amount": S["claim_amount"],
                         "above_trips": S["above_trips"] if S["has_rep"] else np.nan, "above_amount": S["above_amount"] if S["has_rep"] else np.nan}
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ comparison rows (this week vs last week)
_KPI_LABEL = {"Trips": ("Trips", num), "Drivers": ("Drivers", num), "Miles": ("Miles", miles), "Revenue": ("Revenue", usd),
              "Driver Payments": ("Driver payments", usd), "Profit": ("Profit", usd), "Margin %": ("Margin", pct)}


def _compare_rows(D, S, hist, week):
    """Returns (rows, note). Each row: label, cur, prev, kind (fmt). Revenue/payments/profit come from the weekly history (same definitions week to week);
    the claim and above-policy rows come from this report and from the history columns saved with it."""
    code, rows, note = D.get("code"), [], ""
    hs = hist[hist.state == code] if hist is not None and len(hist) and "state" in hist.columns else None
    prev_extra = {}
    if hs is not None and len(hs):
        ws = HI.weeks(hs); wk = pd.Timestamp(week) if week is not None else ws[-1]
        t, ci, pi, warns = HI.weekly_compare(hs, wk); t = t.set_index("KPI")
        for k, (lab, fm) in _KPI_LABEL.items():
            if k not in t.index: continue
            rows.append({"label": lab, "cur": t.at[k, "Current week"], "prev": t.at[k, "Previous week"], "fmt": fm, "pts": k == "Margin %"})
        p = hs[hs.week_start == wk - pd.Timedelta(days=7)]
        if p.empty: note = "No data for last week yet. Save the weekly history (CSV) with this report and upload it next week."
        else:
            for c_ in ("short_trips", "short_amount", "above_trips", "above_amount"):
                prev_extra[c_] = p[c_].sum(min_count=1) if c_ in p.columns else np.nan
            if all(pd.isna(v) for v in prev_extra.values()): note = "Last week's history has no 'paid below price' / 'above policy' figures (they are saved from this week on)."
        incomplete = [w_ for w_ in warns if "incomplete" in w_]
        if incomplete: note = (note + " " if note else "") + incomplete[0]
    else:
        cur = {"Trips": S["first_trips"], "Drivers": S["drivers"], "Miles": S["miles"], "Revenue": S["first_revenue"], "Driver Payments": S["payments"], "Profit": S["profit"], "Margin %": S["margin"]}
        for k, (lab, fm) in _KPI_LABEL.items(): rows.append({"label": lab, "cur": cur[k], "prev": np.nan, "fmt": fm, "pts": k == "Margin %"})
        note = "No weekly history loaded: upload last week's history CSV to compare with last week."
    rows += [{"label": f"Trips paid below the agreed price", "cur": S["claim_trips"], "prev": prev_extra.get("short_trips", np.nan), "fmt": num},
             {"label": "Amount to claim", "cur": S["claim_amount"], "prev": prev_extra.get("short_amount", np.nan), "fmt": usd}]
    if S["has_rep"]:
        rows += [{"label": "Trips paid above the pay policy", "cur": S["above_trips"], "prev": prev_extra.get("above_trips", np.nan), "fmt": num},
                 {"label": "Excess driver pay", "cur": S["above_amount"], "prev": prev_extra.get("above_amount", np.nan), "fmt": usd}]
    return rows, note


# ------------------------------------------------------------------ one state: the PDF
CAP_STEPS = ((12, 8), (8, 6), (5, 4), (3, 3))


def _claims_section(doc, S, cap):
    fp, cl = S["fp"], S["claims"]
    doc.add(doc.h2(f"Trips paid below the agreed price"))
    if not len(cl):
        doc.add(doc.p(f"No trip was paid below the agreed price by {escape(fp)}.")); return
    doc.add(doc.p(f"<b>{_tr(S['claim_trips'])} - {escape(usd(S['claim_amount']))}</b> to claim from {escape(fp)}."))
    if len(cl) <= cap:
        rows = [[sdate(r.Date), r.Driver, r._4, usd(r._5), usd(r.Paid), usd(r.Short)] for r in cl.itertuples()]
        doc.add(table(["Date", "Driver", "Trip", "Agreed", "Paid", "Short"], rows, [8, 22, 38, 11, 11, 11], ["L", "L", "L", "R", "R", "R"], bold_last=True))
    else:
        g = cl.groupby(["Agreed price", "Paid"]).agg(Trips=("Short", "size"), Total=("Short", "sum")).reset_index().sort_values("Total", ascending=False)
        rows = [[num(r.Trips), usd(r._1), usd(r.Paid), usd(r._1 - r.Paid), usd(r.Total)] for r in g.head(cap).itertuples()]
        if len(g) > cap: rows.append([f"+ {len(g) - cap} more prices", "", "", "", usd(g.iloc[cap:].Total.sum())])
        doc.add(table(["Trips", "Agreed", "Paid", "Short per trip", "Total"], rows, [14, 16, 16, 18, 18], bold_last=True))
        doc.add(doc.p("Grouped by price. The trip-by-trip list (date, driver, trip ID) is in the Excel file.", NOTE))
    if S.get("code") == "N.CA":
        doc.add(doc.p("Benicia routes are listed at $45 because First cut them from $50; after the N.CA manager spoke to First, it added $5 on some Richmond routes (now $55-$60). These list prices are the agreed prices, not a claim.", NOTE))


def _policy_section(doc, S, cap):
    doc.add(doc.h2("Driver pay above the pay policy"))
    n, ex = S["above_trips"], S["above_amount"]
    if n == 0:
        doc.add(doc.p("All checked trips are within the pay policy. Profit and margin are unchanged."))
    else:
        doc.add(doc.p(f"<b>{_tr(n)}</b> {'was' if n == 1 else 'were'} paid above the policy - excess driver pay <b>{escape(usd(ex))}</b>."))
        rev = S["state_revenue"]
        rows = [["Actual", usd(rev), usd(S["payments"]), usd(S["profit"]), pct(S["margin"])],
                ["If the policy was applied", usd(rev), usd(S["payments_policy"]), usd(S["profit_policy"]), pct(S["margin_policy"])],
                ["Loss from not applying the policy", "", usd(ex), usd(ex), pts(S["margin_policy"] - S["margin"]) if pd.notna(S["margin_policy"]) and pd.notna(S["margin"]) else "n/a"]]
        doc.add(table(["", "Revenue", "Driver payments", "Profit", "Margin"], rows, [30, 14, 16, 14, 12], bold_last=True))
        doc.add(Spacer(1, 6))
        g = PG._group_pay_differences(S["above"])
        if len(g):
            show = g.head(cap)
            rows = [[r.Driver, r.Route, num(r.Trips), r.Dates, usd(r._7), usd(r._8), usd(r._10)] for r in show.itertuples()]
            if len(g) > cap: rows.append([f"+ {len(g) - cap} more rows", "", num(g.iloc[cap:].Trips.sum()), "", "", "", usd(g.iloc[cap:]["Total difference"].sum())])
            doc.add(table(["Driver", "Route", "Trips", "Dates", "Paid", "Policy", "Excess"], rows, [18, 28, 6, 13, 9, 9, 9], ["L", "L", "R", "L", "R", "R", "R"], bold_last=True))
            if len(g) > cap: doc.add(doc.p("The full list is in the Excel file (sheet 'For state manager').", NOTE))
    if S["not_checked"]:
        doc.add(doc.p(f"Not checked: {_tr(S['not_checked'])} on routes that have no pay policy yet (listed in the Excel file).", NOTE))


def _build_state(D, S, hist, week, cap_claim, cap_above):
    nm, fp = D["name"], D["fp"]
    ms, rs = D["ms"], D["rs"]
    period = PG._period(ms if len(ms) else rs)
    doc = _Doc(f"{nm}", f"{fp} vs state report  |  {period}")

    # 1) summary
    if S["has_rep"]:
        head = ["Trips", "Revenue", "Driver payments", "Profit", "Margin"]
        row = [[num(S["trips"]), usd(S["state_revenue"]), usd(S["payments"]), usd(S["profit"]), pct(S["margin"])]]
        doc.add(table(head, row, [10, 18, 18, 18, 12], ["R"] * 5))
        if S["monitor"] and S["monitor"] > 0.004: doc.add(Spacer(1, 3), doc.p(f"Driver payments include {escape(usd(S['monitor']))} paid to monitors.", NOTE))
        if S.get("cancelled"):
            c_ = S["cancelled"]
            doc.add(Spacer(1, 3), doc.p(f"Includes {_tr(c_['trips'])} at the cancelled-trip rate: revenue {escape(usd(c_['revenue']))} paid by {escape(fp)}, driver pay {escape(usd(c_['pay']))}, profit {escape(usd(c_['revenue'] - c_['pay']))}. Not a price difference and not a claim.", NOTE))
        if S["recon_ok"] is True:
            doc.add(Spacer(1, 3), doc.p(f"Matched with the state report: {S['trips']:,} trips, revenue equal to the cent.", NOTE))
        elif S["recon_ok"] is False:
            a, so, fo, rv = S["recon_counts"]
            doc.add(Spacer(1, 3), doc.p(f"<b>Differences with the state report:</b> {_tr(a)} with a price difference, {fo} only in {escape(fp)}, {so} only in the state report"
                                         + (f", {rv} to review" if rv else "") + ". The list for the state manager is in the Excel file.", NOTE))
    else:
        doc.add(doc.p(f"<b>No state report was uploaded for {escape(nm)}.</b> Driver payments, profit and margin cannot be calculated yet."))
    rows = [["Trips", num(S["first_trips"]), num(S["prov_trips"]), pct(S["share_trips"])],
            [f"Revenue paid by {fp}", usd(S["first_revenue"]), usd(S["prov_revenue"]), pct(S["share_revenue"])]]
    doc.add(Spacer(1, 6), table(["", f"{nm}", f"All {fp} states", "Share"], rows, [26, 18, 20, 12]))
    doc.add(Spacer(1, 6), chart_state_summary(S))

    # 2) paid below the agreed price
    if S["first_trips"]: doc.keep(lambda: _claims_section(doc, S, cap_claim))
    else: doc.add(doc.h2("Trips paid below the agreed price"), doc.p(f"No {escape(fp)} report was uploaded for {escape(nm)}, so the prices {escape(fp)} paid cannot be checked."))

    # 3) driver pay above the policy
    if S["has_rep"]: doc.keep(lambda: _policy_section(doc, S, cap_above))

    # 4) comparison with last week
    rows_c, note = _compare_rows(D, S, hist, week)

    def _compare():
        doc.add(doc.h2("Comparison with last week"))
        body = []
        for r in rows_c:
            cur, prev = r["cur"], r["prev"]; diff = (float(cur) - float(prev)) if not _na(cur) and not _na(prev) else np.nan
            pc = diff / abs(float(prev)) * 100 if not _na(diff) and float(prev) else np.nan
            d_txt = "n/a" if _na(diff) else (pts(diff) if r.get("pts") else (f"{diff:+,.0f}" if r["fmt"] in (num, miles) else usd(diff)))
            body.append([r["label"], r["fmt"](cur), r["fmt"](prev), d_txt, "n/a" if r.get("pts") else chg(pc)])
        doc.add(table(["", "This week", "Last week", "Difference", "Change"], body, [30, 15, 15, 15, 11]))
        if note: doc.add(Spacer(1, 3), doc.p(escape(note), NOTE))
        ch = chart_compare(rows_c)
        if ch is not None: doc.add(Spacer(1, 6), ch)
    doc.keep(_compare)
    return doc.build()


def state_report_pdf(D, hist=None, week=None, rate=45.0, err=None, max_pages=2):
    S = state_summary(D, rate, err)
    out = None
    for cap_c, cap_a in CAP_STEPS:
        out, pages = _build_state(D, S, hist, week, cap_c, cap_a)
        if pages <= max_pages: break
    return out


# ------------------------------------------------------------------ First / EverDriven report
def claims_by_state(main, rec, book, rate=45.0, err=None):
    """DataFrame State / Trips / Amount: the trips paid below the agreed price, per state (same rules as each state report)."""
    rows = []
    for code in sorted(c for c in main.state.dropna().unique() if c not in ("Unassigned", "NEEDS REVIEW", "")):
        try:
            if rec is not None and len(rec):
                D = PG.state_report_data(code, main, rec, book, rate, err, claims_only=True); cl = PG.claims_all(D, rate, err)
                n, amt = len(cl), float(cl.Short.sum()) if len(cl) else 0.0
            else:
                pcs, det, _ = SR.price_check(main[main.state == code], book, SR._err(err), rate)
                n, amt = (int(len(det)), float(-det.Difference.sum())) if len(det) else (0, 0.0)
        except Exception:
            continue
        rows.append({"State": PG.STATE_NAMES.get(code, code), "Trips": n, "Amount": amt})
    return pd.DataFrame(rows, columns=["State", "Trips", "Amount"])


def _chart_first(t):
    d = t[t.State != "TOTAL"].sort_values("Revenue")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, max(2.0, 0.42 * len(d) + 0.9)))
    for ax, col, color, ttl, fmt in ((a1, "Revenue", BLUE, "Revenue by state", _money_k), (a2, "Trips", GREY, "Trips by state", lambda v: f"{v:,.0f}")):
        v = d[col].astype(float).fillna(0).tolist(); b = ax.barh(d.State.tolist(), v, color=color, height=0.55); top = max(v + [1])
        for bar, x in zip(b, v): ax.text(x + top * 0.015, bar.get_y() + bar.get_height() / 2, fmt(x), va="center", fontsize=7.5, color=INK)
        ax.set_xlim(0, top * 1.25); ax.xaxis.set_visible(False); _style_ax(ax); ax.spines["bottom"].set_visible(False); ax.set_title(ttl, fontsize=8.5, color=INK, loc="left")
        if ax is a2: ax.set_yticklabels([])
    fig.tight_layout(w_pad=1.5)
    return _img(fig, 170)


def _chart_claims(c):
    d = c[c.Amount > 0.004].sort_values("Amount")
    if d.empty: return None
    fig, ax = plt.subplots(figsize=(7.4, max(1.4, 0.4 * len(d) + 0.7)))
    b = ax.barh(d.State.tolist(), d.Amount.tolist(), color=AMBER, height=0.5); top = float(d.Amount.max())
    for bar, x in zip(b, d.Amount): ax.text(x + top * 0.015, bar.get_y() + bar.get_height() / 2, usd(x), va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, top * 1.2); ax.xaxis.set_visible(False); _style_ax(ax); ax.spines["bottom"].set_visible(False)
    fig.tight_layout()
    return _img(fig, 170)


def first_report_pdf(main, label=None, adjustments=None, rate=45.0, err=None, rec=None, book=None):
    label = label or SR.provider_label(main)
    doc = _Doc(f"{label} report", f"All states  |  {PG._period(main)}")
    o = SR.first_overview(main, adjustments)
    head, row = ["Trips", "Revenue", "Drivers", "Miles"], [num(o["Trips"]), usd(o["Revenue"]), num(o["Drivers"]), miles(o["Miles"])]
    if "Adjustments" in o: head += ["Adjustments", "Net revenue"]; row += [usd(o["Adjustments"]), usd(o["Net revenue"])]
    doc.add(table(head, [row], [1] * len(head), ["R"] * len(head)))
    if "Adjustments" in o: doc.add(Spacer(1, 3), doc.p("Adjustments are non-trip items paid or charged by the provider (for example a drug test).", NOTE))
    if main.provider.nunique() > 1:
        pt = SR.provider_table(main)
        doc.add(doc.h2("By provider"), table(["Provider", "Trips", "Revenue", "Revenue / trip", "Share of revenue"],
                [[r.Provider, num(r.Trips), usd(r.Revenue), usd(r._6), pct(r._7)] for r in pt.itertuples()], [16, 10, 16, 14, 14], ["L", "R", "R", "R", "R"], bold_last=True))
    t = SR.first_state_table(main)
    doc.add(doc.h2("By state"), table(["State", "Trips", "Revenue", "Revenue / trip", "% of trips", "% of revenue"],
            [[r.State, num(r.Trips), usd(r.Revenue), usd(r._6), pct(r._7), pct(r._8)] for r in t.itertuples()], [20, 9, 16, 13, 10, 11], ["L", "R", "R", "R", "R", "R"], bold_last=True))
    doc.add(Spacer(1, 8), _chart_first(t))
    un = main[main.state.isin(["Unassigned", "NEEDS REVIEW"])]
    if len(un): doc.add(Spacer(1, 4), doc.p(f"{len(un):,} trips ({escape(usd(un.main_amount.sum()))}) of {un.driver.nunique()} drivers have no state yet. Upload the state reports or assign the drivers in the app.", NOTE))

    if book is not None:
        c = claims_by_state(main, rec, book, rate, err)

        def _claims():
            doc.add(doc.h2("Trips paid below the agreed price"))
            if c.empty or c.Trips.sum() == 0:
                doc.add(doc.p("No trip was paid below the agreed price.")); return
            doc.add(doc.p(f"<b>{_tr(c.Trips.sum())} - {escape(usd(c.Amount.sum()))}</b> to claim."))
            rows = [[r.State, num(r.Trips), usd(r.Amount)] for r in c[c.Trips > 0].sort_values("Amount", ascending=False).itertuples()]
            doc.add(table(["State", "Trips", "Amount to claim"], rows, [30, 12, 18], bold_last=True))
            ch = _chart_claims(c)
            if ch is not None: doc.add(Spacer(1, 6), ch)
            doc.add(doc.p("The trip-by-trip lists are in each state's report and in the Excel files.", NOTE))
        doc.keep(_claims)
    return doc.build()[0]
