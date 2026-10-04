from __future__ import annotations
import io, re, sqlite3, zipfile

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from datetime import datetime
import pandas as pd
import streamlit as st

DB_FILE = 'history.db'

STATES = {
    'OR': 'Oregon', 'N.CA': 'North California', 'S.CA': 'South California',
    'AK': 'Alaska', 'IL': 'Illinois', 'NM': 'New Mexico',
    'SAC': 'Sacramento', 'MON': 'Monterey',
    'RS&AZ': 'Riverside & Arizona', 'AZ': 'Arizona',
}

CITIES = {
    'OR': ['Portland', 'Gresham', 'Tigard', 'Salem', 'McMinnville', 'Wilsonville',
           'Roseburg', 'Molalla', 'Lincoln City', 'North Bend', 'Newberg',
           'Gladstone', 'Troutdale', 'Woodburn', 'West Linn', 'Milwaukie', 'Clackamas'],
    'N.CA': ['Benicia', 'Berkeley', 'Richmond', 'San Leandro'],
    'S.CA': ['San Diego', 'Los Angeles'],
    'AK': ['Anchorage'],
    'IL': ['Elgin', 'Carol Stream', 'Chicago'],
    'NM': ['Albuquerque'],
    'MON': ['Monterey'],
}


def clean(x):
    return re.sub(r'\s+', ' ', str(x or '').strip()).lower()


def vehicle_from(name):
    s = clean(name).upper()
    return 'Minivan' if 'MINIVAN' in s or 'M-VAN' in s else 'Sedan'


def city_from(name):
    s = clean(name).upper()
    cities = [
        'McMinnville', 'Wilsonville', 'Portland', 'Gresham', 'Tigard', 'Roseburg',
        'Molalla', 'Lincoln City', 'North Bend', 'Newberg', 'Salem', 'Gladstone',
        'Troutdale', 'Corvallis', 'Woodburn', 'Clackamas', 'West Linn', 'Milwaukie',
        'Benicia', 'Berkeley', 'Richmond', 'San Leandro', 'Sacramento', 'San Diego',
        'Los Angeles', 'Anchorage', 'Monterey', 'Elgin', 'Carol Stream', 'Chicago',
        'Albuquerque',
    ]
    for city in cities:
        if city.upper() in s:
            return city
    return 'Unknown'


def state_from(name, company=''):
    s = f'{name} {company}'.upper()
    if 'MONTEREY' in s:
        return 'MON'
    if 'CROSS BORDER' in s or 'ALASKA' in s or 'ANCHORAGE' in s:
        return 'AK'
    if any(c.upper() in s for c in ['DAMASCUS', 'CLACKAMAS', 'TROUTDALE', 'GLADSTONE',
                                    'CORVALLIS', 'WOODBURN', 'WEST LINN', 'MILWAUKIE']):
        return 'OR'
    if any(c.upper() in s for c in CITIES.get('OR', [])):
        return 'OR'
    if 'PORTLAND' in s or 'GRESHAM' in s or 'SALEM' in s or 'OREGON' in s:
        return 'OR'
    if 'BERKELEY' in s or 'RICHMOND' in s or 'SAN LEANDRO' in s or 'BENICIA' in s:
        return 'N.CA'
    if 'SAN DIEGO' in s or 'LOS ANGELES' in s:
        return 'S.CA'
    if 'SACRAMENTO' in s:
        return 'SAC'
    if ('ILLINOIS' in s or 'ELGIN' in s or 'CAROL STREAM' in s or 'SCHAUMBURG' in s
            or 'CHICAGO' in s or 'AURORA' in s or 'NAPERVILLE' in s):
        return 'IL'
    return 'Unknown'


def state_code_from_name(fname):
    s = str(fname).upper().replace('_', ' ')
    if 'ABQ' in s or 'NEW MEXICO' in s or ' NM' in s:
        return 'NM'
    if 'NORTH CA' in s or 'N.CA' in s or 'NORTHCA' in s:
        return 'N.CA'
    if 'OREGON' in s or ' OR ' in s:
        return 'OR'
    if 'ALASKA' in s or ' AK' in s or s.startswith('AK'):
        return 'AK'
    if 'RS' in s and 'AZ' in s:
        return 'RS&AZ'
    if 'ARIZONA' in s or ' AZ' in s:
        return 'AZ'
    if 'SACRAMENTO' in s or 'SAC' in s:
        return 'SAC'
    if 'MONTEREY' in s or 'MON' in s:
        return 'MON'
    if ' IL' in s or 'ILLINOIS' in s or s.startswith('IL ') or s.startswith('IL-') or s == 'IL':
        return 'IL'
    return 'Unknown'

