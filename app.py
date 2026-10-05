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
NO_POLICY = {'NM', 'IL', 'RS&AZ', 'AZ'}


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
    if 'NORTH CA' in s or 'NORTHCAROLINA' in s or re.search(r'(^| )N CA( |$)', s):
        return 'N.CA'
    if 'SOUTH CA' in s or re.search(r'(^| )S CA( |$)', s):
        return 'S.CA'
    if 'OREGON' in s or re.search(r'(^| )OR( |$)', s):
        return 'OR'
    if 'ALASKA' in s or 'ANCHORAGE' in s or re.search(r'(^| )AK( |$)', s):
        return 'AK'
    if 'CROSS BORDER' in s or ('RS' in s and 'AZ' in s):
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
    district_code = _state_code_from_text(district)
    if district_code != 'Unknown':
        return district_code
    known = DRIVER_STATE.get(clean(driver))
    if known:
        return known
    return state_from(trip, company)


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
        d['Driver_Name'] = _pick(x, up, ['DRIVER NAME', 'DRIVER'], 'Unknown')
        d['District'] = _pick(x, up, ['DISTRICT', 'STATE', 'REGION', 'AREA'], '')
        d['Trip_Name'] = _pick(x, up, ['TRIP NAME', 'NAME'], '')
        d['Trip_Date'] = pd.to_datetime(_pick(x, up, ['DATE', 'TRIP DATE'], None), errors='coerce')
        d['Miles'] = _number_series(_pick(x, up, ['TOTAL MILES', 'MILES'], pd.Series(0, index=x.index))).fillna(0.0)
        d['Revenue'] = _number_series(_pick(x, up, ['REVENUE', 'NET PAY', 'NET'], pd.Series(0, index=x.index))).fillna(0.0)
        d['First_Gross'] = _number_series(_pick(x, up, ['GROSS PAY', 'GROSS'], pd.Series(0, index=x.index))).fillna(0.0)
        d['Company'] = _pick(x, up, ['SP COMPANY', 'COMPANY'], '')
        d['Source_File'] = getattr(f, 'name', '')
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    bad = {'', 'nan', 'total', 'totals', 'grand total'}
    keep = d['Driver_Name'].map(lambda v: clean(v) not in bad) & (
        (d['Revenue'] != 0) | (d['Trip_Name'].map(lambda v: clean(v) not in {'', 'nan'})))
    d = d[keep].copy()
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
    d['Price_Difference'] = pd.NA
    d['Price_Source'] = 'Built-in policy'
    return _recalculate(d)


def _recalculate(d):
    """Recalculate driver payment/profit and state-price reconciliation separately."""
    state_price = pd.to_numeric(d['State_Price'], errors='coerce')
    policy_price = pd.to_numeric(d['Policy_Pay'], errors='coerce')
    d['Price_Difference'] = state_price - d['Revenue']
    d['State_Revenue'] = state_price
    # A state report price is company/state reconciliation data only. It must
    # not make a state with no driver policy look compliant or change payment.
    effective = d['State'].map(has_policy) & policy_price.gt(0)
    d['Checked'] = effective
    d['Policy_Pay'] = policy_price.where(effective, other=pd.NA)
    d.loc[effective, 'Price_Source'] = 'Built-in driver-payment policy'
    d['Profit'] = (d['Revenue'] - d['Policy_Pay']).where(effective, other=pd.NA)
    d['Non_Compliant'] = effective & (d['Revenue'] < d['Policy_Pay'] - 0.01)
    d['Loss'] = (d['Policy_Pay'] - d['Revenue']).where(d['Non_Compliant'], other=0.0)
    return d


def read_state_origin(files):
    """Read state reports as trip-level contract prices, not one state total."""
    rows = {}
    for f in files:
        code = state_code_from_name(getattr(f, 'name', ''))
        try:
            x = _read_report_table(f)
            part = _normalise_state_rows(x, code, getattr(f, 'name', ''))
        except Exception:
            continue
        if part.empty:
            continue
        if code == 'Unknown':
            driver_state_normalized = {_normal_key(name): state for name, state in DRIVER_STATE.items()}
            inferred = part['Driver_Key'].map(lambda n: driver_state_normalized.get(n, 'Unknown'))
            known = inferred[inferred != 'Unknown']
            if not known.empty:
                code = known.mode().iloc[0]
                part['State'] = code
        prev = rows.get(code, {'rows': []})
        prev['rows'].append(part)
        rows[code] = prev
    result = {}
    for code, info in rows.items():
        all_rows = pd.concat(info['rows'], ignore_index=True)
        result[code] = {'rows': all_rows, 'origin': float(all_rows['State_Price'].sum()),
                        'runs': int(len(all_rows))}
    return result


