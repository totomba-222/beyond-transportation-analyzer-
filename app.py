from __future__ import annotations
import io, re, sqlite3, json, tempfile
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

DB_FILE = 'history.db'

STATES = {
    'OR': 'Oregon', 'N.CA': 'North California', 'S.CA': 'South California',
    'AK': 'Alaska', 'IL': 'Illinois', 'NM': 'New Mexico', 'NE': 'Nebraska',
    'SAC': 'Sacramento', 'MON': 'Monterey',
    'RS&AZ': 'Riverside & Arizona', 'AZ': 'Arizona',
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
    'NM': ['Albuquerque'], 'NE': ['Lincoln'],
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
        'Albuquerque', 'Lincoln', 'Winston Knolls',
    ]
    for city in cities:
        if city.upper() in s:
            return city
    return 'Unknown'


def state_from(name, company=''):
    s = f'{name} {company}'.upper()
    if 'MONTEREY' in s:
        return 'MON'
    if 'NEW MEXICO' in s or 'ALBUQUERQUE' in s or 'ABQ' in s:
        return 'NM'
    if 'NEBRASKA' in s or 'LINCOLN' in s or 'LINC ' in s:
        return 'NE'
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
    {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 16, 'Policy_Pay': 30.0, 'Per_Mile_Rate': 0, 'Note': 'Nebraska: $30 through 16 miles'},
    {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 9999, 'Policy_Pay': 30.0, 'Per_Mile_Rate': 1.50, 'Note': 'Nebraska: $30 + $1.50 per mile above 16'},
    {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 9999, 'Policy_Pay': 0.0, 'Per_Mile_Rate': 0, 'Note': 'Not supplied'},
    {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33.0, 'Per_Mile_Rate': 0, 'Note': 'New Mexico: 1–6 miles'},
    {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 37.0, 'Per_Mile_Rate': 0, 'Note': 'New Mexico: 7–14 miles'},
    {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 9999, 'Policy_Pay': 37.0, 'Per_Mile_Rate': 1.50, 'Note': 'New Mexico: $37 + $1.50 per mile above 14'},
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
    'Winston Knolls': [{'min': 0, 'max': 9999, 'base': 85.0, 'per_mile': 0.0, 'note': 'Winston Knolls: driver pay $85'}],
    'Lincoln': [
        {'min': 0, 'max': 16, 'base': 30.0, 'per_mile': 0.0, 'note': 'Lincoln: $30 through 16 miles'},
        {'min': 16.01, 'max': 9999, 'base': 30.0, 'per_mile': 1.50, 'note': 'Lincoln: $30 + $1.50 per mile above 16'},
    ],
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
        # Per-mile increases start above this rule's threshold (for example, NM >14 and NE >16).
        return round(float(rule.Policy_Pay) + max(0.0, miles - (float(rule.Min_Miles) - 0.01)) * float(rule.Per_Mile_Rate), 2), 'Matched - state policy'
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
    'fares ameen alshalh': 'N.CA', 'habes al tayyeb': 'N.CA', 'hassan mahmoud hassan': 'N.CA',
    'hesham alrawhani': 'N.CA', 'hiadar elsayed': 'N.CA', 'husni mubarik': 'N.CA', 'ibrahim m elsayed': 'N.CA',
    'isam qadari': 'N.CA', 'lulit girma bune': 'N.CA', 'mohamed ahmed hugais': 'N.CA',
    'mohamed hussein altayeb abdalla': 'N.CA', 'mohamed omar ali': 'N.CA', 'mohamed omir': 'N.CA',
    'mohammed ahmed haneen': 'N.CA', 'mohammed h adam': 'N.CA', 'mohaned abdelazim ahmed elwali': 'N.CA',
    'muhammad laiq': 'N.CA', 'mustafa ali albarea': 'N.CA', 'mustafa hassan abdalkareem': 'N.CA',
    'nagi alnaeem': 'N.CA', 'nagibah e alghazali': 'N.CA', 'omer omer': 'N.CA', 'rashid masood malik': 'N.CA',
    'salah hassan': 'N.CA', 'samir m abas': 'N.CA', 'siddieg basher khair': 'N.CA',
    'snose omar hamid ali': 'N.CA', 'solomon bekkele': 'N.CA', 'suhaib yousef batayneh': 'N.CA',
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
    'mohammed emad bedaer': 'RS&AZ', 'mona bazzoun': 'RS&AZ', 'mostafa safwan alhakim': 'RS&AZ',
    'mostafa sharaby': 'RS&AZ', 'mukesh kumar': 'RS&AZ', 'mustafa f m zatar': 'RS&AZ',
    'nabeel aldabbas': 'RS&AZ', 'nada a suleiman': 'RS&AZ', 'nada abusnoubar': 'RS&AZ',
    'nesrin elshabasy': 'RS&AZ', 'niveen mohd abdel aziz abbad': 'RS&AZ', 'rana muhammad abrar bashir': 'RS&AZ',
    'rana nazmi abu samrah salaymeh': 'RS&AZ', 'rehan ahmad malik': 'RS&AZ',
    'ruben bruno ramirez rivera': 'RS&AZ', 'safwan alhakim': 'RS&AZ', 'sagar sagar': 'RS&AZ',
    'saif said awda': 'RS&AZ', 'salah musa hussein': 'RS&AZ', 'sandeep singh bajwa': 'RS&AZ',
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
NO_POLICY = set()  # A state is unchecked only when no numeric policy exists.

# Reconciliation controls. The state workbook may contain the observed fare
# ($42.50 in Alaska), while the approved contract target is $45.00. We keep
# both values so the difference is visible and auditable.
CONTRACT_TARGETS = {
    # state: (observed Excel fare, approved contract target)
    'AK': (42.50, 45.00),
}

# Reporting roll-ups requested by the operator. Raw trip rows remain untouched;
# these are applied only to the consolidated comparison table.
ROLLUP_ADJUSTMENTS = {
    'RS&AZ': ['AZ'],       # Riverside & Arizona less Arizona
    'N.CA': ['SAC'],       # North California less Sacramento
}


