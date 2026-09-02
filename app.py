from __future__ import annotations
import io, re, sqlite3, subprocess, tempfile, zipfile
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
from pathlib import Path
import pandas as pd
import streamlit as st

DB_FILE = 'history.db'
STATES = {
    'OR': 'Oregon', 'N.CA': 'North California', 'S.CA': 'South California',
    'AK': 'Alaska', 'IL': 'Illinois', 'NM': 'New Mexico', 'NE': 'Nebraska', 'KS': 'Kansas', 'SAC': 'Sacramento', 'MON': 'Monterey', 'CAN': 'Canada'
}
CITIES = {
    'OR': ['Portland','Gresham','Tigard','Salem','McMinnville','Wilsonville','Roseburg','Molalla','Lincoln City','North Bend','Newberg','Gladstone','Troutdale','Woodburn','West Linn','Milwaukie','Clackamas'],
    'N.CA': ['Benicia','Berkeley','Richmond','San Leandro'], 'S.CA': ['San Diego','Los Angeles','Richmond'],
    'AK': ['Anchorage'], 'NE': ['Lincoln'], 'KS': [], 'IL': ['Elgin','Carol Stream','Chicago'], 'NM': [], 'MON': ['Monterey'], 'CAN': []
}
CITY_MASTER = {
 'N.CA': [
  {'City':'Benicia','Pricing':'$38 all trips','Drivers':'Not supplied'},
  {'City':'Berkeley','Pricing':'1–6 $38; 7–16 $42','Drivers':'Ali Hassan; Mohamed Hussein Altayeb Abdalla'},
  {'City':'Richmond','Pricing':'1–6 $38; 7–11 $42; WC $75','Drivers':'Snose'},
  {'City':'San Leandro','Pricing':'1–6 $38; 7–16 $43; >16 +$1.30/mile','Drivers':'Amer Ali Alabshalah; Nagi Alnaeem; Siddieg Basher Khair; Ahmed Musaad Almakkawi'}],
 'SAC': [{'City':'Sacramento','Pricing':'First 1–8 $34; 9–16 $37; extra +$1.00; Sedan 1–6 $38, 7–14 $42, extra +$0.80; Minivan 1–6 $43, 7–14 $48','Drivers':'Not supplied'}],
 'OR': [
  {'City':'McMinnville','Pricing':'Oregon policy','Drivers':'Katy Martinez'}, {'City':'Wilsonville','Pricing':'Oregon policy','Drivers':'Julie Hussein'},
  {'City':'Portland','Pricing':'Driver target 1–6 $30; general 1–6 $33, 7–10 $36, 11–14 $38, extra +$1.25','Drivers':'Hussein Ibrahim Alsheikh; Hasan Ammar Alkadi; Nasri; Abdoun; Issa'},
  {'City':'Gresham','Pricing':'Driver target 1–6 $30; general Oregon policy','Drivers':'Emad Zaki; Kassaye Medhin; Alaa Alhalaqi; Yaser A Aldabh; Wesal M Alemam'},
  {'City':'Tigard','Pricing':'Oregon policy','Drivers':'Ayad Alabbasi'}, {'City':'Salem','Pricing':'Oregon policy','Drivers':'Doangjok Otan; Leandro Ramirez Bueno; جمال للان'},
  {'City':'Gladstone','Pricing':'Oregon policy','Drivers':'Bashka Hussein Abdirahman'}, {'City':'Troutdale','Pricing':'Oregon policy','Drivers':'Adham Hammadeh; Waeel Al Auosh'},
  {'City':'Corvallis','Pricing':'Oregon policy','Drivers':'Douglas Giron'}, {'City':'Woodburn','Pricing':'Oregon policy','Drivers':'Hashmatullah Alam'},
  {'City':'Clackamas','Pricing':'Oregon policy','Drivers':'Aicha Orabi; Hadeel M Al Imam'}, {'City':'West Linn','Pricing':'Oregon policy','Drivers':'Zainab Gheni; M Alakraa'},
  {'City':'Milwaukie','Pricing':'Oregon policy','Drivers':'Basem Chami'}, {'City':'Roseburg','Pricing':'Oregon policy','Drivers':'Not supplied'}, {'City':'Molalla','Pricing':'Oregon policy','Drivers':'Not supplied'}, {'City':'Lincoln City','Pricing':'Oregon policy','Drivers':'Not supplied'}, {'City':'North Bend','Pricing':'Oregon policy','Drivers':'Not supplied'}, {'City':'Newberg','Pricing':'Oregon policy','Drivers':'Not supplied'}],
 'NE': [{'City':'Lincoln','Pricing':'EverDriven $30 through 16 miles; >16 +$1.50/mile','Drivers':'From EverDriven report'}],
 'KS': [{'City':'Not supplied','Pricing':'EverDriven / Net Pay; rate not supplied','Drivers':'Not supplied'}],
 'NM': [{'City':'Not supplied','Pricing':'First revenue 1–6 $48 / pay $33; 7–14 $48 / pay $37; >14 revenue +$2.25 / pay +$1.50','Drivers':'Not supplied'}],
 'IL': [{'City':'Elgin','Pricing':'First revenue $98.25; pay $75','Drivers':'From First report'}, {'City':'Carol Stream','Pricing':'First revenue $103.50; pay $85','Drivers':'From First report'}, {'City':'Unknown','Pricing':'Winston Knolls revenue $105.25; pay $85','Drivers':'From First report'}],
 'AK': [{'City':'Anchorage','Pricing':'Cross Border = Beyond revenue; Sedan 1–8 $35, 9–16 $37; Minivan 1–8 $40, 9–16 $42','Drivers':'From report; >16 rule not supplied'}],
 'MON': [{'City':'Monterey','Pricing':'Sedan 1–6 $38; 7–14 $42; >14 +$0.80/mile. Minivan 1–6 $43; 7–14 $48; >14 +$0.80/mile','Drivers':'Khalid Wahab'}]
}

