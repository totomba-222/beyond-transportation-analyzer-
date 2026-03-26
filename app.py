import pandas as pd
import streamlit as st
import re

# ==============================================================================
#  1. CONFIGURATION & POLICIES
# ==============================================================================
st.set_page_config(page_title="Hatem's B.T. Analyzer", layout="wide")

@st.cache_data
def get_pricing_policies():
    policies_data = [
        # --- OREGON (OR) ---
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 35.0, 'Note': 'Flat Rate'},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 37.0, 'Per_Mile_Rate': 1.75, 'Note': 'Base 37 + (Miles - 16.01) * 1.75'},
        
        # --- NORTH CALIFORNIA (N.CA / CA) ---
        # Wheelchair Policy for Specific Drivers (Priority)
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (Mohamed Omar Ali)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'If Gross Pay = 100 (Priority)'},
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (Mohamed Elbashir)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'If Gross Pay = 100 (Priority)'},
        # Standard N.CA Policies
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 38 + (Miles - 14) * 1.25'},
        
        # --- SOUTH CALIFORNIA (S.CA) ---
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 43.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 43.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 43 + (Miles - 16) * 1.25'},
        
        # --- ALASKA (AK) ---
        {'State': 'AK', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35.0, 'Note': 'Default Rate'},
        
        # --- CANADA (CAN) ---
        {'State': 'CAN', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35.0, 'Note': 'Default Rate'},
        
        # --- NEBRASKA (NE) ---
        {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 30.0, 'Note': 'Flat Rate'},
        
        # --- ILLINOIS (IL) ---
        {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Flat Rate'},
        
        # --- NEW MEXICO (NM) ---
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33.0, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 12, 'Policy_Pay': 39.50, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 12.01, 'Max_Miles': 20, 'Policy_Pay': 45.0, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 20.01, 'Max_Miles': 999, 'Policy_Pay': 45.0, 'Note': 'Flat Rate'},
    ]
    return pd.DataFrame(policies_data).fillna(0)

# ==============================================================================
#  2. CORE LOGIC ENGINE
# ==============================================================================

def clean_text(text):
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def is_wheelchair_driver(driver_name):
    cleaned_name = clean_text(driver_name)
    targets = ["mohamed omar ali", "mohamed elbashir", "محمد عمر علي", "محمد البشير", "mohammed omar ali", "mohammed elbashir"]
    for target in targets:
        if target in cleaned_name:
            return True
    return False

def calculate_policy_pay(row, selected_state, df_policies):
    miles = float(row.get('Distance_Miles', 0))
    gross_pay = float(row.get('Gross_Pay', 0))
    driver_name = str(row.get('Driver_Name', ''))

    # 1. WHEELCHAIR SPECIAL CASE (N.CA ONLY) - HIGHEST PRIORITY
    if selected_state == 'N.CA' and is_wheelchair_driver(driver_name) and abs(gross_pay - 100.0) < 0.01:
        return 75.0

    # 2. STATE SPECIFIC LOGIC
    if selected_state == 'OR':
        if miles <= 8: return 35.0
        if miles <= 16: return 40.0
        return 37.0 + (max(0, miles - 16.01) * 1.75)

    if selected_state == 'N.CA':
        if miles <= 6: return 38.0
        if miles <= 14: return 42.0
        return 38.0 + (max(0, miles - 14) * 1.25)

    if selected_state == 'S.CA':
        if miles <= 4: return 38.0
        if miles <= 8: return 40.0
        if miles <= 16: return 43.0
        return 43.0 + (max(0, miles - 16) * 1.25)

    # 3. GENERAL FALLBACK FROM POLICY TABLE
    state_policies = df_policies[df_policies['State'] == selected_state]
    if state_policies.empty: return 0.0
    
    # Filter for ANY vehicle type first
    any_policies = state_policies[state_policies['Vehicle_Type'] == 'ANY']
    if any_policies.empty: any_policies = state_policies # Fallback if no ANY type defined
    
    match = any_policies[(miles >= any_policies['Min_Miles']) & (miles <= any_policies['Max_Miles'])]
    if not match.empty:
        rule = match.iloc[0]
        base = float(rule['Policy_Pay'])
        rate = float(rule.get('Per_Mile_Rate', 0))
        if rate > 0:
            extra = max(0, miles - float(rule['Min_Miles']))
            return base + (extra * rate)
        return base
    return float(state_policies.iloc[0]['Policy_Pay'])

