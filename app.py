import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE (FINAL VERSION 15.0 - WHEELCHAIR POLICY)
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
        
        # North California (UPDATED)
        # Wheelchair Policy for Specific Drivers
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (محمد عمر علي)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75, 'Note': 'Gross Pay = 100'},
        {'State': 'N.CA', 'Vehicle_Type': 'Wheelchair (محمد البشير)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75, 'Note': 'Gross Pay = 100'},
        {'State': 'CA', 'Vehicle_Type': 'Wheelchair (محمد عمر علي)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75, 'Note': 'Gross Pay = 100'},
        {'State': 'CA', 'Vehicle_Type': 'Wheelchair (محمد البشير)', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75, 'Note': 'Gross Pay = 100'},
        
        # Standard N.CA Policies
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38, 'Per_Mile_Rate': 1.25},
        {'State': 'CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38, 'Per_Mile_Rate': 1.25},
        
        # Alaska (Vehicle-based logic)
        {'State': 'AK', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'AK', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35},
        # Canada (Example vehicle-based logic)
        {'State': 'CAN', 'Vehicle_Type': 'Minivan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'CAN', 'Vehicle_Type': 'Sedan', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 35},
        # Nebraska (General)
        {'State': 'NE', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 30},
        # Illinois (Inferred from summary data)
        {'State': 'IL', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 75},
        # New Mexico (CORRECTED - Multi-tier policy based on detailed analysis)
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 33},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 12, 'Policy_Pay': 39.50},
        {'State': 'NM', 'Vehicle_Type': 'ANY', 'Min_Miles': 12.01, 'Max_Miles': 20, 'Policy_Pay': 45},
    ]
    return pd.DataFrame(policies_data).fillna(0)

def get_policy_driver_pay(row, df_policies):
    # ROBUST COLUMN DETECTION FOR MILES
    miles = 0
    if 'Distance_Miles' in row: miles = row['Distance_Miles']
    elif 'Miles' in row: miles = row['Miles']
    elif 'Distance' in row: miles = row['Distance']
    
    state = str(row.get('State', 'N.CA')).strip()
    driver_name = str(row.get('Driver_Name', '')).strip()
    gross_pay = row.get('Gross_Pay', 0)
    
    # EXPLICIT LOGIC FOR NORTH CALIFORNIA (N.CA)
    if state == 'N.CA' or state == 'CA':
        # NEW: Wheelchair policy for specific drivers in N.CA/CA
        if (driver_name == "محمد عمر علي" or driver_name == "محمد البشير") and gross_pay == 100:
            return 75.0
        
        # Existing N.CA mileage-based policy
        if miles <= 6:
            return 38.0
        elif 6 < miles <= 14:
            return 42.0
        else:
            # Over 14 miles: (Excess Miles * 1.25) + 38
            excess_miles = max(0, miles - 14)
            return 38.0 + (excess_miles * 1.25)

    # GENERAL LOGIC FOR OTHER STATES
    state_policies = df_policies[df_policies['State'] == state]
    if state_policies.empty: return 0

    if 'Vehicle_Type' in row and pd.notna(row['Vehicle_Type']):
        vehicle_specific_rules = state_policies[state_policies['Vehicle_Type'] == row['Vehicle_Type']]
        rules = vehicle_specific_rules[(miles >= vehicle_specific_rules['Min_Miles']) & (miles <= vehicle_specific_rules['Max_Miles'])]
        if not rules.empty:
            rule = rules.iloc[0]
            if rule.get('Per_Mile_Rate', 0) > 0:
                extra_miles = max(0, miles - rule['Min_Miles'])
                return rule['Policy_Pay'] + (extra_miles * rule['Per_Mile_Rate'])
            else: return rule['Policy_Pay']

    any_vehicle_rules = state_policies[state_policies['Vehicle_Type'] == 'ANY']
    rules = any_vehicle_rules[(miles >= any_vehicle_rules['Min_Miles']) & (miles <= any_vehicle_rules['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra_miles = max(0, miles - (rule['Min_Miles'] or 0))
            return rule['Policy_Pay'] + (extra_miles * rule['Per_Mile_Rate'])
        else: return rule['Policy_Pay']
        
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
    st.table(state_policy_df.drop(columns=['State']))

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
            kpi_col2.metric(label="Potential Margin % (if compliant)", value=f"{potential_margin_percent:.2%}", delta=f"{(potential_margin_percent - current_margin_percent):.2%}")
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
