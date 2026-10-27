from __future__ import annotations
import io
import re
import html
from datetime import datetime

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# Hatem's B.T. Analyzer  -  Beyond Transportation weekly financial analyzer
# Revenue truth = First \"Net Pay\". Policy price = state contract price per trip.
# Price difference per trip = First Net Pay - Policy price  (Beyond's margin).
# Region grouping (Oct 2026):
#   Riverside + Arizona ................................ South California (S.CA)
#   Benicia + Richmond + San Leandro + Berkeley +
#   El Dorado + Sacramento ............................. North California (N.CA)
# ----------------------------------------------------------------------------

REGION_NAME = {
    'N.CA': 'North California',
    'S.CA': 'South California',
    'NM': 'New Mexico',
    'OR': 'Oregon',
    'IL': 'Illinois',
    'AK': 'Alaska',
    'Unknown': 'Unassigned',
}
REGION_ORDER = ['S.CA', 'N.CA', 'NM', 'OR', 'AK', 'IL', 'Unknown']

# Which real cities / labels roll up into each region (shown in the UI).
REGION_CITIES = {
    'N.CA': ['Benicia', 'Richmond', 'San Leandro', 'Berkeley', 'El Dorado', 'Sacramento'],
    'S.CA': ['Riverside', 'Arizona'],
    'NM': ['Albuquerque'],
    'OR': ['Oregon'],
    'IL': ['Illinois'],
    'AK': ['Alaska'],
}

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _is_num(x):
    try:
        float(str(x).replace(',', '').replace('$', ''))
        return True
    except Exception:
        return False


def _num(x):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        v = float(str(x).replace(',', '').replace('$', '').strip())
        return v
    except Exception:
        return None


def region_from_label(txt):
    """Resolve a city-section label or state-sheet name to a region code."""
    s = str(txt or '').upper()
    if 'CROSS' in s or 'ALASKA' in s or 'ANCHORAGE' in s:
        return 'AK'
    if 'NEW MEXICO' in s or 'ALBUQ' in s or 'ABQ' in s or s.strip() == 'NM' or 'NM ' in s:
        return 'NM'
    if 'ILLINOIS' in s or 'ELGIN' in s or 'CHICAGO' in s or s.strip() == 'IL' or 'IL ' in s:
        return 'IL'
    if 'OREGON' in s or 'PORTLAND' in s or s.strip() == 'OR' or 'OR ' in s:
        return 'OR'
    if any(k in s for k in ['RIVERSIDE', 'ARIZONA', 'RS&AZ', 'RS AND AZ', 'S.CA',
                            'SOUTH CA', 'SAN DIEGO', 'LOS ANGELES']):
        return 'S.CA'
    if any(k in s for k in ['BENICIA', 'RICHMOND', 'SAN LEANDRO', 'BERKELEY',
                            'EL DORADO', 'SACRAMENTO', 'NORTH CA', 'N.CA', 'NORTH']):
        return 'N.CA'
    return None


def city_from_label(txt):
    """Clean a city-section label into a display city name (drop trailing state code)."""
    s = re.sub(r'\s+', ' ', str(txt or '').strip())
    s = re.sub(r'[,\s]+(CA|AZ|OR|NM|IL|AK)$', '', s, flags=re.I)
    s = s.strip()
    if s.upper() in ('NEW MEXICO', 'NM', 'ALBUQUERQUE', 'ABQ'):
        return 'Albuquerque'
    return s or '\u2014'


def _clean_name(x):
    return re.sub(r'\s+', ' ', str(x or '').strip())


def _is_total_row(name):
    s = str(name or '').strip().upper()
    return (not s) or ('TOTAL' in s) or s in ('NAN', 'GRAND')


# ----------------------------------------------------------------------------
# Parsers
# ----------------------------------------------------------------------------

def parse_breakup(df):
    """Breakup sheet: per-driver weekly summary grouped by city sections.
    Columns: Sr#, name, trips, Revenue(=First Net Pay total), payment(=policy total).
    Returns one row per driver with region, trips, first_pay, policy_pay."""
    rows = []
    current = None
    current_city = '\u2014'
    n = len(df)
    ncol = df.shape[1]
    for i in range(n):
        c0 = df.iat[i, 0] if ncol > 0 else None
        c1 = df.iat[i, 1] if ncol > 1 else None
        s0 = '' if pd.isna(c0) else str(c0).strip()
        s1 = '' if pd.isna(c1) else str(c1).strip()
        # Section header: text in col0, nothing in col1, not a Sr# / header word.
        if s0 and not _is_num(s0) and not s1 and s0.lower() not in ('sr #', 'sr#', 'particulars'):
            current = region_from_label(s0)
            current_city = city_from_label(s0)
            continue
        # Driver row: numeric Sr# in col0 and a name in col1.
        if _is_num(s0) and s1 and not _is_total_row(s1):
            rev = _num(df.iat[i, 3]) if ncol > 3 else None
            if current and rev is not None:
                rows.append({
                    'region': current,
                    'city': current_city,
                    'driver': _clean_name(s1),
                    'trips': _num(df.iat[i, 2]) or 0,
                    'first_pay': rev or 0.0,
                    'policy_pay': (_num(df.iat[i, 4]) or 0.0) if ncol > 4 else 0.0,
                })
    return pd.DataFrame(rows)