def has_policy(state):
    return state not in NO_POLICY and max_fixed_policy(state) > 0


def iso_week(dt):
    try:
        return int(pd.Timestamp(dt).isocalendar().week)
    except Exception:
        return 0


def _read_report_table(file_obj, preferred_sheet=None):
    """Read a report even when Excel has title rows above the real header."""
    name = str(getattr(file_obj, 'name', '')).lower()
    if name.endswith('.csv'):
        candidates = [pd.read_csv(file_obj, header=0)]
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
    for frame in candidates:
        frame = frame.copy()
        frame.columns = [str(c).strip() for c in frame.columns]
        upper = {str(c).strip().upper() for c in frame.columns}
        if upper & wanted:
            return frame
    return candidates[0] if candidates else pd.DataFrame()


def _normal_key(v):
    if pd.isna(v):
        return ''
    return re.sub(r'[^a-z0-9]+', ' ', str(v).lower()).strip()


def _column_alias(frame, aliases, startswith=()):
    """Find a data column despite suffixes such as (F), spaces, or punctuation."""
    cols = list(frame.columns)
    norm = {_normal_key(c): c for c in cols}
    for alias in aliases:
        key = _normal_key(alias)
        if key in norm:
            return norm[key]
    for key, original in norm.items():
        if any(key.startswith(_normal_key(prefix)) for prefix in startswith):
            return original
    return None


def _series_from_column(frame, aliases, default=0, startswith=()):
    col = _column_alias(frame, aliases, startswith=startswith)
    if col is None:
        return pd.Series([default] * len(frame), index=frame.index), None
    return frame[col], str(col)


def _date_key(v):
    dt = pd.to_datetime(v, errors='coerce')
    return '' if pd.isna(dt) else dt.strftime('%Y-%m-%d')