POLICIES = [
 # Oregon rates from the supplied Oregon pricing note/image. The old 35/40/37 table is kept below as legacy, not active.
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':33.0,'Per_Mile_Rate':0,'Note':'Supplied Oregon schedule: 1–6 miles; confirmation pending'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':10,'Policy_Pay':36.0,'Per_Mile_Rate':0,'Note':'Supplied Oregon schedule: 7–10 miles; confirmation pending'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':10.01,'Max_Miles':14,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'Supplied Oregon schedule: 11–14 miles; confirmation pending'},
 {'State':'OR','Vehicle_Type':'ANY','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':38.0,'Per_Mile_Rate':1.25,'Note':'Supplied Oregon schedule: +$1.25 per mile above 14; confirmation pending'},

 {'State':'N.CA','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':6,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'1–6 miles'},
 {'State':'N.CA','Vehicle_Type':'ANY','Min_Miles':6.01,'Max_Miles':16,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'7–16 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':4,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'1–4 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':4.01,'Max_Miles':8,'Policy_Pay':40.0,'Per_Mile_Rate':0,'Note':'5–8 miles'},
 {'State':'S.CA','Vehicle_Type':'ANY','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':43.0,'Per_Mile_Rate':0,'Note':'9–16 miles'},
 {'State':'AK','Vehicle_Type':'Sedan','Min_Miles':0,'Max_Miles':8,'Policy_Pay':35.0,'Per_Mile_Rate':0,'Note':'Sedan 1–8'},
 {'State':'AK','Vehicle_Type':'Sedan','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':37.0,'Per_Mile_Rate':0,'Note':'Sedan 9–16'},
 {'State':'AK','Vehicle_Type':'Minivan','Min_Miles':0,'Max_Miles':8,'Policy_Pay':40.0,'Per_Mile_Rate':0,'Note':'Minivan 1–8'},
 {'State':'AK','Vehicle_Type':'Minivan','Min_Miles':8.01,'Max_Miles':16,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'Minivan 9–16'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':0,'Max_Miles':6,'Policy_Pay':38.0,'Per_Mile_Rate':0,'Note':'Sedan 1–6'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':6.01,'Max_Miles':14,'Policy_Pay':42.0,'Per_Mile_Rate':0,'Note':'Sedan 7–14'},
 {'State':'MON','Vehicle_Type':'Sedan','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':42.0,'Per_Mile_Rate':0.80,'Note':'Sedan 42 + $0.80 per mile above 14'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':0,'Max_Miles':6,'Policy_Pay':43.0,'Per_Mile_Rate':0,'Note':'Minivan 1–6'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':6.01,'Max_Miles':14,'Policy_Pay':48.0,'Per_Mile_Rate':0,'Note':'Minivan 7–14'},
 {'State':'MON','Vehicle_Type':'Minivan','Min_Miles':14.01,'Max_Miles':9999,'Policy_Pay':48.0,'Per_Mile_Rate':0.80,'Note':'Minivan 48 + $0.80 per mile above 14'},
 {'State':'NE','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':16,'Policy_Pay':30.0,'Per_Mile_Rate':0,'Note':'$30 through 16 miles'},
 {'State':'NE','Vehicle_Type':'ANY','Min_Miles':16.01,'Max_Miles':9999,'Policy_Pay':30.0,'Per_Mile_Rate':1.50,'Note':'$30 + $1.50 per mile above 16'},
 {'State':'IL','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':9999,'Policy_Pay':0.0,'Per_Mile_Rate':0,'Note':'Not supplied'},
 {'State':'NM','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':9999,'Policy_Pay':0.0,'Per_Mile_Rate':0,'Note':'Not supplied'},
 {'State':'CAN','Vehicle_Type':'ANY','Min_Miles':0,'Max_Miles':9999,'Policy_Pay':0.0,'Per_Mile_Rate':0,'Note':'Not supplied'},
]
POLICY_DF = pd.DataFrame(POLICIES)