def parse_details(df, region):
    """A per-state Details sheet: per-trip rows carrying First NET PAY and the
    state policy price (header AMOUNT or PAY). Returns per-trip price diffs."""
    hdr = None
    headers = None
    for i in range(min(10, len(df))):
        vals = [str(x).strip().upper() for x in df.iloc[i].tolist()]
        if 'DRIVER NAME' in vals and 'NET PAY' in vals:
            hdr = i
            headers = vals
            break
    if hdr is None:
        return pd.DataFrame()
    dn = headers.index('DRIVER NAME')
    npay = headers.index('NET PAY')
    price = None
    for cand in ('AMOUNT', 'PAY'):
        if cand in headers:
            price = headers.index(cand)
            break
    if price is None:
        return pd.DataFrame()
    trip_c = next((j for j, h in enumerate(headers) if h == 'TRIP NAME'), None)
    miles_c = next((j for j, h in enumerate(headers) if h in ('MILES', 'MI')), None)
    date_c = next((j for j, h in enumerate(headers) if h == 'DATE'), None)
    data = df.iloc[hdr + 1:]
    out = []
    for _, r in data.iterrows():
        drv = r.iloc[dn] if dn < len(r) else None
        if _is_total_row(drv):
            continue
        fp = _num(r.iloc[npay]) if npay < len(r) else None
        pp = _num(r.iloc[price]) if price < len(r) else None
        if fp is None and pp is None:
            continue
        fp = fp or 0.0
        pp = pp or 0.0
        out.append({
            'region': region,
            'driver': _clean_name(drv),
            'trip': _clean_name(r.iloc[trip_c]) if (trip_c is not None and trip_c < len(r)) else '',
            'date': str(r.iloc[date_c])[:10] if (date_c is not None and date_c < len(r) and pd.notna(r.iloc[date_c])) else '',
            'miles': _num(r.iloc[miles_c]) if (miles_c is not None and miles_c < len(r)) else None,
            'first_pay': fp,
            'policy_price': pp,
            'diff': fp - pp,
        })
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------
# Workbook loading
# ----------------------------------------------------------------------------