POLICIES = [
    {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33.0, 'Per_Mile_Rate': 0, 'Note': 'Oregon schedule 1-6 miles'},
    {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 10, 'Policy_Pay': 36.0, 'Per_Mile_Rate': 0, 'Note': 'Oregon schedule 7-10 miles'},
    {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 10.01, 'Max_Miles': 14, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 0, 'Note': 'Oregon schedule 11-14 miles'},
    {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 9999, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 1.25, 'Note': 'Oregon schedule +$1.25 per mile above 14'},
    {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 0, 'Note': '1-6 miles'},
    {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 16, 'Policy_Pay': 42.0, 'Per_Mile_Rate': 0, 'Note': '7-16 miles'},
    {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 0, 'Note': '1-4 miles'},
    {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40.0, 'Per_Mile_Rate': 0, 'Note': '5-8 miles'},
    {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 43.0, 'Per_Mile_Rate': 0, 'Note': '9-16 miles'},
    {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 35.0, 'Per_Mile_Rate': 0, 'Note': 'Sedan 1-8'},
    {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 37.0, 'Per_Mile_Rate': 0, 'Note': 'Sedan 9-16'},
    {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 40.0, 'Per_Mile_Rate': 0, 'Note': 'Minivan 1-8'},
    {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 42.0, 'Per_Mile_Rate': 0, 'Note': 'Minivan 9-16'},
    {'State': 'MON', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 0, 'Note': 'Sedan 1-6'},
    {'State': 'MON', 'Vehicle_Type': 'Sedan', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42.0, 'Per_Mile_Rate': 0, 'Note': 'Sedan 7-14'},
    {'State': 'MON', 'Vehicle_Type': 'Sedan', 'Min_Miles': 14.01, 'Max_Miles': 9999, 'Policy_Pay': 42.0, 'Per_Mile_Rate': 0.80, 'Note': 'Sedan 42 + $0.80 per mile above 14'},
    {'State': 'MON', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 43.0, 'Per_Mile_Rate': 0, 'Note': 'Minivan 1-6'},
    {'State': 'MON', 'Vehicle_Type': 'Minivan', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 48.0, 'Per_Mile_Rate': 0, 'Note': 'Minivan 7-14'},
    {'State': 'MON', 'Vehicle_Type': 'Minivan', 'Min_Miles': 14.01, 'Max_Miles': 9999, 'Policy_Pay': 48.0, 'Per_Mile_Rate': 0.80, 'Note': 'Minivan 48 + $0.80 per mile above 14'},
    {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'AZ', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'RS&AZ', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'SAC', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'See Sacramento sedan/minivan schedule'},
]
POLICY_DF = pd.DataFrame(POLICIES)

CITY_POLICIES = {
    'Benicia': [{'min': 0, 'max': 9999, 'base': 38.0, 'per_mile': 0.0, 'note': 'Benicia: $38 all trips'}],
    'Berkeley': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Berkeley: 1-6 miles'},
        {'min': 6.01, 'max': 16, 'base': 42.0, 'per_mile': 0.0, 'note': 'Berkeley: 7-16 miles'},
    ],
    'Richmond': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Richmond: 1-6 miles'},
        {'min': 6.01, 'max': 11, 'base': 42.0, 'per_mile': 0.0, 'note': 'Richmond: 7-11 miles'},
    ],
    'San Leandro': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'San Leandro: 1-6 miles'},
        {'min': 6.01, 'max': 16, 'base': 43.0, 'per_mile': 0.0, 'note': 'San Leandro: 7-16 miles'},
        {'min': 16.01, 'max': 9999, 'base': 43.0, 'per_mile': 1.30, 'note': 'San Leandro: $43 + $1.30 per mile above 16'},
    ],
    'Elgin': [{'min': 0, 'max': 9999, 'base': 75.0, 'per_mile': 0.0, 'note': 'Elgin: driver pay $75'}],
    'Carol Stream': [{'min': 0, 'max': 9999, 'base': 85.0, 'per_mile': 0.0, 'note': 'Carol Stream: driver pay $85'}],
}

