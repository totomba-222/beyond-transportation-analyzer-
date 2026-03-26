import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE (FINAL AUDITED VERSION 20.0)
# ==============================================================================
st.set_page_config(page_title="Hatem's B.T. Analyzer", layout="wide")

@st.cache_data
def get_pricing_policies():
    policies_data = [
        # --- OREGON (OR) ---
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 35.0, 'Note': 'Flat Rate'},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'OR', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 37.0, 'Per_Mile_Rate': 1.75, 'Note': 'Base 37 + (Miles - 16.01) * 1.75'},
        
        # --- SOUTH CALIFORNIA (S.CA) ---
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 43.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 43.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 43 + (Miles - 16) * 1.25'},
        
        # --- NORTH CALIFORNIA (N.CA / CA) ---
        # Wheelchair Policy for Specific Drivers (English Names)
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (Mohamed Omar Ali)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Gross Pay = 100'},
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (Mohamed Elbashir)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Gross Pay = 100'},
        {'State': 'CA', 'Vehicle_Type': 'Wheelchair (Mohamed Omar Ali)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Gross Pay = 100'},
        {'State': 'CA', 'Vehicle_Type': 'Wheelchair (Mohamed Elbashir)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Gross Pay = 100'},
        
        # Standard N.CA Policies
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42.0, 'Note': 'Flat Rate'},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 38 + (Miles - 14) * 1.25'},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 38 + (Miles - 14) * 1.25'},
        
        # --- ALASKA (AK) ---
        {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35.0, 'Note': 'Flat Rate'},
        
        # --- CANADA (CAN) ---
        {'State': 'CAN', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'CAN', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35.0, 'Note': 'Flat Rate'},
        
        # --- NEBRASKA (NE) ---
        {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 30.0, 'Note': 'Flat Rate'},
        
        # --- ILLINOIS (IL) ---
        {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75.0, 'Note': 'Flat Rate'},
        
        # --- NEW MEXICO (NM) ---
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33.0, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 12, 'Policy_Pay': 39.50, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 12.01, 'Max_Miles': 20, 'Policy_Pay': 45.0, 'Note': 'Flat Rate'},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 20.01, 'Max_Miles': 999, 'Policy_Pay': 45.0, 'Note': 'Flat Rate (TBD)'},
    ]
    return pd.DataFrame(policies_data).fillna(0)