def load_workbooks(files):
    """files: list of (name, bytes-or-fileobj). Returns (breakup_df, trips_df)."""
    bk_frames = []
    tr_frames = []
    for name, data in files:
        try:
            xl = pd.ExcelFile(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
        except Exception as e:
            st.warning(f'Could not read {name}: {e}')
            continue
        for sh in xl.sheet_names:
            low = sh.strip().lower()
            if low == 'breakup':
                try:
                    bk = parse_breakup(xl.parse(sh, header=None))
                    if len(bk):
                        bk['source'] = name
                        bk_frames.append(bk)
                except Exception:
                    pass
            elif 'details' in low:
                reg = region_from_label(sh)
                if not reg:
                    continue
                try:
                    tr = parse_details(xl.parse(sh, header=None), reg)
                    if len(tr):
                        tr['source'] = name
                        tr_frames.append(tr)
                except Exception:
                    pass
    bk = pd.concat(bk_frames, ignore_index=True) if bk_frames else pd.DataFrame(
        columns=['region', 'city', 'driver', 'trips', 'first_pay', 'policy_pay', 'source'])
    tr = pd.concat(tr_frames, ignore_index=True) if tr_frames else pd.DataFrame(
        columns=['region', 'driver', 'trip', 'date', 'miles', 'first_pay', 'policy_price', 'diff', 'source'])
    return bk, tr


def region_summary(bk):
    """Per-region headline financials from the Breakup summary (authoritative)."""
    if bk.empty:
        return pd.DataFrame(columns=['region', 'drivers', 'trips', 'first_pay', 'policy_pay', 'diff', 'margin'])
    g = bk.groupby('region').agg(
        drivers=('driver', 'nunique'),
        trips=('trips', 'sum'),
        first_pay=('first_pay', 'sum'),
        policy_pay=('policy_pay', 'sum'),
    ).reset_index()
    g['diff'] = g['first_pay'] - g['policy_pay']
    g['margin'] = g.apply(lambda r: (r['diff'] / r['first_pay'] * 100) if r['first_pay'] else 0.0, axis=1)
    g['order'] = g['region'].apply(lambda r: REGION_ORDER.index(r) if r in REGION_ORDER else 99)
    g = g.sort_values('order').drop(columns='order').reset_index(drop=True)
    return g


def driver_summary(bk, region):
    d = bk[bk['region'] == region].copy()
    if d.empty:
        return d
    d = d.groupby('driver').agg(
        trips=('trips', 'sum'),
        first_pay=('first_pay', 'sum'),
        policy_pay=('policy_pay', 'sum'),
    ).reset_index()
    d['diff'] = d['first_pay'] - d['policy_pay']
    d['margin'] = d.apply(lambda r: (r['diff'] / r['first_pay'] * 100) if r['first_pay'] else 0.0, axis=1)
    return d.sort_values('diff', ascending=False).reset_index(drop=True)


def city_summary(bk, region):
    """Per-city headline financials within a region (for N.CA / S.CA sub-tables)."""
    d = bk[bk['region'] == region].copy()
    if d.empty or 'city' not in d.columns:
        return pd.DataFrame()
    g = d.groupby('city').agg(
        drivers=('driver', 'nunique'),
        trips=('trips', 'sum'),
        first_pay=('first_pay', 'sum'),
        policy_pay=('policy_pay', 'sum'),
    ).reset_index()
    g['diff'] = g['first_pay'] - g['policy_pay']
    g['margin'] = g.apply(lambda r: (r['diff'] / r['first_pay'] * 100) if r['first_pay'] else 0.0, axis=1)
    return g.sort_values('diff', ascending=False).reset_index(drop=True)


def driver_summary_city(bk, region, city):
    d = bk[(bk['region'] == region) & (bk['city'] == city)].copy()
    if d.empty:
        return d
    d = d.groupby('driver').agg(
        trips=('trips', 'sum'),
        first_pay=('first_pay', 'sum'),
        policy_pay=('policy_pay', 'sum'),
    ).reset_index()
    d['diff'] = d['first_pay'] - d['policy_pay']
    d['margin'] = d.apply(lambda r: (r['diff'] / r['first_pay'] * 100) if r['first_pay'] else 0.0, axis=1)
    return d.sort_values('diff', ascending=False).reset_index(drop=True)


def build_comparison(rsum, rsum_prev):
    """Week-over-week comparison per region. Returns a merged frame with deltas."""
    cur = rsum[['region', 'trips', 'first_pay', 'policy_pay', 'diff', 'margin']].copy()
    prev = rsum_prev[['region', 'first_pay', 'diff', 'margin']].copy().rename(
        columns={'first_pay': 'first_pay_prev', 'diff': 'diff_prev', 'margin': 'margin_prev'})
    m = cur.merge(prev, on='region', how='outer')
    for c in ['trips', 'first_pay', 'policy_pay', 'diff', 'margin',
              'first_pay_prev', 'diff_prev', 'margin_prev']:
        if c in m:
            m[c] = m[c].fillna(0.0)
    m['rev_delta'] = m['first_pay'] - m['first_pay_prev']
    m['diff_delta'] = m['diff'] - m['diff_prev']
    m['diff_pct'] = m.apply(
        lambda r: (r['diff_delta'] / abs(r['diff_prev']) * 100) if r['diff_prev'] else 0.0, axis=1)
    m['margin_delta'] = m['margin'] - m['margin_prev']
    m['order'] = m['region'].apply(lambda r: REGION_ORDER.index(r) if r in REGION_ORDER else 99)
    m = m.sort_values('order').drop(columns='order').reset_index(drop=True)
    return m


# ----------------------------------------------------------------------------
# Formatting + downloadable (light / print-safe) HTML report
# ----------------------------------------------------------------------------

def money(v):
    try:
        return '${:,.2f}'.format(float(v))
    except Exception:
        return '$0.00'


def pct(v):
    try:
        return '{:.1f}%'.format(float(v))
    except Exception:
        return '0.0%'


def _esc(x):
    return html.escape(str(x))


def _bar_row(label, value, vmax, color, right):
    w = 0 if not vmax else max(2, min(100, value / vmax * 100))
    return (
        '<div class="barrow"><div class="barlbl">{lbl}</div>'
        '<div class="bartrack"><div class="barfill" style="width:{w:.1f}%;background:{c};"></div></div>'
        '<div class="barval">{rv}</div></div>'
    ).format(lbl=_esc(label), w=w, c=color, rv=_esc(right))


def build_html_report(rsum, trips, bk, week_label):
    tot_rev = rsum['first_pay'].sum() if len(rsum) else 0
    tot_pol = rsum['policy_pay'].sum() if len(rsum) else 0
    tot_diff = tot_rev - tot_pol
    tot_trips = int(rsum['trips'].sum()) if len(rsum) else 0
    tot_drv = int(bk['driver'].nunique()) if len(bk) else 0
    margin = (tot_diff / tot_rev * 100) if tot_rev else 0
    noncomp = int((trips['diff'] < 0).sum()) if len(trips) else 0

    css = """
    body{font-family:'Segoe UI',Arial,sans-serif;background:#ffffff;color:#1f2733;margin:0;padding:32px;}
    h1{font-size:26px;margin:0 0 4px;color:#0f2a43;}
    h2{font-size:19px;margin:34px 0 12px;color:#0f2a43;border-bottom:2px solid #e3e8ef;padding-bottom:6px;}
    .sub{color:#6b7684;font-size:13px;margin-bottom:22px;}
    .kpis{display:flex;flex-wrap:wrap;gap:14px;margin:18px 0;}
    .kpi{flex:1;min-width:150px;background:#f6f8fb;border:1px solid #e3e8ef;border-radius:12px;padding:16px 18px;}
    .kpi .lab{font-size:12px;color:#6b7684;text-transform:uppercase;letter-spacing:.04em;}
    .kpi .val{font-size:23px;font-weight:700;color:#0f2a43;margin-top:6px;}
    .kpi.good .val{color:#157347;} .kpi.warn .val{color:#b42318;}
    table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px;}
    th,td{padding:9px 12px;text-align:right;border-bottom:1px solid #e9edf3;}
    th:first-child,td:first-child{text-align:left;}
    thead th{background:#0f2a43;color:#fff;font-weight:600;}
    tbody tr:nth-child(even){background:#f8fafc;}
    .pos{color:#157347;font-weight:600;} .neg{color:#b42318;font-weight:600;}
    .barrow{display:flex;align-items:center;gap:12px;margin:6px 0;}
    .barlbl{width:150px;font-size:13px;color:#33415c;}
    .bartrack{flex:1;background:#eef2f7;border-radius:6px;height:16px;overflow:hidden;}
    .barfill{height:100%;border-radius:6px;}
    .barval{width:120px;text-align:right;font-size:13px;font-weight:600;color:#0f2a43;}
    .note{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:10px 14px;border-radius:8px;font-size:13px;margin:10px 0;}
    .foot{margin-top:40px;color:#9aa4b2;font-size:11px;text-align:center;}
    """

    def kpi(lab, val, cls=''):
        return '<div class="kpi {c}"><div class="lab">{l}</div><div class="val">{v}</div></div>'.format(
            c=cls, l=_esc(lab), v=_esc(val))

    parts = []
    parts.append('<html><head><meta charset="utf-8"><style>%s</style></head><body>' % css)
    parts.append("<h1>Hatem's B.T. Analyzer &mdash; Consolidated Report</h1>")
    parts.append('<div class="sub">Beyond Transportation &nbsp;|&nbsp; %s &nbsp;|&nbsp; generated %s</div>'
                 % (_esc(week_label), datetime.now().strftime('%Y-%m-%d %H:%M')))
    parts.append('<div class="kpis">')
    parts.append(kpi('First Net Pay (Revenue)', money(tot_rev)))
    parts.append(kpi('Policy Pay (Drivers)', money(tot_pol)))
    parts.append(kpi('Price Difference', money(tot_diff), 'good'))
    parts.append(kpi('Overall Margin', pct(margin), 'good'))
    parts.append(kpi('Trips', '{:,}'.format(tot_trips)))
    parts.append(kpi('Drivers', '{:,}'.format(tot_drv)))
    parts.append(kpi('Non-compliant Trips', str(noncomp), 'warn' if noncomp else ''))
    parts.append('</div>')

    # Region comparison table
    parts.append('<h2>Price difference by state</h2>')
    parts.append('<table><thead><tr><th>State / Region</th><th>Drivers</th><th>Trips</th>'
                 '<th>First Net Pay</th><th>Policy Pay</th><th>Price Difference</th><th>Margin</th></tr></thead><tbody>')
    for _, r in rsum.iterrows():
        dcls = 'pos' if r['diff'] >= 0 else 'neg'
        parts.append(
            '<tr><td>{name}</td><td>{dr}</td><td>{tp}</td><td>{rev}</td><td>{pol}</td>'
            '<td class="{dc}">{df}</td><td class="{dc}">{mg}</td></tr>'.format(
                name=_esc(REGION_NAME.get(r['region'], r['region'])), dr=int(r['drivers']),
                tp=int(r['trips']), rev=money(r['first_pay']), pol=money(r['policy_pay']),
                dc=dcls, df=money(r['diff']), mg=pct(r['margin'])))
    parts.append('</tbody></table>')

    # Price-difference bar chart
    if len(rsum):
        rvmax = rsum['first_pay'].abs().max() or 1
        parts.append('<h2>Revenue by state (First Net Pay &mdash; First report)</h2>')
        for _, r in rsum.iterrows():
            parts.append(_bar_row(REGION_NAME.get(r['region'], r['region']), abs(r['first_pay']), rvmax, '#2563eb', money(r['first_pay'])))
        tvmax = rsum['trips'].abs().max() or 1
        parts.append('<h2>Trips (runs) by state &mdash; First report</h2>')
        for _, r in rsum.iterrows():
            parts.append(_bar_row(REGION_NAME.get(r['region'], r['region']), abs(r['trips']), tvmax, '#0d9488', '{:,}'.format(int(r['trips']))))
        vmax = rsum['diff'].abs().max() or 1
        parts.append('<h2>Price difference ($) per state</h2>')
        for _, r in rsum.iterrows():
            col = '#157347' if r['diff'] >= 0 else '#b42318'
            parts.append(_bar_row(REGION_NAME.get(r['region'], r['region']), abs(r['diff']), vmax, col, money(r['diff'])))
        mmax = rsum['margin'].abs().max() or 1
        parts.append('<h2>Margin (%) per state</h2>')
        for _, r in rsum.iterrows():
            col = '#2563eb' if r['margin'] >= 0 else '#b42318'
            parts.append(_bar_row(REGION_NAME.get(r['region'], r['region']), abs(r['margin']), mmax, col, pct(r['margin'])))

    # Per-state driver detail
    for _, r in rsum.iterrows():
        reg = r['region']
        parts.append('<h2>%s &mdash; driver breakdown</h2>' % _esc(REGION_NAME.get(reg, reg)))
        csum = city_summary(bk, reg)
        if len(csum) > 1:
            parts.append('<table><thead><tr><th>City</th><th>Drivers</th><th>Trips</th>'
                         '<th>First Net Pay</th><th>Policy Pay</th><th>Price Difference</th><th>Margin</th>'
                         '</tr></thead><tbody>')
            for _, cr in csum.iterrows():
                dcls = 'pos' if cr['diff'] >= 0 else 'neg'
                parts.append('<tr><td>{c}</td><td>{dr}</td><td>{tp}</td><td>{rev}</td><td>{pol}</td>'
                             '<td class="{dc}">{df}</td><td class="{dc}">{mg}</td></tr>'.format(
                                 c=_esc(cr['city']), dr=int(cr['drivers']), tp=int(cr['trips']),
                                 rev=money(cr['first_pay']), pol=money(cr['policy_pay']),
                                 dc=dcls, df=money(cr['diff']), mg=pct(cr['margin'])))
            parts.append('</tbody></table>')
        ds = driver_summary(bk, reg)
        parts.append('<table><thead><tr><th>Driver</th><th>Trips</th><th>First Net Pay</th>'
                     '<th>Policy Pay</th><th>Price Difference</th><th>Margin</th></tr></thead><tbody>')
        for _, d in ds.iterrows():
            dcls = 'pos' if d['diff'] >= 0 else 'neg'
            parts.append('<tr><td>{n}</td><td>{t}</td><td>{r}</td><td>{p}</td>'
                         '<td class="{dc}">{df}</td><td class="{dc}">{m}</td></tr>'.format(
                             n=_esc(d['driver']), t=int(d['trips']), r=money(d['first_pay']),
                             p=money(d['policy_pay']), dc=dcls, df=money(d['diff']), m=pct(d['margin'])))
        parts.append('</tbody></table>')
        # Non-compliant trips for this region (only when any exist)
        nc = trips[(trips['region'] == reg) & (trips['diff'] < 0)]
        if len(nc):
            parts.append('<div class="note">%d non-compliant trip(s): First Net Pay below the state policy price (loss).</div>' % len(nc))
            parts.append('<table><thead><tr><th>Driver</th><th>Trip</th><th>First Net Pay</th>'
                         '<th>Policy Price</th><th>Difference</th></tr></thead><tbody>')
            for _, t in nc.iterrows():
                parts.append('<tr><td>{n}</td><td>{tr}</td><td>{f}</td><td>{p}</td>'
                             '<td class="neg">{d}</td></tr>'.format(
                                 n=_esc(t['driver']), tr=_esc(t['trip'] or '-'),
                                 f=money(t['first_pay']), p=money(t['policy_price']), d=money(t['diff'])))
            parts.append('</tbody></table>')

    parts.append('<div class="foot">Hatem\'s B.T. Analyzer &middot; Beyond Transportation &middot; '
                 'Revenue = First Net Pay &middot; Price difference = First Net Pay minus state policy price</div>')
    parts.append('</body></html>')
    return ''.join(parts)


# ----------------------------------------------------------------------------
# Print-ready PDF summary (reportlab)
# ----------------------------------------------------------------------------

def build_pdf_report(rsum, trips, bk, week_label, cmp_df=None, prev_label=None):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    NAVY = colors.HexColor('#0f2a43')
    GREEN = colors.HexColor('#157347')
    RED = colors.HexColor('#b42318')
    GREY = colors.HexColor('#6b7684')
    LIGHT = colors.HexColor('#f8fafc')
    LINE = colors.HexColor('#e3e8ef')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="Hatem's B.T. Analyzer - Consolidated Report")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=ss['Title'], textColor=NAVY, fontSize=20,
                        spaceAfter=2, alignment=TA_LEFT)
    sub = ParagraphStyle('sub', parent=ss['Normal'], textColor=GREY, fontSize=9, spaceAfter=10)
    h2 = ParagraphStyle('h2', parent=ss['Heading2'], textColor=NAVY, fontSize=12,
                        spaceBefore=12, spaceAfter=4)
    note = ParagraphStyle('note', parent=ss['Normal'], textColor=RED, fontSize=8.5, spaceBefore=2)

    tot_rev = rsum['first_pay'].sum() if len(rsum) else 0
    tot_pol = rsum['policy_pay'].sum() if len(rsum) else 0
    tot_diff = tot_rev - tot_pol
    tot_trips = int(rsum['trips'].sum()) if len(rsum) else 0
    tot_drv = int(bk['driver'].nunique()) if len(bk) else 0
    margin = (tot_diff / tot_rev * 100) if tot_rev else 0
    noncomp = int((trips['diff'] < 0).sum()) if len(trips) else 0

    def col(v):
        return GREEN if float(v) >= 0 else RED

    story = []
    story.append(Paragraph("Hatem's B.T. Analyzer &ndash; Consolidated Report", h1))
    story.append(Paragraph('Beyond Transportation&nbsp;&nbsp;|&nbsp;&nbsp;%s&nbsp;&nbsp;|&nbsp;&nbsp;generated %s'
                           % (_esc(week_label), datetime.now().strftime('%Y-%m-%d %H:%M')), sub))

    # KPI strip as a table
    kpi_data = [[
        'First Net Pay', 'Policy Pay', 'Price Difference', 'Overall Margin',
        'Trips', 'Drivers', 'Non-compliant',
    ], [
        money(tot_rev), money(tot_pol), money(tot_diff), pct(margin),
        '{:,}'.format(tot_trips), '{:,}'.format(tot_drv), str(noncomp),
    ]]
    kt = Table(kpi_data, colWidths=[38 * mm] * 7)
    kt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT),
        ('TEXTCOLOR', (2, 1), (2, 1), col(tot_diff)),
        ('TEXTCOLOR', (6, 1), (6, 1), RED if noncomp else GREEN),
        ('FONTSIZE', (0, 0), (-1, 0), 7.5),
        ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, LINE),
    ]))
    story.append(kt)

    # Region table
    story.append(Paragraph('Price difference by state', h2))
    head = ['State / Region', 'Drivers', 'Trips', 'First Net Pay', 'Policy Pay',
            'Price Difference', 'Margin']
    data = [head]
    diff_style = []
    for i, (_, r) in enumerate(rsum.iterrows(), start=1):
        data.append([
            REGION_NAME.get(r['region'], r['region']), int(r['drivers']), int(r['trips']),
            money(r['first_pay']), money(r['policy_pay']), money(r['diff']), pct(r['margin']),
        ])
        diff_style.append(('TEXTCOLOR', (5, i), (6, i), col(r['diff'])))
    rt = Table(data, colWidths=[46 * mm, 20 * mm, 18 * mm, 36 * mm, 34 * mm, 38 * mm, 24 * mm])
    rt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.4, LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ] + diff_style))
    story.append(rt)

    # Week-over-week comparison
    if cmp_df is not None and len(cmp_df):
        story.append(Paragraph('Week-over-week comparison (current vs previous)', h2))
        chead = ['State / Region', 'Diff (current)', 'Diff (previous)', 'Change ($)',
                 'Change (%)', 'Margin now', 'Margin before']
        cdata = [chead]
        cstyle = []
        for i, (_, r) in enumerate(cmp_df.iterrows(), start=1):
            cdata.append([
                REGION_NAME.get(r['region'], r['region']),
                money(r['diff']), money(r['diff_prev']), money(r['diff_delta']),
                pct(r['diff_pct']), pct(r['margin']), pct(r['margin_prev']),
            ])
            cstyle.append(('TEXTCOLOR', (3, i), (4, i), col(r['diff_delta'])))
        ct = Table(cdata, colWidths=[42 * mm, 34 * mm, 34 * mm, 32 * mm, 26 * mm, 26 * mm, 26 * mm])
        ct.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
            ('GRID', (0, 0), (-1, -1), 0.4, LINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ] + cstyle))
        story.append(ct)
        if prev_label:
            story.append(Paragraph('Previous: %s' % _esc(prev_label), sub))

    # Non-compliant trips
    if noncomp:
        story.append(Paragraph('Non-compliant trips (First Net Pay below state policy price)', h2))
        nc = trips[trips['diff'] < 0].copy()
        nhead = ['State', 'Driver', 'Trip', 'First Net Pay', 'Policy Price', 'Difference']
        ndata = [nhead]
        for _, t in nc.iterrows():
            ndata.append([
                REGION_NAME.get(t['region'], t['region']), t['driver'], (t['trip'] or '-'),
                money(t['first_pay']), money(t['policy_price']), money(t['diff']),
            ])
        nt = Table(ndata, colWidths=[30 * mm, 48 * mm, 50 * mm, 34 * mm, 32 * mm, 30 * mm])
        nt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), RED),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (5, 1), (5, -1), RED),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
            ('GRID', (0, 0), (-1, -1), 0.4, LINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(nt)
    else:
        story.append(Spacer(1, 6))
        story.append(Paragraph('All trips are compliant: First Net Pay meets or exceeds the policy price.', note))

    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Streamlit UI  (dark on screen; downloadable report is light / print-safe)
# ----------------------------------------------------------------------------

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon='\U0001F69C', layout='wide')