def _price_column(up):
    for n in ['REVENUE', 'NET PAY', 'DRIVER PAY', 'DRIVER RATE', 'CONTRACT PRICE',
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
    """Read every sheet and every side-by-side block in STATESREPORT-style workbooks."""
    name = str(getattr(file_obj, 'name', '')).lower()
    if not name.endswith(('.xlsx', '.xls')):
        return pd.DataFrame()
    book = pd.ExcelFile(file_obj, engine='openpyxl')
    all_out = []
    summary_rows = []
    for sheet in book.sheet_names:
        raw = pd.read_excel(file_obj, sheet_name=sheet, header=None, engine='openpyxl')
        blocks, header_specs = [], []
        for row_no, row in raw.iterrows():
            for col_no, value in enumerate(row):
                if clean(value).upper() != 'DRIVER NAME':
                    continue
                ahead = [clean(v).upper() for v in row.iloc[col_no:col_no + 12].tolist()]
                if 'REVENUE' not in ahead and 'REVENUE ' not in ahead:
                    continue
                revenue_col = next((col_no + j for j, v in enumerate(ahead)
                                    if v in ('REVENUE', 'REVENUE ')), None)
                payment_col = next((col_no + j for j, v in enumerate(ahead)
                                    if v in ('PAY', 'PAYMENT', 'PAYMENT ')), None)
                if revenue_col is None:
                    continue
                title = raw.iat[row_no - 1, col_no] if row_no else getattr(file_obj, 'name', '')
                code = state_code_from_name(title)
                if code == 'Unknown':
                    code = state_code_from_name(f'{sheet} {getattr(file_obj, "name", "")}')
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
        for b in blocks:
            next_headers = [h for h, c in header_specs
                            if h > b['start'] and b['col'] <= c < b['col'] + b['width']]
            end_row = min(next_headers) if next_headers else len(raw)
            for i in range(b['start'], end_row):
                driver = raw.iat[i, b['col']]
                price = raw.iat[i, b['revenue']]
                if pd.isna(driver) or clean(driver) in {'', 'total', 'totals', 'grand total'}:
                    continue
                price_num = _number_series(pd.Series([price])).iloc[0]
                # Keep a numbered state-report row in the run count even when
                # its Revenue cell is text/invalid (e.g. 'drug'). It remains
                # unmatched for the claim, but must not disappear from runs.
                pay_num = (float(_number_series(pd.Series([raw.iat[i, b['payment']]])).iloc[0])
                           if b['payment'] is not None and not pd.isna(_number_series(pd.Series([raw.iat[i, b['payment']]])).iloc[0]) else pd.NA)
                all_out.append({
                    'State': b['code'], 'Driver_Key': _normal_key(driver),
                    'Trip_Key': _normal_key(raw.iat[i, b['trip']]) if b['trip'] is not None else '',
                    'Date_Key': _date_key(raw.iat[i, b['date']]) if b['date'] is not None else '',
                    'Miles_Key': float(_number_series(pd.Series([raw.iat[i, b['miles']]])).fillna(0).iloc[0]) if b['miles'] is not None else 0.0,
                    'State_Price': (float(price_num) if not pd.isna(price_num) else pd.NA), 'State_Pay': pay_num,
                    'Source_File': f'{getattr(file_obj, "name", "")}::{sheet}'})
    out = pd.DataFrame(all_out)
    # Some state workbooks contain summary-only rows such as Monitor with
    # Revenue, Pay and Runs but no driver/trip detail. Capture them separately
    # so they count in state totals without being duplicated in trip matching.
    for sheet in book.sheet_names:
        raw = pd.read_excel(file_obj, sheet_name=sheet, header=None, engine='openpyxl')
        for _, row in raw.iterrows():
            values = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
            # Match a standalone summary label only. Do not treat trip names
            # such as 'District Monitor (...)' as financial summary rows.
            if not any(v in {'monitor', 'monitor summary', 'monitor total'} for v in values):
                continue
            text = ' '.join(values)
            nums = []
            for v in row.tolist():
                n = _number_series(pd.Series([v])).iloc[0]
                if not pd.isna(n):
                    nums.append(float(n))
            if len(nums) >= 3:
                revenue = max(nums)
                remaining = [n for n in nums if n != revenue]
                pay = max(remaining) if remaining else 0.0
                runs = min(nums)
                code = state_code_from_name(f'{sheet} {getattr(file_obj, "name", "")}')
                summary_rows.append({'State': code, 'Summary': 'Monitor',
                                     'Revenue': revenue, 'Pay': pay, 'Runs': int(runs)})
    # Exclude MO/Monitor labels from the state report as well. These are
    # operational labels, not payable trips, and must not affect run counts
    # or the First-vs-State claim.
    if not out.empty:
        non_trip = out.apply(lambda r: is_non_trip_label(r.get('Driver_Key', '')) or
                              is_non_trip_label(r.get('Trip_Key', '')), axis=1)
        out.attrs['excluded_non_trip_rows'] = int(non_trip.sum())
        out = out[~non_trip].reset_index(drop=True)
    out.attrs['summary_rows'] = summary_rows
    return out


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


def _get_history_dir():
    # Streamlit Cloud does not permit writing to /home/ubuntu or the mounted
    # source tree. Prefer an app-local folder when writable, then use /tmp.
    candidates = [Path.cwd() / '.financial_history',
                  Path(tempfile.gettempdir()) / 'bta_financial_history']
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / '.write_test'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            return candidate
        except (OSError, PermissionError):
            continue
    return None


HISTORY_DIR = _get_history_dir()


def is_non_trip_label(value):
    """Exclude explicit Monitor records; MO rows remain part of the state report."""
    text = str(value or '').strip().upper()
    return text == 'MONITOR' or text.endswith(' MONITOR') or bool(re.search(r'\(\s*MONITOR\s*\)', text))


def save_financial_snapshot(df, origin):
    """Persist a compact weekly snapshot for next week's variance review."""
    if df.empty:
        return None
    dates = pd.to_datetime(df.get('Trip_Date'), errors='coerce').dropna()
    week = int(dates.max().isocalendar().week) if len(dates) else int(pd.Timestamp.today().isocalendar().week)
    year = int(dates.max().isocalendar().year) if len(dates) else int(pd.Timestamp.today().isocalendar().year)
    total = display_total(df, origin)
    payload = {'year': year, 'week': week, 'saved_at': pd.Timestamp.now().isoformat(),
               'runs': total['runs'], 'first_paid_fare': total['revenue'],
               'state_revenue': total['state_revenue'], 'state_driver_pay': total['payment'],
               'amount_due': total['amount_due'], 'profit': total['profit'],
               'margin': total['margin'], 'non_compliant': total['non_compliant'],
               'loss': total['loss'], 'matched_runs': total.get('matched_runs', 0),
               'unmatched_state_runs': total.get('unmatched_state_runs', 0)}
    if HISTORY_DIR is not None:
        path = HISTORY_DIR / f'{year}-W{week:02d}.json'
        try:
            path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        except (OSError, PermissionError):
            pass
    return payload


def previous_snapshot(current):
    if not current:
        return None
    if HISTORY_DIR is None:
        return None
    files = sorted(HISTORY_DIR.glob('*.json'))
    old = []
    for path in files:
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            if (item.get('year'), item.get('week')) != (current.get('year'), current.get('week')):
                old.append(item)
        except Exception:
            pass
    return old[-1] if old else None


def pct_change(now, before):
    if before in (None, 0) or pd.isna(before) or pd.isna(now):
        return None
    return (now - before) / abs(before) * 100


def read_first(files):
    """Read First reports with Net Pay as the primary paid-fare source."""
    frames = []
    diagnostics = []
    for f in files:
        preferred = 'SP ITEMIZED REPORT'
        x = _read_report_table(f, preferred)
        x.columns = [str(c).strip() for c in x.columns]
        driver_s, driver_col = _series_from_column(x, ['DRIVER NAME', 'DRIVER'], 'Unknown', ('DRIVER NAME', 'DRIVER'))
        district_s, district_col = _series_from_column(x, ['DISTRICT', 'STATE', 'REGION', 'AREA'], '', ('DISTRICT', 'STATE', 'REGION', 'AREA'))
        trip_s, trip_col = _series_from_column(x, ['TRIP NAME', 'NAME'], '', ('TRIP NAME',))
        date_s, date_col = _series_from_column(x, ['DATE', 'TRIP DATE'], None, ('DATE', 'TRIP DATE'))
        miles_s, miles_col = _series_from_column(x, ['TOTAL MILES', 'MILES'], 0, ('TOTAL MILES', 'MILES'))
        # Net Pay / Paid Fare is intentionally checked before Revenue.
        net_s, net_col = _series_from_column(x,
            ['NET PAY', 'NET PAY (F)', 'PAID FARE', 'PAID FARE (F)', 'FIRST PAID FARE'],
            pd.NA, startswith=('NET PAY', 'PAID FARE', 'FIRST PAID FARE'))
        revenue_s, revenue_col = _series_from_column(x, ['REVENUE', 'GROSS REVENUE'], pd.NA, ('REVENUE',))
        state_payment_col = _column_alias(x, ['PAY', 'PAYMENT', 'DRIVER PAY'], startswith=('PAY', 'DRIVER PAY'))
        state_like_file = net_col is None and revenue_col is not None and state_payment_col is not None
        d = pd.DataFrame(index=x.index)
        d['Driver_Name'] = driver_s
        d['District'] = district_s
        d['Trip_Name'] = trip_s
        d['Trip_Date'] = pd.to_datetime(date_s, errors='coerce')
        d['Miles'] = _number_series(miles_s).fillna(0.0)
        d['First_Reported_Revenue'] = _number_series(revenue_s)
        d['Net_Pay'] = _number_series(net_s)
        # A Revenue + payment workbook without Net Pay is a state report, not
        # a First report. Never reinterpret driver payment as First revenue.
        if state_like_file:
            d['Revenue'] = 0.0
        else:
            d['Revenue'] = d['Net_Pay'].where(d['Net_Pay'].notna(), d['First_Reported_Revenue']).fillna(0.0)
        d['First_Paid_Fare'] = d['Revenue']
        d['Paid_Fare_Source'] = d['Net_Pay'].notna().map({True: 'First Alt Net Pay', False: 'First Alt Revenue'})
        gross_s, gross_col = _series_from_column(x, ['GROSS PAY', 'GROSS'], 0, ('GROSS PAY', 'GROSS'))
        d['First_Gross'] = _number_series(gross_s).fillna(0.0)
        company_s, company_col = _series_from_column(x, ['SP COMPANY', 'COMPANY'], '', ('SP COMPANY', 'COMPANY'))
        d['Company'] = company_s
        d['Source_File'] = getattr(f, 'name', '')
        d['First_NetPay_Column'] = net_col or ''
        d['First_Revenue_Column'] = revenue_col or ''
        frames.append(d)
        diagnostics.append({'File': getattr(f, 'name', ''), 'Rows read': len(x),
                            'Driver column': driver_col or 'NOT FOUND',
                            'Net Pay column': net_col or 'NOT FOUND',
                            'Revenue column': revenue_col or 'NOT FOUND',
                            'Net Pay nonzero rows': int((d['Net_Pay'].fillna(0) != 0).sum()),
                            'First Paid Fare total': float(d['Revenue'].sum()),
                            'Warning': 'Looks like a state report; upload under State reports' if state_like_file else ''})
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    d['Excluded_Non_Trip'] = d['Trip_Name'].map(is_non_trip_label)
    excluded = int(d['Excluded_Non_Trip'].sum())
    d = d[~d['Excluded_Non_Trip']].copy()
    bad = {'', 'nan', 'total', 'totals', 'grand total'}
    keep = d['Driver_Name'].map(lambda v: clean(v) not in bad) & (
        (d['Revenue'] != 0) | (d['Trip_Name'].map(lambda v: clean(v) not in {'', 'nan'})))
    d = d[keep].copy()
    d['State'] = [state_from_first_row(row['District'], row['Driver_Name'], row['Trip_Name'], row['Company'])
                  for _, row in d.iterrows()]
    d['State'] = d['State'].replace({'Unknown': 'Unassigned'})
    d['Vehicle'] = d['Trip_Name'].map(vehicle_from)
    d['City'] = d['Trip_Name'].map(city_from)
    d['Week'] = d['Trip_Date'].map(iso_week)
    pol = d.apply(lambda r: policy_pay(r['State'], r['Miles'], r['Vehicle'], r['City']), axis=1)
    d['Policy_Pay'] = [p[0] for p in pol]
    d['Policy_Note'] = [p[1] for p in pol]
    d['State_Price'] = pd.NA
    d['State_Revenue'] = pd.NA
    d['State_Pay'] = pd.NA
    d['Price_Difference'] = pd.NA
    d['Price_Source'] = 'Pricing policy'
    d.attrs['read_diagnostics'] = diagnostics
    d.attrs['excluded_non_trip_rows'] = excluded
    return _recalculate(d)


def _recalculate(d):
    """Recalculate driver payment/profit and state-price reconciliation separately."""
    state_price = pd.to_numeric(d['State_Price'], errors='coerce')
    state_pay = pd.to_numeric(d.get('State_Pay', pd.Series(pd.NA, index=d.index)), errors='coerce')
    policy_price = pd.to_numeric(d['Policy_Pay'], errors='coerce')
    # Positive difference is money owed to the company by First.
    # Preserve the fare actually read from Excel, then apply an explicit
    # contract target only where configured. This makes AK $42.50 -> $45.00
    # produce a transparent $2.50 shortage per run.
    d['State_Reported_Price'] = state_price
    target = state_price.copy()
    for state, (observed_price, target_price) in CONTRACT_TARGETS.items():
        mask = d['State'].eq(state) & state_price.notna()
        target.loc[mask & state_price.sub(observed_price).abs().le(0.01)] = float(target_price)
    d['State_Price'] = target
    d['Price_Difference'] = target - d['First_Paid_Fare']
    d['State_Revenue'] = target
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
    d['Profit'] = (d['First_Paid_Fare'] - d['Policy_Pay']).where(effective, other=pd.NA)
    d['Non_Compliant'] = effective & (d['First_Paid_Fare'] < d['Policy_Pay'] - 0.01)
    d['Loss'] = (d['Policy_Pay'] - d['First_Paid_Fare']).where(d['Non_Compliant'], other=0.0)
    return d


def read_state_origin(files):
    """Read state reports as trip-level contract prices, not one state total."""
    rows = {}
    summaries = {}
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
        for summary in part.attrs.get('summary_rows', []):
            scode = summary.get('State', code)
            if scode == 'Unknown':
                scode = code
            summaries.setdefault(scode, {'runs': 0, 'revenue': 0.0, 'pay': 0.0})
            summaries[scode]['runs'] += int(summary.get('Runs', 0))
            summaries[scode]['revenue'] += float(summary.get('Revenue', 0.0))
            summaries[scode]['pay'] += float(summary.get('Pay', 0.0))
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
    all_codes = set(rows) | set(summaries)
    for code in all_codes:
        info = rows.get(code, {'rows': []})
        all_rows = pd.concat(info['rows'], ignore_index=True) if info.get('rows') else pd.DataFrame(columns=['State_Price', 'State_Pay'])
        sm = summaries.get(code, {'runs': 0, 'revenue': 0.0, 'pay': 0.0})
        result[code] = {'rows': all_rows,
                        'origin': float(pd.to_numeric(all_rows.get('State_Price', pd.Series(dtype=float)), errors='coerce').sum()) + sm['revenue'],
                        'runs': int(len(all_rows)) + sm['runs'],
                        'summary_runs': sm['runs'], 'summary_revenue': sm['revenue'],
                        'summary_pay': sm['pay']}
    return result


def apply_state_prices(d, origin):
    """Match state rows to First rows, preserving duplicate trips by occurrence."""
    if d.empty or not origin:
        return d
    d = d.copy()
    d['_driver_key'] = d['Driver_Name'].map(_normal_key)
    d['_trip_key'] = d['Trip_Name'].map(_normal_key)
    # Use the uploaded state reports as an additional authoritative roster.
    # This fixes files where the First report contains drivers not present in
    # the built-in name map, preventing valid runs from becoming Unassigned.
    roster = {}
    for origin_code, info in origin.items():
        for driver_key in info.get('rows', pd.DataFrame()).get('Driver_Key', pd.Series(dtype=str)).dropna().unique():
            if driver_key:
                roster.setdefault(driver_key, set()).add(origin_code)
    inferred = d['_driver_key'].map(lambda k: next(iter(roster[k])) if k in roster and len(roster[k]) == 1 else None)
    unassigned = d['State'].eq('Unassigned') & inferred.notna()
    d.loc[unassigned, 'State'] = inferred[unassigned]
    d['_date_key'] = d['Trip_Date'].map(_date_key)
    d['_miles_key'] = pd.to_numeric(d['Miles'], errors='coerce').fillna(0).round(2)
    d['_occ'] = d.groupby(['State', '_driver_key', '_trip_key', '_date_key', '_miles_key'], dropna=False).cumcount()
    def usable(value):
        return bool(value not in ('', '0', 0) and not pd.isna(value))

    def assign_by_keys(first, state_rows, key_pairs):
        """Assign prices using the strongest available key, one occurrence at a time."""
        for first_cols, state_cols in key_pairs:
            if not all(c in first.columns for c in first_cols):
                continue
            if not all(c in state_rows.columns for c in state_cols):
                continue
            available = state_rows.copy()
            available['_used'] = False
            for idx, row in first.iterrows():
                if pd.notna(first.at[idx, 'State_Price']):
                    continue
                values = [row[c] for c in first_cols]
                if not all(usable(v) for v in values):
                    continue
                mask = ~available['_used']
                for col, value in zip(state_cols, values):
                    mask &= available[col].eq(value)
                hits = available.index[mask]
                if len(hits):
                    hit = hits[0]
                    first.at[idx, 'State_Price'] = available.at[hit, 'State_Price']
                    if 'State_Pay' in available.columns:
                        first.at[idx, 'State_Pay'] = available.at[hit, 'State_Pay']
                    available.at[hit, '_used'] = True
            if first['State_Price'].notna().all():
                break

    for first_code in d['State'].dropna().unique():
        compatible_codes = {first_code}
        if first_code == 'AZ':
            compatible_codes.add('RS&AZ')
        if first_code == 'SAC':
            compatible_codes.add('N.CA')
        candidate_frames = [info['rows'] for code, info in origin.items()
                            if code in compatible_codes and 'rows' in info]
        if not candidate_frames:
            continue
        r = pd.concat(candidate_frames, ignore_index=True)
        mask = d['State'].eq(first_code)
        first = d.loc[mask].copy()
        # Try exact trip identity first, then gracefully handle reports without
        # date/miles/driver columns. Every state row is used at most once.
        assign_by_keys(first, r, [
            (['_driver_key', '_trip_key', '_date_key', '_miles_key'],
             ['Driver_Key', 'Trip_Key', 'Date_Key', 'Miles_Key']),
            (['_driver_key', '_trip_key', '_date_key'],
             ['Driver_Key', 'Trip_Key', 'Date_Key']),
            (['_driver_key', '_trip_key'], ['Driver_Key', 'Trip_Key']),
            (['_trip_key', '_date_key', '_miles_key'], ['Trip_Key', 'Date_Key', 'Miles_Key']),
            (['_trip_key', '_miles_key'], ['Trip_Key', 'Miles_Key']),
            (['_driver_key'], ['Driver_Key']),
        ])
        d.loc[mask, 'State_Price'] = first['State_Price']
        d.loc[mask, 'State_Pay'] = first['State_Pay']
    d = _recalculate(d)
    return d.drop(columns=['_driver_key', '_trip_key', '_date_key', '_miles_key', '_occ'])

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
    price_diff = float(diff_values.sum()) if diff_values.notna().any() else float('nan')
    chk = d[d['Checked']]
    policy_state = len(chk) > 0
    if policy_state:
        pay = float(chk['Policy_Pay'].sum())
        profit = rev - pay
        nc = int(d['Non_Compliant'].sum())
        loss = float(d['Loss'].sum())
        profit_if = profit + loss
    else:
        pay = profit = loss = profit_if = float('nan')
        nc = 0
    amount_due = max(price_diff, 0.0) if not pd.isna(price_diff) else float('nan')
    return {
        'runs': runs, 'revenue': rev, 'state_revenue': state_rev,
        'price_difference': price_diff, 'amount_due': amount_due,
        'payment': pay, 'profit': profit,
        'margin': (profit / rev * 100) if (policy_state and rev) else float('nan'),
        'total_runs': runs, 'compliant': (runs - nc) if policy_state else runs,
        'non_compliant': nc, 'loss': loss, 'profit_if': profit_if,
        'margin_if': (profit_if / rev * 100) if (policy_state and rev) else float('nan'),
        'policy_state': policy_state,
    }


def consolidated_rollup(df):
    """Return display-only state summaries after configured child deductions."""
    numeric = ['runs', 'revenue', 'state_revenue', 'price_difference', 'amount_due',
               'payment', 'profit', 'total_runs', 'non_compliant', 'loss', 'profit_if']
    blocks = {code: agg_block(df[df['State'].eq(code)]) for code in df['State'].dropna().unique()}
    out = []
    for code, b in blocks.items():
        row = dict(b)
        row['code'] = code
        row['deducted_from'] = ''
        children = ROLLUP_ADJUSTMENTS.get(code, [])
        for child in children:
            cb = blocks.get(child)
            if not cb:
                continue
            row['deducted_from'] += (', ' if row['deducted_from'] else '') + STATES.get(child, child)
            for key in numeric:
                if pd.notna(row.get(key)) and pd.notna(cb.get(key)):
                    row[key] -= cb[key]
        row['margin'] = (row['profit'] / row['revenue'] * 100) if row.get('revenue') else float('nan')
        row['margin_if'] = (row['profit_if'] / row['revenue'] * 100) if row.get('revenue') else float('nan')
        row['compliant'] = row['total_runs'] - row['non_compliant'] if row.get('policy_state') else row['total_runs']
        out.append(row)
    return out



def _money(v):
    return '-' if pd.isna(v) else f'${v:,.2f}'


def _pct(v):
    return '-' if pd.isna(v) else f'{v:,.1f}%'


def _int(v):
    return '-' if pd.isna(v) else f'{int(v):,}'


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
.block-container {padding-top: 2rem;}
.kpi {background: linear-gradient(135deg,#1e3a8a 0%,#2563eb 100%); color:#fff;
  border-radius:14px; padding:16px 18px; margin:4px 0;
  box-shadow:0 4px 14px rgba(0,0,0,.12);}
.kpi .lab {font-size:.78rem; letter-spacing:.04em; opacity:.85; text-transform:uppercase;}
.kpi .val {font-size:1.55rem; font-weight:700; margin-top:4px;}
.kpi.g {background:linear-gradient(135deg,#065f46 0%,#059669 100%);}
.kpi.r {background:linear-gradient(135deg,#7f1d1d 0%,#dc2626 100%);}
.kpi.o {background:linear-gradient(135deg,#78350f 0%,#d97706 100%);}
.kpi.p {background:linear-gradient(135deg,#4c1d95 0%,#7c3aed 100%);}
</style>
"""


def kpi(col, label, value, tone=''):
    col.markdown(f'<div class="kpi {tone}"><div class="lab">{label}</div>'
                 f'<div class="val">{value}</div></div>', unsafe_allow_html=True)


def kpi_row(total, state_name=''):
    comp_rate = (total['compliant'] / total['total_runs'] * 100) if total['total_runs'] else 0
    revenue_f_label = f'{state_name} Paid Fare / Net Pay (F)' if state_name else 'First Paid Fare / Net Pay (F)'
    revenue_state_label = f'{state_name} Revenue (State Report)' if state_name else 'State Revenue (State Report)'
    a, b, c, d, e = st.columns(5)
    kpi(a, 'Runs', _int(total['runs']))
    kpi(b, revenue_f_label, _money(total['revenue']), 'p')
    kpi(c, revenue_state_label, _money(total['state_revenue']), 'o')
    kpi(d, 'Profit', _money(total['profit']), 'g')
    kpi(e, 'State Driver Pay (State Report)', _money(total['payment']), 'o')
    f, g, h, i, j = st.columns(5)
    kpi(f, 'Amount due from First', _money(total['amount_due']), 'r')
    kpi(g, 'Margin', _pct(total['margin']), 'g')
    kpi(h, 'Revenue / run', _money(total['revenue'] / total['runs']) if total['runs'] else '-')
    kpi(i, 'Profit / run',
        _money(total['profit'] / total['runs']) if (total['runs'] and total['policy_state']) else '-', 'g')
    kpi(j, 'Non-compliant runs', _int(total['non_compliant']), 'r')


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
    """Group matched trips by state and per-trip price difference."""
    if df.empty or 'State_Price' not in df:
        return pd.DataFrame()
    x = df[df['State_Price'].notna()].copy()
    if x.empty:
        return pd.DataFrame()
    x['Difference_Per_Run'] = (pd.to_numeric(x['State_Price'], errors='coerce') -
                               pd.to_numeric(x['Revenue'], errors='coerce')).round(2)
    out = (x.groupby(['State', 'Difference_Per_Run'], dropna=False)
             .agg(Runs=('Revenue', 'size'),
                  First_Revenue=('Revenue', 'sum'),
                  State_Revenue=('State_Price', 'sum'))
             .reset_index())
    out['Total_Difference'] = (out['State_Revenue'] - out['First_Revenue']).round(2)
    out['Amount_Due_From_First'] = out['Total_Difference'].clip(lower=0).round(2)
    out['State'] = out['State'].map(lambda c: STATES.get(c, c))
    return out.sort_values(['State', 'Difference_Per_Run'])


def df_download(df, fname, key, sheets=None):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        if sheets:
            for sn, sdf in sheets.items():
                sdf.to_excel(w, sheet_name=sn[:31], index=True)
        else:
            df.to_excel(w, sheet_name='Report', index=True)
    st.download_button('⬇ Download Excel', out.getvalue(), fname,
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=key)


# ---------------------------------------------------------------------------
# PAGES
# ---------------------------------------------------------------------------

def display_block(d, code, origin):
    """Use complete state totals while keeping First/state matching auditable."""
    b = agg_block(d)
    # Claim basis: contract State Revenue minus First Net Pay, per matched trip.
    # This deliberately does not use State Driver Pay.
    if not d.empty:
        first = pd.to_numeric(d.get('Revenue', pd.Series(pd.NA, index=d.index)), errors='coerce')
        contract = pd.to_numeric(d.get('State_Revenue', pd.Series(pd.NA, index=d.index)), errors='coerce')
        raw_contract = pd.to_numeric(d.get('State_Price', pd.Series(pd.NA, index=d.index)), errors='coerce')
        contract = contract.where(contract.notna(), raw_contract)
        claim = (contract - first).where(contract.notna() & first.notna())
        b['price_difference'] = float(claim.sum()) if claim.notna().any() else float('nan')
        b['amount_due'] = max(b['price_difference'], 0.0) if pd.notna(b['price_difference']) else float('nan')
        b['below_contract_runs'] = int((claim > 0.01).sum())
        b['claim_matched_runs'] = int(claim.notna().sum())
    else:
        b['below_contract_runs'] = 0
        b['claim_matched_runs'] = 0
    info = origin.get(code) if origin else None
    if not info:
        b['matched_runs'] = int(d['State_Price'].notna().sum()) if 'State_Price' in d else 0
        b['unmatched_state_runs'] = 0
        return b
    state_rows = info.get('rows', pd.DataFrame())
    matched = int(d['State_Price'].notna().sum()) if 'State_Price' in d else 0
    b['matched_runs'] = matched
    b['unmatched_state_runs'] = max(int(info.get('runs', 0)) - matched, 0)
    b['runs'] = max(int(b.get('runs', 0)), int(info.get('runs', 0)))
    b['state_revenue'] = float(info.get('origin', b.get('state_revenue', 0.0)))
    pay = pd.to_numeric(state_rows.get('State_Pay', pd.Series(dtype=float)), errors='coerce')
    state_pay_total = float(pay.sum()) if pay.notna().any() else 0.0
    state_pay_total += float(info.get('summary_pay', 0.0))
    if state_pay_total:
        b['payment'] = state_pay_total
    if b['policy_state'] and pd.notna(b['revenue']):
        b['profit'] = b['revenue'] - b['payment']
        b['margin'] = (b['profit'] / b['revenue'] * 100) if b['revenue'] else float('nan')
        b['profit_if'] = b['profit'] + b['loss']
        b['margin_if'] = (b['profit_if'] / b['revenue'] * 100) if b['revenue'] else float('nan')
    return b


def display_total(df, origin):
    """Top dashboard total built from the same state blocks as the table."""
    codes = sorted(set(df['State'].dropna().unique()) | set(origin.keys() if origin else []))
    numeric = ['runs', 'revenue', 'state_revenue', 'price_difference', 'amount_due',
               'payment', 'profit', 'total_runs', 'non_compliant', 'loss', 'profit_if',
               'matched_runs', 'unmatched_state_runs', 'below_contract_runs', 'claim_matched_runs']
    total = {k: 0.0 for k in numeric}
    total['policy_state'] = False
    for code in codes:
        block = display_block(df[df['State'].eq(code)], code, origin)
        for key in numeric:
            value = block.get(key, 0.0)
            if pd.notna(value):
                total[key] += float(value)
        total['policy_state'] = total['policy_state'] or bool(block.get('policy_state'))
    total['runs'] = int(total['runs'])
    total['matched_runs'] = int(total['matched_runs'])
    total['unmatched_state_runs'] = int(total['unmatched_state_runs'])
    total['below_contract_runs'] = int(total['below_contract_runs'])
    total['claim_matched_runs'] = int(total['claim_matched_runs'])
    total['total_runs'] = int(total['total_runs'])
    total['non_compliant'] = int(total['non_compliant'])
    total['margin'] = total['profit'] / total['revenue'] * 100 if total['revenue'] else float('nan')
    total['margin_if'] = total['profit_if'] / total['revenue'] * 100 if total['revenue'] else float('nan')
    total['compliant'] = total['total_runs'] - total['non_compliant']
    return total


def state_only_page(origin):
    st.title('State reports loaded — First report not uploaded yet')
    st.info('You can start with the state report. Upload the First detailed report later to calculate Net Pay differences per trip.')
    rows = []
    for code, info in sorted(origin.items(), key=lambda kv: STATES.get(kv[0], kv[0])):
        sr = info.get('rows', pd.DataFrame())
        pay = pd.to_numeric(sr.get('State_Pay', pd.Series(dtype=float)), errors='coerce')
        state_pay_total = (float(pay.sum()) if pay.notna().any() else 0.0) + float(info.get('summary_pay', 0.0))
        rows.append({'State': STATES.get(code, code), 'State Runs': info.get('runs', 0),
                     'State Revenue': info.get('origin', 0.0),
                     'State Pay': state_pay_total if state_pay_total else float('nan'),
                     'First Net Pay': float('nan'), 'Matched Runs': 0,
                     'Unmatched State Runs': info.get('runs', 0)})
    out = pd.DataFrame(rows)
    st.metric('States loaded', f'{len(out):,}')
    for _, row in out.iterrows():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"{row['State']} runs", f"{int(row['State Runs']):,}")
        c2.metric(f"{row['State']} revenue", _money(row['State Revenue']))
        c3.metric(f"{row['State']} driver pay", _money(row['State Pay']))
        c4.metric(f"{row['State']} unmatched", f"{int(row['Unmatched State Runs']):,}")

def consolidated_page(df, origin):
    st.title('📊 Consolidated Financial Report — All States')
    st.caption('First Paid Fare comes only from First Net Pay. State Revenue and State Driver Pay come only from state reports. MO/Monitor labels are excluded as non-trip records.')
    total = display_total(df, origin)
    if float(pd.to_numeric(df.get('Revenue', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) == 0:
        st.error('No First Net Pay values were detected. Upload the First detailed report in the First reports box.')
        return
    kpi_row(total)
    current = save_financial_snapshot(df, origin)
    before = previous_snapshot(current)
    st.subheader('Financial control summary')
    c1, c2, c3 = st.columns(3)
    c1.metric('Matched trips (First + State)', _int(total.get('matched_runs', 0)))
    c2.metric('Unmatched state trips', _int(total.get('unmatched_state_runs', 0)))
    c3.metric('Amount due from First', _money(total.get('amount_due')))
    st.metric('Below State Revenue (subset of matched)', _int(total.get('below_contract_runs', 0)),
              f"of {int(total.get('claim_matched_runs', 0)):,} matched trips — not additional trips")
    st.subheader('Pricing-policy compliance')
    compliant = max(int(total.get('runs', 0)) - int(total.get('non_compliant', 0)), 0)
    nc = int(total.get('non_compliant', 0))
    rate = compliant / total['runs'] * 100 if total.get('runs') else 0
    loss_rate = nc / total['runs'] * 100 if total.get('runs') else 0
    a, b, c, d = st.columns(4)
    a.metric('Compliant trips', f'{compliant:,}', f'{rate:.1f}% of trips')
    b.metric('Non-compliant trips', f'{nc:,}', f'{loss_rate:.1f}% of trips')
    c.metric('Loss from non-compliance', _money(total.get('loss')))
    d.metric('Profit margin', _pct(total.get('margin')))
    if nc:
        st.warning(f'{nc:,} trips did not comply with the pricing policy. Estimated loss: {_money(total.get("loss"))}.')
    else:
        st.success('All analyzed trips comply with the available pricing policy.')
    if before:
        st.subheader('Change from previous saved week')
        labels = [('Runs', 'runs'), ('First Paid Fare', 'first_paid_fare'),
                  ('State Revenue', 'state_revenue'), ('Amount Due', 'amount_due'),
                  ('Profit', 'profit'), ('Margin', 'margin'), ('Non-compliant trips', 'non_compliant')]
        cols = st.columns(4)
        for i, (label, key) in enumerate(labels):
            now, old = current.get(key), before.get(key)
            delta = pct_change(now, old)
            cols[i % 4].metric(label, _money(now) if key not in ('runs','non_compliant') else f'{int(now):,}',
                                f'{delta:+.1f}% vs W{before.get("week")} ' if delta is not None else None)
    excluded = int(df.attrs.get('excluded_non_trip_rows', 0))
    if excluded:
        st.info(f'{excluded:,} MO/Monitor record(s) were excluded because they are labels, not trips.')
    # Keep only a downloadable summary; no detail tables are rendered below the dashboard.
    summary = pd.DataFrame([{'Metric': k, 'Value': v} for k, v in {
        'Runs': total['runs'], 'First Paid Fare': total['revenue'],
        'State Revenue': total['state_revenue'], 'State Driver Pay': total['payment'],
        'Amount Due': total['amount_due'], 'Profit': total['profit'], 'Margin %': total['margin'],
        'Compliant Trips': compliant, 'Non-compliant Trips': nc, 'Loss': total['loss']}.items()])
    df_download(summary, 'financial_summary.xlsx', 'dl_summary')


def state_page(df, code, origin):
    name = STATES.get(code, code)
    st.title(f'📍 {name} — Financial Summary')
    d = df[df['State'] == code].copy()
    total = display_block(d, code, origin)
    kpi_row(total, name)
    compliant = max(int(total.get('runs', 0)) - int(total.get('non_compliant', 0)), 0)
    nc = int(total.get('non_compliant', 0))
    rate = compliant / total['runs'] * 100 if total.get('runs') else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Compliant trips', f'{compliant:,}', f'{rate:.1f}%')
    c2.metric('Non-compliant trips', f'{nc:,}', f'{nc / total["runs"] * 100:.1f}%' if total.get('runs') else '0%')
    c3.metric('Loss from non-compliance', _money(total.get('loss')))
    c4.metric('Amount due from First', _money(total.get('amount_due')))
    st.metric('Below State Revenue (subset of matched)', _int(total.get('below_contract_runs', 0)),
              f"of {int(total.get('claim_matched_runs', 0)):,} matched trips — not additional trips")
    if total.get('unmatched_state_runs', 0):
        st.info(f"{total['unmatched_state_runs']:,} state-report trip(s) have no matching First trip and are excluded from the per-trip claim until matched.")
    current = save_financial_snapshot(d, {code: origin.get(code)} if code in origin else {})
    before = previous_snapshot(current)
    if before:
        st.subheader('Change from previous saved week')
        for label, key in [('Runs','runs'),('State Revenue','state_revenue'),('Amount Due','amount_due'),('Profit','profit'),('Margin','margin')]:
            now = current.get(key); old = before.get(key); delta = pct_change(now, old)
            st.metric(label, _money(now) if key not in ('runs',) else f'{int(now):,}', f'{delta:+.1f}%' if delta is not None else None)
    st.caption('Only the financial summary is shown. Detailed tables are intentionally hidden.')

# ---------------------------------------------------------------------------
# APP ENTRY
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon='🚐', layout='wide')
st.markdown(CARD_CSS, unsafe_allow_html=True)

st.sidebar.title("Hatem's B.T. Analyzer")
st.sidebar.caption('Beyond Transportation — financial & pricing control')

with st.sidebar:
    first_files = st.file_uploader('First report(s) — Excel / CSV', type=['xlsx', 'xls', 'csv'],
                                   accept_multiple_files=True, key='first_up')
    if first_files:
        try:
            st.session_state['first_df'] = read_first(first_files)
            loaded = st.session_state['first_df']
            st.success(f'Loaded {len(loaded):,} runs.')
            diagnostics = loaded.attrs.get('read_diagnostics', [])
            with st.expander('First report read-check (what the app actually read)', expanded=True):
                if diagnostics:
                    st.dataframe(pd.DataFrame(diagnostics), use_container_width=True, hide_index=True)
                st.write({
                    'First Paid Fare total': _money(float(loaded['Revenue'].sum())) if not loaded.empty else '$0.00',
                    'Net Pay rows used': int((loaded.get('Paid_Fare_Source', pd.Series(dtype=str)) == 'First Alt Net Pay').sum()),
                    'Revenue fallback rows': int((loaded.get('Paid_Fare_Source', pd.Series(dtype=str)) == 'First Alt Revenue').sum()),
                    'Rows with zero paid fare': int((pd.to_numeric(loaded.get('Revenue', pd.Series(dtype=float)), errors='coerce').fillna(0) == 0).sum()),
                })
                if loaded.empty or float(pd.to_numeric(loaded.get('Revenue', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) == 0:
                    st.error('The First report was loaded but no Net Pay/paid-fare values were found. Check the read-check table above; calculations are not reliable until a paid-fare column is detected.')
        except Exception as e:
            st.error(f'Could not read the First report(s): {e}')
    with st.expander('Optional: state reports (origin price)'):
        state_files = st.file_uploader('Weekly state reports', type=['xlsx', 'xls', 'csv'],
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

if df.empty and origin:
    state_only_page(origin)
elif df.empty:
    st.title("Hatem's B.T. Analyzer")
    st.info('Upload either a First detailed report or a state report. Upload both to calculate the financial claim and policy compliance.')
else:
    present = sorted(df['State'].unique(), key=lambda c: (c == 'Unassigned', STATES.get(c, c)))
    labels = ['📊 Consolidated Report'] + [
        ('⚠ Unassigned' if c == 'Unassigned' else STATES.get(c, c)) for c in present]
    choice = st.sidebar.radio('States', labels, key='nav')
    if choice == '📊 Consolidated Report':
        consolidated_page(df, origin)
    else:
        idx = labels.index(choice) - 1
        code = present[idx]
        if code == 'Unassigned':
            st.title('⚠ Unassigned runs')
            st.caption('These runs come from drivers not in the built-in state list. Add them '
                       'to a state report once and they will be recognised automatically.')
            u = df[df['State'] == 'Unassigned']
            st.metric('Runs', f'{len(u):,}')
            st.info('Detailed rows are hidden. These runs are excluded from the state-level financial claim until assigned to a state.')
        else:
            state_page(df, code, origin)