def get_policy_driver_pay(row, df_policies):
    # 1. EXTRACT DATA
    state = str(row.get('State', 'N.CA')).strip().upper()
    driver_name = str(row.get('Driver_Name', '')).strip()
    gross_pay = float(row.get('Gross_Pay', 0))
    
    miles = 0
    if 'Distance_Miles' in row: miles = float(row['Distance_Miles'])
    elif 'Miles' in row: miles = float(row['Miles'])
    elif 'Distance' in row: miles = float(row['Distance'])
    
    # 2. WHEELCHAIR POLICY (N.CA / CA ONLY) - ABSOLUTE PRIORITY
    if state in ['N.CA', 'CA']:
        target_drivers = ["Mohamed Omar Ali", "Mohamed Elbashir"]
        if any(target.lower() in driver_name.lower() for target in target_drivers) and gross_pay == 100.0:
            return 75.0
            
    # 3. OREGON (OR) LOGIC
    if state == 'OR':
        if miles <= 8:
            return 35.0
        elif 8 < miles <= 16:
            return 40.0
        else:
            # Over 16 miles: 37 + (Miles - 16.01) * 1.75
            excess_miles = max(0, miles - 16.01)
            return 37.0 + (excess_miles * 1.75)

    # 4. SOUTH CALIFORNIA (S.CA) LOGIC
    if state == 'S.CA':
        if miles <= 4:
            return 38.0
        elif 4 < miles <= 8:
            return 40.0
        elif 8 < miles <= 16:
            return 43.0
        else:
            # Over 16 miles: 43 + (Miles - 16) * 1.25
            excess_miles = max(0, miles - 16)
            return 43.0 + (excess_miles * 1.25)

    # 5. NORTH CALIFORNIA (N.CA / CA) LOGIC
    if state in ['N.CA', 'CA']:
        if miles <= 6:
            return 38.0
        elif 6 < miles <= 14:
            return 42.0
        else:
            # Over 14 miles: 38 + (Miles - 14) * 1.25
            excess_miles = max(0, miles - 14)
            return 38.0 + (excess_miles * 1.25)

    # 6. GENERAL LOGIC FOR OTHER STATES (NM, AK, CAN, NE, IL)
    state_policies = df_policies[df_policies['State'] == state]
    if state_policies.empty: return 0

    # Try vehicle specific first
    if 'Vehicle_Type' in row and pd.notna(row['Vehicle_Type']):
        v_rules = state_policies[state_policies['Vehicle_Type'] == row['Vehicle_Type']]
        rules = v_rules[(miles >= v_rules['Min_Miles']) & (miles <= v_rules['Max_Miles'])]
        if not rules.empty:
            rule = rules.iloc[0]
            if rule.get('Per_Mile_Rate', 0) > 0:
                extra = max(0, miles - rule['Min_Miles'])
                return rule['Policy_Pay'] + (extra * rule['Per_Mile_Rate'])
            return rule['Policy_Pay']

    # Fallback to ANY vehicle
    any_rules = state_policies[state_policies['Vehicle_Type'] == 'ANY']
    rules = any_rules[(miles >= any_rules['Min_Miles']) & (miles <= any_rules['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra = max(0, miles - (rule['Min_Miles'] or 0))
            return rule['Policy_Pay'] + (extra * rule['Per_Mile_Rate'])
        return rule['Policy_Pay']
        
    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    df.columns = df.columns.str.strip()
    
    # FLEXIBLE COLUMN MAPPING
    mapping = {
        'Trip_Date': ['Trip_Date', 'Date', 'Trip Date'],
        'State': ['State', 'State '],
        'Driver_Name': ['Driver_Name', 'Driver', 'Driver Name'],
        'Distance_Miles': ['Distance_Miles', 'Miles', 'Distance', 'Trip Miles', 'Trip_Miles'],
        'Gross_Pay': ['Gross_Pay', 'Gross Pay', 'Gross'],
        'Net_Pay': ['Net_Pay', 'Net Pay', 'Net', 'Paid to Driver']
    }
    
    # Find and map columns
    found_cols = []
    for target, options in mapping.items():
        for opt in options:
            if opt in df.columns:
                df[target] = df[opt]
                found_cols.append(f"{target} -> {opt}")
                break
    
    # Display found columns for debugging
    st.info(f"Detected Columns: {', '.join(found_cols)}")
    
    # Ensure numeric conversion
    for col in ['Distance_Miles', 'Gross_Pay', 'Net_Pay']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0

    if 'Trip_Date' in df.columns:
        df['Trip_Date'] = pd.to_datetime(df['Trip_Date'], errors='coerce')
    
    if 'Vehicle_Type' not in df.columns:
        df['Vehicle_Type'] = 'ANY'
    else:
        df['Vehicle_Type'] = df['Vehicle_Type'].astype(str).fillna('Unknown')

    # APPLY CALCULATION
    df['Policy_Driver_Pay'] = df.apply(get_policy_driver_pay, axis=1, df_policies=df_policies)
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Loss_Amount'] = df.apply(lambda row: row['Net_Pay'] - row['Policy_Driver_Pay'] if row['Net_Pay'] > row['Policy_Driver_Pay'] else 0, axis=1)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0.01
    return df

# ==============================================================================
#  2. UI PAGE GENERATOR
# ==============================================================================
def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    
    st.subheader("Official Pricing Policy")
    all_policies = get_pricing_policies()
    state_policy_df = all_policies[all_policies['State'] == state_code]
    
    # Clean display for the table
    display_df = state_policy_df.drop(columns=['State']).copy()
    display_df = display_df[['Vehicle_Type', 'Min_Miles', 'Max_Miles', 'Policy_Pay', 'Note']]
    st.table(display_df)

    st.subheader("Upload Trip Data for this State")
    uploaded_file = st.file_uploader(f"Upload {state_code} .xlsx file", type="xlsx", key=f"uploader_{state_code}")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            st.session_state[f'analyzed_df_{state_code}'] = analyze_data(df, all_policies)
            st.success("File processed successfully!")
        except Exception as e:
            st.error(f"Error: {e}")
            return

    if f'analyzed_df_{state_code}' in st.session_state:
        analyzed_df = st.session_state[f'analyzed_df_{state_code}']
        st.markdown("---")
        
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

        st.header("Pricing Policy Compliance Analysis")
        
        # SHOW ALL TRIPS TO COMPARE POLICY PAY
        st.subheader("All Trips with Policy Comparison")
        display_cols = {
            'Trip_Date': 'Date', 'Driver_Name': 'Driver',
            'Distance_Miles': 'Miles', 'Net_Pay': 'Current Driver Pay',
            'Policy_Driver_Pay': 'Policy Driver Pay', 'Loss_Amount': 'Loss'
        }
        st.dataframe(analyzed_df[list(display_cols.keys())].rename(columns=display_cols))

        non_compliant_trips = analyzed_df[analyzed_df['Is_Non_Compliant']]
        if not non_compliant_trips.empty:
            st.subheader("Compliance Impact Summary")
            total_loss = non_compliant_trips['Loss_Amount'].sum()
            non_compliant_ratio = len(non_compliant_trips) / len(analyzed_df)
            loss_to_revenue_ratio = total_loss / total_revenue if total_revenue > 0 else 0
            potential_profit = total_margin + total_loss
            potential_margin_percent = potential_profit / total_revenue if total_revenue > 0 else 0

            kpi_col1, kpi_col2 = st.columns(2)
            kpi_col1.metric(label="Total Loss from Non-Compliance", value=f"${total_loss:,.2f}")
            kpi_col2.metric(label="Non-Compliant Trips %", value=f"{non_compliant_ratio:.2%}")
            kpi_col1.metric(label="Loss as % of Revenue", value=f"{loss_to_revenue_ratio:.2%}")
            kpi_col2.metric(label="Potential Margin % (if compliant)", value=f"{(potential_margin_percent):.2%}", delta=f"{(potential_margin_percent - current_margin_percent):.2%}")
        else:
            st.success("✅ Full Compliance! No trips found with driver pay higher than the policy.")

# ==============================================================================
#  3. MAIN APP ROUTER
# ==============================================================================
st.sidebar.title("Navigation")
st.sidebar.markdown("Select a state to begin analysis.")
STATES = {"OR": "Oregon", "S.CA": "South California", "N.CA": "North California", "AK": "Alaska", "IL": "Illinois", "NM": "New Mexico", "NE": "Nebraska", "CAN": "Canada"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])

create_state_page(selection, STATES[selection])
