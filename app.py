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

def finish_state(d):
    """Add policy pay, margin and compliance to a state report dataframe."""
    cols = ['Policy_Driver_Pay', 'Policy_Status', 'Margin', 'Loss_Amount',
            'Is_Non_Compliant', 'WhatIf_Margin']
    if d.empty:
        for c in cols:
            d[c] = pd.Series(dtype='float64' if c != 'Policy_Status' else 'object')
        return d
    state = str(d['State'].iloc[0])
    maxp = max_fixed_policy(state)
    has_policy = maxp > 0

    def comp(row):
        if not has_policy:
            return float(row.get('Driver_Pay') or 0.0), 'No policy supplied'
        miles = row.get('Miles')
        if pd.notna(miles) and float(miles) > 0:
            ppay, status = policy_pay(state, miles, row.get('Vehicle'), row.get('City'))
            if ppay <= 0:
                return maxp, 'Checked vs top policy value'
            return ppay, status
        return maxp, 'Checked vs top policy value (no miles in report)'

    res = d.apply(comp, axis=1)
    d['Policy_Driver_Pay'] = [r[0] for r in res]
    d['Policy_Status'] = [r[1] for r in res]
    d['Margin'] = d['Revenue'] - d['Driver_Pay']
    d['Loss_Amount'] = (d['Driver_Pay'] - d['Policy_Driver_Pay']).clip(lower=0)
    d['Is_Non_Compliant'] = bool(has_policy) & (d['Loss_Amount'] > 0.05)
    if has_policy:
        d['WhatIf_Margin'] = d['Revenue'] - d[['Driver_Pay', 'Policy_Driver_Pay']].min(axis=1)
    else:
        d['WhatIf_Margin'] = d['Margin']
    return d


def read_state(file, code):
    """Read a weekly state report in ANY common layout (flexible column names)."""
    name = str(getattr(file, 'name', '')).lower()
    if name.endswith('.csv'):
        x = pd.read_csv(file)
    else:
        x = pd.read_excel(file, engine='openpyxl')
    x.columns = [str(c).strip() for c in x.columns]
    up = {c.upper(): c for c in x.columns}
    d = pd.DataFrame(index=x.index)
    d['State'] = code
    d['Driver_Name'] = _pick(x, up, ['DRIVER NAME', 'DRIVER', 'NAME'], 'Unknown')
    d['Trip_Name'] = _pick(x, up, ['TRIP NAME', 'SCHOOL', 'ROUTE'], '')
    d['Trip_Date'] = pd.to_datetime(_pick(x, up, ['DATE', 'TRIP DATE'], None), errors='coerce')
    d['Miles'] = pd.to_numeric(_pick(x, up, ['TOTAL MILES', 'MILES'], None), errors='coerce')
    d['Revenue'] = pd.to_numeric(_pick(x, up, ['REVENUE', 'NET PAY', 'NET'], 0), errors='coerce').fillna(0.0)
    d['Driver_Pay'] = pd.to_numeric(_pick(x, up, ['PAY', 'PAYMENT', 'DRIVER PAY'], 0), errors='coerce').fillna(0.0)
    d['Vehicle'] = d['Trip_Name'].map(vehicle_from)
    d['City'] = d['Trip_Name'].map(city_from)
    keep = (d['Driver_Name'].map(lambda v: clean(v) not in ('', 'nan')) |
            (d['Revenue'] != 0) | (d['Driver_Pay'] != 0))
    d = d[keep].copy()
    return finish_state(d)


