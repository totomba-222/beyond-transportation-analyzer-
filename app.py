import pandas as pd
import streamlit as st
from datetime import datetime

# ==============================================================================
#  1. PRICING POLICIES ENGINE (Hardcoded as requested)
# ==============================================================================
@st.cache_data
def get_pricing_policies():
    policies_data = [
        {'State': 'OR', 'Min_Miles': 0, 'Max_Miles': 8, 'Base_Price': 35, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'OR', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Base_Price': 40, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'OR', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Base_Price': 0, 'Per_Mile_Rate': 1.75, 'Extra_Mile_Base': 37},
        {'State': 'S.CA', 'Min_Miles': 0, 'Max_Miles': 4, 'Base_Price': 38, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'S.CA', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Base_Price': 40, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'S.CA', 'Min_Miles': 8.01, 'Max_Miles': 15, 'Base_Price': 43, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'N.CA', 'Min_Miles': 0, 'Max_Miles': 6, 'Base_Price': 38, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'N.CA', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Base_Price': 42, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'AK', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 40, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'IL', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'NM', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'NE', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
        {'State': 'CAN', 'Min_Miles': 0, 'Max_Miles': 999, 'Base_Price': 0, 'Per_Mile_Rate': 0, 'Extra_Mile_Base': 0},
    ]
    return pd.DataFrame(policies_data)

# ==============================================================================
#  2. THE ANALYSIS ENGINE (Now more powerful)
# ==============================================================================
def get_policy_price(row, df_policies):
    state_policies = df_policies[df_policies['State'] == row['State']]
    if state_policies.empty: return 0
    rules = state_policies[(row['Distance_Miles'] >= state_policies['Min_Miles']) & (row['Distance_Miles'] <= state_policies['Max_Miles'])]
    if not rules.empty:
        rule = rules.iloc[0]
        if rule['Per_Mile_Rate'] > 0:
            if rule['Extra_Mile_Base'] > 0:
                extra_miles = row['Distance_Miles'] - rule['Min_Miles']
                return rule['Extra_Mile_Base'] + (extra_miles * rule['Per_Mile_Rate'])
            else: return rule['Base_Price'] + (row['Distance_Miles'] * rule['Per_Mile_Rate'])
        else: return rule['Base_Price']
    return 0

def analyze_data(df_data, df_policies):
    df = df_data.copy()
    # Convert date column to datetime objects safely
    df['Trip_Date'] = pd.to_datetime(df['Trip_Date'], errors='coerce')
    df['Policy_Price'] = df.apply(get_policy_price, axis=1, df_policies=df_policies)
    df['Total_Cost'] = df['Driver_Pay'] + df['Vehicle_Cost']
    df['Trip_Profit'] = df['Billed_Amount'] - df['Total_Cost']
    df['Price_Variance'] = df['Billed_Amount'] - df['Policy_Price']
    df['Is_Violation'] = df['Price_Variance'] < 0
    df['Profit_Margin'] = df.apply(lambda row: (row['Trip_Profit'] / row['Billed_Amount']) if row['Billed_Amount'] > 0 else 0, axis=1)
    return df

# ==============================================================================
#  3. THE USER INTERFACE (Completely redesigned based on your requests)
# ==============================================================================
st.set_page_config(page_title="Beyond Transportation Analyzer", layout="wide")
st.title("📊 Beyond Transportation - Performance Analyzer")

policies = get_pricing_policies()

st.header("Step 1: Import Weekly Trips File")
st.markdown("Please upload the Excel file containing the weekly trips. The file must be in **.xlsx** format.")
uploaded_file = st.file_uploader("Choose an .xlsx file", type="xlsx")

if uploaded_file is not None:
    try:
        trips_df = pd.read_excel(uploaded_file, engine='openpyxl')
        trips_df['Trip_Date'] = pd.to_datetime(trips_df['Trip_Date'], errors='coerce')
        numeric_cols = ['Distance_Miles', 'Billed_Amount', 'Driver_Pay', 'Vehicle_Cost']
        for col in numeric_cols:
            trips_df[col] = pd.to_numeric(trips_df[col], errors='coerce').fillna(0)

        st.success("File uploaded and read successfully. Running analysis...")
        analyzed_df = analyze_data(trips_df, policies)

        st.header("Step 2: Select a State to Analyze")
        state_list = ["All States"] + sorted(analyzed_df['State'].unique().tolist())
        selected_state = st.selectbox("Choose a State:", state_list)

        if selected_state == "All States":
            display_df = analyzed_df
        else:
            display_df = analyzed_df[analyzed_df['State'] == selected_state]

        if not display_df.empty:
            st.subheader(f"Financial Performance Analysis: {selected_state}")
            total_trips = len(display_df)
            total_revenue = display_df['Billed_Amount'].sum()
            total_profit = display_df['Trip_Profit'].sum()
            avg_profit_per_trip = display_df['Trip_Profit'].mean()
            total_violations = display_df['Is_Violation'].sum()

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Trips", total_trips)
            col2.metric("Total Revenue", f"${total_revenue:,.2f}")
            col3.metric("Total Profit", f"${total_profit:,.2f}")
            col4.metric("Avg. Profit/Trip", f"${avg_profit_per_trip:,.2f}")
            col5.metric("Pricing Violations", total_violations)

            st.subheader("Pricing Policy Violations (Billed < Policy)")
            violations_df = display_df[display_df['Is_Violation']]
            if violations_df.empty:
                st.info("No pricing violations found for this selection.")
            else:
                st.dataframe(violations_df[['Trip_Date', 'Driver_Name', 'Distance_Miles', 'Billed_Amount', 'Policy_Price', 'Price_Variance']])

            st.header("Step 3: Analyze Driver Performance")
            driver_list = sorted(display_df['Driver_Name'].unique().tolist())
            if driver_list:
                selected_driver = st.selectbox("Select a Driver:", driver_list)
                start_date = st.date_input("Start Date", value=display_df['Trip_Date'].min().date())
                end_date = st.date_input("End Date", value=display_df['Trip_Date'].max().date())

                if st.button(f"Generate Report for {selected_driver}"):
                    driver_df = display_df[(display_df['Driver_Name'] == selected_driver) & (display_df['Trip_Date'].dt.date >= start_date) & (display_df['Trip_Date'].dt.date <= end_date)]
                    if driver_df.empty:
                        st.warning("No trips found for this driver in the selected date range.")
                    else:
                        st.subheader(f"Report for {selected_driver} ({start_date} to {end_date})")
                        st.metric(f"Total Trips by {selected_driver}", len(driver_df))
                        st.metric(f"Total Pay for {selected_driver}", f"${driver_df['Driver_Pay'].sum():,.2f}")
                        st.dataframe(driver_df[['Trip_Date', 'Distance_Miles', 'Billed_Amount', 'Driver_Pay', 'Trip_Profit']])
    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.warning("Please check if the uploaded Excel file has the correct columns.")
else:
    st.info("Awaiting file upload to begin analysis...")
