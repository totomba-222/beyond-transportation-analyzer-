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
    'AK': 'Alaska', 'IL': 'Illinois', 'NM': 'New Mexico', 'NE': 'Nebraska',
    'KS': 'Kansas', 'SAC': 'Sacramento', 'MON': 'Monterey', 'CAN': 'Canada',
    'AZ': 'Arizona',
}
CITIES = {
    'OR': ['Portland','Gresham','Tigard','Salem','McMinnville','Wilsonville','Roseburg','Molalla','Lincoln City','North Bend','Newberg','Gladstone','Troutdale','Woodburn','West Linn','Milwaukie','Clackamas'],
    'N.CA': ['Benicia','Berkeley','Richmond','San Leandro'],
    'S.CA': ['San Diego','Los Angeles','Richmond','Riverside','Moreno Valley','Corona','Perris','Hemet','Jurupa Valley','Eastvale','Menifee'],
    'AK': ['Anchorage'], 'NE': ['Lincoln'], 'KS': [], 'IL': ['Elgin','Carol Stream','Chicago'], 'NM': [], 'MON': ['Monterey'], 'CAN': [],
    'AZ': ['Phoenix','Tucson','Mesa','Chandler','Scottsdale','Glendale','Tempe','Gilbert','Peoria','Surprise']
}

# Keywords that positively identify New Mexico (Albuquerque) trips, since the
# company is legally registered as "... IL INC." even though it operates in NM.
NM_KEYS = ['MAYA ANGELOU','GOVERNOR BENT','MANZANO','MONTE VISTA','ALBUQUERQUE','NEW MEXICO']
# Arizona (Phoenix area) schools/keywords. The Arizona trips are mixed into the
# same First file as New Mexico, so we identify them by school name.
AZ_KEYS = ['LONGVIEW','MADISON MEADOWS','ARIZONA','PHOENIX','TUCSON','MESA ','CHANDLER','SCOTTSDALE','GILBERT','TEMPE','GLENDALE','PEORIA','SURPRISE']