def apply_state_prices(d, origin):
    """Match state rows to First rows, preserving duplicate trips by occurrence."""
    if d.empty or not origin:
        return d
    d = d.copy()
    d['_driver_key'] = d['Driver_Name'].map(_normal_key)
    d['_trip_key'] = d['Trip_Name'].map(_normal_key)
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
                    available.at[hit, '_used'] = True
            if first['State_Price'].notna().all():
                break

    for code, info in origin.items():
        if code == 'Unknown' or 'rows' not in info:
            continue
        r = info['rows'].copy()
        mask = d['State'].eq(code)
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
    d = _recalculate(d)
    return d.drop(columns=['_driver_key', '_trip_key', '_date_key', '_miles_key', '_occ'])

# ---------------------------------------------------------------------------
# AGGREGATION & REPORT BUILDERS
# ---------------------------------------------------------------------------
def agg_block(d):
    """Core + compliance figures for a slice of runs (one state, any week set)."""
    runs = int(len(d))
    rev = float(d['Revenue'].sum())
    state_rev = float(pd.to_numeric(d.get('State_Revenue', pd.Series(dtype=float)), errors='coerce').sum())
    price_diff = float(pd.to_numeric(d.get('Price_Difference', pd.Series(dtype=float)), errors='coerce').sum())
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
    return {
        'runs': runs, 'revenue': rev, 'state_revenue': state_rev,
        'price_difference': price_diff, 'payment': pay, 'profit': profit,
        'margin': (profit / rev * 100) if (policy_state and rev) else float('nan'),
        'total_runs': runs, 'compliant': (runs - nc) if policy_state else runs,
        'non_compliant': nc, 'loss': loss, 'profit_if': profit_if,
        'margin_if': (profit_if / rev * 100) if (policy_state and rev) else float('nan'),
        'policy_state': policy_state,
    }


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
        ('FIRST REVENUE (COMPANY)', 'revenue', _money, True),
        ('STATE REVENUE (CONTRACT)', 'state_revenue', _money, True),
        ('STATE PRICE DIFFERENCE', 'price_difference', _money, True),
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


