import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE (FINAL VERSION 19.0 - FINAL N.CA FIX)
# ==============================================================================
st.set_page_config(page_title="Hatem's B.T. Analyzer", layout="wide")

@st.cache_data
def get_pricing_policies():
    policies_data = [
        # Oregon
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 35},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 40},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 37, 'Per_Mile_Rate': 1.75},

        # South California
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 15, 'Policy_Pay': 43},

        # =========================
        # Wheelchair (Reference only - logic handled in code)
        # =========================
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75},
        {'State': 'CA', 'Vehicle_Type': 'Wheelchair', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75},

        # North California (Standard)
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38, 'Per_Mile_Rate': 1.25},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38, 'Per_Mile_Rate': 1.25},

        # Alaska
        {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35},

        # Canada
        {'State': 'CAN', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'CAN', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35},

        # Nebraska
        {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 30},

        # Illinois
        {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75},

        # New Mexico
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 12, 'Policy_Pay': 39.50},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 12.01, 'Max_Miles': 20, 'Policy_Pay': 45},
    ]
    return pd.DataFrame(policies_data).fillna(0)

def get_policy_driver_pay(row, df_policies):
    state = str(row.get('State', 'N.CA')).strip().upper()
    driver_name = str(row.get('Driver_Name', '')).strip()
    
    miles = 0
    if 'Distance_Miles' in row: miles = float(row['Distance_Miles'])
    elif 'Miles' in row: miles = float(row['Miles'])
    elif 'Distance' in row: miles = float(row['Distance'])

    # ==========================================
    # 🚨 ABSOLUTE PRIORITY: Wheelchair FLAT RATE
    # ==========================================
    if state in ['N.CA', 'CA']:
        driver_name_clean = driver_name.lower().strip()

        wheelchair_drivers = [
            "mohamed omar ali",
            "mohammed abdelgadir albashir"
        ]

        if any(name in driver_name_clean for name in wheelchair_drivers):
            return 75.0  # ثابت لكل رحلة (مش بالميل)

    # ==========================================
    # N.CA STANDARD LOGIC
    # ==========================================
    if state in ['N.CA', 'CA']:
        if miles <= 6:
            return 38.0
        elif 6 < miles <= 14:
            return 42.0
        else:
            return 38.0 + ((miles - 14) * 1.25)

    # ==========================================
    # GENERAL STATES
    # ==========================================
    state_policies = df_policies[df_policies['State'] == state]
    if state_policies.empty:
        return 0

    if 'Vehicle_Type' in row and pd.notna(row['Vehicle_Type']):
        vehicle_rules = state_policies[state_policies['Vehicle_Type'] == row['Vehicle_Type']]
        rules = vehicle_rules[(miles >= vehicle_rules['Min_Miles']) & (miles <= vehicle_rules['Max_Miles'])]
        if not rules.empty:
            rule = rules.iloc[0]
            if rule.get('Per_Mile_Rate', 0) > 0:
                extra = max(0, miles - rule['Min_Miles'])
                return rule['Policy_Pay'] + (extra * rule['Per_Mile_Rate'])
            return rule['Policy_Pay']

    any_rules = state_policies[state_policies['Vehicle_Type'] == 'ANY']
    rules = any_rules[(miles >= any_rules['Min_Miles']) & (miles <= any_rules['Max_Miles'])]

    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra = max(0, miles - rule['Min_Miles'])
            return rule['Policy_Pay'] + (extra * rule['Per_Mile_Rate'])
        return rule['Policy_Pay']

    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    df.columns = df.columns.str.strip()
    
    mapping = {
        'Trip_Date': ['Trip_Date', 'Date', 'Trip Date'],
        'State': ['State', 'State '],
        'Driver_Name': ['Driver_Name', 'Driver', 'Driver Name'],
        'Distance_Miles': ['Distance_Miles', 'Miles', 'Distance'],
        'Gross_Pay': ['Gross_Pay', 'Gross'],
        'Net_Pay': ['Net_Pay', 'Net']
    }

    for target, options in mapping.items():
        for opt in options:
            if opt in df.columns:
                df[target] = df[opt]
                break

    for col in ['Distance_Miles', 'Gross_Pay', 'Net_Pay']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    if 'Trip_Date' in df.columns:
        df['Trip_Date'] = pd.to_datetime(df['Trip_Date'], errors='coerce')

    if 'Vehicle_Type' not in df.columns:
        df['Vehicle_Type'] = 'ANY'

    df['Policy_Driver_Pay'] = df.apply(get_policy_driver_pay, axis=1, df_policies=df_policies)
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Loss_Amount'] = df.apply(lambda r: r['Net_Pay'] - r['Policy_Driver_Pay'] if r['Net_Pay'] > r['Policy_Driver_Pay'] else 0, axis=1)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0.01

    return df

# ==============================================================================
#  UI (UNCHANGED)
# ==============================================================================
st.sidebar.title("Navigation")
st.sidebar.markdown("Select a state to begin analysis.")
STATES = {"OR": "Oregon", "S.CA": "South California", "N.CA": "North California", "AK": "Alaska", "IL": "Illinois", "NM": "New Mexico", "NE": "Nebraska", "CAN": "Canada"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])

def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    
    st.subheader("Official Pricing Policy")
    all_policies = get_pricing_policies()
    st.table(all_policies[all_policies['State'] == state_code].drop(columns=['State']))

    uploaded_file = st.file_uploader(f"Upload {state_code} file", type="xlsx")

    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        analyzed = analyze_data(df, all_policies)

        st.success("Processed successfully")
        st.dataframe(analyzed)

create_state_page(selection, STATES[selection])
