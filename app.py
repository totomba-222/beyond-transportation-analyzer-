import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE (VERSION 7.0 - FINAL FIX)
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
        # North California (UPDATED POLICY)
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38, 'Per_Mile_Rate': 1.25},
        # Alaska
        {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35},
        # New Mexico
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 12, 'Policy_Pay': 39.50},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 12.01, 'Max_Miles': 20, 'Policy_Pay': 45},
    ]
    return pd.DataFrame(policies_data).fillna(0)

def get_policy_driver_pay(row, df_policies):
    # Flexible column mapping for Distance/Miles
    miles = 0
    if 'Distance_Miles' in row: miles = row['Distance_Miles']
    elif 'Miles' in row: miles = row['Miles']
    elif 'Distance' in row: miles = row['Distance']
    
    state = row.get('State', 'N.CA') # Default to N.CA if missing
    
    # EXPLICIT LOGIC FOR NORTH CALIFORNIA (N.CA)
    if state == 'N.CA':
        if miles <= 6:
            return 38.0
        elif 6 < miles <= 14:
            return 42.0
        else:
            # Over 14 miles: (Excess Miles * 1.25) + 38
            excess_miles = miles - 14
            return 38.0 + (excess_miles * 1.25)

    # GENERAL LOGIC FOR OTHER STATES
    state_policies = df_policies[df_policies['State'] == state]
    if state_policies.empty: return 0

    any_rules = state_policies[state_policies['Vehicle_Type'] == 'ANY']
    rules = any_rules[(miles >= any_rules['Min_Miles']) & (miles <= any_rules['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra_miles = miles - rule['Min_Miles']
            return rule['Policy_Pay'] + (extra_miles * rule['Per_Mile_Rate'])
        return rule['Policy_Pay']
        
    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    df.columns = df.columns.str.strip()
    
    # Flexible Column Mapping
    mapping = {
        'Trip_Date': ['Trip_Date', 'Date', 'Trip Date'],
        'State': ['State'],
        'Driver_Name': ['Driver_Name', 'Driver', 'Driver Name'],
        'Distance_Miles': ['Distance_Miles', 'Miles', 'Distance', 'Trip Miles'],
        'Gross_Pay': ['Gross_Pay', 'Gross Pay', 'Gross'],
        'Net_Pay': ['Net_Pay', 'Net Pay', 'Net', 'Paid to Driver']
    }
    
    for target, options in mapping.items():
        for opt in options:
            if opt in df.columns:
                df[target] = df[opt]
                break
    
    # Ensure numeric conversion
    for col in ['Distance_Miles', 'Gross_Pay', 'Net_Pay']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0

    # Apply the pricing logic
    df['Policy_Driver_Pay'] = df.apply(get_policy_driver_pay, axis=1, df_policies=df_policies)
    
    # Financial Calculations
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Loss_Amount'] = df.apply(lambda row: row['Net_Pay'] - row['Policy_Driver_Pay'] if row['Net_Pay'] > row['Policy_Driver_Pay'] else 0, axis=1)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0.01 # Small epsilon for float comparison
    return df

# ==============================================================================
#  2. UI PAGE GENERATOR
# ==============================================================================
def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    
    st.subheader("Official Pricing Policy")
    if state_code == 'N.CA':
        nca_display = pd.DataFrame([
            {'Range': '0 - 6 Miles', 'Policy Pay': '$38.00'},
            {'Range': '6.01 - 14 Miles', 'Policy Pay': '$42.00'},
            {'Range': 'Over 14 Miles', 'Policy Pay': '$38.00 + ($1.25 per excess mile over 14)'}
        ])
        st.table(nca_display)
    else:
        all_policies = get_pricing_policies()
        state_policy_df = all_policies[all_policies['State'] == state_code]
        st.table(state_policy_df.drop(columns=['State']))

    st.subheader("Upload Trip Data")
    uploaded_file = st.file_uploader(f"Upload {state_code} .xlsx file", type="xlsx", key=f"uploader_{state_code}")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            all_policies = get_pricing_policies()
            analyzed_df = analyze_data(df, all_policies)
            st.session_state[f'analyzed_df_{state_code}'] = analyzed_df
            st.success("File processed successfully!")
        except Exception as e:
            st.error(f"Error processing file: {e}")
            return

    if f'analyzed_df_{state_code}' in st.session_state:
        df = st.session_state[f'analyzed_df_{state_code}']
        
        st.header("Financial Summary")
        total_rev = df['Gross_Pay'].sum()
        total_paid = df['Net_Pay'].sum()
        total_loss = df['Loss_Amount'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Revenue", f"${total_rev:,.2f}")
        c2.metric("Total Paid to Drivers", f"${total_paid:,.2f}")
        c3.metric("Total Loss (Overpaid)", f"${total_loss:,.2f}", delta_color="inverse")

        st.header("Trip Details & Comparison")
        display_df = df[['Trip_Date', 'Driver_Name', 'Distance_Miles', 'Net_Pay', 'Policy_Driver_Pay', 'Loss_Amount']].copy()
        display_df.columns = ['Date', 'Driver', 'Miles', 'Paid to Driver', 'Policy Pay (Correct)', 'Loss']
        
        # Format for display
        st.dataframe(display_df.style.format({
            'Paid to Driver': '${:,.2f}',
            'Policy Pay (Correct)': '${:,.2f}',
            'Loss': '${:,.2f}'
        }))

# ==============================================================================
#  3. MAIN APP ROUTER
# ==============================================================================
st.sidebar.title("Navigation")
STATES = {"OR": "Oregon", "S.CA": "South California", "N.CA": "North California", "AK": "Alaska", "NM": "New Mexico"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])

create_state_page(selection, STATES[selection])
