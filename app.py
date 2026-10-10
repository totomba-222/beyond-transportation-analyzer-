from __future__ import annotations
import io, re, sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

DB_FILE = 'history.db'

STATES = {
    'OR': 'Oregon', 'N.CA': 'North California', 'S.CA': 'South California',
    'AK': 'Alaska', 'IL': 'Illinois', 'NM': 'New Mexico',
    'SAC': 'Sacramento', 'MON': 'Monterey',
    'RS&AZ': 'Riverside & Arizona', 'AZ': 'Arizona', 'WA': 'Washington',
    'NE': 'Nebraska', 'KS': 'Kansas',
}

SPECIAL_DRIVER_STATE = {
    'mohammed emad bedaer': 'AZ',
    'saif said awda': 'AZ',
    'habes al tayyeb': 'SAC',
    'suhaib yousef batayneh': 'SAC',
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
    'NE': ['Omaha', 'Lincoln'],
    'KS': ['Wichita', 'Topeka', 'Overland Park', 'Kansas City'],
}


def clean(x):
    return re.sub(r'\s+', ' ', str(x or '').strip()).lower()


def vehicle_from(name):
    s = clean(name).upper()
    return 'Minivan' if ('MINIVAN' in s or 'M-VAN' in s or 'HCV' in s or re.search(r'(^|[ (])M([ )]|$)', s)) else 'Sedan'


def city_from(name):
    s = clean(name).upper()
    cities = [
        'McMinnville', 'Wilsonville', 'Portland', 'Gresham', 'Tigard', 'Roseburg',
        'Molalla', 'Lincoln City', 'North Bend', 'Newberg', 'Salem', 'Gladstone',
        'Troutdale', 'Corvallis', 'Woodburn', 'Clackamas', 'West Linn', 'Milwaukie',
        'Benicia', 'Berkeley', 'Richmond', 'San Leandro', 'Sacramento', 'San Diego',
        'Los Angeles', 'Anchorage', 'Monterey', 'Elgin', 'Carol Stream', 'Chicago',
        'Albuquerque', 'Omaha', 'Lincoln', 'Wichita', 'Topeka', 'Overland Park',
        'Kansas City',
    ]
    for city in cities:
        if city.upper() in s:
            return city
    return 'Unknown'