# City-level contract rates override the state-level fallback when supplied.
# Each rule returns the contracted driver pay for one trip.
CITY_POLICIES = {
    'Benicia': [{'min': 0, 'max': 9999, 'base': 38.0, 'per_mile': 0.0, 'note': 'Benicia: $38 all trips'}],
    'Berkeley': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Berkeley: 1–6 miles'},
        {'min': 6.01, 'max': 16, 'base': 42.0, 'per_mile': 0.0, 'note': 'Berkeley: 7–16 miles'},
    ],
    'Richmond': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Richmond: 1–6 miles'},
        {'min': 6.01, 'max': 11, 'base': 42.0, 'per_mile': 0.0, 'note': 'Richmond: 7–11 miles'},
    ],
    'San Leandro': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'San Leandro: 1–6 miles'},
        {'min': 6.01, 'max': 16, 'base': 43.0, 'per_mile': 0.0, 'note': 'San Leandro: 7–16 miles'},
        {'min': 16.01, 'max': 9999, 'base': 43.0, 'per_mile': 1.30, 'note': 'San Leandro: $43 + $1.30 per mile above 16'},
    ],
    'Lincoln': [
        {'min': 0, 'max': 16, 'base': 30.0, 'per_mile': 0.0, 'note': 'Lincoln: $30 through 16 miles'},
        {'min': 16.01, 'max': 9999, 'base': 30.0, 'per_mile': 1.50, 'note': 'Lincoln: $30 + $1.50 per mile above 16'},
    ],
    'Elgin': [{'min': 0, 'max': 9999, 'base': 75.0, 'per_mile': 0.0, 'note': 'Elgin: driver pay $75'}],
    'Carol Stream': [{'min': 0, 'max': 9999, 'base': 85.0, 'per_mile': 0.0, 'note': 'Carol Stream: driver pay $85'}],
}