POLICIES = [
 # Oregon rates from the supplied Oregon pricing note/image.
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':33.0,'Per_Mile_Rate':0,'Note':'Oregon schedule: 1-6 miles'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':10,'Policy_Pay':36.0,'Per_Mile_Rate':0,'Note':'Oregon schedule: 7-10 miles'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':10.01,'Max_Miles':14,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'Oregon schedule: 11-14 miles'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':38.0,'Per_Mile_Rate':1.25,'Note':'Oregon schedule: +$1.25/mile above 14'},

 {'State':'N.CA','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'1-6 miles'},
 {'State':'N.CA','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':16,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'7-16 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':4,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'1-4 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':4.01,'Max_Miles':8,'Policy_Pay':40.0,'Per_Mile_Rate':0,'Note':'5-8 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':43.0,'Per_Mile_Rate':0,'Note':'9-16 miles'},
 {'State':'AK','Vehicle_Type':'Sedan','Min_Miles':0,'Max_Miles':8,'Policy_Pay':35.0,'Per_Mile_Rate':0,'Note':'Sedan 1-8'},
 {'State':'AK','Vehicle_Type':'Sedan','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':37.0,'Per_Mile_Rate':0,'Note':'Sedan 9-16'},
 {'State':'AK','Vehicle_Type':'Minivan','Min_Miles':0,'Max_Miles':8,'Policy_Pay':40.0,'Per_Mile_Rate':0,'Note':'Minivan 1-8'},
 {'State':'AK','Vehicle_Type':'Minivan','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'Minivan 9-16'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':0,'Max_Miles':6,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'Sedan 1-6'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':6.01,'Max_Miles':14,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'Sedan 7-14'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':42.0,'Per_Mile_Rate':0.80,'Note':'Sedan 42 + $0.80/mile above 14'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':0,'Max_Miles':6,'Policy_Pay':43.0,'Per_Mile_Rate':0,'Note':'Minivan 1-6'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':6.01,'Max_Miles':14,'Policy_Pay':48.0,'Per_Mile_Rate':0,'Note':'Minivan 7-14'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':48.0,'Per_Mile_Rate':0.80,'Note':'Minivan 48 + $0.80/mile above 14'},
 {'State':'NE','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':16,'Policy_Pay':30.0,'Per_Mile_Rate':0,'Note':'$30 through 16 miles'},
 {'State':'NE','Vehicle_Type':'ANY','Min_Miles':16.01,'Max_Miles':9999,'Policy_Pay':30.0,'Per_Mile_Rate':1.50,'Note':'$30 + $1.50/mile above 16'},
 # New Mexico now populated from the supplied NM schedule (driver-pay side).
 {'State':'NM','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':33.0,'Per_Mile_Rate':0,'Note':'NM driver pay 1-6 (First revenue $48)'},
 {'State':'NM','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':14,'Policy_Pay':37.0,'Per_Mile_Rate':0,'Note':'NM driver pay 7-14 (First revenue $48)'},
 {'State':'NM','Vehicle_Type':'ANY','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':37.0,'Per_Mile_Rate':1.50,'Note':'NM driver pay 37 + $1.50/mile above 14 (First revenue +$2.25)'},
 {'State':'IL','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':9999,'Policy_Pay':0.0,'Per_Mile_Rate':0,'Note':'Not supplied'},
 # Arizona driver pay derived from the weekly summary cross-checked with the
 # First report: 2-mile trips = $40, 10-mile trips = $45 (First revenue $50/trip).
 {'State':'AZ','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':40.0,'Per_Mile_Rate':0,'Note':'AZ driver pay 1-6 (derived: 2mi=$40)'},
 {'State':'AZ','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':9999,'Policy_Pay':45.0,'Per_Mile_Rate':0,'Note':'AZ driver pay 7+ (derived: 10mi=$45)'},
 {'State':'CAN','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':9999,'Policy_Pay':0.0,'Per_Mile_Rate':0,'Note':'Not supplied'},
]
POLICY_DF = pd.DataFrame(POLICIES)

# City-level contract rates override the state-level fallback when supplied.
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
        {'min': 16.01, 'max': 9999, 'base': 43.0, 'per_mile': 1.30, 'note': 'San Leandro: $43 + $1.30/mile above 16'},
    ],
    'Lincoln': [
        {'min': 0, 'max': 16, 'base': 30.0, 'per_mile': 0.0, 'note': 'Lincoln: $30 through 16 miles'},
        {'min': 16.01, 'max': 9999, 'base': 30.0, 'per_mile': 1.50, 'note': 'Lincoln: $30 + $1.50/mile above 16'},
    ],
    'Elgin': [{'min': 0, 'max': 9999, 'base': 75.0, 'per_mile': 0.0, 'note': 'Elgin: driver pay $75'}],
    'Carol Stream': [{'min': 0, 'max': 9999, 'base': 85.0, 'per_mile': 0.0, 'note': 'Carol Stream: driver pay $85'}],
}

