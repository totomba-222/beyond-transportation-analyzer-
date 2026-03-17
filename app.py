import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE
# ==============================================================================
@st.cache_data
def get_pricing_policies():
    policies_data = [
        {'State': 'OR', 'Min_Miles': 0, 'Max_Miles': 8, 'Base_Price': 35},
        {'State': 'OR', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Base_Price': 40},
        {'State': 'OR', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Base_Price': 37, 'Per_Mile_Rate': 1.75},
        {'State': 'S.CA', 'Min_Miles': 0, 'Max_Miles': 4, 'Base_Price': 38},
        {'State': 'S.CA', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Base_Price': 40},
        {'State': 'S.CA', 'Min_Miles': 8.01, 'Max_Miles': 15, 'Base_Price': 43},
        {'State': 'N.CA', 'Min_Miles': 0, 'Max_Miles': 6, 'Base_Price': 38},
        {'State': 'N.CA', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Base_Price': 42},
        {'State': 'AK', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 40},
        {'State': 'IL', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0},
        {'State': 'NM', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0},
        {'State': 'NE', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0},
        {'State': 'CAN', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0},
    ]
    df = pd.DataFrame(policies_data).fillna(0)
    return df

def get_policy_price(row, df_policies):
    state_policies = df_policies[df_policies['State'] == row['State']]
    if state_policies.empty: return 0
    rules = state_policies[(row['Distance_Miles'] >= state_policies['Min_Miles']) & (row['Distance_Miles'] <= state_policies['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule.get('Per_Mile_Rate', 0) > 0:
            extra_miles = row['Distance_Miles'] - rule['Min_Miles']
            return rule['Base_Price'] + (extra_miles * rule['Per_Mile_Rate'])
        else: return rule['Base_Price']
    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    df['Policy_Price'] = df.apply(get_policy_price, axis=1, df_policies=df_policies)
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Price_Variance'] = df['Gross_Pay'] - df['Policy_Price']
    df['Is_High_Margin'] = df['Price_Variance'] > 0
    df['Margin_%'] = df.apply(lambda row: (row['Margin'] / row['Gross_Pay']) if row['Gross_Pay'] > 0 else 0, axis=1)
    return df

# ==============================================================================
#  2. UI PAGE GENERATOR
# ==============================================================================
def create_state_page(state_code, state_name):
    st.title(f"📊 {state_name} - Analysis Dashboard")
    st.subheader("Official Pricing Policy")
    all_policies = get_pricing_policies()
    state_policy_df = all_policies[all_policies['State'] == state_code]
    st.table(state_policy_df)

    st.subheader("Upload Trip Data for this State")
    uploaded_file = st.file_uploader(f"Upload {state_code} .xlsx file", type="xlsx", key=f"uploader_{state_code}")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            
            # **THE FIX IS HERE: Clean column names automatically**
            df.columns = df.columns.str.strip()

            # Now, check for required columns after cleaning
            required_cols = ['Trip_Date', 'State', 'Driver_Name', 'Distance_Miles', 'Gross_Pay', 'Net_Pay']
            if not all(col in df.columns for col in required_cols):
                missing_cols = [col for col in required_cols if col not in df.columns]
                st.error(f"File is missing required columns: {', '.join(missing_cols)}")
                return

            st.session_state[f'analyzed_df_{state_code}'] = analyze_data(df, all_policies)
            st.success("File processed. Select an analysis to run below.")
        except Exception as e:
            st.error(f"Error processing file: {e}")
            return

    if f'analyzed_df_{state_code}' in st.session_state:
        analyzed_df = st.session_state[f'analyzed_df_{state_code}']
        st.markdown("---")
        st.subheader("Run Analysis")
        
        if st.button("Run Financial Analysis", key=f"financial_{state_code}"):
            # ... (rest of the code is the same)
            total_gross = analyzed_df['Gross_Pay'].sum()
            total_margin = analyzed_df['Margin'].sum()
            avg_margin_percent = total_margin / total_gross if total_gross > 0 else 0
            summary_data = {'Metric': ['Total Trips', 'Total Gross Pay (Revenue)', 'Total Net Pay (Driver Cost)', 'Total Margin (Profit)', 'Average Margin %'], 'Value': [f"{len(analyzed_df)}", f"${total_gross:,.2f}", f"${analyzed_df['Net_Pay'].sum():,.2f}", f"${total_margin:,.2f}", f"{avg_margin_percent:.2%}"]}
            st.table(pd.DataFrame(summary_data).set_index('Metric'))

        if st.button("Analyze High-Margin Trips", key=f"margin_{state_code}"):
            high_margin_trips = analyzed_df[analyzed_df['Is_High_Margin']]
            if high_margin_trips.empty:
                st.info("No trips found with a billed amount higher than the policy price.")
            else:
                st.dataframe(high_margin_trips[['Trip_Date', 'Driver_Name', 'Distance_Miles', 'Gross_Pay', 'Policy_Price', 'Price_Variance']])

        if st.button("Generate Driver Statement", key=f"driver_{state_code}"):
            st.session_state.page = f'driver_{state_code}'
            st.rerun()

def create_driver_subpage(state_code):
    # ... (rest of the code is the same)
    st.title(f"👤 Driver Statement for {state_code}")
    if f'analyzed_df_{state_code}' not in st.session_state:
        st.warning("No data available. Please upload data on the state page first.")
        if st.button("Go back to State Page"):
            st.session_state.page = state_code
            st.rerun()
        return

    df = st.session_state[f'analyzed_df_{state_code}']
    driver_list = sorted(df['Driver_Name'].unique().tolist())
    selected_driver = st.selectbox("Select a Driver:", driver_list)
    start_date = st.date_input("Start Date", value=df['Trip_Date'].min().date())
    end_date = st.date_input("End Date", value=df['Trip_Date'].max().date())

    if st.button(f"Generate Statement"):
        driver_df = df[(df['Driver_Name'] == selected_driver) & (df['Trip_Date'].dt.date >= start_date) & (df['Trip_Date'].dt.date <= end_date)].copy()
        if not driver_df.empty:
            st.subheader(f"Statement for: {selected_driver}")
            driver_df['DATE'] = driver_df['Trip_Date'].dt.strftime('%m/%d/%Y')
            driver_df['MEMO/DESCRIPTION'] = "Trip Payment - " + driver_df['Distance_Miles'].astype(str) + " miles"
            driver_df['AMOUNT'] = driver_df['Net_Pay']
            st.table(driver_df[['DATE', 'MEMO/DESCRIPTION', 'AMOUNT']].style.format({'AMOUNT': '${:,.2f}'}))
            st.markdown(f"**Total for {selected_driver}: ${driver_df['AMOUNT'].sum():,.2f}**")
        else:
            st.warning("No trips found for this driver in the selected date range.")

    if st.button("Go back to State Page"):
        st.session_state.page = state_code
        st.rerun()

# ==============================================================================
#  3. MAIN APP ROUTER
# ==============================================================================
st.sidebar.title("Navigation")
st.sidebar.markdown("Select a state to begin analysis.")
STATES = {"OR": "Oregon", "S.CA": "South California", "N.CA": "North California", "AK": "Alaska", "IL": "Illinois", "NM": "New Mexico", "NE": "Nebraska", "CAN": "Canada"}
selection = st.sidebar.radio("States", list(STATES.keys()), format_func=lambda x: STATES[x])

if 'page' not in st.session_state:
    st.session_state.page = selection

if selection != st.session_state.page and not st.session_state.page.startswith('driver_'):
    st.session_state.page = selection
    st.rerun()

current_page = st.session_state.page
if current_page.startswith('driver_'):
    state_code = current_page.split('_')[1]
    create_driver_subpage(state_code)
elif current_page in STATES:
    create_state_page(current_page, STATES[current_page])
else:
    create_state_page("OR", "Oregon")