def read_first(file):
    """Read a First itemized report (used only to compare actual vs agreed price)."""
    name = str(getattr(file, 'name', '')).lower()
    if name.endswith('.csv'):
        x = pd.read_csv(file)
    else:
        book = pd.ExcelFile(file, engine='openpyxl')
        sheet = 'SP ITEMIZED REPORT' if 'SP ITEMIZED REPORT' in book.sheet_names else book.sheet_names[0]
        x = pd.read_excel(file, sheet_name=sheet, engine='openpyxl')
    x.columns = [str(c).strip() for c in x.columns]
    up = {c.upper(): c for c in x.columns}
    d = pd.DataFrame(index=x.index)
    d['Driver_Name'] = _pick(x, up, ['DRIVER NAME', 'DRIVER'], 'Unknown')
    d['Trip_Name'] = _pick(x, up, ['TRIP NAME', 'NAME'], '')
    d['Trip_Date'] = pd.to_datetime(_pick(x, up, ['DATE', 'TRIP DATE'], None), errors='coerce')
    d['Miles'] = pd.to_numeric(_pick(x, up, ['TOTAL MILES', 'MILES'], 0), errors='coerce').fillna(0.0)
    d['First_Revenue'] = pd.to_numeric(_pick(x, up, ['NET PAY', 'REVENUE', 'NET'], 0), errors='coerce').fillna(0.0)
    d['Company'] = _pick(x, up, ['SP COMPANY', 'COMPANY'], '')
    d['State'] = d.apply(lambda r: state_from(r['Trip_Name'], r['Company']), axis=1)
    keep = (d['Driver_Name'].map(lambda v: clean(v) not in ('', 'nan', 'total', 'totals', 'grand total')) |
            d['Trip_Name'].map(lambda v: clean(v) not in ('', 'nan')))
    return d[keep].copy()


def roster_from_states(states):
    roster = {}
    for code, df in states.items():
        for v in df.get('Driver_Name', []):
            k = clean(v)
            if k and k != 'nan':
                roster[k] = code
    return roster


def attribute_first(first, roster):
    if first.empty:
        return first
    first = first.copy()
    mapped = first['Driver_Name'].map(lambda n: roster.get(clean(n)))
    first['State'] = mapped.where(mapped.notna(), first['State'])
    return first


def all_states_df():
    states = st.session_state.get('states', {})
    if not states:
        return pd.DataFrame()
    return pd.concat(states.values(), ignore_index=True)


def save_history(state, df):
    if df.empty:
        return
    with sqlite3.connect(DB_FILE) as c:
        c.execute('INSERT INTO weekly_summary VALUES(NULL,?,?,?,?,?,?,?,?,?)',
                  (datetime.now().strftime('%Y-%m-%d'), state,
                   str(df.Trip_Date.min().date()) if df.Trip_Date.notna().any() else '',
                   str(df.Trip_Date.max().date()) if df.Trip_Date.notna().any() else '',
                   len(df), float(df.Revenue.sum()), float(df.Driver_Pay.sum()),
                   float(df.Margin.sum()), float(df.Loss_Amount.sum())))

def state_summary_row(code, df):
    revenue = float(df.Revenue.sum())
    pay = float(df.Driver_Pay.sum())
    margin = revenue - pay
    whatif = float(df.WhatIf_Margin.sum())
    nc = int(df.Is_Non_Compliant.sum())
    loss = float(df.Loss_Amount.sum())
    return {
        'State': code, 'State_Name': STATES.get(code, code), 'Trips': int(len(df)),
        'Revenue': revenue, 'Payments': pay, 'Margin': margin,
        'Margin_%': round(margin / revenue * 100, 1) if revenue else 0.0,
        'Violations': nc,
        'Violation_%': round(nc / len(df) * 100, 1) if len(df) else 0.0,
        'Loss': loss, 'Margin_if_Compliant': whatif,
        'Margin_%_if_Compliant': round(whatif / revenue * 100, 1) if revenue else 0.0,
    }


def first_vs_agreed(states, first_df):
    """Agreed price (state report Revenue) vs what First actually pays."""
    if not states or first_df.empty:
        return pd.DataFrame()
    roster = roster_from_states(states)
    fa = attribute_first(first_df, roster)
    rows = []
    for code, df in states.items():
        agreed = float(df.Revenue.sum())
        fsub = fa[fa.State == code]
        first_rev = float(fsub.First_Revenue.sum())
        rows.append({
            'State': code, 'State_Name': STATES.get(code, code),
            'Agreed_Trips': int(len(df)), 'First_Trips': int(len(fsub)),
            'Agreed_Revenue': agreed, 'First_Revenue': first_rev,
            'Difference': agreed - first_rev,
        })
    return pd.DataFrame(rows)