SACRAMENTO_POLICIES = {
    'Sedan': [
        {'min': 0, 'max': 6, 'base': 38.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 1–6 miles'},
        {'min': 6.01, 'max': 14, 'base': 42.0, 'per_mile': 0.0, 'note': 'Sacramento Sedan: 7–14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 42.0, 'per_mile': 0.80, 'note': 'Sacramento Sedan: $42 + $0.80 per mile above 14'},
    ],
    'Minivan': [
        {'min': 0, 'max': 6, 'base': 43.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 1–6 miles'},
        {'min': 6.01, 'max': 14, 'base': 48.0, 'per_mile': 0.0, 'note': 'Sacramento Minivan: 7–14 miles'},
        {'min': 14.01, 'max': 9999, 'base': 48.0, 'per_mile': 0.80, 'note': 'Sacramento Minivan: $48 + $0.80 per mile above 14'},
    ],
}

def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS weekly_summary (id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_date TEXT, state TEXT, week_start_date TEXT, week_end_date TEXT, total_trips INTEGER, total_revenue REAL, total_driver_cost REAL, total_margin REAL, total_loss REAL)''')
init_db()

def clean(x): return re.sub(r'\s+',' ',str(x or '').strip()).lower()
def vehicle_from(name):
    s=clean(name).upper()
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
    s=f'{name} {company}'.upper()
    # Use every supplied Oregon city/region as an explicit state mapping.
    if any(city.upper() in s for city in CITIES.get('OR', [])) or any(city.upper() in s for city in ['DAMASCUS','CLACKAMAS','TROUTDALE','GLADSTONE','CORVALLIS','WOODBURN','WEST LINN','MILWAUKIE']): return 'OR'
    if 'MONTEREY' in s: return 'MON'
    if 'CROSS BORDER' in s or 'ALASKA' in s or 'ANCHORAGE' in s: return 'AK'
    if 'LINCOLN' in s or 'LINC ' in s or 'BRYAN' in s or 'NEBRASKA' in s: return 'NE'
    if 'PORTLAND' in s or 'GRESHAM' in s or 'SALEM' in s or 'OREGON' in s: return 'OR'
    if 'BERKELEY' in s or 'RICHMOND' in s or 'SAN LEANDRO' in s: return 'N.CA'
    if 'SAN DIEGO' in s or 'LOS ANGELES' in s: return 'S.CA'
    if 'SACRAMENTO' in s: return 'SAC'
    if 'ILLINOIS' in s or ' IL' in s: return 'IL'
    return 'Unknown'
def policy_pay(state, miles, vehicle='Unknown', city='Unknown'):
    """Return the contracted driver pay using city/vehicle rules first, then state rules."""
    miles = float(miles or 0)
    vehicle = str(vehicle or 'Unknown').title()
    city = str(city or 'Unknown').strip()

    # City rules are the primary source whenever a city-specific contract exists.
    city_rules = CITY_POLICIES.get(city, [])
    if state == 'SAC' and city == 'Sacramento':
        city_rules = SACRAMENTO_POLICIES.get(vehicle, [])
    for rule in city_rules:
        if rule['min'] <= miles <= rule['max']:
            amount = rule['base']
            if rule['per_mile']:
                amount += max(0.0, miles - rule.get('over', rule['min'] - 0.01)) * rule['per_mile']
            return round(amount, 2), f"Matched — {rule['note']}"

    # If there is no city-specific rate, use the state-level policy table.
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
        return round(float(rule.Policy_Pay) + (miles - 16) * float(rule.Per_Mile_Rate), 2), 'Matched — state policy'
    return float(rule.Policy_Pay), 'Matched — state policy'

def finish(df):
    if df.empty:
        return df
    for column in ['Miles', 'Gross_Pay', 'Net_Pay']:
        df[column] = pd.to_numeric(df.get(column, 0), errors='coerce').fillna(0.0)
    calculated = df.apply(lambda row: policy_pay(row.State, row.Miles, row.Vehicle, row.City), axis=1)
    df['Policy_Driver_Pay'] = calculated.map(lambda result: result[0])
    df['Policy_Status'] = calculated.map(lambda result: result[1])
    df['Actual_Pay'] = df['Net_Pay']
    # Positive difference means the actual driver payment exceeded the contract rate.
    df['Difference_Actual_vs_Contract'] = df['Actual_Pay'] - df['Policy_Driver_Pay']
    df['Loss_Amount'] = df['Difference_Actual_vs_Contract'].clip(lower=0)
    df['Is_Non_Compliant'] = (df['Policy_Status'].str.startswith('Matched')) & (df['Difference_Actual_vs_Contract'] > 0.05)
    df['Margin'] = df['Gross_Pay'] - df['Actual_Pay']
    return df

def read_first(file):
    book=pd.ExcelFile(file,engine='openpyxl'); sheet='SP ITEMIZED REPORT' if 'SP ITEMIZED REPORT' in book.sheet_names else book.sheet_names[0]; x=pd.read_excel(file,sheet_name=sheet,engine='openpyxl'); x.columns=[str(c).strip() for c in x.columns]
    d=pd.DataFrame(index=x.index); d['Source']='First'; d['Source Company']=x.get('SP COMPANY',''); d['Driver_Name']=x.get('DRIVER NAME','Unknown'); d['Trip_Date']=pd.to_datetime(x.get('DATE'),errors='coerce'); d['Trip_ID']=x.get('TRIP CODE',''); d['Trip_Name']=x.get('TRIP NAME',''); d['Miles']=x.get('TOTAL MILES',x.get('MILES',0)); d['Gross_Pay']=x.get('GROSS PAY',0); d['Net_Pay']=x.get('NET PAY',0); d['Vehicle']=d.Trip_Name.map(vehicle_from); d['State']=d.apply(lambda r:state_from(r.Trip_Name,r['Source Company']),axis=1); d['City']=d.Trip_Name.map(city_from); return finish(d)

def read_csv(file, source='First'):
    x=pd.read_csv(file)
    x.columns=[str(c).strip() for c in x.columns]
    d=pd.DataFrame(index=x.index); d['Source']=source; d['Source Company']=x.get('SP COMPANY',x.get('COMPANY',''))
    d['Driver_Name']=x.get('DRIVER NAME',x.get('DRIVER','Unknown')); d['Trip_Date']=pd.to_datetime(x.get('DATE',x.get('TRIP DATE')),errors='coerce')
    d['Trip_ID']=x.get('TRIP CODE',x.get('TRIP ID',x.get('TRIP_ID',''))); d['Trip_Name']=x.get('TRIP NAME',x.get('NAME',''))
    d['Miles']=x.get('TOTAL MILES',x.get('MILES',0)); d['Gross_Pay']=x.get('GROSS PAY',x.get('GROSS',0)); d['Net_Pay']=x.get('NET PAY',x.get('NET',x.get('ACTUAL PAY',0)))
    d['Vehicle']=d.Trip_Name.map(vehicle_from); d['State']=d.apply(lambda r:state_from(r.Trip_Name,r['Source Company']),axis=1); d['City']=d.Trip_Name.map(city_from)
    return finish(d)

def read_any(file, source='First'):
    name=str(getattr(file,'name','')).lower()
    if name.endswith('.pdf'):
        return read_ever(file) if source == 'EverDriven' else read_ever(file)
    if name.endswith('.csv'):
        return read_csv(file,source)
    if name.endswith('.xls') and not name.endswith('.xlsx'):
        x=pd.read_excel(file)
        x.columns=[str(c).strip() for c in x.columns]
        # Reuse the standard First normalizer through an in-memory xlsx-compatible path where possible.
        d=pd.DataFrame(index=x.index); d['Source']=source; d['Source Company']=x.get('SP COMPANY',x.get('COMPANY','')); d['Driver_Name']=x.get('DRIVER NAME',x.get('DRIVER','Unknown')); d['Trip_Date']=pd.to_datetime(x.get('DATE',x.get('TRIP DATE')),errors='coerce'); d['Trip_ID']=x.get('TRIP CODE',x.get('TRIP ID','')); d['Trip_Name']=x.get('TRIP NAME',x.get('NAME','')); d['Miles']=x.get('TOTAL MILES',x.get('MILES',0)); d['Gross_Pay']=x.get('GROSS PAY',x.get('GROSS',0)); d['Net_Pay']=x.get('NET PAY',x.get('NET',0)); d['Vehicle']=d.Trip_Name.map(vehicle_from); d['State']=d.apply(lambda r:state_from(r.Trip_Name,r['Source Company']),axis=1); d['City']=d.Trip_Name.map(city_from); return finish(d)
    return read_first(file) if source == 'First' else read_ever(file)

def pdf_text(file):
    payload = file.read() if hasattr(file, 'read') else Path(file).read_bytes()
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('PDF reader is not installed. Add pypdf to requirements.txt, commit it, and reboot the Streamlit app.') from exc
    try:
        reader = PdfReader(io.BytesIO(payload))
        return '\n'.join(page.extract_text(extraction_mode='layout') or '' for page in reader.pages)
    except Exception as exc:
        raise RuntimeError(f'Could not extract text from PDF: {exc}') from exc
def read_ever(file):
    """Read EverDriven/Beyond Cashiering Receipt PDF detail rows.

    The receipt places the driver and date only on the first row of a group;
    continuation rows contain only the trip key. Therefore the current driver
    and date are carried forward while each detail row is parsed independently.
    """
    text = pdf_text(file)
    rows = []
    current_driver = 'Unknown'
    current_date = pd.NaT
    row_rx = re.compile(
        r'^\s*'
        r'(?:(?P<driver>[A-Za-z][A-Za-z .\'-]+?)\s+(?P<code>\d{5,6})\s+)?'
        r'(?:(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+)?'
        r'(?P<key>\d{6,})\s+'
        r'(?P<name>.+?)\s+'
        r'(?P<miles>\d+(?:\.\d+)?)\s+'
        r'\$(?P<gross>[\d,]+\.\d{2})\s+'
        r'\$(?P<net>[\d,]+\.\d{2})\s*$'
    )

    for raw_line in text.splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip()
        if not line or line.startswith(('Cashiering Receipt', 'BEYOND TRANSPORTATION', '(Formerly', 'Cashiering Dates:', 'Details', 'Person ', 'Subtotal')):
            continue
        match = row_rx.match(line)
        if not match:
            continue
        data = match.groupdict()
        if data['driver']:
            current_driver = data['driver'].strip()
        if data['date']:
            current_date = pd.to_datetime(data['date'], format='%m/%d/%Y', errors='coerce')
        trip_name = data['name'].strip()
        rows.append({
            'Source': 'EverDriven',
            'Source Company': 'Beyond Transportation (IL)',
            'Driver_Name': current_driver,
            'Trip_Date': current_date,
            'Trip_ID': data['key'],
            'Trip_Name': trip_name,
            'Miles': float(data['miles']),
            'Gross_Pay': float(data['gross'].replace(',', '')),
            'Net_Pay': float(data['net'].replace(',', '')),
            'Vehicle': vehicle_from(trip_name),
            'State': 'NE',  # This CashieringReceipt is a Nebraska report; all rows belong to Nebraska.
            'City': city_from(trip_name),
        })

    return finish(pd.DataFrame(rows))

def combine(first,ever):
    frames=[]
    first_files = first if isinstance(first, (list, tuple)) else ([first] if first is not None else [])
    ever_files = ever if isinstance(ever, (list, tuple)) else ([ever] if ever is not None else [])
    for item in first_files:
        frames.append(read_first(item))
    for item in ever_files:
        frames.append(read_ever(item))
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
def pdf_report(view, code, name):
    if not REPORTLAB_AVAILABLE:
        return None
    out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=landscape(letter),rightMargin=0.35*inch,leftMargin=0.35*inch,topMargin=0.35*inch,bottomMargin=0.35*inch)
    styles=getSampleStyleSheet(); story=[Paragraph(f'{name} — Beyond Transportation Report',styles['Title']),Spacer(1,8)]
    summary=[['Trips','Revenue','Actual Pay','Contracted','Difference'],[str(len(view)),f"${view.Gross_Pay.sum():,.2f}",f"${view.Actual_Pay.sum():,.2f}",f"${view.Policy_Driver_Pay.sum():,.2f}",f"${view.Difference_Actual_vs_Contract.sum():,.2f}"]]
    t=Table(summary,colWidths=[1.1*inch]*5); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1f4e78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.5,colors.grey),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,0),(-1,-1),'Helvetica')]))
    story += [t,Spacer(1,10)]
    cols=['Source','Trip_Date','Trip_ID','City','Driver_Name','Miles','Gross_Pay','Policy_Driver_Pay','Actual_Pay','Difference_Actual_vs_Contract','Policy_Status']
    data=[cols]
    for _,r in view[cols].fillna('').iterrows():
        data.append([str(r[c])[:42] for c in cols])
    detail=Table(data,repeatRows=1,colWidths=[0.65*inch,0.75*inch,0.9*inch,0.8*inch,1.25*inch,0.55*inch,0.75*inch,0.85*inch,0.75*inch,0.7*inch,0.9*inch])
    detail.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1f4e78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),6),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(detail); doc.build(story); return out.getvalue()

def originals_zip(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,payload in files:
            z.writestr(name,payload)
    return out.getvalue()

def save_history(state,df):
    if df.empty:return
    with sqlite3.connect(DB_FILE) as c: c.execute('INSERT INTO weekly_summary VALUES(NULL,?,?,?,?,?,?,?,?)',(datetime.now().strftime('%Y-%m-%d'),state,str(df.Trip_Date.min().date()),str(df.Trip_Date.max().date()),len(df),float(df.Gross_Pay.sum()),float(df.Actual_Pay.sum()),float(df.Margin.sum()),float(df.Loss_Amount.sum())))

def show_metrics_and_tables(view, code, name, key_prefix):
    if view.empty:
        st.warning(f'No {name} trips were detected in the uploaded reports.')
        return
    total_revenue=float(view.Gross_Pay.sum()); total_actual=float(view.Actual_Pay.sum()); total_margin=total_revenue-total_actual
    compliant=int(view.Policy_Status.str.startswith('Matched').sum() - view.Is_Non_Compliant.sum())
    non_compliant=int(view.Is_Non_Compliant.sum()); total=len(view)
    a,b,c,d,e=st.columns(5); a.metric('Trips',total); b.metric('Revenue',f'${total_revenue:,.2f}'); c.metric('Actual Pay',f'${total_actual:,.2f}'); d.metric('Margin',f'${total_margin:,.2f}'); e.metric('Non-compliant %',f'{non_compliant/total:.1%}' if total else '0.0%')
    st.subheader('Compliance Summary')
    st.dataframe(pd.DataFrame({'Metric':['Compliant trips','Non-compliant trips','Trips without a matching policy'],'Count':[compliant,non_compliant,int((~view.Policy_Status.str.startswith('Matched')).sum())],'Percentage':[f'{compliant/total:.1%}' if total else '0.0%',f'{non_compliant/total:.1%}' if total else '0.0%',f'{(~view.Policy_Status.str.startswith("Matched")).sum()/total:.1%}' if total else '0.0%']}),use_container_width=True,hide_index=True)
    st.subheader('By City'); st.dataframe(view.groupby(['Source','City']).agg(Trips=('Trip_ID','count'),Miles=('Miles','sum'),Revenue=('Gross_Pay','sum'),Actual_Pay=('Actual_Pay','sum'),Contracted=('Policy_Driver_Pay','sum'),Difference=('Difference_Actual_vs_Contract','sum')).reset_index(),use_container_width=True)
    st.subheader('By Driver'); st.dataframe(view.groupby(['Source','Driver_Name']).agg(Trips=('Trip_ID','count'),Miles=('Miles','sum'),Revenue=('Gross_Pay','sum'),Actual_Pay=('Actual_Pay','sum'),Contracted=('Policy_Driver_Pay','sum'),Difference=('Difference_Actual_vs_Contract','sum')).reset_index(),use_container_width=True)
    st.subheader('Per-trip comparison: contracted vs actual paid')
    st.dataframe(view[['Source','Trip_Date','Trip_ID','Trip_Name','City','Driver_Name','Miles','Gross_Pay','Policy_Driver_Pay','Actual_Pay','Difference_Actual_vs_Contract','Policy_Status']],use_container_width=True)
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        view.to_excel(w,sheet_name='Trips',index=False)
        POLICY_DF[POLICY_DF.State==code].to_excel(w,sheet_name='Policy',index=False)
    st.download_button('Download report — Excel',out.getvalue(),f'{key_prefix}_{code}_report.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'dl_xlsx_{key_prefix}_{code}')
    st.download_button('Download report — CSV',view.to_csv(index=False).encode('utf-8-sig'),f'{key_prefix}_{code}_report.csv','text/csv',key=f'dl_csv_{key_prefix}_{code}')
    pdf_bytes=pdf_report(view,code,name)
    if pdf_bytes:
        st.download_button('Download report — PDF',pdf_bytes,f'{key_prefix}_{code}_report.pdf','application/pdf',key=f'dl_pdf_{key_prefix}_{code}')
    else:
        st.warning('PDF download is unavailable until reportlab is installed. Add reportlab to requirements.txt and reboot the app.')

def company_page(company):
    st.title(f'{company} Reports')
    st.caption('Upload company reports here. Results are stored and displayed inside the matching state pages.')
    if company == 'First':
        files=st.file_uploader('First reports — any file format (Excel, CSV, PDF, TXT)',type=None,accept_multiple_files=True,key='company_first_upload')
    else:
        files=st.file_uploader('EverDriven reports — any file format (Excel, CSV, PDF, TXT)',type=None,accept_multiple_files=True,key='company_ever_upload')
    if files:
        try:
            df=pd.concat([read_any(f,company) for f in files],ignore_index=True)
            st.session_state[f'{company}_df']=df
            st.session_state[f'{company}_files']=[(f.name,f.getvalue()) for f in files]
            st.success(f'Loaded {len(df):,} trips from {len(files)} file(s).')
        except Exception as e:
            st.error(f'Could not read the {company} files: {e}'); return
    df=st.session_state.get(f'{company}_df',pd.DataFrame())
    if df.empty: st.info('Upload one or more files to begin.'); return
    if company=='First': df=df[df.State.isin(['OR','N.CA','S.CA','SAC','NM','IL','AK','MON'])]
    else: df=df[df.State.isin(['NE','KS'])]
    state=st.selectbox('Choose state',sorted(df.State.dropna().unique()),key=f'{company}_state_filter') if not df.empty else None
    view=df[df.State==state] if state else df
    show_metrics_and_tables(view,state or 'ALL',company,f'{company.lower()}_company')
    original_files=st.session_state.get(f'{company}_files',[])
    if original_files:
        st.download_button('Download original uploaded files — ZIP',originals_zip(original_files),f'{company.lower()}_original_files.zip','application/zip',key=f'zip_{company.lower()}')

def state_page(code,name):
    st.title(f'{name} — Analysis Dashboard')
    st.subheader('Official Pricing Policy')
    st.table(POLICY_DF[POLICY_DF.State==code][['Vehicle_Type','Min_Miles','Max_Miles','Policy_Pay','Per_Mile_Rate','Note']])
    st.subheader('Upload state report for the original financial analysis')
    state_files=st.file_uploader(f'{name} state reports — any file format',type=None,accept_multiple_files=True,key=f'state_{code}')
    if state_files:
        try:
            state_df=pd.concat([read_any(f,'First') for f in state_files],ignore_index=True)
            state_view=state_df[state_df.State==code]
            st.session_state[f'state_df_{code}']=state_view
            st.session_state[f'state_files_{code}']=[(f.name,f.getvalue()) for f in state_files]
        except Exception as e: st.error(f'Could not read state report: {e}'); return
    state_view=st.session_state.get(f'state_df_{code}',pd.DataFrame())
    has_company_data = False
    if not state_view.empty:
        st.header('Original State Analysis')
        show_metrics_and_tables(state_view, code, name, f'state_{code}')

    # Keep each company completely separate. Each one is compared with the
    # contract policy for this state/city, never with the other company.
    for source in ['First', 'EverDriven']:
        stored = st.session_state.get(f'{source}_df', pd.DataFrame())
        if stored.empty:
            continue
        company_view = stored[stored.State == code].copy()
        if company_view.empty:
            continue
        has_company_data = True
        st.header(f'{source} — Contract Rate Comparison')
        st.caption('Actual Pay = Net Pay from this company report. Difference = Actual Pay − Contract Rate for this state/city.')
        show_metrics_and_tables(company_view, code, name, f'{source.lower()}_state_{code}')

    if state_view.empty and not has_company_data:
        st.info('Upload the state report here, or upload First/EverDriven reports from their sidebar pages first.')
    state_originals=st.session_state.get(f'state_files_{code}',[])
    if state_originals:
        st.download_button('Download original state files — ZIP',originals_zip(state_originals),f'{code}_original_state_files.zip','application/zip',key=f'zip_state_{code}')

st.set_page_config(page_title="Hatem's B.T. Analyzer",layout='wide')
st.sidebar.title('Navigation')
menu=st.sidebar.radio('Choose section',['State Reports','First Reports','EverDriven Reports'])
if menu=='First Reports': company_page('First')
elif menu=='EverDriven Reports': company_page('EverDriven')
else:
    selected=st.sidebar.selectbox('Choose state',list(STATES),format_func=lambda x:STATES[x])
    state_page(selected,STATES[selected])