def kpi_row(total):
    comp_rate = (total['compliant'] / total['total_runs'] * 100) if total['total_runs'] else 0
    a, b, c, d, e = st.columns(5)
    kpi(a, 'Runs', _int(total['runs']))
    kpi(b, 'First Revenue (company)', _money(total['revenue']), 'p')
    kpi(c, 'State Revenue (contract)', _money(total['state_revenue']), 'o')
    kpi(d, 'Profit', _money(total['profit']), 'g')
    kpi(e, 'Driver Payment', _money(total['payment']), 'o')
    f, g, h, i, j = st.columns(5)
    kpi(f, 'State − First difference', _money(total['price_difference']), 'r')
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
def consolidated_page(df, origin):
    st.title('📊 Consolidated Financial Report — All States')
    st.caption('Built automatically from the First report. Each run is assigned to its '
               'state from the driver, then priced against your built-in policy.')
    total = agg_block(df)
    kpi_row(total)

    st.subheader('Performance by state')
    rows = []
    for code in sorted(df['State'].unique(), key=lambda c: STATES.get(c, c)):
        b = agg_block(df[df['State'] == code])
        rows.append({
            'State': STATES.get(code, code), 'Runs': b['runs'],
            'First Revenue': b['revenue'], 'State Revenue': b['state_revenue'],
            'Price Difference': b['price_difference'], 'Driver Payment': b['payment'],
            'Profit': b['profit'], 'Margin %': b['margin'],
            'Non-compliant': b['non_compliant'], 'Loss': b['loss'],
            'Profit if compliant': b['profit_if'], 'Margin if compliant %': b['margin_if'],
        })
    perf = pd.DataFrame(rows)
    st.dataframe(perf.style.format({
        'First Revenue': '${:,.2f}', 'State Revenue': '${:,.2f}',
        'Price Difference': '${:,.2f}', 'Driver Payment': '${:,.2f}', 'Profit': '${:,.2f}',
        'Margin %': '{:,.1f}%', 'Loss': '${:,.2f}', 'Profit if compliant': '${:,.2f}',
        'Margin if compliant %': '{:,.1f}%'}, na_rep='—'),
        use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.caption('First Revenue vs State Contract Revenue')
    c1.bar_chart(perf.set_index('State')[['First Revenue', 'State Revenue']])
    mperf = perf.dropna(subset=['Margin %'])
    if not mperf.empty:
        c2.caption('Margin % by state')
        c2.bar_chart(mperf.set_index('State')[['Margin %']])

    if origin:
        st.subheader('Price matching by state and difference per run')
        diff_report = price_difference_report(df)
        if not diff_report.empty:
            st.dataframe(diff_report.style.format({
                'Difference_Per_Run': '${:,.2f}', 'First_Revenue': '${:,.2f}',
                'State_Revenue': '${:,.2f}', 'Total_Difference': '${:,.2f}'}),
                use_container_width=True, hide_index=True)
        else:
            st.warning('No state-report rows were matched to First Alt yet.')

    if 'Unassigned' in df['State'].values:
        n = int((df['State'] == 'Unassigned').sum())
        st.warning(f'{n} run(s) could not be matched to a state (new drivers not in the '
                   'built-in list). Open the "Unassigned" section to review them.')
    df_download(perf.set_index('State'), 'consolidated_report.xlsx', 'dl_cons',
                sheets={'State Summary': perf.set_index('State'),
                        'Price Differences': price_difference_report(df)})


def state_page(df, code, origin):
    name = STATES.get(code, code)
    st.title(f'📍 {name} — Weekly Financial Report')
    d = df[df['State'] == code].copy()
    if not has_policy(code):
        st.info('No pricing policy is supplied for this state yet, so runs are not checked '
                'for compliance. Revenue and runs are still reported. Provide the rates to '
                'enable profit and compliance.')
    rep, total, weeks = weekly_report(d)
    kpi_row(total)

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

    price_cols = ['Trip_Date', 'Driver_Name', 'District', 'Trip_Name', 'Miles', 'Revenue',
                  'State_Price', 'Price_Difference', 'Price_Source']
    with st.expander('Matched contract prices from state report'):
        st.dataframe(d[[c for c in price_cols if c in d.columns]], use_container_width=True, hide_index=True)
        st.caption('First Revenue is the company revenue from First Alt. State Revenue is the agreed trip price from the state report. Driver Payment comes only from the pricing policy. Price Difference = State Revenue − First Revenue.')
        state_diff = price_difference_report(d)
        if not state_diff.empty:
            st.dataframe(state_diff.style.format({
                'Difference_Per_Run': '${:,.2f}', 'First_Revenue': '${:,.2f}',
                'State_Revenue': '${:,.2f}', 'Total_Difference': '${:,.2f}'}),
                use_container_width=True, hide_index=True)

    if has_policy(code) and total['non_compliant']:
        st.warning(f"{total['non_compliant']} loss-making run(s): First paid less than the "
                   f"policy driver pay. Total loss ${total['loss']:,.2f}. If every run were "
                   f"priced per policy, profit would be ${total['profit_if']:,.2f} "
                   f"({_pct(total['margin_if'])}) instead of ${total['profit']:,.2f} "
                   f"({_pct(total['margin'])}).")
        bad = d[d['Non_Compliant']][['Trip_Date', 'Driver_Name', 'Trip_Name', 'Miles',
                                     'Revenue', 'Policy_Pay', 'State_Price', 'Price_Difference', 'Price_Source', 'Loss']].sort_values('Loss', ascending=False)
        with st.expander(f'Show {len(bad)} loss-making runs'):
            st.dataframe(bad.style.format({'Revenue': '${:,.2f}', 'Policy_Pay': '${:,.2f}', 'State_Price': '${:,.2f}',
                                           'Price_Difference': '${:,.2f}', 'Loss': '${:,.2f}'}),
                         use_container_width=True, hide_index=True)

    ov = origin_vs_first(d, code, origin)
    if ov and ov['Matched_Runs']:
        st.subheader('State Revenue vs First Revenue reconciliation')
        st.dataframe(pd.DataFrame([{
            'State': name, 'Matched Runs': ov['Matched_Runs'],
            'First Revenue': ov['First_Paid'], 'State Revenue': ov['Origin_Price'],
            'Total Price Difference': ov['Difference'],
            'Unmatched First Runs': ov['Unmatched_First_Runs']
        }]).style.format({
            'First Revenue': '${:,.2f}', 'State Revenue': '${:,.2f}',
            'Total Price Difference': '${:,.2f}'}), use_container_width=True, hide_index=True)
        if abs(ov['Difference']) > 0.05:
            direction = 'higher than' if ov['Difference'] > 0 else 'lower than'
            st.warning(f"The state contract revenue is ${abs(ov['Difference']):,.2f} total {direction} First Revenue for {name}. This does not change Driver Payment or Profit.")
    df_download(rep, f'{code}_weekly_report.xlsx', f'dl_{code}')

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
            st.success(f'Loaded {len(st.session_state["first_df"]):,} runs.')
        except Exception as e:
            st.error(f'Could not read the First report(s): {e}')
    with st.expander('Optional: state reports (origin price)'):
        state_files = st.file_uploader('Weekly state reports', type=['xlsx', 'xls', 'csv'],
                                       accept_multiple_files=True, key='state_up')
        if state_files:
            st.session_state['origin'] = read_state_origin(state_files)
            st.success('State contract prices loaded for: ' +
                       ', '.join(STATES.get(k, k) for k in st.session_state['origin']))

df = st.session_state.get('first_df', pd.DataFrame())
origin = st.session_state.get('origin', {})
if not df.empty and origin:
    df = apply_state_prices(df, origin)

if df.empty:
    st.title("Hatem's B.T. Analyzer")
    st.info('Upload a First report in the left sidebar to begin. The app assigns every run '
            'to its state automatically and builds a financial report for each state plus a '
            'consolidated view — no need to upload the state reports.')
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
            st.dataframe(u[['Trip_Date', 'Driver_Name', 'Trip_Name', 'Miles', 'Revenue',
                            'Source_File']], use_container_width=True, hide_index=True)
        else:
            state_page(df, code, origin)