def analyze_data(df_data, selected_state, df_policies):
    df = df_data.copy()
    df.columns = df.columns.str.strip()
    mapping = {
        'Driver_Name': ['Driver_Name', 'Driver', 'Driver Name', 'اسم السائق'],
        'Distance_Miles': ['Distance_Miles', 'Miles', 'Distance', 'Trip Miles', 'Trip_Miles', 'المسافة'],
        'Gross_Pay': ['Gross_Pay', 'Gross Pay', 'Gross', 'إجمالي الدفع'],
        'Net_Pay': ['Net_Pay', 'Net Pay', 'Net', 'Paid to Driver', 'صافي الدفع']
    }
    for target, options in mapping.items():
        for opt in options:
            if opt in df.columns:
                df[target] = df[opt]
                break
    for col in ['Distance_Miles', 'Gross_Pay', 'Net_Pay']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            df[col] = 0.0

    df['Policy_Driver_Pay'] = df.apply(calculate_policy_pay, axis=1, selected_state=selected_state, df_policies=df_policies)
    state_min = df_policies[df_policies['State'] == selected_state]['Policy_Pay'].min() if not df_policies[df_policies['State'] == selected_state].empty else 0
    df.loc[(df['Policy_Driver_Pay'] == 0) & (df['Distance_Miles'] > 0), 'Policy_Driver_Pay'] = state_min

    df['Loss_Amount'] = (df['Net_Pay'] - df['Policy_Driver_Pay']).clip(lower=0)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0.05
    return df

# ==============================================================================
#  3. UI INTERFACE
# ==============================================================================

def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    
    st.subheader("Official Pricing Policy")
    all_policies = get_pricing_policies()
    state_policy_df = all_policies[all_policies['State'] == state_code].drop(columns=['State'])
    st.table(state_policy_df[['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Note']])

    st.subheader("Upload Trip Data")
    uploaded_file = st.file_uploader(f"Upload {state_code} .xlsx file", type="xlsx", key=f"uploader_{state_code}")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            analyzed_df = analyze_data(df, state_code, all_policies)
            st.session_state[f'analyzed_df_{state_code}'] = analyzed_df
            st.success("File processed successfully!")
        except Exception as e:
            st.error(f"Error: {e}")
            return

    if f'analyzed_df_{state_code}' in st.session_state:
        analyzed_df = st.session_state[f'analyzed_df_{state_code}']
        
        st.header("Financial Summary")
        total_revenue = analyzed_df['Gross_Pay'].sum()
        total_driver_cost = analyzed_df['Net_Pay'].sum()
        total_margin = total_revenue - total_driver_cost
        current_margin_percent = total_margin / total_revenue if total_revenue > 0 else 0
        
        summary_data = {
            'Metric': ['Total Trips', 'Total Revenue (Gross Pay)', 'Total Driver Cost (Net Pay)', 'Total Margin (Profit)', 'Current Margin %'],
            'Value': [f"{len(analyzed_df)}", f"${total_revenue:,.2f}", f"${total_driver_cost:,.2f}", f"${total_margin:,.2f}", f"{current_margin_percent:.2%}"]
        }
        st.table(pd.DataFrame(summary_data).set_index('Metric'))

        st.header("Compliance Impact Summary")
        non_compliant_trips = analyzed_df[analyzed_df['Is_Non_Compliant']]
        total_loss = analyzed_df['Loss_Amount'].sum()
        non_compliant_ratio = len(non_compliant_trips) / len(analyzed_df) if len(analyzed_df) > 0 else 0
        
        potential_margin = total_margin + total_loss
        potential_margin_percent = potential_margin / total_revenue if total_revenue > 0 else 0
        
        kpi_col1, kpi_col2 = st.columns(2)
        kpi_col1.metric(label="Total Loss from Non-Compliance", value=f"${total_loss:,.2f}")
        kpi_col2.metric(label="Non-Compliant Trips %", value=f"{non_compliant_ratio:.2%}")
        
        st.subheader("Potential Profit Analysis")
        profit_data = {
            'Scenario': ['Current Margin (Actual)', 'Potential Margin (If Compliant)', 'Profit Increase'],
            'Amount': [f"${total_margin:,.2f}", f"${potential_margin:,.2f}", f"${total_loss:,.2f}"],
            'Margin %': [f"{current_margin_percent:.2%}", f"{potential_margin_percent:.2%}", f"+{(potential_margin_percent - current_margin_percent):.2%}"]
        }
        st.table(pd.DataFrame(profit_data).set_index('Scenario'))

        st.header("Detailed Trip Analysis")
        display_cols = {
            'Driver_Name': 'Driver',
            'Distance_Miles': 'Miles', 
            'Gross_Pay': 'Gross Pay',
            'Net_Pay': 'Current Driver Pay',
            'Policy_Driver_Pay': 'POLICY DRIVER PAY', 
            'Loss_Amount': 'Loss'
        }
        st.dataframe(analyzed_df[list(display_cols.keys())].rename(columns=display_cols))

# ==============================================================================
#  4. MAIN APP ROUTER
# ==============================================================================
st.sidebar.title("Navigation")
STATES = {"OR": "Oregon", "N.CA": "North California", "S.CA": "South California", "AK": "Alaska", "IL": "Illinois", "NM": "New Mexico", "NE": "Nebraska", "CAN": "Canada"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])
create_state_page(selection, STATES[selection])