def download_buttons(df, code, prefix):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='Trips', index=False)
        POLICY_DF[POLICY_DF.State == code].to_excel(w, sheet_name='Policy', index=False)
    st.download_button('Download - Excel', out.getvalue(), f'{prefix}_{code}.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key=f'xlsx_{prefix}_{code}')
    st.download_button('Download - CSV', df.to_csv(index=False).encode('utf-8-sig'),
                       f'{prefix}_{code}.csv', 'text/csv', key=f'csv_{prefix}_{code}')


def show_state_report(code, name, df):
    s = state_summary_row(code, df)
    a, b, c, d, e = st.columns(5)
    a.metric('Trips', s['Trips'])
    b.metric('Revenue (agreed)', f"${s['Revenue']:,.2f}")
    c.metric('Payments (drivers)', f"${s['Payments']:,.2f}")
    d.metric('Margin', f"${s['Margin']:,.2f}")
    e.metric('Margin %', f"{s['Margin_%']}%")

    st.subheader('Pricing-policy compliance')
    if max_fixed_policy(code) <= 0:
        st.info('No pricing policy is supplied for this state yet, so trips are not '
                'checked for violations. Provide the policy to enable this check.')
    elif s['Violations'] == 0:
        st.success('All trips are within the pricing policy.')
    else:
        st.warning(
            f"{s['Violations']} trip(s) break the pricing policy "
            f"({s['Violation_%']}% of all trips). "
            f"Extra paid to drivers above policy (loss): ${s['Loss']:,.2f}. "
            f"If every trip followed the policy, margin would be "
            f"${s['Margin_if_Compliant']:,.2f} ({s['Margin_%_if_Compliant']}%) "
            f"instead of ${s['Margin']:,.2f} ({s['Margin_%']}%).")

    first_df = st.session_state.get('first_df', pd.DataFrame())
    cmp = first_vs_agreed({code: df}, first_df)
    if not cmp.empty:
        r = cmp.iloc[0]
        st.subheader('Agreed price (this report) vs what First actually paid')
        st.dataframe(cmp[['Agreed_Trips', 'First_Trips', 'Agreed_Revenue',
                          'First_Revenue', 'Difference']],
                     use_container_width=True, hide_index=True)
        if abs(r['Difference']) > 0.05:
            direction = 'less than' if r['Difference'] > 0 else 'more than'
            st.warning(f"First paid ${abs(r['Difference']):,.2f} {direction} the agreed "
                       f"price for {name}.")

    download_buttons(df, code, 'state_report')
    try:
        save_history(code, df)
    except Exception:
        pass


def upload_state_files():
    files = st.file_uploader('Weekly state reports (Excel / CSV) - any layout',
                             type=['xlsx', 'xls', 'csv'], accept_multiple_files=True,
                             key='state_upload')
    if files:
        states, unknown = {}, []
        for f in files:
            code = state_code_from_name(getattr(f, 'name', ''))
            if code == 'Unknown':
                unknown.append(f.name)
                continue
            try:
                df = read_state(f, code)
            except Exception as e:
                st.error(f'Could not read {f.name}: {e}')
                continue
            states[code] = pd.concat([states[code], df], ignore_index=True) if code in states else df
        if states:
            st.session_state['states'] = states
            st.success('Loaded: ' + ', '.join(f'{STATES.get(k, k)} ({len(v)} trips)'
                                               for k, v in states.items()))
        if unknown:
            st.warning('Could not detect the state from these file names (rename to include '
                       'the state, e.g. "Oregon", "North CA", "AK"): ' + ', '.join(unknown))


def state_page():
    st.title('State Reports')
    st.caption('Upload each weekly state report. The app reads any layout and builds that '
               "state's report automatically.")
    upload_state_files()
    states = st.session_state.get('states', {})
    if not states:
        st.info('Upload one or more weekly state reports to see their reports here.')
        return
    codes = list(states.keys())
    sel = st.selectbox('Choose state', codes, format_func=lambda x: STATES.get(x, x))
    st.header(f'{STATES.get(sel, sel)} - Report')
    st.subheader('Official pricing policy')
    st.table(POLICY_DF[POLICY_DF.State == sel][
        ['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Per_Mile_Rate', 'Note']])
    show_state_report(sel, STATES.get(sel, sel), states[sel])


def first_page():
    st.title('First Reports')
    st.caption('Upload First itemized reports. They are used to compare what First actually '
               'pays against the agreed price from the state reports.')
    files = st.file_uploader('First reports (Excel / CSV)', type=['xlsx', 'xls', 'csv'],
                             accept_multiple_files=True, key='first_upload')
    if files:
        try:
            df = pd.concat([read_first(f) for f in files], ignore_index=True)
            st.session_state['first_df'] = df
            st.success(f'Loaded {len(df):,} First trips from {len(files)} file(s).')
        except Exception as e:
            st.error(f'Could not read the First files: {e}')
    first_df = st.session_state.get('first_df', pd.DataFrame())
    states = st.session_state.get('states', {})
    if not first_df.empty and states:
        st.subheader('Agreed price vs First actual payment (by state)')
        st.dataframe(first_vs_agreed(states, first_df), use_container_width=True, hide_index=True)
    elif not first_df.empty:
        st.info('Upload the weekly state reports (State Reports page) to compare against the '
                'agreed price.')


def consolidated_page():
    st.title('Consolidated Financial Report - All States')
    states = st.session_state.get('states', {})
    if not states:
        st.info('Upload the weekly state reports on the "State Reports" page first.')
        return
    summary = pd.DataFrame([state_summary_row(c, d) for c, d in states.items()])
    summary = summary.sort_values('Revenue', ascending=False).reset_index(drop=True)

    tot_rev = float(summary.Revenue.sum())
    tot_pay = float(summary.Payments.sum())
    tot_margin = tot_rev - tot_pay
    a, b, c, d, e = st.columns(5)
    a.metric('States', len(states))
    b.metric('Trips', f"{int(summary.Trips.sum()):,}")
    c.metric('Revenue', f'${tot_rev:,.2f}')
    d.metric('Payments', f'${tot_pay:,.2f}')
    e.metric('Margin', f'${tot_margin:,.2f}')

    st.subheader('Performance by state')
    perf = summary[['State', 'State_Name', 'Trips', 'Revenue', 'Payments', 'Margin',
                    'Margin_%', 'Margin_if_Compliant', 'Margin_%_if_Compliant']]
    st.dataframe(perf, use_container_width=True, hide_index=True)

    st.subheader('Trips not compliant with the pricing policy')
    viol = summary[summary.Violations > 0][['State', 'State_Name', 'Trips', 'Violations',
                                            'Violation_%', 'Loss']]
    if viol.empty:
        st.success('No trips break the pricing policy (states with no supplied policy are '
                   'not checked).')
    else:
        st.dataframe(viol, use_container_width=True, hide_index=True)
        st.caption(f'Total extra paid to drivers above policy: ${float(viol.Loss.sum()):,.2f}')

    st.subheader('Trips where First differs from the agreed price')
    first_df = st.session_state.get('first_df', pd.DataFrame())
    cmp = first_vs_agreed(states, first_df)
    if cmp.empty:
        st.info('Upload the First reports (First Reports page) to see this comparison.')
    else:
        st.dataframe(cmp[['State', 'State_Name', 'Agreed_Trips', 'First_Trips',
                          'Agreed_Revenue', 'First_Revenue', 'Difference']],
                     use_container_width=True, hide_index=True)
        st.caption(f'Total agreed: ${float(cmp.Agreed_Revenue.sum()):,.2f} | '
                   f'Total First paid: ${float(cmp.First_Revenue.sum()):,.2f} | '
                   f'Difference: ${float(cmp.Difference.sum()):,.2f}')

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        perf.to_excel(w, sheet_name='Performance', index=False)
        (viol if not viol.empty else pd.DataFrame(
            columns=['State', 'State_Name', 'Trips', 'Violations', 'Violation_%', 'Loss'])
         ).to_excel(w, sheet_name='Policy_Violations', index=False)
        (cmp if not cmp.empty else pd.DataFrame(
            columns=['State', 'State_Name', 'Agreed_Revenue', 'First_Revenue', 'Difference'])
         ).to_excel(w, sheet_name='Agreed_vs_First', index=False)
    st.download_button('Download consolidated report - Excel', out.getvalue(),
                       'consolidated_all_states.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key='dl_consolidated')


st.set_page_config(page_title="Hatem's B.T. Analyzer", layout='wide')
st.sidebar.title('Navigation')
menu = st.sidebar.radio('Choose section',
                        ['Consolidated Report', 'State Reports', 'First Reports'])
if menu == 'State Reports':
    state_page()
elif menu == 'First Reports':
    first_page()
else:
    consolidated_page()