SACRAMENTO_POLICIES = {
    'Sedan': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 1-6 miles'},
        {'min': 6.01, 'max': 14, 'base': 42.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 7-14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 42.0, 'per_mile': 0.80, 'note': 'Sacramento Sedan: $42 + $0.80 per mile above 14'},
    ],
    'Minivan': [
        {'min': 0, 'max': 6, 'base': 43.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 1-6 miles'},
        {'min': 6.01, 'max': 14, 'base': 48.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 7-14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 48.0, 'per_mile': 0.80, 'note': 'Sacramento Minivan: $48 + $0.80 per mile above 14'},
    ],
}


def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS weekly_summary
            (id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_date TEXT, state TEXT,
             week_start_date TEXT, week_end_date TEXT, total_trips INTEGER,
             total_revenue REAL, total_driver_cost REAL, total_margin REAL, total_loss REAL)''')


init_db()

def policy_pay(state, miles, vehicle='Unknown', city='Unknown'):
    """Return the contracted driver pay using city/vehicle rules first, then state rules."""
    miles = float(miles or 0)
    vehicle = str(vehicle or 'Unknown').title()
    city = str(city or 'Unknown').strip()
    city_rules = CITY_POLICIES.get(city, [])
    if state == 'SAC':
        city_rules = SACRAMENTO_POLICIES.get(vehicle, [])
    for rule in city_rules:
        if rule['min'] <= miles <= rule['max']:
            amount = rule['base']
            if rule['per_mile']:
                amount += max(0.0, miles - rule['min'] + 0.01) * rule['per_mile']
            return round(amount, 2), f"Matched - {rule['note']}"
    rules = POLICY_DF[(POLICY_DF.State == state) &
                      (POLICY_DF.Min_Miles <= miles) & (POLICY_DF.Max_Miles >= miles)]
    if state in ('AK', 'MON') and vehicle in ('Sedan', 'Minivan'):
        exact = rules[rules.Vehicle_Type == vehicle]
        if not exact.empty:
            rules = exact
    if rules.empty:
        return 0.0, 'No policy'
    rule = rules.iloc[0]
    if 'Not supplied' in str(rule.Note):
        return 0.0, 'No policy supplied'
    if state == 'AK' and miles > 16:
        return 0.0, 'Alaska >16-mile rule needed'
    if float(rule.Per_Mile_Rate) > 0:
        return round(float(rule.Policy_Pay) + (miles - 16) * float(rule.Per_Mile_Rate), 2), 'Matched - state policy'
    return float(rule.Policy_Pay), 'Matched - state policy'


def finish(df):
    if df.empty:
        return df
    # Drop totals / summary rows (no driver and no trip name) often appended at the
    # bottom of First reports; otherwise their grand-total revenue is double counted.
    if 'Driver_Name' in df.columns and 'Trip_Name' in df.columns:
        drv = df['Driver_Name'].map(lambda v: clean(v).lower() not in ('', 'nan', 'unknown', 'total', 'totals', 'grand total'))
        trp = df['Trip_Name'].map(lambda v: clean(v).lower() not in ('', 'nan'))
        df = df[drv | trp].copy()
    if df.empty:
        return df
    for column in ['Miles', 'Gross_Pay', 'Net_Pay']:
        df[column] = pd.to_numeric(df.get(column, 0), errors='coerce').fillna(0.0)
    calculated = df.apply(lambda row: policy_pay(row.State, row.Miles, row.Vehicle, row.City), axis=1)
    df['Policy_Driver_Pay'] = calculated.map(lambda result: result[0])
    df['Policy_Status'] = calculated.map(lambda result: result[1])
    # First NET PAY (new files: 'Revenue' column) = Beyond revenue from First.
    df['Revenue'] = df['Net_Pay']
    df['Difference_vs_Contract'] = df['Revenue'] - df['Policy_Driver_Pay']
    df['Loss_Amount'] = df['Difference_vs_Contract'].clip(lower=0)
    df['Is_Non_Compliant'] = (df['Policy_Status'].str.startswith('Matched')) & (df['Difference_vs_Contract'] > 0.05)
    df['Margin'] = df['Revenue'] - df['Policy_Driver_Pay']
    return df


def _pick(x, up, names, default=0):
    for n in names:
        if n in up:
            return x[up[n]]
    return pd.Series([default] * len(x), index=x.index)


def read_first(file):
    book = pd.ExcelFile(file, engine='openpyxl')
    sheet = 'SP ITEMIZED REPORT' if 'SP ITEMIZED REPORT' in book.sheet_names else book.sheet_names[0]
    x = pd.read_excel(file, sheet_name=sheet, engine='openpyxl')
    x.columns = [str(c).strip() for c in x.columns]
    up = {c.upper(): c for c in x.columns}
    d = pd.DataFrame(index=x.index)
    d['Source'] = 'First'
    d['Source Company'] = _pick(x, up, ['SP COMPANY', 'COMPANY'], '')
    d['Driver_Name'] = _pick(x, up, ['DRIVER NAME', 'DRIVER'], 'Unknown')
    d['Trip_Date'] = pd.to_datetime(_pick(x, up, ['DATE', 'TRIP DATE'], None), errors='coerce')
    d['Trip_ID'] = _pick(x, up, ['TRIP CODE', 'TRIP ID'], '')
    d['Trip_Name'] = _pick(x, up, ['TRIP NAME', 'NAME'], '')
    d['Miles'] = _pick(x, up, ['TOTAL MILES', 'MILES'], 0)
    d['Gross_Pay'] = _pick(x, up, ['GROSS PAY', 'GROSS'], 0)
    d['Net_Pay'] = _pick(x, up, ['NET PAY', 'REVENUE', 'NET'], 0)
    d['Vehicle'] = d.Trip_Name.map(vehicle_from)
    d['State'] = d.apply(lambda r: state_from(r.Trip_Name, r['Source Company']), axis=1)
    d['City'] = d.Trip_Name.map(city_from)
    return finish(d)


def read_csv(file):
    x = pd.read_csv(file)
    x.columns = [str(c).strip() for c in x.columns]
    up = {c.upper(): c for c in x.columns}
    d = pd.DataFrame(index=x.index)
    d['Source'] = 'First'
    d['Source Company'] = _pick(x, up, ['SP COMPANY', 'COMPANY'], '')
    d['Driver_Name'] = _pick(x, up, ['DRIVER NAME', 'DRIVER'], 'Unknown')
    d['Trip_Date'] = pd.to_datetime(_pick(x, up, ['DATE', 'TRIP DATE'], None), errors='coerce')
    d['Trip_ID'] = _pick(x, up, ['TRIP CODE', 'TRIP ID'], '')
    d['Trip_Name'] = _pick(x, up, ['TRIP NAME', 'NAME'], '')
    d['Miles'] = _pick(x, up, ['TOTAL MILES', 'MILES'], 0)
    d['Gross_Pay'] = _pick(x, up, ['GROSS PAY', 'GROSS'], 0)
    d['Net_Pay'] = _pick(x, up, ['NET PAY', 'REVENUE', 'NET'], 0)
    d['Vehicle'] = d.Trip_Name.map(vehicle_from)
    d['State'] = d.apply(lambda r: state_from(r.Trip_Name, r['Source Company']), axis=1)
    d['City'] = d.Trip_Name.map(city_from)
    return finish(d)


def read_any(file, source='First'):
    name = str(getattr(file, 'name', '')).lower()
    if name.endswith('.csv'):
        return read_csv(file)
    return read_first(file)


def build_roster(weekly_files):
    """Learn which driver belongs to which state from weekly state reports."""
    roster = {}
    for f in weekly_files:
        code = state_code_from_name(getattr(f, 'name', ''))
        try:
            df = pd.read_excel(f)
        except Exception:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        up = {c.upper(): c for c in df.columns}
        dcol = up.get('DRIVER NAME') or up.get('DRIVER')
        if not dcol:
            continue
        for v in df[dcol].dropna():
            key = clean(v)
            if key and key != 'nan':
                roster[key] = code
    return roster


def apply_roster(df, roster):
    if roster and not df.empty:
        mapped = df['Driver_Name'].map(lambda n: roster.get(clean(n)))
        df['State'] = mapped.where(mapped.notna(), df['State'])
    return df


def originals_zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, payload in files:
            z.writestr(name, payload)
    return out.getvalue()


def save_history(state, df):
    if df.empty:
        return
    with sqlite3.connect(DB_FILE) as c:
        c.execute('INSERT INTO weekly_summary VALUES(NULL,?,?,?,?,?,?,?,?,?)',
                  (datetime.now().strftime('%Y-%m-%d'), state,
                   str(df.Trip_Date.min().date()) if df.Trip_Date.notna().any() else '',
                   str(df.Trip_Date.max().date()) if df.Trip_Date.notna().any() else '',
                   len(df), float(df.Revenue.sum()), float(df.Policy_Driver_Pay.sum()),
                   float(df.Margin.sum()), float(df.Loss_Amount.sum())))


def pdf_report(view, code, name):
    if not REPORTLAB_AVAILABLE:
        return None
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(letter), rightMargin=0.35 * inch,
                            leftMargin=0.35 * inch, topMargin=0.35 * inch, bottomMargin=0.35 * inch)
    styles = getSampleStyleSheet()
    story = [Paragraph(f'{name} - Beyond Transportation Report', styles['Title']), Spacer(1, 8)]
    summary = [['Trips', 'Revenue (First)', 'Driver Pay (policy)', 'Margin'],
               [str(len(view)), f"${view.Revenue.sum():,.2f}",
                f"${view.Policy_Driver_Pay.sum():,.2f}", f"${view.Margin.sum():,.2f}"]]
    t = Table(summary, colWidths=[1.4 * inch] * 4)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e78')),
                           ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                           ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story += [t, Spacer(1, 10)]
    cols = ['Trip_Date', 'Trip_ID', 'City', 'Driver_Name', 'Miles', 'Revenue',
            'Policy_Driver_Pay', 'Margin', 'Policy_Status']
    data = [cols]
    for _, r in view[cols].fillna('').iterrows():
        data.append([str(r[c])[:40] for c in cols])
    detail = Table(data, repeatRows=1)
    detail.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e78')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                                ('FONTSIZE', (0, 0), (-1, -1), 6),
                                ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(detail)
    doc.build(story)
    return out.getvalue()

def show_metrics_and_tables(view, code, name, key_prefix):
    if view.empty:
        st.warning(f'No {name} trips were detected in the uploaded reports.')
        return
    total_revenue = float(view.Revenue.sum())
    total_driver = float(view.Policy_Driver_Pay.sum())
    total_margin = total_revenue - total_driver
    total = len(view)
    non_compliant = int(view.Is_Non_Compliant.sum())
    matched = int(view.Policy_Status.str.startswith('Matched').sum())
    compliant = matched - non_compliant
    no_policy = int((~view.Policy_Status.str.startswith('Matched')).sum())

    a, b, c, d, e = st.columns(5)
    a.metric('Trips', total)
    b.metric('Revenue (First)', f'${total_revenue:,.2f}')
    c.metric('Driver Pay (policy)', f'${total_driver:,.2f}')
    d.metric('Margin', f'${total_margin:,.2f}')
    e.metric('Margin %', f'{total_margin/total_revenue:.1%}' if total_revenue else '0.0%')

    st.subheader('Policy compliance summary')
    st.dataframe(pd.DataFrame({
        'Metric': ['Trips paid within policy', 'Trips above policy (overpaid)',
                   'Trips without a supplied policy'],
        'Count': [compliant, non_compliant, no_policy],
        'Percentage': [f'{compliant/total:.1%}' if total else '0.0%',
                       f'{non_compliant/total:.1%}' if total else '0.0%',
                       f'{no_policy/total:.1%}' if total else '0.0%'],
    }), use_container_width=True, hide_index=True)
    if non_compliant:
        over_rev = float(view[view.Is_Non_Compliant].Revenue.sum())
        over_loss = float(view[view.Is_Non_Compliant].Loss_Amount.sum())
        st.warning(f'{non_compliant} trip(s) exceeded the pricing policy '
                   f'({non_compliant/total:.1%} of trips, {over_rev/total_revenue:.1%} of revenue). '
                   f'Extra amount above policy: ${over_loss:,.2f}. '
                   f'If the policy had been applied, margin would be ${total_margin + over_loss:,.2f}.')

    st.subheader('By City')
    st.dataframe(view.groupby(['City']).agg(
        Trips=('Trip_ID', 'count'), Miles=('Miles', 'sum'), Revenue=('Revenue', 'sum'),
        Driver_Pay=('Policy_Driver_Pay', 'sum'), Margin=('Margin', 'sum')).reset_index(),
        use_container_width=True)
    st.subheader('By Driver')
    st.dataframe(view.groupby(['Driver_Name']).agg(
        Trips=('Trip_ID', 'count'), Miles=('Miles', 'sum'), Revenue=('Revenue', 'sum'),
        Driver_Pay=('Policy_Driver_Pay', 'sum'), Margin=('Margin', 'sum')).reset_index(),
        use_container_width=True)
    st.subheader('Per-trip detail: revenue vs policy driver pay')
    st.dataframe(view[['Trip_Date', 'Trip_ID', 'Trip_Name', 'City', 'Driver_Name', 'Miles',
                       'Revenue', 'Policy_Driver_Pay', 'Margin', 'Difference_vs_Contract',
                       'Policy_Status']], use_container_width=True)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        view.to_excel(w, sheet_name='Trips', index=False)
        POLICY_DF[POLICY_DF.State == code].to_excel(w, sheet_name='Policy', index=False)
    st.download_button('Download report - Excel', out.getvalue(),
                       f'{key_prefix}_{code}_report.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key=f'dl_xlsx_{key_prefix}_{code}')
    st.download_button('Download report - CSV', view.to_csv(index=False).encode('utf-8-sig'),
                       f'{key_prefix}_{code}_report.csv', 'text/csv',
                       key=f'dl_csv_{key_prefix}_{code}')
    pdf_bytes = pdf_report(view, code, name)
    if pdf_bytes:
        st.download_button('Download report - PDF', pdf_bytes,
                           f'{key_prefix}_{code}_report.pdf', 'application/pdf',
                           key=f'dl_pdf_{key_prefix}_{code}')


def first_page():
    st.title('First Reports')
    st.caption('Upload First detailed reports here. Per-state reports are then generated '
               'automatically on the "State Reports" page.')
    files = st.file_uploader('First reports (Excel / CSV)', type=['xlsx', 'xls', 'csv'],
                             accept_multiple_files=True, key='first_upload')
    if files:
        try:
            df = pd.concat([read_any(f, 'First') for f in files], ignore_index=True)
            st.session_state['First_df'] = df
            st.session_state['First_files'] = [(f.name, f.getvalue()) for f in files]
            st.success(f'Loaded {len(df):,} trips from {len(files)} file(s).')
        except Exception as e:
            st.error(f'Could not read the First files: {e}')

    st.subheader('Driver roster (optional)')
    st.caption('Upload the weekly state reports once so the app learns which driver belongs '
               'to which state. After that it splits every First report by state on its own.')
    rfiles = st.file_uploader('Weekly state reports (optional - used only to map drivers to states)',
                              type=['xlsx', 'xls'], accept_multiple_files=True, key='roster_upload')
    if rfiles:
        roster = build_roster(rfiles)
        st.session_state['roster'] = roster
        st.success(f'Roster built: {len(roster)} drivers mapped to states.')

    df = st.session_state.get('First_df', pd.DataFrame())
    if not df.empty:
        d2 = apply_roster(df.copy(), st.session_state.get('roster', {}))
        st.subheader('Detected trips by state')
        st.dataframe(d2.groupby('State').agg(
            Trips=('Trip_ID', 'count'), Revenue=('Revenue', 'sum'),
            Driver_Pay=('Policy_Driver_Pay', 'sum'), Margin=('Margin', 'sum')).reset_index(),
            use_container_width=True)
        orig = st.session_state.get('First_files', [])
        if orig:
            st.download_button('Download original First files - ZIP', originals_zip(orig),
                               'first_original_files.zip', 'application/zip', key='zip_first')


def state_page(code, name):
    st.title(f'{name} - Analysis Dashboard')
    st.subheader('Official Pricing Policy')
    st.table(POLICY_DF[POLICY_DF.State == code][
        ['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Per_Mile_Rate', 'Note']])

    first_df = st.session_state.get('First_df', pd.DataFrame())
    if first_df.empty:
        st.info('Upload a First report on the "First Reports" page first. '
                'The state report is generated automatically from it.')
        return
    first_df = apply_roster(first_df.copy(), st.session_state.get('roster', {}))
    view = first_df[first_df.State == code]
    if view.empty:
        st.warning(f'No {name} trips were attributed in the First report. '
                   'If the drivers were not recognised, upload the weekly state reports as a '
                   'roster on the "First Reports" page so the app can map drivers to this state.')
        return
    st.header(f'{name} - State report (generated from the First report)')
    show_metrics_and_tables(view, code, name, f'state_{code}')
    try:
        save_history(code, view)
    except Exception:
        pass


def consolidated_summary(df):
    """Per-state financial roll-up used by the consolidated report."""
    rows = []
    for code, g in df.groupby('State'):
        total_rev = float(g.Revenue.sum())
        driver = float(g.Policy_Driver_Pay.sum())
        margin = total_rev - driver
        nc = int(g.Is_Non_Compliant.sum())
        over = float(g[g.Is_Non_Compliant].Loss_Amount.sum())
        rows.append({
            'State': code,
            'State_Name': STATES.get(code, code),
            'Trips': int(len(g)),
            'Miles': float(g.Miles.sum()),
            'Revenue': total_rev,
            'Driver_Pay': driver,
            'Margin': margin,
            'Margin_%': (margin / total_rev * 100) if total_rev else 0.0,
            'Violations': nc,
            'Over_Policy_Amount': over,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values('Revenue', ascending=False).reset_index(drop=True)
    return out


def consolidated_page():
    st.title('Consolidated Financial Report - All States')
    first_df = st.session_state.get('First_df', pd.DataFrame())
    if first_df.empty:
        st.info('Upload a First report on the "First Reports" page first. '
                'The consolidated report is generated automatically from it.')
        return
    df = apply_roster(first_df.copy(), st.session_state.get('roster', {}))
    summary = consolidated_summary(df)
    if summary.empty:
        st.warning('No trips were attributed to any state yet.')
        return

    tot_rev = float(summary.Revenue.sum())
    tot_driver = float(summary.Driver_Pay.sum())
    tot_margin = tot_rev - tot_driver
    tot_trips = int(summary.Trips.sum())
    tot_viol = int(summary.Violations.sum())
    tot_over = float(summary.Over_Policy_Amount.sum())

    a, b, c, d, e = st.columns(5)
    a.metric('States', int(summary.State.nunique()))
    b.metric('Trips', f'{tot_trips:,}')
    c.metric('Revenue (First)', f'${tot_rev:,.2f}')
    d.metric('Driver Pay (policy)', f'${tot_driver:,.2f}')
    e.metric('Margin', f'${tot_margin:,.2f}')

    # ---- 1) Consolidated financial report (all states) ----
    st.subheader('Financial summary by state')
    disp = summary.copy()
    disp['Margin_%'] = disp['Margin_%'].round(1)
    grand = pd.DataFrame([{
        'State': 'ALL', 'State_Name': 'Grand total', 'Trips': tot_trips,
        'Miles': float(summary.Miles.sum()), 'Revenue': tot_rev, 'Driver_Pay': tot_driver,
        'Margin': tot_margin, 'Margin_%': round(tot_margin / tot_rev * 100, 1) if tot_rev else 0.0,
        'Violations': tot_viol, 'Over_Policy_Amount': tot_over,
    }])
    st.dataframe(pd.concat([disp, grand], ignore_index=True), use_container_width=True,
                 hide_index=True)

    # ---- 2) Actual vs Target profit ----
    st.subheader('Actual vs Target profit')
    st.caption('Enter your own target margin % for each state (no targets are assumed). '
               'The target amount and the variance are calculated from the revenue you uploaded.')
    prev = st.session_state.get('targets', {})
    target_input = pd.DataFrame({
        'State': summary.State,
        'State_Name': summary.State_Name,
        'Target_Margin_%': [float(prev.get(s, 0.0)) for s in summary.State],
    })
    edited = st.data_editor(
        target_input, hide_index=True, use_container_width=True, num_rows='fixed',
        disabled=['State', 'State_Name'], key='target_editor',
        column_config={'Target_Margin_%': st.column_config.NumberColumn(
            'Target Margin %', min_value=0.0, max_value=100.0, step=1.0, format='%.1f')})
    st.session_state['targets'] = dict(zip(edited.State, edited['Target_Margin_%']))

    comp = summary[['State', 'State_Name', 'Revenue', 'Margin', 'Margin_%']].copy()
    comp = comp.merge(edited[['State', 'Target_Margin_%']], on='State', how='left')
    comp['Target_Margin_$'] = comp['Revenue'] * comp['Target_Margin_%'] / 100.0
    comp['Actual_Margin_$'] = comp['Margin']
    comp['Variance_$'] = comp['Actual_Margin_$'] - comp['Target_Margin_$']
    comp['Achievement_%'] = comp.apply(
        lambda r: round(r['Actual_Margin_$'] / r['Target_Margin_$'] * 100, 1)
        if r['Target_Margin_$'] else 0.0, axis=1)
    comp['Actual_Margin_%'] = comp['Margin_%'].round(1)
    comp_view = comp[['State', 'State_Name', 'Revenue', 'Target_Margin_%', 'Actual_Margin_%',
                      'Target_Margin_$', 'Actual_Margin_$', 'Variance_$', 'Achievement_%']]
    st.dataframe(comp_view, use_container_width=True, hide_index=True)
    tgt_total = float(comp['Target_Margin_$'].sum())
    if tgt_total:
        var_total = tot_margin - tgt_total
        st.info(f'Total target margin: ${tgt_total:,.2f} | actual: ${tot_margin:,.2f} | '
                f'variance: ${var_total:,.2f} '
                f'({"above" if var_total >= 0 else "below"} target).')

    # ---- 3) Financial violations summary per state ----
    st.subheader('Financial violations summary (per state)')
    viol_trips = df[df.Is_Non_Compliant].copy()
    viol_summary = (summary[summary.Violations > 0]
                    [['State', 'State_Name', 'Trips', 'Violations', 'Revenue',
                      'Over_Policy_Amount']].copy())
    if viol_summary.empty:
        st.success('No trips exceeded the supplied pricing policy. '
                   '(States marked "Not supplied" are not checked for violations.)')
    else:
        viol_summary['Violation_Rate_%'] = (
            viol_summary['Violations'] / viol_summary['Trips'] * 100).round(1)
        st.dataframe(viol_summary, use_container_width=True, hide_index=True)

    cols = ['Trip_Date', 'Trip_ID', 'Trip_Name', 'State', 'City', 'Driver_Name', 'Miles',
            'Revenue', 'Policy_Driver_Pay', 'Margin', 'Loss_Amount', 'Policy_Status']
    cols = [c for c in cols if c in viol_trips.columns]

    # Consolidated report export (summary + targets)
    out1 = io.BytesIO()
    with pd.ExcelWriter(out1, engine='openpyxl') as w:
        pd.concat([disp, grand], ignore_index=True).to_excel(w, sheet_name='Summary', index=False)
        comp_view.to_excel(w, sheet_name='Actual_vs_Target', index=False)
    st.download_button('Download consolidated report - Excel', out1.getvalue(),
                       'consolidated_all_states.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key='dl_consolidated_xlsx')
    st.download_button('Download consolidated summary - CSV',
                       pd.concat([disp, grand], ignore_index=True).to_csv(index=False).encode('utf-8-sig'),
                       'consolidated_all_states.csv', 'text/csv', key='dl_consolidated_csv')

    # Violations export (per-state summary + every flagged trip)
    out2 = io.BytesIO()
    with pd.ExcelWriter(out2, engine='openpyxl') as w:
        (viol_summary if not viol_summary.empty else
         pd.DataFrame(columns=['State', 'State_Name', 'Trips', 'Violations', 'Revenue',
                               'Over_Policy_Amount', 'Violation_Rate_%'])
         ).to_excel(w, sheet_name='Violations_by_State', index=False)
        (viol_trips[cols] if cols and not viol_trips.empty else
         pd.DataFrame(columns=cols)).to_excel(w, sheet_name='Violation_Trips', index=False)
    st.download_button('Export financial violations summary - Excel', out2.getvalue(),
                       'violations_summary_all_states.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key='dl_viol_xlsx')
    if cols and not viol_trips.empty:
        st.download_button('Export violation trips - CSV',
                           viol_trips[cols].to_csv(index=False).encode('utf-8-sig'),
                           'violation_trips_all_states.csv', 'text/csv', key='dl_viol_csv')


st.set_page_config(page_title="Hatem's B.T. Analyzer", layout='wide')
st.sidebar.title('Navigation')
menu = st.sidebar.radio('Choose section',
                        ['Consolidated Report', 'State Reports', 'First Reports'])
if menu == 'First Reports':
    first_page()
elif menu == 'Consolidated Report':
    consolidated_page()
else:
    selected = st.sidebar.selectbox('Choose state', list(STATES), format_func=lambda x: STATES[x])
    state_page(selected, STATES[selected])