SACRAMENTO_POLICIES = {
    'Sedan': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 1-6 miles'},
        {'min': 6.01, 'max': 14, 'base': 42.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 7-14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 42.0, 'per_mile': 0.80, 'over': 14, 'note': 'Sacramento Sedan: $42 + $0.80/mile above 14'},
    ],
    'Minivan': [
        {'min': 0, 'max': 6, 'base': 43.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 1-6 miles'},
        {'min': 6.01, 'max': 14, 'base': 48.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 7-14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 48.0, 'per_mile': 0.80, 'over': 14, 'note': 'Sacramento Minivan: $48 + $0.80/mile above 14'},
    ],
}
def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS weekly_summary (id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_date TEXT, state TEXT, week_start_date TEXT, week_end_date TEXT, total_trips INTEGER, total_revenue REAL, total_driver_cost REAL, total_margin REAL, total_loss REAL)''')
init_db()

def clean(x): return re.sub(r'\s+', ' ', str(x or '').strip()).lower()

def vehicle_from(name):
    s = clean(name).upper()
    return 'Minivan' if 'MINIVAN' in s or 'M-VAN' in s else 'Sedan'

def city_from(name):
    s = clean(name).upper()
    if 'LINC ' in s or 'LINCOLN' in s or 'BRYAN' in s:
        return 'Lincoln'
    cities = [
        'McMinnville', 'Wilsonville', 'Portland', 'Gresham', 'Tigard',
        'Roseburg', 'Molalla', 'Lincoln City', 'North Bend', 'Newberg',
        'Salem', 'Gladstone', 'Troutdale', 'Corvallis', 'Woodburn',
        'Clackamas', 'West Linn', 'Milwaukie', 'Benicia', 'Berkeley',
        'Richmond', 'San Leandro', 'Sacramento', 'San Diego',
        'Los Angeles', 'Anchorage', 'Monterey', 'Elgin', 'Carol Stream',
        'Chicago',
    ]
    for city in cities:
        if city.upper() in s:
            return city
    return 'Unknown'

def state_from(name, company=''):
    """Best-effort state detection from the trip name only.

    NOTE: the company column is intentionally NOT used to infer the state,
    because a legal name such as 'Beyond Transportation IL INC.' used to be
    mis-read as Illinois even though all of its trips are in New Mexico.
    When auto-detection is uncertain, the user confirms the state per file
    in the upload screen.
    """
    s = str(name).upper()
    if any(k in s for k in AZ_KEYS):
        return 'AZ'
    if any(k in s for k in NM_KEYS):
        return 'NM'
    if any(c.upper() in s for c in CITIES.get('OR', [])) or any(c.upper() in s for c in ['DAMASCUS','CLACKAMAS','TROUTDALE','GLADSTONE','CORVALLIS','WOODBURN','WEST LINN','MILWAUKIE']):
        return 'OR'
    if 'MONTEREY' in s: return 'MON'
    if 'CROSS BORDER' in s or 'ALASKA' in s or 'ANCHORAGE' in s: return 'AK'
    if 'LINCOLN' in s or 'LINC ' in s or 'BRYAN' in s or 'NEBRASKA' in s: return 'NE'
    if 'PORTLAND' in s or 'GRESHAM' in s or 'SALEM' in s or 'OREGON' in s: return 'OR'
    if 'BERKELEY' in s or 'RICHMOND' in s or 'SAN LEANDRO' in s: return 'N.CA'
    if 'SAN DIEGO' in s or 'LOS ANGELES' in s: return 'S.CA'
    if 'SACRAMENTO' in s: return 'SAC'
    if 'ILLINOIS' in s or 'ELGIN' in s or 'CAROL STREAM' in s or 'WINSTON KNOLLS' in s: return 'IL'
    return 'Unknown'

def policy_pay(state, miles, vehicle='Unknown', city='Unknown'):
    """Return the contracted amount using city/vehicle rules first, then state rules."""
    miles = float(miles or 0)
    vehicle = str(vehicle or 'Unknown').title()
    city = str(city or 'Unknown').strip()

    city_rules = CITY_POLICIES.get(city, [])
    if state == 'SAC' and city == 'Sacramento':
        city_rules = SACRAMENTO_POLICIES.get(vehicle, [])
    for rule in city_rules:
        if rule['min'] <= miles <= rule['max']:
            amount = rule['base']
            if rule['per_mile']:
                amount += max(0.0, miles - rule.get('over', rule['min'] - 0.01)) * rule['per_mile']
            return round(amount, 2), f"Matched - {rule['note']}"

    rules = POLICY_DF[
        (POLICY_DF.State == state)
        & (POLICY_DF.Min_Miles <= miles)
        & (POLICY_DF.Max_Miles >= miles)
    ]
    if state in ('AK', 'MON') and vehicle in ('Sedan', 'Minivan'):
        exact = rules[rules.Vehicle_Type == vehicle]
        if not exact.empty:
            rules = exact
    if rules.empty:
        return 0.0, 'No policy'
    rule = rules.iloc[0]
    if state == 'AK' and miles > 16:
        return 0.0, 'Alaska >16-mile rule needed'
    if float(rule.Per_Mile_Rate) > 0:
        # Overage is charged above the lower edge of the per-mile tier
        # (e.g. 14 for NM/MON, 16 for NE), not a hard-coded 16.
        breakpoint_mile = int(rule.Min_Miles)
        return round(float(rule.Policy_Pay) + (miles - breakpoint_mile) * float(rule.Per_Mile_Rate), 2), 'Matched - state policy'
    return float(rule.Policy_Pay), 'Matched - state policy'

def finish(df):
    if df.empty:
        return df
    for column in ['Miles', 'Gross_Pay', 'Net_Pay']:
        df[column] = pd.to_numeric(df.get(column, 0), errors='coerce').fillna(0.0)
    calculated = df.apply(lambda row: policy_pay(row.State, row.Miles, row.Vehicle, row.City), axis=1)
    df['Policy_Driver_Pay'] = calculated.map(lambda result: result[0])
    df['Policy_Status'] = calculated.map(lambda result: result[1])
    df['Actual_Pay'] = df['Net_Pay']
    df['Difference_Actual_vs_Contract'] = df['Actual_Pay'] - df['Policy_Driver_Pay']
    df['Loss_Amount'] = df['Difference_Actual_vs_Contract'].clip(lower=0)
    df['Is_Non_Compliant'] = (df['Policy_Status'].str.startswith('Matched')) & (df['Difference_Actual_vs_Contract'] > 0.05)
    # Revenue = what First pays us (Net Pay). Driver cost = contracted policy pay.
    # Margin / profit = Revenue - Driver cost.
    df['Revenue'] = df['Actual_Pay']
    df['Driver_Cost'] = df['Policy_Driver_Pay']
    df['Margin'] = df['Revenue'] - df['Driver_Cost']
    df['Margin_Pct'] = (df['Margin'] / df['Revenue'].replace(0, pd.NA)).fillna(0.0)
    # Amount to claim back from First: when what First pays us (Revenue) is less
    # than the contracted driver pay we owe, we are short that gap and claim it.
    df['Amount_to_Claim'] = (df['Driver_Cost'] - df['Revenue']).clip(lower=0)
    return df

def read_first(buf):
    book = pd.ExcelFile(buf, engine='openpyxl')
    sheet = 'SP ITEMIZED REPORT' if 'SP ITEMIZED REPORT' in book.sheet_names else book.sheet_names[0]
    x = book.parse(sheet)
    x.columns = [str(c).strip() for c in x.columns]
    return _normalize(x)

def read_csv(buf):
    x = pd.read_csv(buf)
    x.columns = [str(c).strip() for c in x.columns]
    return _normalize(x)

def read_xls(buf):
    x = pd.read_excel(buf)
    x.columns = [str(c).strip() for c in x.columns]
    return _normalize(x)

def _normalize(x):
    d = pd.DataFrame(index=x.index)
    d['Source'] = 'First'
    d['Source Company'] = x.get('SP COMPANY', x.get('COMPANY', ''))
    d['Driver_Name'] = x.get('DRIVER NAME', x.get('DRIVER', 'Unknown'))
    d['Trip_Date'] = pd.to_datetime(x.get('DATE', x.get('TRIP DATE')), errors='coerce')
    d['Trip_ID'] = x.get('TRIP CODE', x.get('TRIP ID', x.get('TRIP_ID', '')))
    d['Trip_Name'] = x.get('TRIP NAME', x.get('NAME', ''))
    d['Miles'] = x.get('TOTAL MILES', x.get('MILES', 0))
    d['Gross_Pay'] = x.get('GROSS PAY', x.get('GROSS', 0))
    d['Net_Pay'] = x.get('NET PAY', x.get('NET', x.get('ACTUAL PAY', 0)))
    d['Vehicle'] = d.Trip_Name.map(vehicle_from)
    d['State'] = d.apply(lambda r: state_from(r.Trip_Name, r['Source Company']), axis=1)
    d['City'] = d.Trip_Name.map(city_from)
    return finish(d)

def read_source(payload, name, force_state=None):
    """Read a First report from raw bytes, dispatching by file extension."""
    lower = str(name).lower()
    buf = io.BytesIO(payload)
    if lower.endswith('.csv'):
        d = read_csv(buf)
    elif lower.endswith('.xls') and not lower.endswith('.xlsx'):
        d = read_xls(buf)
    elif lower.endswith(('.xlsx', '.xlsm')):
        d = read_first(buf)
    else:
        raise RuntimeError('Unsupported file type. Upload a First report as .xlsx, .xlsm, .xls or .csv.')
    if force_state and force_state in STATES and not d.empty:
        # Arizona trips are mixed into the same First file as other states, so
        # even when the whole file is forced to e.g. New Mexico we keep the
        # trips that positively identify as Arizona on their own state.
        if force_state != 'AZ':
            _az_re = '|'.join(re.escape(k) for k in AZ_KEYS)
            az_mask = d['Trip_Name'].astype(str).str.upper().str.contains(_az_re, na=False, regex=True)
        else:
            az_mask = pd.Series(False, index=d.index)
        force_mask = ~az_mask
        d.loc[force_mask, 'State'] = force_state
        # Drop city-level overrides that belong to a different state so the
        # forced state's own rate is used (avoids e.g. a NM trip accidentally
        # matching a California city name inside its school name).
        valid_cities = set(CITIES.get(force_state, [])) | {'Unknown'}
        if force_state == 'SAC':
            valid_cities |= {'Sacramento'}
        bad_city = force_mask & ~d['City'].isin(valid_cities)
        d.loc[bad_city, 'City'] = 'Unknown'
        d = finish(d)  # recompute every derived column against the forced state
    return d

def originals_zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, payload in files:
            z.writestr(name, payload)
    return out.getvalue()

def save_history(state, df):
    if df.empty: return
    with sqlite3.connect(DB_FILE) as c:
        c.execute('INSERT INTO weekly_summary VALUES(NULL,?,?,?,?,?,?,?,?,?)', (datetime.now().strftime('%Y-%m-%d'), state, str(df.Trip_Date.min().date()), str(df.Trip_Date.max().date()), len(df), float(df.Gross_Pay.sum()), float(df.Actual_Pay.sum()), float(df.Margin.sum()), float(df.Loss_Amount.sum())))
def pdf_report(view, code, name):
    if not REPORTLAB_AVAILABLE:
        return None
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(letter), rightMargin=0.35*inch, leftMargin=0.35*inch, topMargin=0.35*inch, bottomMargin=0.35*inch)
    styles = getSampleStyleSheet()
    story = [Paragraph(f'{name} - Beyond Transportation Report', styles['Title']), Spacer(1, 8)]
    summary = [['Trips', 'Revenue', 'Driver Cost', 'Margin', 'Margin %', 'Claim from First'], [str(len(view)), f"${view.Revenue.sum():,.2f}", f"${view.Driver_Cost.sum():,.2f}", f"${view.Margin.sum():,.2f}", (f"{view.Margin.sum()/view.Revenue.sum():.1%}" if view.Revenue.sum() else '0.0%'), f"${view.Amount_to_Claim.sum():,.2f}"]]
    t = Table(summary, colWidths=[1.0*inch]*6)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1f4e78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.5,colors.grey),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,0),(-1,-1),'Helvetica')]))
    story += [t, Spacer(1, 10)]
    cols = ['Source','Trip_Date','Trip_ID','City','Driver_Name','Miles','Revenue','Driver_Cost','Margin','Amount_to_Claim','Policy_Status']
    data = [cols]
    for _, r in view[cols].fillna('').iterrows():
        data.append([str(r[c])[:42] for c in cols])
    detail = Table(data, repeatRows=1, colWidths=[0.75*inch,0.75*inch,0.9*inch,1.35*inch,0.55*inch,0.8*inch,0.85*inch,0.75*inch,0.85*inch,0.95*inch])
    detail.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1f4e78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),6),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(detail); doc.build(story); return out.getvalue()

def show_metrics_and_tables(view, code, name, key_prefix):
    if view.empty:
        st.warning(f'No {name} trips were detected in the uploaded reports.')
        return
    revenue = float(view.Revenue.sum())          # Net Pay = what First pays us
    driver_cost = float(view.Driver_Cost.sum())  # contracted driver pay (policy)
    margin = revenue - driver_cost
    margin_pct = margin / revenue if revenue else 0.0
    claim = float(view.Amount_to_Claim.sum())
    total = len(view)
    no_policy = int((~view.Policy_Status.str.startswith('Matched')).sum())
    a, b, c, d, e, f = st.columns(6)
    a.metric('Trips', total)
    b.metric('Revenue (from First)', f'${revenue:,.2f}')
    c.metric('Driver cost (policy)', f'${driver_cost:,.2f}')
    d.metric('Margin / profit', f'${margin:,.2f}')
    e.metric('Profit margin %', f'{margin_pct:.1%}')
    f.metric('Claim from First', f'${claim:,.2f}')
    if no_policy:
        st.caption(f'{no_policy} trip(s) have no matching policy (counted at $0 driver cost). Fix their state/city or add the policy - e.g. Alaska trips over 16 miles.')
    st.subheader('By City')
    st.dataframe(view.groupby(['Source','City']).agg(Trips=('Trip_ID','count'),Miles=('Miles','sum'),Revenue=('Revenue','sum'),Driver_Cost=('Driver_Cost','sum'),Margin=('Margin','sum'),Claim=('Amount_to_Claim','sum')).reset_index(), use_container_width=True)
    st.subheader('By Driver')
    st.dataframe(view.groupby(['Source','Driver_Name']).agg(Trips=('Trip_ID','count'),Miles=('Miles','sum'),Revenue=('Revenue','sum'),Driver_Cost=('Driver_Cost','sum'),Margin=('Margin','sum'),Claim=('Amount_to_Claim','sum')).reset_index(), use_container_width=True)
    st.subheader('Per-trip detail: revenue vs driver cost')
    st.dataframe(view[['Source','Trip_Date','Trip_ID','Trip_Name','City','Driver_Name','Miles','Revenue','Driver_Cost','Margin','Amount_to_Claim','Policy_Status']], use_container_width=True)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        view.to_excel(w, sheet_name='Trips', index=False)
        POLICY_DF[POLICY_DF.State == code].to_excel(w, sheet_name='Policy', index=False)
    st.download_button('Download report - Excel', out.getvalue(), f'{key_prefix}_{code}_report.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'dl_xlsx_{key_prefix}_{code}')
    st.download_button('Download report - CSV', view.to_csv(index=False).encode('utf-8-sig'), f'{key_prefix}_{code}_report.csv', 'text/csv', key=f'dl_csv_{key_prefix}_{code}')
    pdf_bytes = pdf_report(view, code, name)
    if pdf_bytes:
        st.download_button('Download report - PDF', pdf_bytes, f'{key_prefix}_{code}_report.pdf', 'application/pdf', key=f'dl_pdf_{key_prefix}_{code}')
    else:
        st.warning('PDF download is unavailable until reportlab is installed. Add reportlab to requirements.txt and reboot the app.')

def load_first_uploads(files, key_prefix):
    """Read uploaded First files, let the user confirm/override each file's state,
    then store the combined dataframe + raw payloads in session."""
    frames = []; payloads = []
    options = ['(auto-detect per trip)'] + list(STATES)
    for f in files:
        payload = f.getvalue(); payloads.append((f.name, payload))
        try:
            raw = read_source(payload, f.name)
        except Exception as exc:
            st.error(f'Could not read {f.name}: {exc}'); continue
        detected = raw.State.mode().iat[0] if (not raw.empty and raw.State.notna().any()) else 'Unknown'
        default_idx = options.index(detected) if detected in options else 0
        choice = st.selectbox(f'State for file "{f.name}" (auto-detected: {STATES.get(detected, detected)})', options, index=default_idx, key=f'{key_prefix}_state_{f.name}')
        if choice != '(auto-detect per trip)':
            raw = read_source(payload, f.name, force_state=choice)
        frames.append(raw)
    if not frames:
        return pd.DataFrame(), payloads
    return pd.concat(frames, ignore_index=True), payloads

def company_page():
    st.title('First Reports')
    st.caption('Upload the First itemized report(s) here. Each file is split by state automatically so you can build every state report without waiting for the state managers.')
    files = st.file_uploader('First reports (.xlsx, .xlsm, .xls, .csv)', type=['xlsx','xlsm','xls','csv'], accept_multiple_files=True, key='company_first_upload')
    if files:
        df, payloads = load_first_uploads(files, 'first_upload')
        if not df.empty:
            st.session_state['First_df'] = df
            st.session_state['First_files'] = payloads
            st.success(f'Loaded {len(df):,} trips from {len(files)} file(s).')
    df = st.session_state.get('First_df', pd.DataFrame())
    if df.empty:
        st.info('Upload one or more First files to begin.'); return

    st.header('All States - Overview')
    overview = df.groupby('State').agg(Trips=('Trip_ID','count'), Miles=('Miles','sum'), Revenue=('Revenue','sum'), Driver_Cost=('Driver_Cost','sum'), Margin=('Margin','sum'), Claim=('Amount_to_Claim','sum')).reset_index()
    overview['Margin_%'] = (overview['Margin'] / overview['Revenue'].replace(0, pd.NA)).fillna(0.0).map(lambda v: f'{v:.1%}')
    overview['State'] = overview['State'].map(lambda s: f'{STATES.get(s, s)} ({s})')
    st.dataframe(overview, use_container_width=True, hide_index=True)
    st.caption(f'Total amount to claim back from First across all states: ${float(df.Amount_to_Claim.sum()):,.2f}')

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='All Trips', index=False)
        overview.to_excel(w, sheet_name='Overview', index=False)
    st.download_button('Download ALL states - Excel', out.getvalue(), 'first_all_states_report.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_all_states')

    st.header('Per-state reports')
    for code in [c for c in STATES if c in set(df.State.dropna().unique())]:
        with st.expander(f'{STATES[code]} ({code}) - full report', expanded=False):
            show_metrics_and_tables(df[df.State == code].copy(), code, STATES[code], f'first_auto_{code}')

    payloads = st.session_state.get('First_files', [])
    if payloads:
        st.download_button('Download original uploaded files - ZIP', originals_zip(payloads), 'first_original_files.zip', 'application/zip', key='zip_first')

def state_page(code, name):
    st.title(f'{name} - Analysis Dashboard')
    st.subheader('Official Pricing Policy')
    st.table(POLICY_DF[POLICY_DF.State == code][['Vehicle_Type','Min_Miles','Max_Miles','Policy_Pay','Per_Mile_Rate','Note']])

    df = st.session_state.get('First_df', pd.DataFrame())
    view = df[df.State == code].copy() if not df.empty else pd.DataFrame()

    st.subheader('Optional: upload a report just for this state')
    state_files = st.file_uploader(f'{name} report (.xlsx, .xlsm, .xls, .csv) - optional', type=['xlsx','xlsm','xls','csv'], accept_multiple_files=True, key=f'state_{code}')
    if state_files:
        frames = []; payloads = []
        for f in state_files:
            payload = f.getvalue(); payloads.append((f.name, payload))
            try:
                frames.append(read_source(payload, f.name, force_state=code))
            except Exception as exc:
                st.error(f'Could not read {f.name}: {exc}')
        if frames:
            view = pd.concat(frames, ignore_index=True)
            st.session_state[f'state_files_{code}'] = payloads

    if view.empty:
        st.info(f'No {name} trips yet. Upload the combined First report on the "First Reports" page (it is split by state automatically), or upload a {name}-only report above.')
        return

    st.header(f'{name} - Contract Rate Comparison')
    st.caption('Actual Pay = Net Pay from the First report. Difference = Actual Pay - contracted rate for this state/city.')
    show_metrics_and_tables(view, code, name, f'state_{code}')

    state_originals = st.session_state.get(f'state_files_{code}', [])
    if state_originals:
        st.download_button('Download original state files - ZIP', originals_zip(state_originals), f'{code}_original_state_files.zip', 'application/zip', key=f'zip_state_{code}')

st.set_page_config(page_title="Hatem's B.T. Analyzer", layout='wide')
st.sidebar.title('Navigation')
menu = st.sidebar.radio('Choose section', ['State Reports', 'First Reports'])
if menu == 'First Reports':
    company_page()
else:
    selected = st.sidebar.selectbox('Choose state', list(STATES), format_func=lambda x: STATES[x])
    state_page(selected, STATES[selected])
