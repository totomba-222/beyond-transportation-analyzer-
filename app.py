import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE (REBUILT LOGIC)
# ==============================================================================
@st.cache_data
def get_pricing_policies():
    # This is the policy for what the DRIVER should be paid (Net_Pay)
    policies_data = [
        {'State': 'OR', 'Min_Miles': 0, 'Max_Miles': 8, 'Policy_Pay': 35},
        {'State': 'OR', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 40},
        {'State': 'OR', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 37, 'Per_Mile_Rate': 1.75},
        {'State': 'S.CA', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38},
        {'State': 'S.CA', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40},
        {'State': 'S.CA', 'Min_Miles': 8.01, 'Max_Miles': 15, 'Policy_Pay': 43},
        {'State': 'N.CA', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38},
        {'State': 'N.CA', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42},
        {'State': 'AK', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 40},
        {'State': 'IL', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 0},
        {'State': 'NM', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 0},
        {'State': 'NE', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 0},
        {'State': 'CAN', 'Min_Miles': 0, 'Max_Miles': 999, 'Policy_Pay': 0},
    ]
    df = pd.DataFrame(policies_data).fillna(0)
    return df

def get_policy_driver_pay(row, df_policies):
    state_policies = df_policies[df_policies['State'] == row['State']]
    if state_policies.empty: return 0
    rules = state_policies[(row['Distance_Miles'] >= state_policies['Min_Miles']) & (row['Distance_Miles'] <= state_policies['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra_miles = row['Distance_Miles'] - rule['Min_Miles']
            return rule['Policy_Pay'] + (extra_miles * rule['Per_Mile_Rate'])
        else: return rule['Policy_Pay']
    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    # Clean column names
    df.columns = df.columns.str.strip()
    
    # Convert types
    df['Trip_Date'] = pd.to_datetime(df['Trip_Date'], errors='coerce')
    numeric_cols = ['Distance_Miles', 'Gross_Pay', 'Net_Pay']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Core Analysis based on CORRECTED logic
    df['Policy_Driver_Pay'] = df.apply(get_policy_driver_pay, axis=1, df_policies=df_policies)
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Loss_Amount'] = df.apply(lambda row: row['Net_Pay'] - row['Policy_Driver_Pay'] if row['Net_Pay'] > row['Policy_Driver_Pay'] else 0, axis=1)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0
    return df

# ==============================================================================
#  2. UI PAGE GENERATOR
# ==============================================================================
def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    
    # --- Upload Data ---
    st.subheader("Upload Trip Data for this State")
    uploaded_file = st.file_uploader(f"Upload {state_code} .xlsx file", type="xlsx", key=f"uploader_{state_code}")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            all_policies = get_pricing_policies()
            st.session_state[f'analyzed_df_{state_code}'] = analyze_data(df, all_policies)
            st.success("File processed. Select an analysis to run below.")
        except Exception as e:
            st.error(f"Error processing file: {e}")
            return

    if f'analyzed_df_{state_code}' in st.session_state:
        analyzed_df = st.session_state[f'analyzed_df_{state_code}']
        st.markdown("---")
        
        # --- Financial Analysis ---
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

        # --- Compliance Analysis (THE NEW SECTION) ---
        st.header("Pricing Policy Compliance Analysis")
        non_compliant_trips = analyzed_df[analyzed_df['Is_Non_Compliant']]
        
        if non_compliant_trips.empty:
            st.success("✅ Full Compliance! No trips found with driver pay higher than the policy.")
        else:
            st.subheader("Non-Compliant Trips (Driver Paid > Policy)")
            display_cols = {
                'Trip_Date': 'Date',
                'Driver_Name': 'Driver',
                'Distance_Miles': 'Miles',
                'Net_Pay': 'Current Driver Pay',
                'Policy_Driver_Pay': 'Policy Driver Pay',
                'Loss_Amount': 'Loss'
            }
            st.dataframe(non_compliant_trips[display_cols.keys()].rename(columns=display_cols))

            # --- NEW KPIs ---
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

# ==============================================================================
#  3. MAIN APP ROUTER (No changes needed here)
# ==============================================================================
st.sidebar.title("Navigation")
st.sidebar.markdown("Select a state to begin analysis.")
STATES = {"OR": "Oregon", "S.CA": "South California", "N.CA": "North California", "AK": "Alaska", "IL": "Illinois", "NM": "New Mexico", "NE": "Nebraska", "CAN": "Canada"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])

# This part handles page navigation and remains the same
if 'page' not in st.session_state:
    st.session_state.page = selection

if selection != st.session_state.page:
    st.session_state.page = selection
    st.rerun()

create_state_page(selection, STATES[selection])