def state_from(name, company=''):
    s = f'{name} {company}'.upper()
    if 'WASHINGTON' in s or 'SEATTLE' in s or re.search(r'(^|\s)WA(\s|$)', s):
        return 'WA'
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
    if 'NEBRASKA' in s or 'OMAHA' in s:
        return 'NE'
    if 'KANSAS' in s or 'WICHITA' in s or 'TOPEKA' in s or 'OVERLAND PARK' in s:
        return 'KS'
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
    if 'SOUTH CA' in s or 'S.CA' in s or 'SAN DIEGO' in s or 'LOS ANGELES' in s:
        return 'S.CA'
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
    {'State': 'WA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'KS', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
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
        # Consolidated month-end snapshots used for month-over-month KPI comparison.
        c.execute('''CREATE TABLE IF NOT EXISTS monthly_summary
            (period TEXT PRIMARY KEY, saved_on TEXT, runs INTEGER, covered_runs INTEGER,
             revenue REAL, state_revenue REAL, payment REAL, profit REAL, margin REAL,
             amount_due REAL, non_compliant INTEGER, loss REAL)''')


init_db()


def save_monthly_snapshot(period, total):
    """Store/overwrite the consolidated KPIs for a given period (e.g. '2026-10')."""
    with sqlite3.connect(DB_FILE) as c:
        c.execute('''INSERT OR REPLACE INTO monthly_summary
            (period, saved_on, runs, covered_runs, revenue, state_revenue, payment,
             profit, margin, amount_due, non_compliant, loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (period, datetime.now().strftime('%Y-%m-%d %H:%M'),
             int(total['runs']), int(total.get('covered_runs') or 0),
             _num(total['revenue']), _num(total['state_revenue']), _num(total['payment']),
             _num(total['profit']), _num(total['margin']), _num(total['amount_due']),
             int(total['non_compliant']), _num(total['loss'])))


def all_monthly_snapshots():
    with sqlite3.connect(DB_FILE) as c:
        return pd.read_sql_query(
            'SELECT * FROM monthly_summary ORDER BY period ASC', c)


def previous_monthly_snapshot(exclude_period=None):
    """Return the most recent saved snapshot, optionally skipping the current period."""
    snaps = all_monthly_snapshots()
    if snaps.empty:
        return None
    if exclude_period is not None:
        snaps = snaps[snaps['period'] != exclude_period]
    if snaps.empty:
        return None
    return snaps.iloc[-1].to_dict()


def _num(v):
    """NaN-safe float for SQLite storage."""
    try:
        return None if pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


def save_weekly_summary(state_code, d, total):
    """Persist the legacy weekly summary without changing the new matching data."""
    raw_dates = d.get('Trip_Date', pd.Series(dtype='datetime64[ns]'))
    dates = pd.to_datetime(raw_dates, errors='coerce').dropna()
    week_start = dates.min().strftime('%Y-%m-%d') if not dates.empty else ''
    week_end = dates.max().strftime('%Y-%m-%d') if not dates.empty else ''
    with sqlite3.connect(DB_FILE) as c:
        c.execute('''INSERT INTO weekly_summary
            (analysis_date, state, week_start_date, week_end_date, total_trips,
             total_revenue, total_driver_cost, total_margin, total_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (datetime.now().strftime('%Y-%m-%d'), state_code, week_start, week_end,
             total['runs'], total['revenue'], total['payment'], total['profit'], total['loss']))


def historical_summary(state_code):
    with sqlite3.connect(DB_FILE) as c:
        return pd.read_sql_query(
            'SELECT * FROM weekly_summary WHERE state = ? ORDER BY week_start_date DESC',
            c, params=[state_code])


def policy_pay(state, miles, vehicle='Unknown', city='Unknown'):
    """Contracted driver pay from city/vehicle rules first, then state rules."""
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
    if float(rule.Per_Mile_Rate) > 0:
        return round(float(rule.Policy_Pay) + max(0.0, miles - 16) * float(rule.Per_Mile_Rate), 2), 'Matched - state policy'
    return float(rule.Policy_Pay), 'Matched - state policy'


def _pick(x, up, names, default=0):
    for n in names:
        if n in up:
            return x[up[n]]
    return pd.Series([default] * len(x), index=x.index)


def max_fixed_policy(state):
    """Highest supplied driver-pay value for a state (used when miles are missing)."""
    vals = []
    for _, r in POLICY_DF[POLICY_DF.State == state].iterrows():
        if 'Not supplied' not in str(r.Note) and float(r.Policy_Pay) > 0:
            vals.append(float(r.Policy_Pay))
    for cty in CITIES.get(state, []):
        for rule in CITY_POLICIES.get(cty, []):
            vals.append(float(rule['base']))
    if state == 'SAC':
        for rules in SACRAMENTO_POLICIES.values():
            for rule in rules:
                vals.append(float(rule['base']))
    return max(vals) if vals else 0.0

DRIVER_STATE = {
    'abdelhakem benazouz': 'AK', 'ahmed (mo)': 'AK', 'alamin mohammed y bakor': 'AK', 'ali adam babeker': 'AK',
    'bahati basoma': 'AK', 'boniface bahiziri': 'AK', 'brahima conde': 'AK', 'dehanyi ruiz piti (mo)': 'AK',
    'faisal seifou mahamat eltahir': 'AK', 'fausta piti montero': 'AK', 'ildephonse tshimpumpu': 'AK',
    'james ken puol': 'AK', 'jeremie kitenge katumba': 'AK', 'jose antonio abreu': 'AK',
    'julio e victoriano': 'AK', 'magali de los angeles garcia': 'AK', 'mansoor saleh mohammed al ansy': 'AK',
    'mohamed ayoub': 'AK', 'mustafa mohamed': 'AK', 'noreldin saddig osaman': 'AK',
    'pedro julio victoriano , (mo)': 'AK', 'yajaira mercedes rodriguez (mo)': 'AK', 'awad ali arbab': 'IL',
    'judith mutalegwa kizungu': 'IL', 'martin bugere': 'IL', 'total': 'IL', 'abdalrahman omer fadlalla': 'N.CA',
    'abdulfatah ali alowdi': 'N.CA', 'abdulgaleel a albadani': 'N.CA', 'abdullah ahmed eissa': 'N.CA',
    'abdulrahman alnagar alnagar': 'N.CA', 'abeer ahmad dhaifallah': 'N.CA', 'ahmed musaad almakkawi': 'N.CA',
    'alal mohammed bosh': 'N.CA', 'ali saleh hassan': 'N.CA', 'alsadig m mohammed': 'N.CA',
    'amer ali alabshalah': 'N.CA', 'ammar alammari': 'N.CA', 'asma mohammed alhamdani': 'N.CA',
    'fares ameen alshalh': 'N.CA', 'habes al tayyeb': 'SAC', 'hassan mahmoud hassan': 'N.CA',
    'hesham alrawhani': 'N.CA', 'hiadar elsayed': 'N.CA', 'husni mubarik': 'N.CA', 'ibrahim m elsayed': 'N.CA',
    'isam qadari': 'N.CA', 'lulit girma bune': 'N.CA', 'mohamed ahmed hugais': 'N.CA',
    'mohamed hussein altayeb abdalla': 'N.CA', 'mohamed omar ali': 'N.CA', 'mohamed omir': 'N.CA',
    'mohammed ahmed haneen': 'N.CA', 'mohammed h adam': 'N.CA', 'mohaned abdelazim ahmed elwali': 'N.CA',
    'muhammad laiq': 'N.CA', 'mustafa ali albarea': 'N.CA', 'mustafa hassan abdalkareem': 'N.CA',
    'nagi alnaeem': 'N.CA', 'nagibah e alghazali': 'N.CA', 'omer omer': 'N.CA', 'rashid masood malik': 'N.CA',
    'salah hassan': 'N.CA', 'samir m abas': 'N.CA', 'siddieg basher khair': 'N.CA',
    'snose omar hamid ali': 'N.CA', 'solomon bekkele': 'N.CA', 'suhaib yousef batayneh': 'SAC',
    'sultan alhalemi': 'N.CA', 'wadah alomaisi alomaisi': 'N.CA', 'yeshi challa': 'N.CA',
    'yousef yahya alzawkari': 'N.CA', 'abdelaziz dafi': 'NM', 'adam ait azzat': 'NM', 'adonis gonzalez': 'NM',
    'alexis santos': 'NM', 'angely wladiuska carrero': 'NM', 'ayman awad': 'NM', 'brahim bouhamadi': 'NM',
    'christine abrego leyva': 'NM', 'danier requejo': 'NM', 'dayanys pie rodriguez': 'NM',
    'fitsum t tessema': 'NM', 'hiter requejo pena': 'NM', 'irvin diego llanes': 'NM',
    'jennifer soes alizon': 'NM', 'jumana f naser': 'NM', 'khalil asfan': 'NM', 'lazaro raciel rosendo': 'NM',
    'lucia c rosendo': 'NM', 'mayelin rives santiesteban': 'NM', 'mohammad m al bitari': 'NM',
    'mourad adil': 'NM', 'nafeesa hakimi': 'NM', 'najib fettah': 'NM', 'niazbina joyan': 'NM',
    'radwan soueidan': 'NM', 'raisa rosendo': 'NM', 'rasem s alessa': 'NM',
    'robert luis cabrera ibargoyin': 'NM', 'rodney perez': 'NM', 'wilder antonio montejo arencibia': 'NM',
    'yaremys rodriguez rosendo': 'NM', 'yasmany carmona luna': 'NM', 'yoel graveran': 'NM',
    'yosmer armando carrero': 'NM', 'yuder casanova robles': 'NM', 'zajary laza chapotin': 'NM',
    'zeinab ali': 'NM', 'zohra joyan': 'NM', 'abdoun abdulmutalb hassan abdoun': 'OR', 'abdulazlz hamwl': 'OR',
    'adham hammadeh': 'OR', 'aicha orabi': 'OR', 'alaa hassan alhalaqi': 'OR',
    'asalia azucena escobedo barrios de giron': 'OR', 'basem chami': 'OR', 'bashka hussein abdirahman': 'OR',
    'djamal ali alkhali': 'OR', 'doangjok otan': 'OR', 'douglas omar giron': 'OR', 'emad h zaki': 'OR',
    'getachew dadi areda': 'OR', 'ghofran aldudu': 'OR', 'hadeel m al imam': 'OR', 'hafizullah kakar': 'OR',
    'hanan mezher alhashimi': 'OR', 'hasan ammar alkadi': 'OR', 'hashmatullah alam': 'OR',
    'hussein ibrahim alsheikh': 'OR', 'hussien al akraa': 'OR', 'iayad nazmi mardinli': 'OR',
    'issa a ghallan': 'OR', 'jaafar jaafar': 'OR', 'julie ali hussein': 'OR', 'kassaye amaha medhin': 'OR',
    'katy martinez barboza': 'OR', 'mahamat noh': 'OR', 'maram issa ghallan': 'OR', 'mohamad ali alakraa': 'OR',
    'nasri abdirahman hussen': 'OR', 'sanoussi ali alkhali': 'OR', 'sara patricia benitez sosa': 'OR',
    'thet naing tun': 'OR', 'waeel al auosh': 'OR', 'yahya alakraa': 'OR', 'zainab gheni': 'OR',
    'abla suleiman': 'RS&AZ', 'ahmad jaarah': 'RS&AZ', 'akram awad': 'RS&AZ', 'alberto ramirez': 'RS&AZ',
    'arette celeste eredia': 'RS&AZ', 'ashu no last name': 'RS&AZ', 'atta ul mohsin': 'RS&AZ',
    'avinash tiwari': 'RS&AZ', 'aziza rayan': 'RS&AZ', 'azmi maghathe': 'RS&AZ', 'bassel bahnassi': 'RS&AZ',
    'dana r dbiesi': 'RS&AZ', 'denakhalil mahmoud al shoukha': 'RS&AZ', 'fuad aleiadih': 'RS&AZ',
    'heba al nser': 'RS&AZ', 'himanshu gupta': 'RS&AZ', 'hoda sharaby': 'RS&AZ', 'iyad yousef hamdan': 'RS&AZ',
    'jihane benchaouch': 'RS&AZ', 'khalid abu sarriyeh': 'RS&AZ', 'leen albahnassi': 'RS&AZ',
    'leila hamad rayan': 'RS&AZ', 'lithe farouk abdullah': 'RS&AZ', 'mandeep singh': 'RS&AZ',
    'maria rivera-ramirez': 'RS&AZ', 'miriam dawod rayan': 'RS&AZ', 'mohammad hamdan ahmad alsutari': 'RS&AZ',
    'mohammed emad bedaer': 'AZ', 'mona bazzoun': 'RS&AZ', 'mostafa safwan alhakim': 'RS&AZ',
    'mostafa sharaby': 'RS&AZ', 'mukesh kumar': 'RS&AZ', 'mustafa f m zatar': 'RS&AZ',
    'nabeel aldabbas': 'RS&AZ', 'nada a suleiman': 'RS&AZ', 'nada abusnoubar': 'RS&AZ',
    'nesrin elshabasy': 'RS&AZ', 'niveen mohd abdel aziz abbad': 'RS&AZ', 'rana muhammad abrar bashir': 'RS&AZ',
    'rana nazmi abu samrah salaymeh': 'RS&AZ', 'rehan ahmad malik': 'RS&AZ',
    'ruben bruno ramirez rivera': 'RS&AZ', 'safwan alhakim': 'RS&AZ', 'sagar sagar': 'RS&AZ',
    'saif said awda': 'AZ', 'salah musa hussein': 'RS&AZ', 'sandeep singh bajwa': 'RS&AZ',
    'saqib hussain': 'RS&AZ', 'sukhjit singh': 'RS&AZ', 'syed saleem ahmad': 'RS&AZ', 'tahani hussain': 'RS&AZ',
    'taquia davis': 'RS&AZ', 'taranjeet singh': 'RS&AZ', 'thaer abusnoubar': 'RS&AZ',
}

# ---------------------------------------------------------------------------
# DATA MODEL (First report is the single source of truth)
#   First_Revenue       = company revenue / trip price from First Alt
#   State_Contract_Price = agreed trip price shown in the state report
#   Policy_Pay          = driver payment from the pricing policy (entered by you)
#   Profit              = First_Revenue - Policy_Pay
#   State_Difference    = State_Contract_Price - First_Revenue (a separate
#                         reconciliation; it is never used as driver payment)
#   States with no supplied policy (NM, IL, RS&AZ, AZ) are NOT checked.
# ---------------------------------------------------------------------------
NO_POLICY = {'NM', 'IL', 'RS&AZ', 'AZ', 'SAC', 'WA', 'NE', 'KS'}


def has_policy(state):
    return state not in NO_POLICY and max_fixed_policy(state) > 0


def iso_week(dt):
    try:
        return int(pd.Timestamp(dt).isocalendar().week)
    except Exception:
        return 0


def _read_pdf_candidates(file_obj):
    """Extract table candidates from a PDF report using pdfplumber.

    Each returned DataFrame is a possible trip table; the shared scoring logic
    in _read_report_table then picks the best one by column names.
    """
    try:
        import pdfplumber
    except Exception:
        return []
    wanted = {'DRIVER NAME', 'DRIVER', 'TRIP NAME', 'REVENUE', 'NET PAY',
              'TOTAL MILES', 'MILES', 'PAY', 'PAYMENT', 'DATE', 'TRIP DATE', 'GROSS PAY'}
    candidates = []
    try:
        file_obj.seek(0)
    except Exception:
        pass
    try:
        pdf = pdfplumber.open(file_obj)
    except Exception:
        return []
    with pdf:
        for page in pdf.pages:
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for table in tables:
                if not table or len(table) < 2:
                    continue
                grid = [[('' if cell is None else str(cell).strip()) for cell in row]
                        for row in table]
                # Locate the header row inside the first rows of the table.
                header_idx = 0
                for i in range(min(12, len(grid))):
                    vals = {clean(v).upper() for v in grid[i]}
                    if vals & wanted:
                        header_idx = i
                        break
                header = grid[header_idx]
                cols, seen = [], {}
                for j, h in enumerate(header):
                    label = h or f'col{j}'
                    if label in seen:
                        seen[label] += 1
                        label = f'{label}.{seen[label]}'
                    else:
                        seen[label] = 0
                    cols.append(label)
                body = grid[header_idx + 1:]
                if not body:
                    continue
                width = len(cols)
                body = [(r + [''] * width)[:width] for r in body]
                frame = pd.DataFrame(body, columns=cols)
                frame = frame.replace('', pd.NA).dropna(how='all')
                if not frame.empty:
                    candidates.append(frame)
    return candidates


def _read_report_table(file_obj, preferred_sheet=None):
    """Read a report even when Excel has title rows above the real header."""
    name = str(getattr(file_obj, 'name', '')).lower()
    if name.endswith('.csv'):
        candidates = [pd.read_csv(file_obj, header=0)]
    elif name.endswith('.pdf'):
        candidates = _read_pdf_candidates(file_obj)
    else:
        book = pd.ExcelFile(file_obj, engine='openpyxl')
        sheets = ([preferred_sheet] if preferred_sheet in book.sheet_names else []) + [
            sh for sh in book.sheet_names if sh != preferred_sheet]
        candidates = [pd.read_excel(file_obj, sheet_name=sh, header=0, engine='openpyxl')
                      for sh in sheets]
        # If the first pass did not find a useful header, inspect the first 20 rows.
        for sh in sheets[:3]:
            raw = pd.read_excel(file_obj, sheet_name=sh, header=None, engine='openpyxl')
            for i in range(min(20, len(raw))):
                vals = {clean(v).upper() for v in raw.iloc[i].tolist()}
                if vals & {'DRIVER NAME', 'DRIVER', 'TRIP NAME', 'REVENUE', 'NET PAY',
                           'TOTAL MILES', 'MILES'}:
                    candidates.append(pd.read_excel(file_obj, sheet_name=sh, header=i,
                                                    engine='openpyxl'))
                    break
    wanted = {'DRIVER NAME', 'DRIVER', 'TRIP NAME', 'REVENUE', 'NET PAY', 'TOTAL MILES', 'MILES'}
    scored = []
    for position, frame in enumerate(candidates):
        frame = frame.copy()
        frame.columns = [str(c).strip() for c in frame.columns]
        upper = {str(c).strip().upper() for c in frame.columns}
        if not (upper & wanted):
            continue
        normalized = {re.sub(r'[^A-Z0-9]+', '', c) for c in upper}
        # A trip-level table with Net Pay, driver, route and miles wins over
        # a summary table that happens to contain only Revenue.
        score = (100 if 'NETPAY' in normalized else 0)
        score += 20 if ('DRIVERNAME' in normalized or 'DRIVER' in normalized) else 0
        score += 20 if ('TRIPNAME' in normalized or 'TRIP' in normalized or 'ROUTE' in normalized) else 0
        score += 20 if ('TOTALMILES' in normalized or 'MILES' in normalized or 'DISTANCE' in normalized) else 0
        score += 10 if ('DATE' in normalized or 'TRIPDATE' in normalized) else 0
        scored.append((score, -position, frame))
    if scored:
        return max(scored, key=lambda item: (item[0], item[1]))[2]
    return candidates[0] if candidates else pd.DataFrame()


def _normal_key(v):
    if pd.isna(v):
        return ''
    return re.sub(r'[^a-z0-9]+', ' ', str(v).lower()).strip()


def _column_map(columns):
    """Map report columns by normalized names, tolerating spaces, underscores and punctuation."""
    return {re.sub(r'[^A-Z0-9]+', '', str(c).upper()): c for c in columns}


def _pick_norm(frame, names, default=''):
    cmap = _column_map(frame.columns)
    for name in names:
        key = re.sub(r'[^A-Z0-9]+', '', str(name).upper())
        if key in cmap:
            return frame[cmap[key]]
    return pd.Series(default, index=frame.index)


def _date_key(v):
    dt = pd.to_datetime(v, errors='coerce')
    return '' if pd.isna(dt) else dt.strftime('%Y-%m-%d')


def _price_column(up):
    for n in ['REVENUE', 'REV', 'NET PAY', 'DRIVER PAY', 'DRIVER RATE', 'CONTRACT PRICE',
              'PRICE', 'RATE', 'PAYMENT', 'AMOUNT', 'TOTAL PAY', 'TOTAL', 'GROSS PAY']:
        if n in up:
            return up[n]
    return None


def _number_series(values):
    """Parse currency/numeric cells such as '$1,234.50' reliably."""
    return pd.to_numeric(values.astype(str).str.replace(r'[$,()]', '', regex=True)
                         .str.replace('-', '-', regex=False), errors='coerce')

def _state_code_from_text(text):
    """State detection with token-aware matching (avoids OR matching words)."""
    s = re.sub(r'[^A-Z0-9]+', ' ', str(text).upper()).strip()
    if 'NEW MEXICO' in s or re.search(r'(^| )NM( |$)', s) or 'ABQ' in s:
        return 'NM'
    if 'WASHINGTON' in s or re.search(r'(^| )WA( |$)', s) or 'SEATTLE' in s:
        return 'WA'
    if 'NORTH CA' in s or 'NORTH CALIFORNIA' in s or 'NORTHCAROLINA' in s or re.search(r'(^| )N CA( |$)', s):
        return 'N.CA'
    if 'SOUTH CA' in s or 'SOUTH CALIFORNIA' in s or re.search(r'(^| )S CA( |$)', s):
        return 'S.CA'
    if 'OREGON' in s or re.search(r'(^| )OR( |$)', s):
        return 'OR'
    if 'ALASKA' in s or 'ANCHORAGE' in s or re.search(r'(^| )AK( |$)', s):
        return 'AK'
    if 'CROSS BORDER' in s or ('RS' in s and 'AZ' in s):
        return 'RS&AZ'
    if 'RIVERSIDE' in s:
        return 'RS&AZ'
    if 'ARIZONA' in s or re.search(r'(^| )AZ( |$)', s):
        return 'AZ'
    if 'SACRAMENTO' in s or re.search(r'(^| )SAC( |$)', s):
        return 'SAC'
    if 'MONTEREY' in s or re.search(r'(^| )MON( |$)', s):
        return 'MON'
    if 'NEBRASKA' in s or 'OMAHA' in s or re.search(r'(^| )NE( |$)', s):
        return 'NE'
    if 'KANSAS' in s or 'WICHITA' in s or 'TOPEKA' in s or 'OVERLAND PARK' in s or re.search(r'(^| )KS( |$)', s):
        return 'KS'
    if 'ILLINOIS' in s or re.search(r'(^| )IL( |$)', s):
        return 'IL'
    return 'Unknown'


def state_code_from_name(fname):
    return _state_code_from_text(fname)


def state_from_first_row(district, driver, trip, company):
    """First Alt district is authoritative; driver/trip are fallback only."""
    district_text = clean(district).upper()
    route_text = f'{clean(trip)} {clean(company)}'.upper()
    driver_key = clean(driver)
    # Route and school district identify the operating location. Washington
    # must never be folded into Oregon merely because both appear in one file.
    if ('WASHINGTON' in route_text or 'SEATTLE' in route_text
            or re.search(r'(^|\s)WA(\s|$)', route_text)
            or 'WASHINGTON' in district_text or 'SEATTLE' in district_text
            or re.search(r'(^|\s)WA(\s|$)', district_text)):
        return 'WA'
    if 'SACRAMENTO' in route_text or 'SACRAMENTO' in district_text:
        return 'SAC'
    if 'ARIZONA' in route_text or re.search(r'(^|\s)AZ(\s|$)', route_text):
        return 'AZ'
    if driver_key in SPECIAL_DRIVER_STATE:
        return SPECIAL_DRIVER_STATE[driver_key]
    district_code = _state_code_from_text(district)
    if district_code != 'Unknown':
        return district_code
    known = DRIVER_STATE.get(driver_key)
    if known:
        return known
    return state_from(trip, company)


def _read_combined_states_workbook(file_obj):
    """Read STATESREPORT-style sheets containing several blocks side by side."""
    name = str(getattr(file_obj, 'name', '')).lower()
    if not name.endswith(('.xlsx', '.xls')):
        return pd.DataFrame()
    raw = pd.read_excel(file_obj, sheet_name=0, header=None, engine='openpyxl')
    blocks = []
    header_specs = []
    for row_no, row in raw.iterrows():
        for col_no, value in enumerate(row):
            if clean(value).upper() != 'DRIVER NAME':
                continue
            ahead = [clean(v).upper() for v in row.iloc[col_no:col_no + 12].tolist()]
            if not ({'REVENUE', 'REVENUE ', 'REV'} & set(ahead)):
                continue
            # Find the revenue/payment columns belonging to this block.
            revenue_col = next((col_no + j for j, v in enumerate(ahead)
                                if v in ('REVENUE', 'REVENUE ', 'REV')), None)
            payment_col = next((col_no + j for j, v in enumerate(ahead)
                                if v in ('PAY', 'PAYMENT', 'PAYMENT ')), None)
            if revenue_col is None:
                continue
            title = raw.iat[row_no - 1, col_no] if row_no else getattr(file_obj, 'name', '')
            code = state_code_from_name(title)
            if code == 'Unknown':
                code = state_code_from_name(getattr(file_obj, 'name', ''))
            # Trip-wise block has DATE/TRIP NAME/MILES after DRIVER NAME.
            date_col = next((col_no + j for j, v in enumerate(ahead)
                             if v in ('DATE', 'TRIP DATE')), None)
            trip_col = next((col_no + j for j, v in enumerate(ahead)
                             if v in ('TRIP NAME', 'TRIP', 'NAME')), None)
            miles_col = next((col_no + j for j, v in enumerate(ahead)
                              if v in ('MILES', 'TOTAL MILES')), None)
            blocks.append({'start': row_no + 1, 'col': col_no, 'revenue': revenue_col,
                           'payment': payment_col, 'date': date_col, 'trip': trip_col,
                           'miles': miles_col, 'code': code,
                           'width': 6 if date_col is not None else 3})
            header_specs.append((row_no, col_no))
    if not blocks:
        return pd.DataFrame()
    out = []
    for b in blocks:
        next_headers = [h for h, c in header_specs
                        if h > b['start'] and b['col'] <= c < b['col'] + b['width']]
        end = min(next_headers) if next_headers else len(raw)
        for i in range(b['start'], end):
            driver = raw.iat[i, b['col']]
            price = raw.iat[i, b['revenue']]
            if pd.isna(driver) or clean(driver) in {'', 'total', 'totals', 'grand total'}:
                continue
            price_num = _number_series(pd.Series([price])).iloc[0]
            if pd.isna(price_num):
                continue
            out.append({
                'State': b['code'], 'Driver_Key': _normal_key(driver),
                'Trip_Key': _normal_key(raw.iat[i, b['trip']]) if b['trip'] is not None else '',
                'Date_Key': _date_key(raw.iat[i, b['date']]) if b['date'] is not None else '',
                'Miles_Key': float(_number_series(pd.Series([raw.iat[i, b['miles']]])).fillna(0).iloc[0]) if b['miles'] is not None else 0.0,
                'State_Price': float(price_num),
                'State_Pay': (float(_number_series(pd.Series([raw.iat[i, b['payment']]])).iloc[0])
                              if b['payment'] is not None and not pd.isna(_number_series(pd.Series([raw.iat[i, b['payment']]])).iloc[0]) else pd.NA),
                'Source_File': getattr(file_obj, 'name', '')})
    return pd.DataFrame(out)

def _normalise_state_rows(x, code, source_file):
    x = x.copy()
    x.columns = [str(c).strip() for c in x.columns]
    up = {c.upper(): c for c in x.columns}
    price_col = _price_column(up)
    if not price_col:
        return pd.DataFrame()
    out = pd.DataFrame(index=x.index)
    out['State'] = code
    out['Driver_Key'] = _pick(x, up, ['DRIVER NAME', 'DRIVER'], '').map(_normal_key)
    out['Trip_Key'] = _pick(x, up, ['TRIP NAME', 'NAME', 'TRIP'], '').map(_normal_key)
    out['Date_Key'] = _pick(x, up, ['DATE', 'TRIP DATE'], '').map(_date_key)
    out['Miles_Key'] = pd.to_numeric(_pick(x, up, ['TOTAL MILES', 'MILES'], 0), errors='coerce').fillna(0).round(2)
    out['State_Price'] = _number_series(x[price_col])
    pay_col = next((up[n] for n in ['PAY', 'PAYMENT', 'DRIVER PAY'] if n in up), None)
    out['State_Pay'] = (_number_series(x[pay_col]) if pay_col else pd.Series(pd.NA, index=x.index))
    out['Source_File'] = source_file
    out = out[out['State_Price'].notna()].copy()
    # Remove report totals and blank lines, but keep legitimate zero-price rows out.
    out = out[(out['Driver_Key'] != 'total') & (out['Trip_Key'] != 'total')]
    return out.reset_index(drop=True)


def read_first(files):
    """Read First reports into trip-level rows; First remains the revenue source."""
    frames = []
    for f in files:
        preferred = 'SP ITEMIZED REPORT'
        x = _read_report_table(f, preferred)
        x.columns = [str(c).strip() for c in x.columns]
        up = {c.upper(): c for c in x.columns}
        d = pd.DataFrame(index=x.index)
        d['Driver_Name'] = _pick_norm(x, ['DRIVER NAME', 'DRIVER', 'DRIVER_NAME'], 'Unknown')
        d['District'] = _pick_norm(x, ['DISTRICT', 'STATE', 'REGION', 'AREA'], '')
        d['Trip_Name'] = _pick_norm(x, ['TRIP NAME', 'TRIP', 'NAME', 'ROUTE'], '')
        d['Trip_Date'] = pd.to_datetime(_pick_norm(x, ['DATE', 'TRIP DATE', 'TRIP_DATE'], None), errors='coerce')
        d['Miles'] = _number_series(_pick_norm(x, ['TOTAL MILES', 'MILES', 'DISTANCE', 'TRIP MILES'], 0)).fillna(0.0)
        d['First_Reported_Revenue'] = _number_series(
            _pick_norm(x, ['REVENUE', 'REV', 'GROSS PAY', 'GROSS'], pd.Series(pd.NA, index=x.index)))
        d['Net_Pay'] = _number_series(
            _pick_norm(x, ['NET PAY', 'NETPAY', 'NET', 'PAID FARE', 'PAID'], pd.Series(pd.NA, index=x.index)))
        # First Alt's Net Pay is the paid fare. If the file has no Net Pay
        # column, use Revenue as the paid-fare field.
        d['Revenue'] = d['Net_Pay'].where(d['Net_Pay'].notna(),
                                         d['First_Reported_Revenue']).fillna(0.0)
        d['Paid_Fare_Source'] = d['Net_Pay'].notna().map(
            {True: 'First Alt Net Pay', False: 'First Alt Revenue'})
        d['First_Gross'] = _number_series(_pick_norm(x, ['GROSS PAY', 'GROSS', 'REV', 'REVENUE'], 0)).fillna(0.0)
        d['Company'] = _pick_norm(x, ['SP COMPANY', 'COMPANY'], '')
        d['Source_File'] = getattr(f, 'name', '')
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    bad = {'', 'nan', 'total', 'totals', 'grand total'}
    keep = d['Driver_Name'].map(lambda v: clean(v) not in bad) & (
        (d['Revenue'] != 0) | (d['Trip_Name'].map(lambda v: clean(v) not in {'', 'nan'})))
    d = d[keep].copy()
    # Monitors / escorts (marked "(MO)" / "(Monitor)") ride ALONG with a driver;
    # they are NOT trips, so drop them from the First flow entirely so they never
    # count toward trips, revenue, driver cost or profit anywhere downstream.
    _dn = d['Driver_Name'].astype(str)
    d = d[~_dn.str.contains(r'\(mo\)|\(monitor\)|\bmonitor\b|\bmo\b', case=False, regex=True, na=False)].copy()
    d['State'] = [state_from_first_row(row['District'], row['Driver_Name'],
                                        row['Trip_Name'], row['Company'])
                  for _, row in d.iterrows()]
    d['State'] = d['State'].replace({'Unknown': 'Unassigned'})
    d['Vehicle'] = d['Trip_Name'].map(vehicle_from)
    d['City'] = d['Trip_Name'].map(city_from)
    d['Week'] = d['Trip_Date'].map(iso_week)
    pol = d.apply(lambda r: policy_pay(r['State'], r['Miles'], r['Vehicle'], r['City']), axis=1)
    d['Policy_Pay'] = [p[0] for p in pol]
    d['Policy_Note'] = [p[1] for p in pol]
    d['State_Price'] = pd.NA  # state contract price; never overwrite Policy_Pay
    d['State_Revenue'] = pd.NA
    d['State_Pay'] = pd.NA
    d['Price_Difference'] = pd.NA
    d['Price_Source'] = 'Pricing policy'
    return _recalculate(d)


def _recalculate(d):
    """Recalculate driver payment/profit and state-price reconciliation separately."""
    state_price = pd.to_numeric(d['State_Price'], errors='coerce')
    state_pay = pd.to_numeric(d.get('State_Pay', pd.Series(pd.NA, index=d.index)), errors='coerce')
    policy_price = pd.to_numeric(d['Policy_Pay'], errors='coerce')
    # Positive difference is money owed to the company by First.
    d['Price_Difference'] = state_price - d['Revenue']
    d['State_Revenue'] = state_price
    # Pricing Policy is the authoritative driver payment when it exists.
    # State-report Pay is a fallback for states without an internal policy.
    policy_available = d['State'].map(has_policy) & policy_price.gt(0)
    effective = policy_available | state_pay.notna()
    d['Checked'] = effective
    d['Policy_Pay'] = policy_price.where(effective, other=pd.NA)
    fallback_pay = state_pay.notna() & ~policy_available
    d.loc[fallback_pay, 'Policy_Pay'] = state_pay[fallback_pay]
    d.loc[policy_available, 'Price_Source'] = 'Pricing policy'
    d.loc[fallback_pay, 'Price_Source'] = 'State report Pay (no internal policy)'
    d['Driver_Pay'] = state_pay
    d['Profit'] = (d['Revenue'] - d['Policy_Pay']).where(effective, other=pd.NA)
    # Compliance is a driver-pay test. First Net Pay is a company fare and must not be
    # compared to the driver policy; use the state's payment column when available.
    d['Non_Compliant'] = policy_available & state_pay.notna() & (state_pay < policy_price - 0.01)
    d['Loss'] = (policy_price - state_pay).where(d['Non_Compliant'], other=0.0)
    return d

def read_state_origin(files):
    """Read state reports as trip-level contract prices, not one state total."""
    rows = {}
    for f in files:
        code = state_code_from_name(getattr(f, 'name', ''))
        try:
            part = _read_combined_states_workbook(f)
            if part.empty:
                x = _read_report_table(f)
                part = _normalise_state_rows(x, code, getattr(f, 'name', ''))
        except Exception:
            continue
        if part.empty:
            continue
        if code == 'Unknown' and set(part['State'].dropna().unique()) <= {'Unknown'}:
            driver_state_normalized = {_normal_key(name): state for name, state in DRIVER_STATE.items()}
            inferred = part['Driver_Key'].map(lambda n: driver_state_normalized.get(n, 'Unknown'))
            known = inferred[inferred != 'Unknown']
            if not known.empty:
                code = known.mode().iloc[0]
                part['State'] = code
        if set(part['State'].dropna().unique()) - {'Unknown'}:
            for block_code, block_rows in part.groupby('State'):
                prev = rows.get(block_code, {'rows': []})
                prev['rows'].append(block_rows.copy())
                rows[block_code] = prev
            continue
        prev = rows.get(code, {'rows': []})
        prev['rows'].append(part)
        rows[code] = prev
    result = {}
    for code, info in rows.items():
        all_rows = pd.concat(info['rows'], ignore_index=True)
        result[code] = {'rows': all_rows, 'origin': float(all_rows['State_Price'].sum()),
                        'runs': int(len(all_rows))}
    return result


def _matching_keys(driver, trip, date, miles):
    """Ordered identity keys; every key keeps Driver in the match."""
    keys = []
    if driver and trip and date and miles not in ('', 0, None):
        keys.append((driver, trip, date, miles))
    if driver and trip and date:
        keys.append((driver, trip, date))
    if driver and trip:
        keys.append((driver, trip))
    if driver and date and miles not in ('', 0, None):
        keys.append((driver, date, miles))
    # Some state workbooks (including Alaska) contain no trip ID/date.
    # Driver + miles is then the strongest safe identity; duplicates are consumed in order.
    if driver and miles not in ('', 0, None):
        keys.append((driver, '', '', miles))
    return keys


def _match_state_rows(first, state_rows):
    """Return one-to-one First->state row assignments without trip-only guessing."""
    first = first.copy()
    state_rows = state_rows.copy()
    if state_rows.empty:
        return {}
    indexes_by_key = {}
    for si, sr in state_rows.iterrows():
        values = (sr.get('Driver_Key', ''), sr.get('Trip_Key', ''),
                  sr.get('Date_Key', ''), sr.get('Miles_Key', 0))
        for key in _matching_keys(*values):
            indexes_by_key.setdefault(key, []).append(si)
    used = set()
    assignments = {}
    for fi, fr in first.iterrows():
        values = (_normal_key(fr.get('Driver_Name', '')),
                  _normal_key(fr.get('Trip_Name', '')),
                  _date_key(fr.get('Trip_Date')),
                  float(pd.to_numeric(fr.get('Miles', 0), errors='coerce') or 0))
        for key in _matching_keys(*values):
            available = [si for si in indexes_by_key.get(key, []) if si not in used]
            # A driver+miles fallback is safe only when the state report has one
            # contract price for that group. If it has several prices, the state
            # workbook omitted the route/date needed to decide which one belongs.
            if len(key) == 4 and key[1] == '' and key[2] == '':
                prices = {state_rows.at[si, 'State_Price'] for si in available
                          if pd.notna(state_rows.at[si, 'State_Price'])}
                if len(prices) != 1:
                    continue
            if available:
                si = available[0]
                used.add(si)
                assignments[fi] = si
                break
    return assignments

def apply_state_prices(d, origin):
    """Match each First trip to one state-report trip, preserving duplicates by occurrence."""
    if d.empty or not origin:
        return d
    d = d.copy()
    d['Match_Method'] = d.get('Match_Method', 'Unmatched')
    driver_states = {}
    for code, info in origin.items():
        for driver in info.get('rows', pd.DataFrame()).get('Driver_Key', pd.Series(dtype=str)).dropna():
            key = _normal_key(driver)
            if key:
                driver_states.setdefault(key, set()).add(code)
    # Uploaded state reports provide the authoritative state when a driver is unique.
    for idx, row in d.iterrows():
        states = driver_states.get(_normal_key(row.get('Driver_Name', '')), set())
        if len(states) == 1:
            d.at[idx, 'State'] = next(iter(states))
    for first_code in d['State'].dropna().unique():
        compatible = {first_code}
        if first_code == 'AZ':
            compatible.add('RS&AZ')
        if first_code == 'SAC':
            compatible.add('N.CA')
        frames = [info['rows'] for code, info in origin.items()
                  if code in compatible and 'rows' in info]
        if not frames:
            continue
        state_rows = pd.concat(frames, ignore_index=True)
        mask = d['State'].eq(first_code)
        first = d.loc[mask].copy()
        assignments = _match_state_rows(first, state_rows)
        for fi, si in assignments.items():
            d.at[fi, 'State_Price'] = state_rows.at[si, 'State_Price']
            if 'State_Pay' in state_rows.columns:
                d.at[fi, 'State_Pay'] = state_rows.at[si, 'State_Pay']
            if state_rows.at[si, 'Trip_Key'] or state_rows.at[si, 'Date_Key']:
                d.at[fi, 'Match_Method'] = 'Driver + trip/date identity'
            else:
                d.at[fi, 'Match_Method'] = 'Driver + miles occurrence match'
        # Explain rows deliberately left unmatched instead of presenting a guessed price.
        for fi in first.index:
            if pd.notna(d.at[fi, 'State_Price']):
                continue
            fk = _normal_key(d.at[fi, 'Driver_Name'])
            fm = float(pd.to_numeric(d.at[fi, 'Miles'], errors='coerce') or 0)
            candidates = state_rows[(state_rows['Driver_Key'] == fk) &
                                    (pd.to_numeric(state_rows['Miles_Key'], errors='coerce').round(2) == round(fm, 2))]
            prices = set(candidates['State_Price'].dropna().tolist())
            if len(prices) > 1:
                d.at[fi, 'Match_Method'] = 'Ambiguous: multiple state prices; route/date missing'
            elif not len(candidates):
                d.at[fi, 'Match_Method'] = 'No state row for driver + miles'
            else:
                d.at[fi, 'Match_Method'] = 'State rows exhausted for driver + miles'
    return _recalculate(d)


def unmatched_state_rows(first_df, origin, first_code):
    """Return state-report rows not consumed by the same one-to-one matcher."""
    compatible = {first_code}
    if first_code == 'AZ':
        compatible.add('RS&AZ')
    if first_code == 'SAC':
        compatible.add('N.CA')
    frames = [info['rows'].copy() for code, info in origin.items()
              if code in compatible and 'rows' in info]
    if not frames:
        return pd.DataFrame()
    state_rows = pd.concat(frames, ignore_index=True)
    first = first_df[first_df['State'].eq(first_code)].copy()
    assignments = _match_state_rows(first, state_rows)
    used = set(assignments.values())
    out = state_rows.loc[~state_rows.index.isin(used)].copy()
    if out.empty:
        return out
    out['Possible_State'] = out['Trip_Key'].map(
        lambda x: STATES.get(_state_code_from_text(x), _state_code_from_text(x)))
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# AGGREGATION & REPORT BUILDERS
# ---------------------------------------------------------------------------
def agg_block(d):
    """Core + compliance figures for a slice of runs (one state, any week set)."""
    runs = int(len(d))
    rev = float(d['Revenue'].sum())
    state_values = pd.to_numeric(d.get('State_Revenue', pd.Series(dtype=float)), errors='coerce')
    diff_values = pd.to_numeric(d.get('Price_Difference', pd.Series(dtype=float)), errors='coerce')
    state_rev = float(state_values.sum()) if state_values.notna().any() else float('nan')
    # Only a positive State Revenue minus First Net Pay is money due to Beyond.
    # Never net a negative-price group against a positive group in Consolidated.
    price_diff = float(diff_values.clip(lower=0).sum()) if diff_values.notna().any() else float('nan')
    chk = d[d['Checked']]
    policy_state = len(chk) > 0
    # Profit must compare revenue and driver pay on the SAME set of runs.
    # Only runs that actually have a driver payment (policy or state-Pay fallback)
    # may enter the profit/margin figures; otherwise revenue from no-policy runs
    # would inflate profit because their driver cost is unknown ($0).
    covered_runs = int(len(chk))
    covered_rev = float(chk['Revenue'].sum()) if policy_state else 0.0
    if policy_state:
        pay = float(chk['Policy_Pay'].sum())
        profit = covered_rev - pay
        nc = int(d['Non_Compliant'].sum())
        loss = float(d['Loss'].sum())
        profit_if = profit + loss
    else:
        pay = profit = loss = profit_if = float('nan')
        nc = 0
    amount_due = price_diff
    return {
        'runs': runs, 'revenue': rev, 'state_revenue': state_rev,
        'covered_runs': covered_runs, 'covered_revenue': covered_rev,
        'uncovered_runs': runs - covered_runs,
        'price_difference': price_diff, 'amount_due': amount_due,
        'payment': pay, 'profit': profit,
        'margin': (profit / covered_rev * 100) if (policy_state and covered_rev) else float('nan'),
        'total_runs': runs, 'compliant': (runs - nc) if policy_state else runs,
        'non_compliant': nc, 'loss': loss, 'profit_if': profit_if,
        'margin_if': (profit_if / covered_rev * 100) if (policy_state and covered_rev) else float('nan'),
        'policy_state': policy_state,
    }


def _money(v):
    return '-' if pd.isna(v) else f'${v:,.2f}'


def _pct(v):
    return '-' if pd.isna(v) else f'{v:,.1f}%'


def _int(v):
    return '-' if pd.isna(v) else f'{int(v):,}'


def _color_pos_neg(val):
    """Green for positive money/margin, red for negative, used in styled tables."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ''
    if pd.isna(v):
        return ''
    if v > 0.005:
        return 'background-color:#dcfce7; color:#065f46; font-weight:700;'
    if v < -0.005:
        return 'background-color:#fee2e2; color:#991b1b; font-weight:700;'
    return ''

def weekly_report(d):
    """Image-style weekly report: metrics as rows, weeks + total/vertical/variance cols."""
    weeks = sorted(w for w in d['Week'].dropna().unique() if w)
    blocks = {w: agg_block(d[d['Week'] == w]) for w in weeks}
    total = agg_block(d)
    wk_cols = [f'WEEK {w}' for w in weeks]
    cols = wk_cols + ['TOTAL', 'VERTICAL %', 'VARIANCE %']

    def vshare(key):
        rv = total['revenue']
        return (total[key] / rv * 100) if rv else float('nan')

    def variance(key):
        if len(weeks) < 2:
            return float('nan')
        a, b = blocks[weeks[-2]][key], blocks[weeks[-1]][key]
        if not a or pd.isna(a) or pd.isna(b):
            return float('nan')
        return (b - a) / abs(a) * 100

    rows = []
    spec = [
        ('RUNS', 'runs', _int, False),
        ('FIRST PAID FARE / NET PAY (F)', 'revenue', _money, True),
        ('STATE REVENUE (CONTRACT)', 'state_revenue', _money, True),
        ('STATE PRICE DIFFERENCE', 'price_difference', _money, True),
        ('AMOUNT DUE FROM FIRST', 'amount_due', _money, True),
        ('DRIVER PAYMENT (POLICY)', 'payment', _money, True),
        ('PROFIT', 'profit', _money, True),
        ('MARGIN', 'margin', _pct, False),
        ('__sep1__', None, None, None),
        ('TOTAL RUNS', 'total_runs', _int, False),
        ('COMPLIANT RUNS', 'compliant', _int, False),
        ('NON COMPLIANT RUNS', 'non_compliant', _int, False),
        ('TOTAL LOSS', 'loss', _money, True),
        ('PROFIT IF ALL COMPLIANT', 'profit_if', _money, True),
        ('MARGIN IF ALL COMPLIANT', 'margin_if', _pct, False),
    ]
    index = []
    for label, key, fmt, vert in spec:
        if key is None:
            index.append('PRICING-POLICY COMPLIANCE')
            rows.append({c: '' for c in cols})
            continue
        index.append(label)
        row = {}
        for w in weeks:
            row[f'WEEK {w}'] = fmt(blocks[w][key])
        row['TOTAL'] = fmt(total[key])
        row['VERTICAL %'] = _pct(vshare(key)) if vert else ''
        row['VARIANCE %'] = _pct(variance(key))
        rows.append(row)
    rep = pd.DataFrame(rows, index=index)[cols]
    return rep, total, weeks

# ---------------------------------------------------------------------------
# UI HELPERS
# ---------------------------------------------------------------------------
CARD_CSS = """
<style>
/* Keep the dark theme \u2014 only polish layout, cards and tables */
.block-container {padding-top: 2rem; max-width: 1700px;}
h1 {font-size: 2.1rem !important; font-weight: 800 !important;}
h2, h3 {font-weight: 700 !important;}
[data-testid=stDataFrame] {font-size: .98rem;}
/* KPI cards tuned for a dark background */
.kpi {background:#1e293b; color:#e2e8f0; border:1px solid #334155;
  border-left:5px solid #3b82f6; border-radius:10px; padding:14px 16px; margin:4px 0;
  box-shadow:0 2px 6px rgba(0,0,0,.35);}
.kpi .lab {font-size:.74rem; letter-spacing:.03em; color:#94a3b8 !important; text-transform:uppercase;}
.kpi .val {font-size:1.5rem; font-weight:800; margin-top:4px; color:#f1f5f9 !important;}
.kpi .delta {font-size:.82rem; font-weight:700; margin-top:3px;}
.kpi .delta.up {color:#4ade80 !important;}
.kpi .delta.down {color:#f87171 !important;}
.kpi .delta.flat {color:#94a3b8 !important;}
.kpi .prevv {font-size:.7rem; color:#94a3b8 !important; margin-top:1px;}
.state-kpi .val {font-size:1.75rem;}
.kpi.g {border-left-color:#22c55e;} .kpi.g .val {color:#4ade80 !important;}
.kpi.r {border-left-color:#ef4444;} .kpi.r .val {color:#f87171 !important;}
.kpi.o {border-left-color:#f59e0b;} .kpi.o .val {color:#fbbf24 !important;}
.kpi.p {border-left-color:#a855f7;} .kpi.p .val {color:#c084fc !important;}
/* Dark-friendly static tables */
[data-testid=stTable] table {border-collapse:collapse; width:100%; background:#1e293b;}
[data-testid=stTable] thead th {background:#1d4ed8; color:#ffffff !important; font-weight:700;
  text-align:center; padding:10px; border:1px solid #334155;}
[data-testid=stTable] tbody th {background:#0f172a; color:#e2e8f0 !important; font-weight:600; border:1px solid #334155;}
[data-testid=stTable] tbody td {padding:8px 10px; color:#e2e8f0; border:1px solid #334155;}
[data-testid=stTable] tbody tr:nth-child(even) td {background:#172033;}
</style>
"""


def kpi(col, label, value, tone=''):
    col.markdown(f'<div class="kpi {tone}"><div class="lab">{label}</div>'
                 f'<div class="val">{value}</div></div>', unsafe_allow_html=True)


def state_kpi(col, label, value, tone=''):
    """Bright, larger KPI card used by individual state reports."""
    col.markdown(f'<div class="kpi state-kpi {tone}"><div class="lab">{label}</div>'
                 f'<div class="val">{value}</div></div>', unsafe_allow_html=True)


_TONE_COLORS = {'g': '#22c55e', 'r': '#ef4444', 'o': '#f59e0b', 'p': '#a855f7', '': '#3b82f6'}
# Brighter text colors so KPI values never look plain white.
_VAL_COLORS = {'g': '#4ade80', 'r': '#f87171', 'o': '#fbbf24', 'p': '#c084fc', '': '#60a5fa'}

# matplotlib powers the donut / ratio charts. It is an optional dependency: if it
# is missing from the deployed environment (e.g. a failed install on Streamlit
# Cloud) the charts are skipped gracefully instead of crashing the whole app.
try:
    import matplotlib as _mpl
    _mpl.use('Agg')
    HAS_MPL = True
except Exception:
    HAS_MPL = False


def _show_png(container, png, **kwargs):
    """Render PNG bytes with st.image, skipping silently when empty (no mpl)."""
    if png:
        container.image(png, **kwargs)


def _mpl_png(fig):
    """Serialize a matplotlib figure to PNG bytes on the dark canvas."""
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor='#0e1117', dpi=130, bbox_inches='tight')
    import matplotlib.pyplot as plt
    plt.close(fig)
    return buf.getvalue()


def _donut_png(values, labels, colors, center=''):
    """Dark donut chart -> PNG bytes. Zero/negative slices are dropped."""
    if not HAS_MPL:
        return b''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data = [(v, l, c) for v, l, c in zip(values, labels, colors) if v and v > 0]
    if not data:
        data = [(1, 'n/a', '#334155')]
    vals = [d[0] for d in data]
    labs = [d[1] for d in data]
    cols = [d[2] for d in data]
    fig, ax = plt.subplots(figsize=(3.1, 3.1))
    fig.patch.set_facecolor('#0e1117')
    wedges, _ = ax.pie(vals, colors=cols, startangle=90,
                       wedgeprops=dict(width=0.42, edgecolor='#0e1117', linewidth=2))
    total = sum(vals)
    ax.legend(wedges, [f'{l}  ({v/total:.0%})' for l, v in zip(labs, vals)],
              loc='center', bbox_to_anchor=(0.5, -0.08), ncol=1, frameon=False,
              fontsize=8, labelcolor='#e2e8f0')
    if center:
        ax.text(0, 0, center, ha='center', va='center', color='#f1f5f9',
                fontsize=11, fontweight='bold')
    ax.set_aspect('equal')
    return _mpl_png(fig)


def _ratio_bars_png(pairs):
    """Horizontal percentage bars (label, pct 0-100, color) -> PNG bytes."""
    if not HAS_MPL:
        return b''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels = [p[0] for p in pairs]
    vals = [max(0.0, min(100.0, float(p[1]))) for p in pairs]
    cols = [p[2] for p in pairs]
    fig, ax = plt.subplots(figsize=(5.4, 0.62 * len(pairs) + 0.6))
    fig.patch.set_facecolor('#0e1117')
    ax.set_facecolor('#0e1117')
    y = range(len(pairs))
    ax.barh(list(y), [100] * len(pairs), color='#1e293b', edgecolor='#334155', height=0.6)
    ax.barh(list(y), vals, color=cols, height=0.6)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, color='#e2e8f0', fontsize=9)
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    for i, v in enumerate(vals):
        ax.text(min(v + 2, 99), i, f'{v:.1f}%', va='center', ha='left',
                color='#f1f5f9', fontsize=9, fontweight='bold')
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis='x', colors='#64748b', labelsize=7)
    ax.set_xticks([0, 25, 50, 75, 100])
    return _mpl_png(fig)


def _grouped_bars_png(frame, categories, series, title, percent=False):
    """Render the same comparison charts shown on the dashboard as PNG bytes."""
    if not HAS_MPL or frame.empty:
        return b''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data = frame.copy()
    fig, ax = plt.subplots(figsize=(8.8, max(3.4, 0.48 * len(data) + 1.2)))
    fig.patch.set_facecolor('#0e1117')
    ax.set_facecolor('#0e1117')
    x = list(range(len(data)))
    width = 0.78 / max(1, len(series))
    colors = ['#f59e0b', '#a855f7', '#22c55e', '#3b82f6']
    for i, column in enumerate(series):
        vals = pd.to_numeric(data[column], errors='coerce').fillna(0).tolist()
        bars = ax.bar([v + (i - (len(series) - 1) / 2) * width for v in x],
                      vals, width=width, label=column, color=colors[i % len(colors)])
        for bar, value in zip(bars, vals):
            label = f'{value:.1f}%' if percent else f'${value:,.0f}'
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + (max(abs(max(vals)), 1) * 0.018), label,
                    ha='center', va='bottom', fontsize=7, color='#e2e8f0')
    ax.set_title(title, color='#f1f5f9', fontsize=12, pad=12, loc='left')
    ax.set_xticks(x)
    ax.set_xticklabels(data[categories].astype(str), color='#cbd5e1', rotation=25, ha='right')
    ax.tick_params(axis='y', colors='#94a3b8', labelsize=8)
    if percent:
        ax.set_ylabel('Percent', color='#94a3b8')
    else:
        ax.set_ylabel('USD', color='#94a3b8')
    ax.grid(axis='y', color='#334155', alpha=0.45)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, labelcolor='#e2e8f0', fontsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _mpl_png(fig)


def _horizontal_bars_png(frame, category, value, title, percent=False):
    """Render a sorted horizontal comparison chart for the PDF."""
    if not HAS_MPL or frame.empty:
        return b''
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data = frame[[category, value]].dropna().sort_values(value).copy()
    vals = pd.to_numeric(data[value], errors='coerce').fillna(0).tolist()
    fig, ax = plt.subplots(figsize=(8.8, max(3.2, 0.45 * len(data) + 1.0)))
    fig.patch.set_facecolor('#0e1117')
    ax.set_facecolor('#0e1117')
    colors = ['#22c55e' if v >= 0 else '#ef4444' for v in vals]
    bars = ax.barh(data[category].astype(str), vals, color=colors)
    for bar, number in zip(bars, vals):
        label = f'{number:.1f}%' if percent else f'${number:,.0f}'
        ax.text(number + (0.3 if number >= 0 else -0.3), bar.get_y() + bar.get_height() / 2,
                label, va='center', ha='left' if number >= 0 else 'right',
                color='#e2e8f0', fontsize=8)
    ax.set_title(title, color='#f1f5f9', fontsize=12, pad=12, loc='left')
    ax.tick_params(axis='x', colors='#94a3b8', labelsize=8)
    ax.tick_params(axis='y', colors='#cbd5e1', labelsize=8)
    ax.grid(axis='x', color='#334155', alpha=0.45)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _mpl_png(fig)


def _png_data_uri(png):
    import base64
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def _pdf_friendly_html(spec):
    """Dark report markup that xhtml2pdf can render (table-based, no flexbox,
    inline row striping, base64 charts). Pure-pip engine \u2014 no system libraries."""
    from html import escape
    title = spec['title']
    subtitle = spec.get('subtitle', '')
    kpis = spec.get('kpis', [])
    note_html = spec.get('note', '')
    tables = spec.get('tables', [])
    ratios = spec.get('ratios', [])
    charts = spec.get('charts', [])
    gen = datetime.now().strftime('%Y-%m-%d %H:%M')
    report_date = datetime.now().strftime('%B %d, %Y')

    def kpi_table(items):
        if not items:
            return ''
        w = max(16, int(100 / max(1, len(items))))
        cells = ''.join(
            f'<td width="{w}%" valign="top" style="background:#1e293b;border:1px solid #334155;'
            f'border-left:5px solid {_TONE_COLORS.get(tone, tone)};padding:8px">'
            f'<span style="font-size:6pt;color:#94a3b8">{escape(str(lab)).upper()}</span><br/>'
            f'<span style="font-size:12pt;color:{_VAL_COLORS.get(tone, "#f1f5f9")}"><b>{escape(str(val))}</b></span></td>'
            for lab, val, tone in items)
        return (f'<table border="0" cellspacing="3" cellpadding="0" width="100%">'
                f'<tr>{cells}</tr></table><br/>')

    kpi_block = kpi_table(kpis)
    note_block = ''
    if note_html:
        note_block = (f'<table width="100%"><tr><td style="background:#172033;border:1px solid #334155;'
                      f'border-left:5px solid #3b82f6;padding:9px">'
                      f'<span style="font-size:7pt;color:#cbd5e1">{note_html}</span></td></tr></table><br/>')
    ratio_block = ''
    if ratios:
        ratio_block = ('<p><span style="font-size:11pt;color:#f1f5f9"><b>Financial Ratios</b></span></p>'
                       + kpi_table(ratios))
    chart_block = ''
    for cap, png in charts:
        if not png:
            continue
        chart_block += (
            f'<table width="100%"><tr><td align="center" style="padding:4px">'
            f'<img src="{_png_data_uri(png)}" style="width:340px"/><br/>'
            f'<span style="font-size:7pt;color:#94a3b8">{escape(cap)}</span></td></tr></table><br/>')
    sections = ''
    for sec_title, df, fmt, posneg in tables:
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        thead = ''.join(
            f'<td style="background:#1d4ed8;border:1px solid #334155;padding:6px">'
            f'<span style="font-size:8pt;color:#ffffff"><b>{escape(str(c))}</b></span></td>' for c in cols)
        body = ''
        for i, (_, r) in enumerate(df.iterrows()):
            rowbg = '#172033' if i % 2 else '#1e293b'
            tds = ''
            for c in cols:
                v = r[c]
                f = fmt.get(c)
                txt = f(v) if f else ('\u2014' if (v is None or (not isinstance(v, str) and pd.isna(v))) else str(v))
                align = 'right' if f else 'left'
                bg, fg, bold = rowbg, '#e2e8f0', ''
                if c in posneg:
                    try:
                        fv = float(v)
                        if fv > 0.005:
                            bg, fg, bold = '#dcfce7', '#065f46', 'b'
                        elif fv < -0.005:
                            bg, fg, bold = '#fee2e2', '#991b1b', 'b'
                    except (TypeError, ValueError):
                        pass
                inner = escape(txt)
                if bold:
                    inner = f'<b>{inner}</b>'
                tds += (f'<td align="{align}" valign="top" style="background:{bg};border:1px solid #334155;'
                        f'padding:5px"><span style="font-size:7pt;color:{fg}">{inner}</span></td>')
            body += f'<tr>{tds}</tr>'
        sections += (
            f'<p><span style="font-size:11pt;color:#f1f5f9"><b>{escape(sec_title)}</b></span></p>'
            f'<table border="0" cellspacing="0" cellpadding="0" width="100%">'
            f'<tr>{thead}</tr>{body}</table><br/>')
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
@page {{
  size: a4 landscape; margin: 1.2cm; background-color: #0e1117;
  @frame content_frame {{ left:1.2cm; width:27.3cm; top:1.2cm; height:17.3cm; }}
  @frame footer_frame {{ -pdf-frame-content: footerContent; left:1.2cm; width:27.3cm; top:18.7cm; height:0.9cm; }}
}}
body {{ background-color:#0e1117; font-family: Helvetica, Arial, sans-serif; }}
td {{ font-family: Helvetica, Arial, sans-serif; }}
</style></head>
<body>
<table width="100%"><tr><td align="center" valign="middle" height="430">
<span style="font-size:12pt;color:#60a5fa;letter-spacing:3px"><b>BEYOND TRANSPORTATION</b></span><br/><br/>
<span style="font-size:30pt;color:#f8fafc"><b>{escape(title)}</b></span><br/><br/>
<span style="font-size:11pt;color:#94a3b8">{escape(subtitle)}</span><br/><br/><br/>
<span style="font-size:9pt;color:#cbd5e1"><b>&nbsp;&nbsp;FINANCIAL REPORT&nbsp;&nbsp;</b></span><br/><br/>
<span style="font-size:14pt;color:#e2e8f0"><b>{report_date}</b></span><br/><br/><br/>
<span style="font-size:8pt;color:#64748b">Hatem&#39;s B.T. Analyzer &#183; Confidential</span>
</td></tr></table>
<pdf:nextpage />
<p><span style="font-size:17pt;color:#f1f5f9"><b>{escape(title)}</b></span></p>
<p><span style="font-size:8pt;color:#94a3b8">{escape(subtitle)} &#183; generated {gen}</span></p>
{kpi_block}{note_block}{ratio_block}{chart_block}{sections}
<div id="footerContent" style="text-align:center">
<span style="font-size:7pt;color:#64748b">Beyond Transportation &#183; {report_date} &#183; Page <pdf:pagenumber /> of <pdf:pagecount /></span>
</div>
</body></html>"""


def _html_to_pdf(screen_html, spec=None):
    """Render report to PDF bytes. Prefers WeasyPrint (pixel-faithful to the screen);
    falls back to xhtml2pdf (pure-pip, no system libraries) when WeasyPrint is
    unavailable. Returns None only if both engines fail."""
    try:
        from weasyprint import HTML
        return HTML(string=screen_html).write_pdf()
    except Exception:
        pass
    if spec is not None:
        try:
            import io
            from xhtml2pdf import pisa
            buf = io.BytesIO()
            result = pisa.CreatePDF(src=_pdf_friendly_html(spec), dest=buf,
                                    encoding='utf-8')
            if not result.err:
                return buf.getvalue()
        except Exception:
            pass
    # Last-resort fallback for hosted environments where neither WeasyPrint nor
    # xhtml2pdf is installed. Matplotlib is already used by the dashboard charts
    # and can create a real, downloadable PDF without system PDF libraries.
    if spec is not None:
        try:
            import textwrap
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages

            output = io.BytesIO()
            with PdfPages(output) as pdf_file:
                def add_text_page(title, lines):
                    fig = plt.figure(figsize=(11.69, 8.27), facecolor='#0e1117')
                    ax = fig.add_axes([0.05, 0.05, 0.90, 0.90])
                    ax.set_facecolor('#0e1117')
                    ax.axis('off')
                    ax.text(0.0, 0.97, title, color='#f8fafc', fontsize=20,
                            fontweight='bold', va='top')
                    y = 0.90
                    for line in lines:
                        ax.text(0.0, y, line, color='#e2e8f0', fontsize=10,
                                va='top', family='DejaVu Sans Mono')
                        y -= 0.035
                        if y < 0.06:
                            pdf_file.savefig(fig, facecolor=fig.get_facecolor(),
                                             bbox_inches='tight')
                            plt.close(fig)
                            fig = plt.figure(figsize=(11.69, 8.27), facecolor='#0e1117')
                            ax = fig.add_axes([0.05, 0.05, 0.90, 0.90])
                            ax.set_facecolor('#0e1117')
                            ax.axis('off')
                            y = 0.97
                    pdf_file.savefig(fig, facecolor=fig.get_facecolor(),
                                     bbox_inches='tight')
                    plt.close(fig)

                kpi_lines = [f'{label}: {value}' for label, value, _tone in spec.get('kpis', [])]
                ratio_lines = [f'{label}: {value}' for label, value, _tone in spec.get('ratios', [])]
                add_text_page(spec.get('title', 'Financial Report'),
                              kpi_lines + (['', 'Financial Ratios'] + ratio_lines if ratio_lines else []))

                for section_title, frame, fmt, _posneg in spec.get('tables', []):
                    if frame is None or frame.empty:
                        continue
                    frame = frame.copy()
                    cols = list(frame.columns)
                    lines = [section_title, ' | '.join(str(c) for c in cols)]
                    for _, row in frame.iterrows():
                        values = []
                        for col in cols:
                            value = row[col]
                            formatter = fmt.get(col) if fmt else None
                            try:
                                value = formatter(value) if formatter else value
                            except Exception:
                                pass
                            values.append(str(value))
                        lines.append(' | '.join(values))
                    add_text_page(section_title, [x for line in lines
                                                  for x in textwrap.wrap(line, 150) or ['']])
            return output.getvalue()
        except Exception:
            pass
    return None


def _report_downloads(spec, base_name, key):
    """spec = dict(title, subtitle, kpis, note, tables, ratios, charts).
    Offers a dark PDF (same look as the screen) plus an HTML fallback."""
    screen_html = _dark_report_html(spec)
    pdf = _html_to_pdf(screen_html, spec)
    if pdf:
        st.download_button(
            '\U0001F4C4 Download full report as PDF (charts, ratios & tables)',
            pdf, file_name=f'{base_name}.pdf', mime='application/pdf', key=f'pdf_{key}')
        st.caption('A dark, color-coded PDF with a cover page, page numbers & report date, '
                   'plus the KPIs, donut charts, ratios and tables \u2014 ready to share.')
    else:
        st.info('PDF export is not available in this environment. Use the HTML report below, '
                'then Print \u2192 Save as PDF in your browser.')
    st.download_button(
        '\U0001F5A8\uFE0F Download printable report (HTML)',
        screen_html, file_name=f'{base_name}.html', mime='text/html', key=f'html_{key}')


def _dark_report_html(spec):
    """Self-contained DARK HTML report mirroring the app screen (KPIs, ratios,
    donut charts, tables). Static markup only \u2014 no scripts or event handlers."""
    from html import escape
    title = spec['title']
    subtitle = spec.get('subtitle', '')
    kpis = spec.get('kpis', [])
    note_html = spec.get('note', '')
    tables = spec.get('tables', [])
    ratios = spec.get('ratios', [])
    charts = spec.get('charts', [])
    gen = datetime.now().strftime('%Y-%m-%d %H:%M')
    report_date = datetime.now().strftime('%B %d, %Y')

    def card_html(items, cls='card'):
        return ''.join(
            f'<div class="{cls}" style="border-left:6px solid {_TONE_COLORS.get(tone, tone)}">'
            f'<div class="lab">{escape(str(lab))}</div>'
            f'<div class="val" style="color:{_VAL_COLORS.get(tone, "#f1f5f9")}">{escape(str(val))}</div></div>'
            for lab, val, tone in items)

    cards = card_html(kpis)
    ratio_block = ''
    if ratios:
        ratio_block = f'<h3>Financial Ratios</h3><div class="cards">{card_html(ratios)}</div>'
    chart_block = ''
    if charts:
        imgs = ''.join(
            f'<div class="chart"><img src="{_png_data_uri(png)}"/>'
            f'<div class="cap">{escape(cap)}</div></div>'
            for cap, png in charts if png)
        if imgs:
            chart_block = f'<h3>Visual Breakdown</h3><div class="charts">{imgs}</div>'
    sections = ''
    for sec_title, df, fmt, posneg in tables:
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        thead = ''.join(f'<th>{escape(str(c))}</th>' for c in cols)
        body = ''
        for _, r in df.iterrows():
            tds = ''
            for c in cols:
                v = r[c]
                f = fmt.get(c)
                txt = f(v) if f else ('\u2014' if (v is None or (not isinstance(v, str) and pd.isna(v))) else str(v))
                cls = 'n' if f else ''
                style = ''
                if c in posneg:
                    try:
                        fv = float(v)
                        if fv > 0.005:
                            style = 'background:#dcfce7;color:#065f46;font-weight:700'
                        elif fv < -0.005:
                            style = 'background:#fee2e2;color:#991b1b;font-weight:700'
                    except (TypeError, ValueError):
                        pass
                tds += f'<td class="{cls}" style="{style}">{escape(txt)}</td>'
            body += f'<tr>{tds}</tr>'
        sections += (f'<h3>{escape(sec_title)}</h3>'
                     f'<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>')
    note_block = f'<div class="note">{note_html}</div>' if note_html else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
*{{box-sizing:border-box}}
@page{{size:A4;margin:1.4cm 1.4cm 1.7cm;background:#0e1117;
  @bottom-left{{content:"Beyond Transportation";color:#64748b;font-size:9px}}
  @bottom-center{{content:"{report_date}";color:#64748b;font-size:9px}}
  @bottom-right{{content:"Page " counter(page) " of " counter(pages);color:#64748b;font-size:9px}}}}
@page cover{{@bottom-left{{content:none}}@bottom-center{{content:none}}@bottom-right{{content:none}}}}
.cover{{page:cover;page-break-after:always;text-align:center;padding-top:24%}}
.cv-brand{{color:#60a5fa;font-size:14px;letter-spacing:.35em;font-weight:700}}
.cv-rule{{width:120px;height:4px;background:#2563eb;margin:18px auto 30px;border-radius:3px}}
.cv-title{{font-size:40px;color:#f8fafc;font-weight:800;margin:0 0 12px;line-height:1.15}}
.cv-sub{{color:#94a3b8;font-size:15px;margin-bottom:46px}}
.cv-chip{{display:inline-block;background:#1e293b;border:1px solid #334155;color:#cbd5e1;font-size:12px;letter-spacing:.08em;text-transform:uppercase;padding:7px 18px;border-radius:20px;margin-bottom:18px}}
.cv-date{{color:#e2e8f0;font-size:17px;font-weight:600}}
.cv-foot{{margin-top:64px;color:#64748b;font-size:11px;letter-spacing:.1em}}
body{{font-family:Segoe UI,Arial,sans-serif;color:#e2e8f0;margin:0;padding:28px;
  background:#0e1117;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
h1{{font-size:24px;margin:0 0 2px;color:#f1f5f9;font-weight:800}}
h3{{font-size:16px;color:#f1f5f9;margin:22px 0 8px;font-weight:700}}
.sub{{color:#94a3b8;font-size:12px;margin-bottom:18px}}
.cards{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px}}
.card{{flex:1 1 160px;background:#1e293b;border:1px solid #334155;border-radius:10px;
  padding:14px 16px;box-shadow:0 2px 6px rgba(0,0,0,.35)}}
.card .lab{{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:#94a3b8}}
.card .val{{font-size:20px;font-weight:800;margin-top:4px}}
.charts{{display:flex;flex-wrap:wrap;gap:18px;margin-bottom:16px;align-items:flex-start}}
.chart{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px;text-align:center}}
.chart img{{max-width:360px;width:100%}}
.chart .cap{{color:#94a3b8;font-size:11px;margin-top:6px}}
.note{{background:#172033;border:1px solid #334155;border-left:5px solid #3b82f6;border-radius:10px;
  padding:12px 14px;font-size:13px;color:#cbd5e1;margin-bottom:8px}}
table{{border-collapse:collapse;width:100%;font-size:12px;background:#1e293b;margin-bottom:6px}}
thead th{{background:#1d4ed8;color:#fff;text-align:center;padding:9px 10px;border:1px solid #334155;font-weight:700}}
tbody td{{padding:7px 10px;border:1px solid #334155;color:#e2e8f0}}
tbody tr:nth-child(even) td{{background:#172033}}
td.n{{text-align:right}}
@media print{{body{{padding:0;background:#0e1117}} .card,.chart{{break-inside:avoid}} thead{{display:table-header-group}}}}
</style></head><body>
<section class="cover">
  <div class="cv-brand">BEYOND TRANSPORTATION</div>
  <div class="cv-rule"></div>
  <div class="cv-title">{escape(title)}</div>
  <div class="cv-sub">{escape(subtitle)}</div>
  <div class="cv-chip">Financial Report</div>
  <div class="cv-date">{report_date}</div>
  <div class="cv-foot">Hatem&#39;s B.T. Analyzer &middot; Confidential</div>
</section>
<h1>{escape(title)}</h1>
<div class="sub">{escape(subtitle)} \u00b7 generated {gen}</div>
<div class="cards">{cards}</div>
{note_block}
{ratio_block}
{chart_block}
{sections}
</body></html>"""


def build_printable_report(name, driver_trips, monitor_rides, runs, rev, pay,
                           profit, margin, loss, detail, non_compliant_pct=0.0,
                           potential_profit=None):
    """Return a full report spec (dict) for a single state: KPIs, financial ratios,
    donut/ratio charts and the trip table. Monitors must already be excluded from `detail`."""
    safe_profit = 0.0 if (profit is None or pd.isna(profit)) else float(profit)
    safe_pay = 0.0 if (pay is None or pd.isna(pay)) else float(pay)
    kpis = [
        ('Driver Trips (counted)', f'{driver_trips:,}', ''),
        ('Monitor Rides (excluded)', f'{monitor_rides:,}', 'p'),
        ('Total Revenue', _money(rev), 'g'),
        ('Driver Cost', _money(pay), 'o'),
        ('Profit', _money(profit), 'g' if safe_profit >= 0 else 'r'),
        ('Margin', f'{margin:.2%}', 'g' if margin >= 0 else 'r'),
    ]
    cost_ratio = (safe_pay / rev * 100) if rev else 0.0
    profit_ratio = (safe_profit / rev * 100) if rev else 0.0
    ratios = [
        ('Profit Margin', f'{margin:.1%}', 'g' if margin >= 0 else 'r'),
        ('Driver-Cost Ratio', f'{cost_ratio:.1f}%', 'o'),
        ('Profit Ratio', f'{profit_ratio:.1f}%', 'g' if profit_ratio >= 0 else 'r'),
        ('Non-Compliant Trips', f'{non_compliant_pct:.1f}%',
         'r' if non_compliant_pct > 0 else 'g'),
    ]
    charts = [
        ('Revenue split: driver cost vs. profit',
         _donut_png([safe_pay, max(safe_profit, 0.0)],
                    ['Driver Cost', 'Profit'], ['#f59e0b', '#22c55e'],
                    center=_money(rev))),
        ('Trip mix: driver trips (counted) vs. monitor rides (excluded)',
         _donut_png([driver_trips, monitor_rides],
                    ['Driver Trips', 'Monitor Rides'], ['#3b82f6', '#a855f7'],
                    center=f'{driver_trips + monitor_rides:,}')),
        ('Key financial ratios',
         _ratio_bars_png([('Profit Margin', margin * 100, '#22c55e'),
                          ('Driver-Cost Ratio', cost_ratio, '#f59e0b'),
                          ('Non-Compliant %', non_compliant_pct, '#ef4444')])),
    ]
    note = (f'<b>Monitor exclusion:</b> {driver_trips:,} driver trips are counted; '
            f'{monitor_rides:,} rows marked "(MO)" / "(Monitor)" are escorts riding ALONG with '
            f'students and the driver \u2014 they are NOT trips, so they are kept OUT of the trip '
            f'count, revenue, driver cost and profit, and listed separately. '
            f'&nbsp;<b>Recoverable loss</b> (driver paid below policy): {_money(loss)}.')
    money = lambda v: _money(v)
    fmt = {'Gross Pay': money, 'Current Driver Pay': money,
           'POLICY DRIVER PAY': money, 'Loss': money}
    tables = [('Detailed Trip Analysis (driver trips only)', detail, fmt, ['Loss'])]
    return {
        'title': f'{name} \u2014 Weekly Financial Report',
        'subtitle': 'Beyond Transportation',
        'kpis': kpis, 'ratios': ratios, 'charts': charts,
        'note': note, 'tables': tables,
    }



def kpi_row(total, state_name=''):
    comp_rate = (total['compliant'] / total['total_runs'] * 100) if total['total_runs'] else 0
    revenue_f_label = f'{state_name} Paid Fare / Net Pay (F)' if state_name else 'First Paid Fare / Net Pay (F)'
    revenue_state_label = f'{state_name} Revenue (State)' if state_name else 'State Revenue (contract)'
    a, b, c, d, e = st.columns(5)
    kpi(a, 'Runs', _int(total['runs']))
    kpi(b, revenue_f_label, _money(total['revenue']), 'p')
    kpi(c, revenue_state_label, _money(total['state_revenue']), 'o')
    kpi(d, 'Profit', _money(total['profit']), 'g')
    kpi(e, 'Driver Payment', _money(total['payment']), 'o')
    f, g, h, i, j = st.columns(5)
    kpi(f, 'Amount due from First', _money(total['amount_due']), 'r')
    kpi(g, 'Margin', _pct(total['margin']), 'g')
    kpi(h, 'Revenue / run', _money(total['revenue'] / total['runs']) if total['runs'] else '-')
    kpi(i, 'Profit / covered run',
        _money(total['profit'] / total['covered_runs']) if (total.get('covered_runs') and total['policy_state']) else '-', 'g')
    kpi(j, 'Non-compliant runs', _int(total['non_compliant']), 'r')
    if total.get('uncovered_runs'):
        st.warning(
            f"\u26A0\uFE0F Profit & Margin cover only {total['covered_runs']:,} of {total['runs']:,} runs "
            f"(revenue {_money(total['covered_revenue'])}). The other {total['uncovered_runs']:,} runs are in "
            'states with no pricing policy and no uploaded state Pay, so their driver cost is unknown and they are '
            'excluded from Profit/Margin to avoid inflating them. Add those state policies (or upload the state Pay '
            'reports) to include them.'
        )

def origin_vs_first(d_state, code, origin):
    info = origin.get(code)
    if not info:
        return None
    matched = d_state[d_state['State_Price'].notna()] if 'State_Price' in d_state else d_state.iloc[0:0]
    first_paid = float(matched['Revenue'].sum())
    matched_origin = float(matched['State_Price'].sum())
    return {
        'State': STATES.get(code, code), 'Origin_Runs': info['runs'],
        'First_Runs': int(len(d_state)), 'Origin_Price': matched_origin,
        'First_Paid': first_paid, 'Difference': matched_origin - first_paid,
        'Matched_Runs': int(len(matched)),
        'Unmatched_First_Runs': int(len(d_state) - len(matched)),
    }


def price_difference_report(df):
    """Group matched trips: State contract revenue minus First paid Net Pay."""
    if df.empty or 'State_Price' not in df:
        return pd.DataFrame()
    x = df[df['State_Price'].notna()].copy()
    if x.empty:
        return pd.DataFrame()
    x['Difference_Per_Run'] = (pd.to_numeric(x['State_Price'], errors='coerce') -
                               pd.to_numeric(x['Revenue'], errors='coerce')).round(2)
    x['First_Price'] = pd.to_numeric(x['Revenue'], errors='coerce').round(2)
    x['State_Price_Rate'] = pd.to_numeric(x['State_Price'], errors='coerce').round(2)
    out = (x.groupby(['State', 'First_Price', 'State_Price_Rate', 'Difference_Per_Run'], dropna=False)
             .agg(Runs=('Revenue', 'size'),
                  First_Revenue=('Revenue', 'sum'),
                  State_Revenue=('State_Price', 'sum'))
             .reset_index())
    out['Total_Difference'] = (out['State_Revenue'] - out['First_Revenue']).round(2)
    out['Amount_Due_From_First'] = out['Total_Difference'].clip(lower=0).round(2)
    out['Difference_Direction'] = out['Total_Difference'].map(
        lambda v: 'Beyond due from First' if v > 0.005
        else ('First paid above contract' if v < -0.005 else 'No price difference'))
    out['State'] = out['State'].map(lambda c: STATES.get(c, c))
    return out.sort_values(['State', 'Difference_Per_Run'])


def trip_reconciliation_report(df):
    """One row per First trip, including matched, different, and unmatched status."""
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        'State': df.get('State', ''),
        'Driver': df.get('Driver_Name', ''),
        'Trip': df.get('Trip_Name', ''),
        'Date': df.get('Trip_Date', pd.Series(index=df.index)),
        'Miles': pd.to_numeric(df.get('Miles', 0), errors='coerce'),
        'First Net Pay': pd.to_numeric(df.get('Revenue', pd.Series(index=df.index)), errors='coerce'),
        'State Revenue': pd.to_numeric(df.get('State_Price', pd.Series(index=df.index)), errors='coerce'),
        'State Driver Pay': pd.to_numeric(df.get('State_Pay', pd.Series(index=df.index)), errors='coerce'),
        'Difference': pd.to_numeric(df.get('Price_Difference', pd.Series(index=df.index)), errors='coerce'),
        'Match Method': df.get('Match_Method', 'Unmatched'),
        'Policy Driver Pay': pd.to_numeric(df.get('Policy_Pay', pd.Series(index=df.index)), errors='coerce'),
        'Non-Compliant': df.get('Non_Compliant', False),
        'Policy Gap': pd.to_numeric(df.get('Loss', 0), errors='coerce').fillna(0),
    })
    out['State'] = out['State'].map(lambda c: STATES.get(c, c))
    out['Status'] = out.apply(lambda r: ('Ambiguous state match' if str(r['Match Method']).startswith('Ambiguous') else 'Unmatched to state report') if pd.isna(r['State Revenue'])
                               else ('Price difference' if abs(float(r['Difference'] or 0)) > 0.005 else 'Matched price'), axis=1)
    return out


def state_report_detail(info, code):
    rows = info.get('rows', pd.DataFrame()).copy()
    if rows.empty:
        return rows
    out = rows.rename(columns={'Driver_Key':'Driver', 'Trip_Key':'Trip', 'Date_Key':'Date',
                               'Miles_Key':'Miles', 'State_Price':'State Revenue',
                               'State_Pay':'State Driver Pay'}).copy()
    out['State'] = STATES.get(code, code)
    cols=['State'] + [c for c in out.columns if c != 'State']
    return out[cols]


def df_download(df, fname, key, sheets=None):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        if sheets:
            for sn, sdf in sheets.items():
                sdf.to_excel(w, sheet_name=sn[:31], index=True)
        else:
            df.to_excel(w, sheet_name='Report', index=True)
    st.download_button('\u2b07 Download Excel', out.getvalue(), fname,
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=key)

# ---------------------------------------------------------------------------
# PAGES
# ---------------------------------------------------------------------------
def state_reports_consolidated_page(origin):
    st.title('\U0001F4DA State Reports \u2014 Consolidated')
    st.caption('Built directly from the uploaded state workbooks (Excel / CSV / PDF). '
               'Profit = State Revenue \u2212 Driver Pay. It does not use First data.')
    summary = []
    sheets = {}
    for code, info in sorted(origin.items(), key=lambda kv: STATES.get(kv[0], kv[0])):
        rows = info.get('rows', pd.DataFrame()).copy()
        rev = float(pd.to_numeric(rows.get('State_Price', pd.Series(dtype=float)), errors='coerce').sum())
        pay_series = pd.to_numeric(rows.get('State_Pay', pd.Series(dtype=float)), errors='coerce')
        pay = float(pay_series.sum()) if pay_series.notna().any() else float('nan')
        profit = rev - pay if not pd.isna(pay) else float('nan')
        margin = (profit / rev * 100) if rev and not pd.isna(profit) else float('nan')
        summary.append({'State': STATES.get(code, code), 'Runs': len(rows),
                        'State Revenue': rev, 'Driver Pay': pay, 'Profit': profit,
                        'Margin %': margin,
                        'Source File': rows.get('Source_File', pd.Series([''])).iloc[0] if not rows.empty else ''})
        sheets[f'{code} Trips'] = state_report_detail(info, code)
    rep = pd.DataFrame(summary)
    if not rep.empty:
        tot_runs = int(rep['Runs'].sum())
        tot_rev = float(pd.to_numeric(rep['State Revenue'], errors='coerce').sum())
        pay_vals = pd.to_numeric(rep['Driver Pay'], errors='coerce')
        tot_pay = float(pay_vals.sum()) if pay_vals.notna().any() else float('nan')
        tot_profit = tot_rev - tot_pay if not pd.isna(tot_pay) else float('nan')
        tot_margin = (tot_profit / tot_rev * 100) if tot_rev and not pd.isna(tot_profit) else float('nan')
        st.subheader('Overview')
        a, b, c, d, e = st.columns(5)
        state_kpi(a, 'Total Runs', _int(tot_runs))
        state_kpi(b, 'State Revenue', _money(tot_rev), 'o')
        state_kpi(c, 'Driver Pay', _money(tot_pay), 'p')
        state_kpi(d, 'Profit', _money(tot_profit), 'g')
        state_kpi(e, 'Margin', _pct(tot_margin), 'g')
        st.subheader('Profit & Margin by State')
        sty = (rep.style
               .format({'State Revenue': '${:,.2f}', 'Driver Pay': '${:,.2f}',
                        'Profit': '${:,.2f}', 'Margin %': '{:,.1f}%'}, na_rep='\u2014')
               .map(_color_pos_neg, subset=['Profit', 'Margin %'])
               .set_properties(**{'font-size': '1.05rem', 'text-align': 'center'})
               .set_properties(subset=['State'], **{'font-weight': '700', 'text-align': 'left'}))
        st.dataframe(sty, use_container_width=True, hide_index=True)
        cc1, cc2 = st.columns(2)
        cc1.caption('State Revenue vs Driver Pay')
        cc1.bar_chart(rep.set_index('State')[['State Revenue', 'Driver Pay']])
        mrep = rep.dropna(subset=['Margin %'])
        if not mrep.empty:
            cc2.caption('Margin % by State')
            cc2.bar_chart(mrep.set_index('State')[['Margin %']])
        st.subheader('\U0001F4C8 Profit Margin Comparison by State')
        st.caption('States ranked by profit margin \u2014 green bars are profitable, red bars are below break-even.')
        margin_comparison_chart(rep)
        st.subheader('\U0001F4B0 Profit Distribution by State')
        st.caption('How total profit is split across states \u2014 dollar amounts and each state\u2019s share.')
        profit_distribution_chart(rep)

        kpis = [
            ('Total Runs', _int(tot_runs), ''),
            ('State Revenue', _money(tot_rev), 'o'),
            ('Driver Pay', _money(tot_pay), 'p'),
            ('Profit', _money(tot_profit), 'g' if (tot_profit or 0) >= 0 else 'r'),
            ('Margin', _pct(tot_margin), 'g' if (tot_margin or 0) >= 0 else 'r'),
        ]
        money = lambda v: _money(v)
        fmt = {'Runs': _int, 'State Revenue': money, 'Driver Pay': money,
               'Profit': money, 'Margin %': _pct}
        cons_charts = [
            ('State Revenue vs Driver Pay',
             _grouped_bars_png(rep, 'State', ['State Revenue', 'Driver Pay'],
                               'State Revenue vs Driver Pay')),
            ('Margin % by State',
             _horizontal_bars_png(rep, 'State', 'Margin %',
                                  'Profit Margin Comparison by State', percent=True)),
            ('Profit by State',
             _horizontal_bars_png(rep, 'State', 'Profit',
                                  'Profit Distribution by State')),
            ('Profit share by state',
             _donut_png(list(pd.to_numeric(rep['Profit'], errors='coerce').clip(lower=0).fillna(0)),
                        list(rep['State'].astype(str)),
                        ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444',
                         '#14b8a6', '#eab308', '#ec4899'] * 4,
                        center=_money(tot_profit))) if not rep.empty else ('', b''),
        ]
        report_spec = {
            'title': 'State Reports \u2014 Consolidated',
            'subtitle': 'Beyond Transportation',
            'kpis': kpis, 'note': 'This PDF includes the same overview KPIs, state comparison charts, profit-margin comparison, profit distribution, and detailed state table displayed on the page.', 'charts': cons_charts,
            'tables': [('Profit & Margin by State', rep, fmt, ['Profit', 'Margin %'])],
        }
        _report_downloads(report_spec, 'state_reports_consolidated', 'state_cons')
    df_download(rep.set_index('State') if not rep.empty else rep, 'state_reports_consolidated.xlsx', 'dl_state_cons', sheets={'State Summary': rep.set_index('State') if not rep.empty else rep, **sheets})


def profit_distribution_chart(frame, state_col='State', profit_col='Profit'):
    """Profit distribution by state: ranked $ bars + share-of-profit donut.

    Labels use light text so they stay readable on the dark theme.
    Falls back to st.bar_chart if Altair is unavailable.
    """
    data = frame[[state_col, profit_col]].dropna(subset=[profit_col]).copy()
    if data.empty:
        st.info('No profit data available to chart yet.')
        return
    data = data.sort_values(profit_col, ascending=False)
    try:
        import altair as alt
    except Exception:
        st.bar_chart(data.set_index(state_col)[[profit_col]])
        return
    data['Sign'] = data[profit_col].map(lambda v: 'Profit' if v >= 0 else 'Loss')
    data['Label'] = data[profit_col].map(lambda v: f'${v:,.0f}')
    c1, c2 = st.columns([3, 2])
    base = alt.Chart(data)
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X(f'{profit_col}:Q', title='Profit (USD)'),
        y=alt.Y(f'{state_col}:N', sort='-x', title=None),
        color=alt.Color('Sign:N',
                        scale=alt.Scale(domain=['Profit', 'Loss'],
                                        range=['#22c55e', '#ef4444']),
                        legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip(f'{state_col}:N', title='State'),
                 alt.Tooltip(f'{profit_col}:Q', title='Profit', format='$,.2f')])
    text = base.mark_text(align='left', baseline='middle', dx=4, color='#e2e8f0').encode(
        x=alt.X(f'{profit_col}:Q'), y=alt.Y(f'{state_col}:N', sort='-x'), text='Label:N')
    c1.caption('Profit by state (USD)')
    c1.altair_chart((bars + text).properties(height=max(220, 34 * len(data))),
                    use_container_width=True)
    # Share-of-profit donut over states that actually made money.
    share = data[data[profit_col] > 0].copy()
    if not share.empty:
        total_profit = float(share[profit_col].sum())
        share['Share'] = share[profit_col] / total_profit * 100
        donut = alt.Chart(share).mark_arc(innerRadius=55, stroke='#0f172a', strokeWidth=1).encode(
            theta=alt.Theta(f'{profit_col}:Q', stack=True),
            color=alt.Color(f'{state_col}:N', legend=alt.Legend(title='State')),
            tooltip=[alt.Tooltip(f'{state_col}:N', title='State'),
                     alt.Tooltip(f'{profit_col}:Q', title='Profit', format='$,.2f'),
                     alt.Tooltip('Share:Q', title='Share of profit', format=',.1f')])
        c2.caption('Share of total profit')
        c2.altair_chart(donut.properties(height=max(220, 34 * len(data))),
                        use_container_width=True)


def margin_comparison_chart(frame, state_col='State', margin_col='Margin %'):
    """Horizontal, sorted, color-coded profit-margin comparison across states.

    Green bars = positive margin, red = negative, so weak states are obvious.
    Falls back to st.bar_chart if Altair is unavailable.
    """
    data = frame[[state_col, margin_col]].dropna(subset=[margin_col]).copy()
    if data.empty:
        st.info('No margin data available to compare yet.')
        return
    data = data.sort_values(margin_col, ascending=False)
    try:
        import altair as alt
    except Exception:
        st.bar_chart(data.set_index(state_col)[[margin_col]])
        return
    data['Sign'] = data[margin_col].map(lambda v: 'Positive' if v >= 0 else 'Negative')
    data['Label'] = data[margin_col].map(lambda v: f'{v:,.1f}%')
    base = alt.Chart(data)
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X(f'{margin_col}:Q', title='Profit Margin (%)'),
        y=alt.Y(f'{state_col}:N', sort='-x', title=None),
        color=alt.Color('Sign:N',
                        scale=alt.Scale(domain=['Positive', 'Negative'],
                                        range=['#059669', '#dc2626']),
                        legend=alt.Legend(title='Margin')),
        tooltip=[alt.Tooltip(f'{state_col}:N', title='State'),
                 alt.Tooltip(f'{margin_col}:Q', title='Margin %', format=',.1f')])
    text = base.mark_text(align='left', baseline='middle', dx=4, color='#111827').encode(
        x=alt.X(f'{margin_col}:Q'), y=alt.Y(f'{state_col}:N', sort='-x'),
        text='Label:N')
    st.altair_chart((bars + text).properties(height=max(220, 32 * len(data))),
                    use_container_width=True)


def _delta_kpi(col, label, cur, prev, kind='money', higher_is_better=True, tone=''):
    """KPI card that also shows the change vs the previous month's snapshot."""
    fmt = {'money': _money, 'pct': _pct, 'int': _int}.get(kind, _money)
    val = fmt(cur)
    delta_html = ''
    if prev is not None and not pd.isna(prev) and not (cur is None or pd.isna(cur)):
        diff = float(cur) - float(prev)
        if kind == 'pct':
            change_txt = f'{diff:+.1f} pts'
        elif kind == 'int':
            change_txt = f'{int(round(diff)):+,}'
        else:
            change_txt = f'{diff:+,.2f}'.replace('+', '+$').replace('-', '-$')
        pct_txt = ''
        if kind != 'pct' and abs(float(prev)) > 1e-9:
            pct_txt = f' ({diff / abs(float(prev)) * 100:+.1f}%)'
        if abs(diff) < 1e-9:
            cls, arrow = 'flat', '→'
        else:
            good = (diff > 0) if higher_is_better else (diff < 0)
            cls = 'up' if good else 'down'
            arrow = '▲' if diff > 0 else '▼'
        delta_html = (f'<div class="delta {cls}">{arrow} {change_txt}{pct_txt}</div>'
                      f'<div class="prevv">prev: {fmt(prev)}</div>')
    elif prev is None:
        delta_html = '<div class="prevv">no prior month saved</div>'
    col.markdown(f'<div class="kpi {tone}"><div class="lab">{label}</div>'
                 f'<div class="val">{val}</div>{delta_html}</div>', unsafe_allow_html=True)


def monthly_comparison_block(total):
    """Save the current consolidated KPIs as a month snapshot and compare to the prior month."""
    st.subheader('\U0001F5D3\uFE0F Month-over-Month Comparison')
    default_period = datetime.now().strftime('%Y-%m')
    c1, c2, c3 = st.columns([2, 2, 3])
    period = c1.text_input('Current period label', value=default_period, key='mom_period',
                           help='e.g. 2026-10. Save it, then next month save again to see the change.')
    if c2.button('\U0001F4BE Save this month\u2019s KPIs', key='save_month'):
        save_monthly_snapshot(period.strip() or default_period, total)
        st.success(f'Saved consolidated KPIs for {period.strip() or default_period}.')
    prev = previous_monthly_snapshot(exclude_period=(period.strip() or default_period))
    if prev is None:
        c3.info('No earlier month saved yet. Save this month, then come back next month '
                'to see the trend against it.')
    else:
        c3.caption(f'Comparing against **{prev["period"]}** (saved {prev.get("saved_on", "")}).')

    a, b, cc, d, e = st.columns(5)
    _delta_kpi(a, 'Runs', total['runs'], (prev or {}).get('runs'), 'int')
    _delta_kpi(b, 'First Net Pay', total['revenue'], (prev or {}).get('revenue'), 'money', True, 'p')
    _delta_kpi(cc, 'Profit', total['profit'], (prev or {}).get('profit'), 'money', True, 'g')
    _delta_kpi(d, 'Margin', total['margin'], (prev or {}).get('margin'), 'pct', True, 'g')
    _delta_kpi(e, 'Driver Payment', total['payment'], (prev or {}).get('payment'), 'money', True, 'o')
    f, g, h, i, j = st.columns(5)
    _delta_kpi(f, 'Revenue / run', (total['revenue'] / total['runs']) if total['runs'] else float('nan'),
               ((prev or {}).get('revenue') / prev['runs']) if (prev and prev.get('runs')) else None, 'money')
    _delta_kpi(g, 'Amount due from First', total['amount_due'], (prev or {}).get('amount_due'), 'money', True, 'r')
    _delta_kpi(h, 'State Revenue', total['state_revenue'], (prev or {}).get('state_revenue'), 'money', True, 'o')
    _delta_kpi(i, 'Non-compliant runs', total['non_compliant'], (prev or {}).get('non_compliant'), 'int', False, 'r')
    _delta_kpi(j, 'Recoverable loss', total['loss'], (prev or {}).get('loss'), 'money', False, 'r')

    snaps = all_monthly_snapshots()
    if len(snaps) >= 2:
        with st.expander('Saved monthly snapshots & trend', expanded=False):
            show = snaps.rename(columns={
                'period': 'Period', 'runs': 'Runs', 'revenue': 'First Net Pay',
                'profit': 'Profit', 'margin': 'Margin %', 'payment': 'Driver Payment',
                'loss': 'Loss', 'non_compliant': 'Non-compliant', 'saved_on': 'Saved on'})
            st.dataframe(show[['Period', 'Runs', 'First Net Pay', 'Driver Payment', 'Profit',
                               'Margin %', 'Non-compliant', 'Loss', 'Saved on']].style.format({
                'First Net Pay': '${:,.2f}', 'Driver Payment': '${:,.2f}', 'Profit': '${:,.2f}',
                'Margin %': '{:,.1f}%', 'Loss': '${:,.2f}'}, na_rep='\u2014'),
                use_container_width=True, hide_index=True)
            trend = snaps.set_index('period')
            st.caption('First Net Pay & Profit by period')
            st.bar_chart(trend[['revenue', 'profit']])
            if trend['margin'].notna().any():
                st.caption('Margin % by period')
                st.line_chart(trend[['margin']])


def _consolidated_summary(total, perf):
    """Short, decision-ready bottom line for management."""
    bullets = []
    per_trip = _money(total['revenue'] / total['runs']) if total['runs'] else '-'
    bullets.append(f"**Business volume:** {total['runs']:,} trips produced **{_money(total['revenue'])}** "
                   f"in First Net Pay (about {per_trip} per trip).")
    if total['policy_state'] and total.get('covered_runs'):
        bullets.append(f"**Profit (where driver cost is known):** **{_money(total['profit'])}** on "
                       f"{total['covered_runs']:,} covered trips \u2014 a **{_pct(total['margin'])} margin** "
                       f"after paying drivers {_money(total['payment'])}.")
    mperf = perf.dropna(subset=['Margin %'])
    if not mperf.empty:
        best = mperf.loc[mperf['Margin %'].idxmax()]
        worst = mperf.loc[mperf['Margin %'].idxmin()]
        bullets.append(f"**Strongest state:** {best['State']} ({best['Margin %']:.1f}% margin). "
                       f"**Weakest:** {worst['State']} ({worst['Margin %']:.1f}%).")
    if total.get('uncovered_runs'):
        bullets.append(f"**Needs rates:** {total['uncovered_runs']:,} trips are in states with no pricing policy "
                       f"and no uploaded driver Pay, so their true profit is unknown. Add those rates to complete the picture.")
    if total.get('non_compliant'):
        bullets.append(f"**Recoverable:** {total['non_compliant']:,} trips were underpaid vs policy, worth "
                       f"**{_money(total['loss'])}** (profit would rise to {_money(total['profit_if'])} if corrected).")
    st.success('\n\n'.join('- ' + b for b in bullets))


def consolidated_page(df, origin):
    st.title('\U0001F4CA Consolidated Financial Report \u2014 All States')
    st.caption('First Net Pay is the revenue source of truth. Driver Payment comes from your pricing policy, or the uploaded state Pay for states with no policy.')
    total = agg_block(df)
    rows = []
    for code in sorted(df['State'].unique(), key=lambda c: STATES.get(c, c)):
        b = agg_block(df[df['State'] == code])
        info = origin.get(code, {})
        full_rows = info.get('rows', pd.DataFrame())
        full_state_revenue = (float(pd.to_numeric(full_rows.get('State_Price', pd.Series(dtype=float)), errors='coerce').sum())
                              if not full_rows.empty else float('nan'))
        rows.append({
            'State': STATES.get(code, code), 'First Runs': b['runs'],
            'First Net Pay': b['revenue'], 'Matched Runs': int(df[(df['State'] == code) & df['State_Price'].notna()].shape[0]),
            'Matched State Revenue': b['state_revenue'],
            'State Report Runs': int(info.get('runs', 0)), 'State Report Revenue': full_state_revenue,
            'Price Difference': b['price_difference'], 'Amount Due': b['amount_due'],
            'Driver Payment': b['payment'], 'Profit': b['profit'], 'Margin %': b['margin'],
            'Non-compliant': b['non_compliant'], 'Loss': b['loss'],
            'Profit if compliant': b['profit_if'], 'Margin if compliant %': b['margin_if'],
        })
    perf = pd.DataFrame(rows)

    st.subheader('\U0001F3AF Executive Summary \u2014 Bottom Line')
    _consolidated_summary(total, perf)

    monthly_comparison_block(total)

    st.subheader('Headline KPIs')
    kpi_row(total)

    with st.expander('Full performance table by state', expanded=False):
        st.dataframe(perf.style.format({
            'First Net Pay': '${:,.2f}', 'Matched State Revenue': '${:,.2f}', 'State Report Revenue': '${:,.2f}',
            'Price Difference': '${:,.2f}', 'Amount Due': '${:,.2f}',
            'Driver Payment': '${:,.2f}', 'Profit': '${:,.2f}',
            'Margin %': '{:,.1f}%', 'Loss': '${:,.2f}', 'Profit if compliant': '${:,.2f}',
            'Margin if compliant %': '{:,.1f}%'}, na_rep='\u2014').map(_color_pos_neg, subset=['Profit', 'Margin %']), use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.caption('First Net Pay vs matched state contract revenue')
    c1.bar_chart(perf.set_index('State')[['First Net Pay', 'Matched State Revenue']])
    mperf = perf.dropna(subset=['Margin %'])
    if not mperf.empty:
        c2.caption('Margin % by state')
        c2.bar_chart(mperf.set_index('State')[['Margin %']])

    st.subheader('\U0001F4C8 Profit Margin Comparison by State')
    st.caption('States ranked by profit margin \u2014 green bars are profitable, red bars are below break-even.')
    margin_comparison_chart(perf)

    st.subheader('\U0001F4B0 Profit Distribution by State')
    st.caption('How total profit is split across states \u2014 dollar amounts and each state\u2019s share.')
    profit_distribution_chart(perf)

    if origin:
        diff_report = price_difference_report(df)
        positive_diff = diff_report[diff_report['Amount_Due_From_First'] > 0] if not diff_report.empty else diff_report
        if not positive_diff.empty:
            st.subheader('Price differences \u2014 State Revenue \u2212 First Net Pay')
            st.dataframe(positive_diff.style.format({
                'First_Price': '${:,.2f}', 'State_Price_Rate': '${:,.2f}',
                'Difference_Per_Run': '${:,.2f}', 'First_Revenue': '${:,.2f}',
                'State_Revenue': '${:,.2f}', 'Total_Difference': '${:,.2f}',
                'Amount_Due_From_First': '${:,.2f}'}),
                use_container_width=True, hide_index=True)

    # Show the actual policy used for each state, not just the compliance result.
    st.subheader('Pricing Policy by State')
    policy_view = POLICY_DF[POLICY_DF.State.isin(df['State'].dropna().unique())][
        ['State', 'Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Per_Mile_Rate', 'Note']].copy()
    policy_view['State'] = policy_view['State'].map(lambda c: STATES.get(c, c))
    if not policy_view.empty:
        st.dataframe(policy_view, use_container_width=True, hide_index=True)

    non_compliant = df[df['Non_Compliant']].copy() if 'Non_Compliant' in df else pd.DataFrame()
    if not non_compliant.empty:
        st.subheader('Non-Compliant Trips')
        st.caption('These trips are shown because State Driver Payment is below the applicable driver-pay policy. First Net Pay is not used for this compliance test.')
        nc_view = non_compliant[['State', 'Driver_Name', 'Trip_Name', 'Miles', 'Revenue',
                                 'Policy_Pay', 'Loss']].copy()
        nc_view['State'] = nc_view['State'].map(lambda c: STATES.get(c, c))
        st.dataframe(nc_view.style.format({'Revenue': '${:,.2f}', 'Policy_Pay': '${:,.2f}',
                                           'Loss': '${:,.2f}'}),
                     use_container_width=True, hide_index=True)

    if 'Unassigned' in df['State'].values:
        n = int((df['State'] == 'Unassigned').sum())
        st.warning(f'{n} run(s) could not be matched to a state (new drivers not in the '
                   'built-in list). Open the "Unassigned" section to review them.')
    trip_detail = trip_reconciliation_report(df)
    different_trips = trip_detail[trip_detail['Status'].eq('Price difference')].copy() if not trip_detail.empty else trip_detail
    unmatched_trips = trip_detail[trip_detail['Status'].eq('Unmatched to state report')].copy() if not trip_detail.empty else trip_detail
    if not different_trips.empty:
        st.subheader('Detailed price differences by driver and trip')
        st.dataframe(different_trips.style.format({'First Net Pay':'${:,.2f}','State Revenue':'${:,.2f}','State Driver Pay':'${:,.2f}','Difference':'${:,.2f}','Policy Driver Pay':'${:,.2f}','Policy Gap':'${:,.2f}'}),use_container_width=True,hide_index=True)
    if not unmatched_trips.empty:
        st.subheader('First trips not matched to a state row')
        st.dataframe(unmatched_trips,use_container_width=True,hide_index=True)

    # PDF export for the same consolidated report shown on this page.
    cons_kpis = [
        ('Runs', _int(total['runs']), ''),
        ('First Net Pay', _money(total['revenue']), 'p'),
        ('Driver Payment', _money(total['payment']), 'o'),
        ('Profit', _money(total['profit']), 'g' if total['profit'] >= 0 else 'r'),
        ('Margin', _pct(total['margin']), 'g' if total['margin'] >= 0 else 'r'),
        ('Amount Due', _money(total['amount_due']), 'r' if total['amount_due'] > 0 else 'g'),
    ]
    cons_fmt = {
        'First Runs': _int, 'First Net Pay': _money,
        'Matched Runs': _int, 'Matched State Revenue': _money,
        'State Report Runs': _int, 'State Report Revenue': _money,
        'Price Difference': _money, 'Amount Due': _money,
        'Driver Payment': _money, 'Profit': _money,
        'Margin %': _pct, 'Non-compliant': _int, 'Loss': _money,
        'Profit if compliant': _money, 'Margin if compliant %': _pct,
    }
    _report_downloads({
        'title': 'Consolidated Financial Report — All States',
        'subtitle': 'Beyond Transportation',
        'kpis': cons_kpis,
        'note': 'First Net Pay is compared with matched state contract revenue. '
                'Driver Payment and Profit use the applicable pricing policy.',
        'tables': [('Performance by State', perf, cons_fmt, ['Profit', 'Margin %', 'Amount Due'])],
    }, 'consolidated_report', 'pdf_cons')
    df_download(perf.set_index('State'), 'consolidated_report.xlsx', 'dl_cons',
                sheets={'State Summary': perf.set_index('State'),
                        'Price Differences': different_trips,
                        'Unmatched First': unmatched_trips,
                        'All Reconciliation': trip_detail})

def _state_analysis_page(df, code, origin):
    name = STATES.get(code, code)
    st.title(f'\U0001F4CD {name} \u2014 Weekly Financial Report')
    d = df[df['State'] == code].copy()
    # Keep the original state-report financial summary separate from First Alt.
    # The state file may contain more runs than First; never replace its totals
    # with the matched subset.
    state_info = origin.get(code)
    if state_info:
        sr = state_info['rows'].copy()
        state_rev = float(pd.to_numeric(sr['State_Price'], errors='coerce').sum())
        state_pay_series = pd.to_numeric(sr.get('State_Pay', pd.Series(dtype=float)), errors='coerce')
        state_pay = float(state_pay_series.sum()) if state_pay_series.notna().any() else float('nan')
        state_profit = state_rev - state_pay if not pd.isna(state_pay) else float('nan')
        state_margin = state_profit / state_rev * 100 if state_rev and not pd.isna(state_profit) else float('nan')
        st.subheader(f'{name} State Report \u2014 Original Totals')
        st.caption('Contract Revenue is the state trip price. Driver Payment is a separate field and must not be used as the trip price.')
        sa, sb, sc, sd, se = st.columns(5)
        sa.metric('RUNS', f'{len(sr):,}')
        sb.metric('REV', _money(state_rev))
        sc.metric('DRIVER PAYMENT', _money(state_pay))
        sd.metric('PROFIT', _money(state_profit))
        se.metric('MARGIN', _pct(state_margin))
        state_summary = pd.DataFrame({
            'Metric': ['Total Trips', f'{name} Contract Revenue (Trip Price)', 'Total Driver Payment',
                       'Total Margin (Profit)', 'Current Margin %'],
            'Value': [f'{len(sr):,}', _money(state_rev), _money(state_pay),
                      _money(state_profit), _pct(state_margin)]
        }).set_index('Metric')
        st.table(state_summary)
        st.markdown('---')
        st.subheader(f'{name} First Alt \u2014 Paid Fare Matching')
        st.caption('First Net Pay is compared only with State Contract Revenue. State Driver Payment is a separate policy/compliance field.')
    else:
        st.subheader(f'{name} First Alt \u2014 Paid Fare Matching')
    rep, total, weeks = weekly_report(d)
    kpi_row(total, name)
    if not total.get('policy_state'):
        st.info('No pricing policy is supplied for this state yet, so runs are not checked '
                'for compliance. Revenue and runs are still reported. Provide the rates to '
                'enable profit and compliance.')

    st.subheader('Pricing policy')
    pol = POLICY_DF[POLICY_DF.State == code][
        ['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Per_Mile_Rate', 'Note']]
    if code == 'SAC':
        pol = pd.DataFrame([{'Vehicle_Type': v, 'Min_Miles': r['min'], 'Max_Miles': r['max'],
                             'Policy_Pay': r['base'], 'Per_Mile_Rate': r['per_mile'],
                             'Note': r['note']}
                            for v, rs in SACRAMENTO_POLICIES.items() for r in rs])
    st.table(pol)

    st.subheader('Weekly report')
    st.dataframe(rep, use_container_width=True)

    # Legacy feature retained: save this state's weekly analysis and review history.
    if st.button('\U0001F4BE Save this Weekly Analysis to History', key=f'save_{code}'):
        save_weekly_summary(code, d, total)
        st.success(f'Analysis for {name} has been saved.')
    price_cols = ['Trip_Date', 'Driver_Name', 'District', 'Trip_Name', 'Miles',
                  'First_Reported_Revenue', 'Net_Pay', 'Revenue', 'Paid_Fare_Source',
                  'State_Price', 'State_Pay', 'Price_Difference', 'Price_Source', 'Match_Method', 'Driver_Pay', 'Policy_Pay', 'Non_Compliant', 'Loss']
    with st.expander('Matched contract prices from state report'):
        st.dataframe(d[[c for c in price_cols if c in d.columns]], use_container_width=True, hide_index=True)
    st.caption('PRICE COMPARISON: First Net Pay vs State Contract Revenue. Driver Payment is separate. Amount Due = State Contract Revenue \u2212 First Net Pay.')
    state_diff = price_difference_report(d)
    state_diff = state_diff[state_diff['Amount_Due_From_First'] > 0.005] if not state_diff.empty else state_diff
    if not state_diff.empty:
        st.subheader('Price differences \u2014 State Revenue \u2212 First Net Pay')
        st.dataframe(state_diff.style.format({
            'Difference_Per_Run': '${:,.2f}', 'First_Revenue': '${:,.2f}',
            'State_Revenue': '${:,.2f}', 'Total_Difference': '${:,.2f}',
            'Amount_Due_From_First': '${:,.2f}'}),
            use_container_width=True, hide_index=True)

    if total['policy_state'] and total['non_compliant']:
        st.warning(f"{total['non_compliant']} loss-making run(s): State Driver Payment is below the "
                   f"policy driver pay. Total loss ${total['loss']:,.2f}. If every run were "
                   f"priced per policy, profit would be ${total['profit_if']:,.2f} "
                   f"({_pct(total['margin_if'])}) instead of ${total['profit']:,.2f} "
                   f"({_pct(total['margin'])}).")
        bad = d[d['Non_Compliant']][['Trip_Date', 'Driver_Name', 'Trip_Name', 'Miles',
                                     'Revenue', 'Policy_Pay', 'State_Price', 'Price_Difference', 'Price_Source', 'Loss']].sort_values('Loss', ascending=False)
        with st.expander(f'Show {len(bad)} loss-making runs'):
            st.dataframe(bad.style.format({'Revenue': '${:,.2f}', 'Policy_Pay': '${:,.2f}', 'State_Price': '${:,.2f}', 'State_Pay': '${:,.2f}',
                                           'Price_Difference': '${:,.2f}', 'Loss': '${:,.2f}'}),
                         use_container_width=True, hide_index=True)

    ov = origin_vs_first(d, code, origin)
    if ov and ov['Matched_Runs']:
        st.subheader('State Revenue vs First Revenue reconciliation')
        st.dataframe(pd.DataFrame([{
            'State': name, 'Matched Runs': ov['Matched_Runs'],
            'First Net Pay (F)': ov['First_Paid'], 'Matched State Revenue': ov['Origin_Price'],
            'Total Price Difference': ov['Difference'],
            'First Runs': ov['First_Runs'], 'State Report Runs': ov['Origin_Runs'],
            'Unmatched First Runs': ov['Unmatched_First_Runs'],
            'Unmatched State Runs': ov['Origin_Runs'] - ov['Matched_Runs']
        }]).style.format({
            'First Net Pay (F)': '${:,.2f}', 'Matched State Revenue': '${:,.2f}',
            'Total Price Difference': '${:,.2f}'}), use_container_width=True, hide_index=True)
        if abs(ov['Difference']) > 0.05:
            direction = 'higher than' if ov['Difference'] > 0 else 'lower than'
            st.warning(f"The state contract revenue is ${abs(ov['Difference']):,.2f} total {direction} First Revenue for {name}. This does not change Driver Payment or Profit.")
    weekly_kpis = [
        ('Runs', _int(total['runs']), ''),
        ('First Net Pay', _money(total['revenue']), 'p'),
        ('State Revenue', _money(total['state_revenue']), 'o'),
        ('Driver Payment', _money(total['payment']), 'o'),
        ('Profit', _money(total['profit']), 'g' if total['profit'] >= 0 else 'r'),
        ('Margin', _pct(total['margin']), 'g' if total['margin'] >= 0 else 'r'),
    ]
    weekly_fmt = {
        c: _money for c in ['Revenue', 'State_Price', 'State_Pay', 'Price_Difference',
                            'Driver_Pay', 'Policy_Pay', 'Loss'] if c in rep.columns
    }
    _report_downloads({
        'title': f'{name} — Weekly Financial Report',
        'subtitle': 'Beyond Transportation',
        'kpis': weekly_kpis,
        'note': 'Weekly analysis generated from the uploaded First Alt report and matched state report data.',
        'tables': [('Weekly Report', rep, weekly_fmt, ['Price_Difference', 'Loss'])],
    }, f'{code}_weekly_report', f'pdf_weekly_{code}')
    df_download(rep, f'{code}_weekly_report.xlsx', f'dl_{code}')


def state_history_page(code, name):
    st.header('Historical Performance')
    history = historical_summary(code)
    if history.empty:
        st.warning('No historical data found for this state. Save a weekly analysis first.')
        return
    st.subheader('Saved Weekly Summaries')
    st.dataframe(history, use_container_width=True, hide_index=True)
    history['week_start_date'] = pd.to_datetime(history['week_start_date'], errors='coerce')
    history = history.dropna(subset=['week_start_date']).set_index('week_start_date')
    if not history.empty:
        st.subheader('Performance Over Time')
        st.line_chart(history[['total_revenue', 'total_margin']])
        st.bar_chart(history[['total_loss']])

def state_page(df, code, origin):
    """Keep the original state page; append First Alt price differences only."""
    name = STATES.get(code, code)
    state_only_page(origin, code)
    d = df[df['State'] == code].copy()
    matched = d[d['State_Price'].notna()].copy() if 'State_Price' in d else d.iloc[0:0]
    if matched.empty:
        return
    st.markdown('---')
    st.header(f'{name} \u2014 First Alt Price Difference')
    st.caption('This is an add-on only. The state report above remains unchanged. Difference = State Revenue (contract) \u2212 First Net Pay (paid). A positive result is money due to Beyond from First.')
    first_total = float(pd.to_numeric(matched['Revenue'], errors='coerce').sum())
    state_total = float(pd.to_numeric(matched['State_Price'], errors='coerce').sum())
    difference = state_total - first_total
    state_info = origin.get(code, {})
    state_run_count = int(state_info.get('runs', len(matched)))
    unmatched_state_runs = max(state_run_count - len(matched), 0)
    full_state_total = float(pd.to_numeric(state_info.get('rows', pd.DataFrame()).get(
        'State_Price', pd.Series(dtype=float)), errors='coerce').sum())
    unmatched_state_revenue = full_state_total - state_total
    if unmatched_state_runs:
        st.warning(
            f'{unmatched_state_runs:,} state-report run(s) are not matched to First Alt. '
            f'Their state-report revenue is {_money(unmatched_state_revenue)}. '
            'This is a run-count/matching difference, not a price difference for matched trips. '
            'They may belong to Washington or may have different driver, route, date, or miles values.'
        )
        unmatched = unmatched_state_rows(df, origin, code)
        if not unmatched.empty:
            st.subheader('Unmatched State-Report Trips \u2014 Review Before Classifying')
            st.caption('These rows are read directly from the uploaded state report. They are not included in the price-difference calculation until matched.')
            unmatched['Washington_Candidate'] = unmatched.apply(
                lambda r: 'Yes' if 'WASHINGTON' in f"{r.get('Trip_Key', '')} {r.get('Driver_Key', '')}".upper()
                or 'SEATTLE' in f"{r.get('Trip_Key', '')} {r.get('Driver_Key', '')}".upper()
                else 'No', axis=1)
            filter_choice = st.selectbox(
                'Filter unmatched trips',
                ['All unmatched', 'Washington candidates', 'Other unmatched'],
                key=f'unmatched_filter_{code}')
            view = unmatched
            if filter_choice == 'Washington candidates':
                view = unmatched[unmatched['Washington_Candidate'].eq('Yes')]
            elif filter_choice == 'Other unmatched':
                view = unmatched[unmatched['Washington_Candidate'].eq('No')]
            display = view.rename(columns={
                'Driver_Key': 'Driver', 'Trip_Key': 'Route / Trip',
                'Date_Key': 'Date', 'Miles_Key': 'Miles',
                'State_Price': 'State Revenue', 'State_Pay': 'State PAY',
                'Source_File': 'Source File'})
            cols = ['Driver', 'Route / Trip', 'Date', 'Miles', 'State Revenue',
                    'State PAY', 'Possible_State', 'Washington_Candidate', 'Source File']
            st.dataframe(display[[c for c in cols if c in display.columns]].style.format({
                'State Revenue': '${:,.2f}', 'State PAY': '${:,.2f}'}),
                use_container_width=True, hide_index=True)
    x1, x2, x3, x4 = st.columns(4)
    x1.metric('Matched First Runs', f'{len(matched):,}')
    x2.metric('First Net Pay (F)', _money(first_total))
    x3.metric('Matched State Revenue', _money(state_total))
    x4.metric('Amount Due From First', _money(max(difference, 0)))
    st.caption(
        f'Full state report: {state_run_count:,} runs / {_money(full_state_total)}. '
        f'Matched for price comparison: {len(matched):,} runs / {_money(state_total)}. '
        f'Price difference is calculated only on those {len(matched):,} matched runs.'
    )
    # Keep the matched trip detail available, but collapsed, so the Price Difference
    # section below is the final thing the report ends on (per request).
    with st.expander('First Alt Trips Used in Matching', expanded=False):
        st.dataframe(matched[[c for c in ['Trip_Date', 'Driver_Name', 'District', 'Trip_Name',
                                          'Miles', 'Net_Pay', 'State_Price', 'Price_Difference']
                                         if c in matched.columns]].style.format({
                                             'Net_Pay': '${:,.2f}', 'State_Price': '${:,.2f}',
                                             'Price_Difference': '${:,.2f}'}),
                     use_container_width=True, hide_index=True)

    diff_report = price_difference_report(matched)
    if not diff_report.empty:
        st.subheader('Price Difference by Trip Price \u2014 State Revenue \u2212 First Net Pay')
        st.caption('Difference per run = State contract revenue \u2212 First Net Pay (what Beyond was actually paid). '
                   'A positive \u201cAmount Due From First\u201d is money owed to Beyond. This is the final section of the report.')
        diff_filter = st.selectbox(
            'Price difference filter',
            ['All price differences', 'Beyond due only', 'Only First $42.50 \u2192 State $45.00'],
            index=0, key=f'price_filter_{code}')
        shown_diff = diff_report
        if diff_filter == 'Only First $42.50 \u2192 State $45.00':
            shown_diff = diff_report[(diff_report['First_Price'].round(2) == 42.50)
                                     & (diff_report['State_Price_Rate'].round(2) == 45.00)]
            if shown_diff.empty:
                st.info('No matched trips with First $42.50 and state contract $45.00 were found.')
        elif diff_filter == 'Beyond due only':
            shown_diff = diff_report[diff_report['Amount_Due_From_First'] > 0]
            if shown_diff.empty:
                st.info('No matched trips where the state contract is above First Net Pay.')
        st.dataframe(shown_diff.style.format({
            'First_Price': '${:,.2f}', 'State_Price_Rate': '${:,.2f}',
            'Difference_Per_Run': '${:,.2f}', 'First_Revenue': '${:,.2f}',
            'State_Revenue': '${:,.2f}', 'Total_Difference': '${:,.2f}',
            'Amount_Due_From_First': '${:,.2f}'}),
            use_container_width=True, hide_index=True)

def state_only_page(origin, code):
    """The original state-report page; First matching is intentionally not mixed into it."""
    name = STATES.get(code, code)
    info = origin.get(code)
    if not info:
        st.title(f'\U0001F4CA {name} - Analysis Dashboard')
        st.warning('No uploaded state report was detected for this state.')
        return
    rows = info['rows'].copy()
    miles = pd.to_numeric(rows.get('Miles_Key', 0), errors='coerce').fillna(0)
    actual_pay = pd.to_numeric(rows.get('State_Pay', pd.Series(pd.NA, index=rows.index)), errors='coerce')
    rows['Driver_Name'] = rows.get('Driver_Key', '')
    rows['Trip_Name'] = rows.get('Trip_Key', '')
    rows['Miles'] = miles
    rows['Gross_Pay'] = pd.to_numeric(rows['State_Price'], errors='coerce')
    rows['Net_Pay'] = actual_pay
    # Monitors / escorts ride ALONG with a driver (marked "(MO)" or "(Monitor)");
    # they are not standalone driver trips, so they are counted separately.
    dnames = rows['Driver_Name'].astype(str)
    # Driver names are normalised (parentheses become spaces), so "(MO)" ends up as a
    # bare "mo" token — match that plus the explicit "(mo)"/"(monitor)"/"monitor" forms.
    rows['Is_Monitor'] = dnames.str.contains(r'\(mo\)|\(monitor\)|\bmonitor\b|\bmo\b', case=False, regex=True, na=False)
    monitor_rides = int(rows['Is_Monitor'].sum())
    driver_trips = int((~rows['Is_Monitor']).sum())
    # State-only files often omit vehicle/route; do not invent a vehicle-specific Alaska policy.
    if code == 'AK':
        rows['Policy_Driver_Pay'] = pd.NA
        rows['Loss_Amount'] = 0.0
        rows['Is_Non_Compliant'] = False
    else:
        rows['Policy_Driver_Pay'] = [policy_pay(code, m, 'Unknown', 'Unknown')[0] for m in miles]
        rows['Loss_Amount'] = (rows['Policy_Driver_Pay'] - actual_pay).clip(lower=0).fillna(0)
        rows['Is_Non_Compliant'] = rows['Loss_Amount'] > 0.05
    # Monitors / escorts are NOT trips: exclude them from revenue, driver cost,
    # trip count, profit and loss. They are reported separately for transparency.
    trip_rows = rows[~rows['Is_Monitor']]
    trip_net = pd.to_numeric(trip_rows['Net_Pay'], errors='coerce')
    rev = float(pd.to_numeric(trip_rows['Gross_Pay'], errors='coerce').sum())
    pay = float(trip_net.sum()) if trip_net.notna().any() else float('nan')
    runs = int(len(trip_rows))
    profit = rev - pay if not pd.isna(pay) else float('nan')
    margin = profit / rev if rev and not pd.isna(profit) else 0.0
    loss = float(pd.to_numeric(trip_rows['Loss_Amount'], errors='coerce').sum())
    monitor_billed = float(pd.to_numeric(rows.loc[rows['Is_Monitor'], 'Gross_Pay'],
                                         errors='coerce').sum())
    st.title(f'\U0001F4CA {name} - Analysis Dashboard')
    tab1, tab2 = st.tabs(['Weekly Analysis', 'Historical Performance'])
    with tab1:
        st.header('Weekly Analysis')
        st.subheader('Official Pricing Policy')
        pol = POLICY_DF[POLICY_DF.State == code][
            ['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Per_Mile_Rate', 'Note']]
        st.table(pol)
        st.subheader('Financial Summary')
        k1, k2, k3 = st.columns(3)
        state_kpi(k1, 'Driver Trips (counted)', f'{driver_trips:,}', '')
        state_kpi(k2, 'Monitor Rides (excluded)', f'{monitor_rides:,}', 'p')
        state_kpi(k3, 'Trips in Totals', f'{runs:,}', '')
        k4, k5, k6 = st.columns(3)
        state_kpi(k4, 'Total Revenue', _money(rev), 'g')
        state_kpi(k5, 'Driver Cost', _money(pay), 'o')
        prof_tone = 'g' if (pd.isna(profit) or profit >= 0) else 'r'
        state_kpi(k6, 'Profit', _money(profit), prof_tone)
        m1, _m2, _m3 = st.columns(3)
        state_kpi(m1, 'Current Margin', f'{margin:.2%}', 'g' if margin >= 0 else 'r')
        summary = pd.DataFrame({
            'Metric': ['Driver Trips (counted)', 'Monitor / Escort Rides (excluded)',
                       'Monitor Billing (excluded)',
                       'Total Revenue (Gross Pay)', 'Total Driver Cost (Net Pay)',
                       'Total Margin (Profit)', 'Current Margin %'],
            'Value': [f'{driver_trips:,}', f'{monitor_rides:,}', _money(monitor_billed),
                      _money(rev), _money(pay), _money(profit), f'{margin:.2%}']
        }).set_index('Metric')
        with st.expander('Financial summary (table)', expanded=False):
            st.table(summary)
        if monitor_rides:
            st.caption(
                f'Monitor exclusion: **{monitor_rides:,} rows marked "(MO)" / "(Monitor)"** '
                f'({_money(monitor_billed)} billed) are **not trips**, so they are removed from '
                f'the trip count, revenue, driver cost and profit above. Only the '
                f'**{driver_trips:,} actual driver trips** are counted. Monitors are listed '
                'separately below for reference.')
        if code == 'AK':
            st.info('Alaska state rows do not include vehicle type or trip route. Alaska policy compliance is calculated only after First trip detail is uploaded and matched.')
        st.subheader('Compliance Impact Summary')
        non_compliant = trip_rows[trip_rows['Is_Non_Compliant']]
        ratio = len(non_compliant) / runs if runs else 0
        c1, c2 = st.columns(2)
        c1.metric('Total Loss from Non-Compliance', _money(loss))
        c2.metric('Non-Compliant Trips %', f'{ratio:.2%}')
        potential = profit + loss if not pd.isna(profit) else float('nan')
        st.subheader('Potential Profit Analysis')
        st.table(pd.DataFrame({
            'Amount': [_money(profit), _money(potential), _money(loss)],
            'Margin %': [f'{margin:.2%}', f'{(potential / rev if rev else 0):.2%}',
                         f'+{((potential - profit) / rev if rev and not pd.isna(profit) else 0):.2%}']
        }, index=['Current Margin (Actual)', 'Potential Margin (If Compliant)', 'Profit Increase']))

        nc_pct = ratio * 100
        safe_profit = 0.0 if pd.isna(profit) else float(profit)
        safe_pay = 0.0 if pd.isna(pay) else float(pay)
        st.subheader('\U0001F4C8 Visual Breakdown')
        v1, v2 = st.columns(2)
        _show_png(v1, _donut_png([safe_pay, max(safe_profit, 0.0)],
                            ['Driver Cost', 'Profit'], ['#f59e0b', '#22c55e'],
                            center=_money(rev)),
                 caption='Revenue split: driver cost vs. profit', use_container_width=True)
        _show_png(v2, _donut_png([driver_trips, monitor_rides],
                            ['Driver Trips', 'Monitor Rides'], ['#3b82f6', '#a855f7'],
                            center=f'{driver_trips + monitor_rides:,}'),
                 caption='Trip mix: driver trips (counted) vs. monitor rides (excluded)', use_container_width=True)
        _show_png(st, _ratio_bars_png([('Profit Margin', margin * 100, '#22c55e'),
                                  ('Driver-Cost Ratio', (safe_pay / rev * 100) if rev else 0, '#f59e0b'),
                                  ('Non-Compliant %', nc_pct, '#ef4444')]),
                 caption='Key financial ratios', use_container_width=False)
        st.subheader('Detailed Trip Analysis')
        st.caption('**Loss** = POLICY DRIVER PAY \u2212 Current Driver Pay, counted only when the driver was paid '
                   '**below** policy. Example: policy says the driver should get $50 but was paid $33 \u2192 Loss = $17. '
                   'Rows at or above policy show $0.')
        detail = rows[~rows['Is_Monitor']][['Driver_Name', 'Miles', 'Gross_Pay', 'Net_Pay',
                       'Policy_Driver_Pay', 'Loss_Amount']].rename(columns={
                           'Driver_Name': 'Driver', 'Gross_Pay': 'Gross Pay',
                           'Net_Pay': 'Current Driver Pay',
                           'Policy_Driver_Pay': 'POLICY DRIVER PAY',
                           'Loss_Amount': 'Loss'})
        st.caption('Monitors / escorts (marked "(MO)" / "(Monitor)") are excluded here \u2014 '
                   'they are not trips. They are listed in their own section below.')
        st.dataframe(detail.style.format({c: '${:,.2f}' for c in
                                          ['Gross Pay', 'Current Driver Pay',
                                           'POLICY DRIVER PAY', 'Loss']}).map(
                                               _color_pos_neg, subset=['Loss']),
                     use_container_width=True, hide_index=True)
        if monitor_rides:
            with st.expander(f'Monitor / Escort rides ({monitor_rides:,})', expanded=False):
                mon = rows[rows['Is_Monitor']][['Driver_Name', 'Gross_Pay', 'Net_Pay']].rename(
                    columns={'Driver_Name': 'Monitor', 'Gross_Pay': 'Billed', 'Net_Pay': 'Monitor Pay'})
                st.caption('These ride along with a driver and are billed/paid separately from the trip itself.')
                st.dataframe(mon.style.format({'Billed': '${:,.2f}', 'Monitor Pay': '${:,.2f}'}),
                             use_container_width=True, hide_index=True)

        report_spec = build_printable_report(
            name, driver_trips, monitor_rides, runs, rev, pay, profit, margin, loss, detail,
            non_compliant_pct=nc_pct, potential_profit=potential)
        _report_downloads(report_spec, f'{code}_report', code)

        if st.button('\U0001F4BE Save this Weekly Analysis to History', key=f'save_state_{code}'):
            save_weekly_summary(code, rows,
                                {'runs': runs, 'revenue': rev, 'payment': pay,
                                 'profit': profit, 'loss': loss})
            st.success(f'Analysis for {name} has been saved.')
    with tab2:
        state_history_page(code, name)

# ---------------------------------------------------------------------------
# APP ENTRY
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon='\U0001F690', layout='wide')
st.markdown(CARD_CSS, unsafe_allow_html=True)

st.sidebar.title("Hatem's B.T. Analyzer")
st.sidebar.caption('Beyond Transportation \u2014 financial & pricing control')

with st.sidebar:
    first_files = st.file_uploader('First report(s) \u2014 Excel / CSV / PDF', type=['xlsx', 'xls', 'csv', 'pdf'],
                                   accept_multiple_files=True, key='first_up')
    if first_files:
        try:
            st.session_state['first_df'] = read_first(first_files)
            st.success(f'Loaded {len(st.session_state["first_df"]):,} runs.')
        except Exception as e:
            st.error(f'Could not read the First report(s): {e}')
    with st.expander('Optional: state reports (origin price)'):
        state_files = st.file_uploader('Weekly state reports (Excel / CSV / PDF)', type=['xlsx', 'xls', 'csv', 'pdf'],
                                       accept_multiple_files=True, key='state_up')
        if state_files:
            st.session_state['origin'] = read_state_origin(state_files)
            st.success('State contract prices loaded for: ' +
                       ', '.join(STATES.get(k, k) for k in st.session_state['origin']))
        else:
            # Do not reuse a state report from an earlier upload/session.
            st.session_state['origin'] = {}

df = st.session_state.get('first_df', pd.DataFrame())
origin = st.session_state.get('origin', {})
if not df.empty and origin:
    df = apply_state_prices(df, origin)

legacy_labels = ['\U0001F4CA Consolidated Report', '\U0001F4DA State Reports Consolidated'] + list(STATES.values()) + ['\u26A0 Unassigned']
choice = st.sidebar.radio('Navigation', legacy_labels, key='nav')

if df.empty:
    if choice in ('\U0001F4CA Consolidated Report', '\U0001F4DA State Reports Consolidated'):
        st.title("Hatem's B.T. Analyzer")
        if origin:
            state_reports_consolidated_page(origin)
        else:
            st.info('Upload a First Alt report or a state report in the left sidebar to begin.')
    else:
        code = next(k for k, v in STATES.items() if v == choice)
        if origin:
            state_only_page(origin, code)
        else:
            st.title(f'\U0001F4CA {choice} - Analysis Dashboard')
            tab1, tab2 = st.tabs(['Weekly Analysis', 'Historical Performance'])
            with tab1:
                st.header('Weekly Analysis')
                st.subheader('Official Pricing Policy')
                pol = POLICY_DF[POLICY_DF.State == code]
                st.table(pol[['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay',
                              'Per_Mile_Rate', 'Note']])
                st.info('Upload a First Alt report in the left sidebar to calculate the weekly report.')
            with tab2:
                state_history_page(code, choice)
else:
    if choice == '\U0001F4DA State Reports Consolidated':
        if origin:
            state_reports_consolidated_page(origin)
        else:
            st.info('Upload state reports to build the state-only consolidated report.')
    elif choice == '\U0001F4CA Consolidated Report':
        consolidated_page(df, origin)
    else:
        code = 'Unassigned' if choice == '\u26A0 Unassigned' else next(
            (k for k, v in STATES.items() if v == choice), choice)
        if code == 'Unassigned':
            st.title('\u26A0 Unassigned runs')
            st.caption('These runs come from drivers not in the built-in state list. Add them '
                       'to a state report once and they will be recognised automatically.')
            u = df[df['State'] == 'Unassigned']
            st.metric('Runs', f'{len(u):,}')
            st.dataframe(u[['Trip_Date', 'Driver_Name', 'Trip_Name', 'Miles', 'Revenue',
                            'Source_File']], use_container_width=True, hide_index=True)
        else:
            state_page(df, code, origin)