DARK_CSS = """
<style>
.stApp{background:#0e1726;color:#e6edf6;}
section[data-testid="stSidebar"]{background:#0a1220;}
h1,h2,h3,h4{color:#f2f6fc;}
.kcard{background:#15213a;border:1px solid #23314f;border-radius:14px;padding:16px 18px;}
.kcard .lab{font-size:12px;color:#8ea2c0;text-transform:uppercase;letter-spacing:.05em;}
.kcard .val{font-size:26px;font-weight:700;margin-top:6px;color:#f2f6fc;}
.kcard.good .val{color:#4ade80;} .kcard.warn .val{color:#f87171;}
.pill{display:inline-block;background:#1d2b49;color:#9fb4d6;border-radius:20px;padding:3px 12px;font-size:12px;margin-right:6px;}
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)


def kcard(lab, val, cls=''):
    st.markdown(
        '<div class="kcard {c}"><div class="lab">{l}</div><div class="val">{v}</div></div>'.format(
            c=cls, l=html.escape(str(lab)), v=html.escape(str(val))),
        unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _load(cached_files):
    return load_workbooks(cached_files)


st.sidebar.markdown("## \U0001F69C Hatem's B.T. Analyzer")
st.sidebar.caption('Beyond Transportation \u2014 weekly financial analyzer')

uploads = st.sidebar.file_uploader(
    'Upload CURRENT week report file(s)', type=['xlsx'], accept_multiple_files=True,
    help='Upload the "WEEKLY ALL STATES" workbook and the Alaska weekly workbook for the current week.')

prev_uploads = st.sidebar.file_uploader(
    'Upload PREVIOUS week file(s) — optional', type=['xlsx'], accept_multiple_files=True,
    help='Optional. Upload last week\'s workbook(s) to see a week-over-week comparison.')

files = []
if uploads:
    for u in uploads:
        files.append((u.name, u.getvalue()))

prev_files = []
if prev_uploads:
    for u in prev_uploads:
        prev_files.append((u.name, u.getvalue()))

if not files:
    st.title("Hatem's B.T. Analyzer")
    st.info('Upload the weekly report workbook(s) from the left sidebar to begin. '
            'The app reads the **Breakup** summary and each per-state **Details** sheet, '
            'then computes the price difference (First Net Pay \u2212 state policy price) for every state.')
    st.stop()

bk, trips = _load(files)

if bk.empty and trips.empty:
    st.error('No usable Breakup or Details sheets found in the uploaded file(s).')
    st.stop()

# Fallback: if Breakup missing for a region but Details present, synthesize a summary.
if bk.empty and not trips.empty:
    syn = trips.groupby(['region', 'driver']).agg(
        trips=('first_pay', 'size'), first_pay=('first_pay', 'sum'),
        policy_pay=('policy_price', 'sum')).reset_index()
    syn['city'] = syn['region']
    syn['source'] = 'details'
    bk = syn

rsum = region_summary(bk)
week_label = 'Week ending 9 Oct 2026'
prev_label = 'Previous week'

# Optional previous-week dataset for week-over-week comparison.
bk_prev = trips_prev = None
rsum_prev = None
cmp_df = None
if prev_files:
    bk_prev, trips_prev = _load(prev_files)
    if bk_prev.empty and not trips_prev.empty:
        synp = trips_prev.groupby(['region', 'driver']).agg(
            trips=('first_pay', 'size'), first_pay=('first_pay', 'sum'),
            policy_pay=('policy_price', 'sum')).reset_index()
        synp['city'] = synp['region']
        synp['source'] = 'details'
        bk_prev = synp
    if not bk_prev.empty:
        rsum_prev = region_summary(bk_prev)
        cmp_df = build_comparison(rsum, rsum_prev)

regions_present = list(rsum['region']) if len(rsum) else []
nav_options = ['\U0001F4CA Consolidated Report'] + [
    REGION_NAME.get(r, r) for r in regions_present]
choice = st.sidebar.radio('Report', nav_options)

st.sidebar.markdown('---')
st.sidebar.caption('Revenue = First Net Pay (truth). Price difference = First Net Pay \u2212 state policy price.')


def _style_money(df, money_cols, pct_cols):
    d = df.copy()
    for c in money_cols:
        if c in d:
            d[c] = d[c].apply(money)
    for c in pct_cols:
        if c in d:
            d[c] = d[c].apply(pct)
    return d


if choice.startswith('\U0001F4CA'):
    st.title("Consolidated Report")
    st.caption(week_label)

    tot_rev = rsum['first_pay'].sum()
    tot_pol = rsum['policy_pay'].sum()
    tot_diff = tot_rev - tot_pol
    tot_trips = int(rsum['trips'].sum())
    tot_drv = int(bk['driver'].nunique())
    margin = (tot_diff / tot_rev * 100) if tot_rev else 0
    noncomp = int((trips['diff'] < 0).sum()) if len(trips) else 0

    c = st.columns(4)
    with c[0]:
        kcard('First Net Pay (Revenue)', money(tot_rev))
    with c[1]:
        kcard('Policy Pay (Drivers)', money(tot_pol))
    with c[2]:
        kcard('Price Difference', money(tot_diff), 'good')
    with c[3]:
        kcard('Overall Margin', pct(margin), 'good')
    c = st.columns(4)
    with c[0]:
        kcard('Trips', '{:,}'.format(tot_trips))
    with c[1]:
        kcard('Drivers', '{:,}'.format(tot_drv))
    with c[2]:
        kcard('States', str(len(rsum)))
    with c[3]:
        kcard('Non-compliant Trips', str(noncomp), 'warn' if noncomp else 'good')

    st.markdown('### Price difference by state')
    disp = rsum.copy()
    disp['State'] = disp['region'].map(lambda r: REGION_NAME.get(r, r))
    show = disp[['State', 'drivers', 'trips', 'first_pay', 'policy_pay', 'diff', 'margin']].rename(
        columns={'drivers': 'Drivers', 'trips': 'Trips', 'first_pay': 'First Net Pay',
                 'policy_pay': 'Policy Pay', 'diff': 'Price Difference', 'margin': 'Margin'})
    st.dataframe(_style_money(show, ['First Net Pay', 'Policy Pay', 'Price Difference'], ['Margin']),
                 use_container_width=True, hide_index=True)

    cc = st.columns(2)
    with cc[0]:
        st.markdown('#### Revenue by state (First Net Pay \u2014 First report)')
        st.bar_chart(disp.set_index('State')['first_pay'], color='#60a5fa', height=300)
    with cc[1]:
        st.markdown('#### Trips (runs) by state \u2014 First report')
        st.bar_chart(disp.set_index('State')['trips'], color='#34d399', height=300)

    cc = st.columns(2)
    with cc[0]:
        st.markdown('#### Price difference ($)')
        st.bar_chart(disp.set_index('State')['diff'], color='#4ade80', height=300)
    with cc[1]:
        st.markdown('#### Margin (%)')
        st.bar_chart(disp.set_index('State')['margin'], color='#60a5fa', height=300)

    st.markdown('#### First Net Pay vs Policy Pay')
    st.bar_chart(disp.set_index('State')[['first_pay', 'policy_pay']].rename(
        columns={'first_pay': 'First Net Pay', 'policy_pay': 'Policy Pay'}),
        color=['#60a5fa', '#f59e0b'], height=320)

    if noncomp:
        st.markdown('### \u26a0\ufe0f Non-compliant trips (First Net Pay below policy price)')
        nc = trips[trips['diff'] < 0].copy()
        nc['State'] = nc['region'].map(lambda r: REGION_NAME.get(r, r))
        ncs = nc[['State', 'driver', 'trip', 'first_pay', 'policy_price', 'diff']].rename(
            columns={'driver': 'Driver', 'trip': 'Trip', 'first_pay': 'First Net Pay',
                     'policy_price': 'Policy Price', 'diff': 'Difference'})
        st.dataframe(_style_money(ncs, ['First Net Pay', 'Policy Price', 'Difference'], []),
                     use_container_width=True, hide_index=True)

    if cmp_df is not None and len(cmp_df):
        st.markdown('### \U0001F504 Week-over-week comparison')
        st.caption('Current ({}) vs previous ({})'.format(week_label, prev_label))
        prev_rev = rsum_prev['first_pay'].sum() if rsum_prev is not None else 0
        prev_pol = rsum_prev['policy_pay'].sum() if rsum_prev is not None else 0
        prev_diff = prev_rev - prev_pol
        prev_margin = (prev_diff / prev_rev * 100) if prev_rev else 0
        cc = st.columns(4)
        with cc[0]:
            kcard('Revenue change', money(tot_rev - prev_rev),
                  'good' if (tot_rev - prev_rev) >= 0 else 'warn')
        with cc[1]:
            kcard('Price Difference change', money(tot_diff - prev_diff),
                  'good' if (tot_diff - prev_diff) >= 0 else 'warn')
        with cc[2]:
            kcard('Margin change', pct(margin - prev_margin),
                  'good' if (margin - prev_margin) >= 0 else 'warn')
        with cc[3]:
            pctchg = ((tot_diff - prev_diff) / abs(prev_diff) * 100) if prev_diff else 0
            kcard('Price Diff change (%)', pct(pctchg),
                  'good' if pctchg >= 0 else 'warn')

        cmp_disp = cmp_df.copy()
        cmp_disp['State'] = cmp_disp['region'].map(lambda r: REGION_NAME.get(r, r))
        cshow = cmp_disp[['State', 'diff', 'diff_prev', 'diff_delta', 'diff_pct',
                          'margin', 'margin_prev']].rename(columns={
            'diff': 'Diff (current)', 'diff_prev': 'Diff (previous)',
            'diff_delta': 'Change ($)', 'diff_pct': 'Change (%)',
            'margin': 'Margin now', 'margin_prev': 'Margin before'})
        st.dataframe(_style_money(
            cshow, ['Diff (current)', 'Diff (previous)', 'Change ($)'],
            ['Change (%)', 'Margin now', 'Margin before']),
            use_container_width=True, hide_index=True)
        st.markdown('#### Price difference change ($) vs previous week')
        st.bar_chart(cmp_disp.set_index('State')['diff_delta'], color='#a78bfa', height=300)

    st.markdown('### \U0001F4E5 Download reports')
    html_report = build_html_report(rsum, trips, bk, week_label)
    dc = st.columns(2)
    with dc[0]:
        st.download_button('\u2b07\ufe0f Download full report (HTML, print-ready)',
                           data=html_report.encode('utf-8'),
                           file_name='BT_consolidated_report.html', mime='text/html')
    with dc[1]:
        try:
            pdf_bytes = build_pdf_report(rsum, trips, bk, week_label, cmp_df, prev_label)
            st.download_button('\U0001F4C4 Download summary (PDF, print-ready)',
                               data=pdf_bytes,
                               file_name='BT_consolidated_summary.pdf',
                               mime='application/pdf')
        except Exception as e:
            st.caption('PDF export unavailable: %s' % e)


else:
    # Per-state page
    code = next((r for r in regions_present if REGION_NAME.get(r, r) == choice), None)
    if code is None:
        st.error('State not found.')
        st.stop()
    row = rsum[rsum['region'] == code].iloc[0]
    st.title(REGION_NAME.get(code, code))
    cities = REGION_CITIES.get(code)
    if cities:
        st.markdown(' '.join('<span class="pill">%s</span>' % html.escape(c) for c in cities),
                    unsafe_allow_html=True)
    st.caption(week_label)

    c = st.columns(4)
    with c[0]:
        kcard('First Net Pay', money(row['first_pay']))
    with c[1]:
        kcard('Policy Pay', money(row['policy_pay']))
    with c[2]:
        kcard('Price Difference', money(row['diff']), 'good' if row['diff'] >= 0 else 'warn')
    with c[3]:
        kcard('Margin', pct(row['margin']), 'good' if row['margin'] >= 0 else 'warn')
    c = st.columns(4)
    with c[0]:
        kcard('Drivers', int(row['drivers']))
    with c[1]:
        kcard('Trips', int(row['trips']))
    reg_trips = trips[trips['region'] == code]
    nc = reg_trips[reg_trips['diff'] < 0]
    with c[2]:
        kcard('Non-compliant Trips', str(len(nc)), 'warn' if len(nc) else 'good')
    with c[3]:
        avg = (row['diff'] / row['trips']) if row['trips'] else 0
        kcard('Avg diff / trip', money(avg))

    # City sub-tables for grouped regions (North / South California).
    csum = city_summary(bk, code)
    if len(csum) > 1:
        st.markdown('### \U0001F3D9\ufe0f City breakdown')
        cdisp = csum.rename(columns={'city': 'City', 'drivers': 'Drivers', 'trips': 'Trips',
                                     'first_pay': 'First Net Pay', 'policy_pay': 'Policy Pay',
                                     'diff': 'Price Difference', 'margin': 'Margin'})
        st.dataframe(_style_money(cdisp, ['First Net Pay', 'Policy Pay', 'Price Difference'], ['Margin']),
                     use_container_width=True, hide_index=True)
        st.bar_chart(csum.set_index('city')['diff'], color='#38bdf8', height=280)
        st.caption('Open each city for its driver-level detail.')
        for _, cr in csum.iterrows():
            with st.expander('{} \u2014 {} ({} drivers, {} trips)'.format(
                    cr['city'], money(cr['diff']), int(cr['drivers']), int(cr['trips']))):
                dcity = driver_summary_city(bk, code, cr['city'])
                dcshow = dcity.rename(columns={'driver': 'Driver', 'trips': 'Trips',
                                               'first_pay': 'First Net Pay', 'policy_pay': 'Policy Pay',
                                               'diff': 'Price Difference', 'margin': 'Margin'})
                st.dataframe(_style_money(dcshow, ['First Net Pay', 'Policy Pay', 'Price Difference'], ['Margin']),
                             use_container_width=True, hide_index=True)

    st.markdown('### Driver breakdown')
    ds = driver_summary(bk, code)
    dsshow = ds.rename(columns={'driver': 'Driver', 'trips': 'Trips', 'first_pay': 'First Net Pay',
                                'policy_pay': 'Policy Pay', 'diff': 'Price Difference', 'margin': 'Margin'})
    st.dataframe(_style_money(dsshow, ['First Net Pay', 'Policy Pay', 'Price Difference'], ['Margin']),
                 use_container_width=True, hide_index=True)

    if len(reg_trips):
        st.markdown('### Per-trip price difference')
        tt = reg_trips.copy().sort_values('diff')
        ttshow = tt[['driver', 'trip', 'miles', 'first_pay', 'policy_price', 'diff']].rename(
            columns={'driver': 'Driver', 'trip': 'Trip', 'miles': 'Miles',
                     'first_pay': 'First Net Pay', 'policy_price': 'Policy Price', 'diff': 'Difference'})
        st.dataframe(_style_money(ttshow, ['First Net Pay', 'Policy Price', 'Difference'], []),
                     use_container_width=True, hide_index=True)

    # Per-trip charts: only shown when there are non-compliant trips.
    if len(nc):
        st.markdown('### \u26a0\ufe0f Non-compliant trips (loss: First Net Pay below policy price)')
        ncshow = nc[['driver', 'trip', 'first_pay', 'policy_price', 'diff']].rename(
            columns={'driver': 'Driver', 'trip': 'Trip', 'first_pay': 'First Net Pay',
                     'policy_price': 'Policy Price', 'diff': 'Difference'})
        st.dataframe(_style_money(ncshow, ['First Net Pay', 'Policy Price', 'Difference'], []),
                     use_container_width=True, hide_index=True)
        chart = nc.copy()
        chart['label'] = chart['driver'].str.slice(0, 18) + ' | ' + chart['trip'].str.slice(0, 20)
        st.bar_chart(chart.set_index('label')['diff'], color='#f87171', height=300)
    else:
        st.success('All trips in this state are compliant (First Net Pay meets or exceeds the policy price).')
