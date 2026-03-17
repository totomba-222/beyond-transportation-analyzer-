import pandas as pd
import streamlit as st
from datetime import datetime

# --- Data and Policies ---
def get_pricing_policies():
    policies_data = {
        'State': ['OR', 'OR', 'OR', 'CA', 'CA', 'AK'],
        'Region': ['Any', 'Any', 'Any', 'Any', 'Any', 'Any'],
        'Min_Miles': [0, 8.1, 16.1, 0, 6.1, 0],
        'Max_Miles': [8, 16, 999, 6, 14, 999],
        'Base_Price': [35, 40, 37, 38, 42, 40],
        'Per_Mile_Rate': [0, 0, 1.40, 0, 0, 0]
    }
    return pd.DataFrame(policies_data)

def get_sample_trip_data():
    trip_data = {
        'Trip_ID': ['OR-001', 'OR-002', 'OR-003', 'CA-001', 'CA-002', 'AK-001'],
        'Trip_Date': [datetime(2026, 3, 15), datetime(2026, 3, 15), datetime(2026, 3, 16), datetime(2026, 3, 16), datetime(2026, 3, 17), datetime(2026, 3, 18)],
        'State': ['OR', 'OR', 'OR', 'CA', 'CA', 'AK'],
        'Region': ['Portland', 'Portland', 'Eugene', 'Richmond', 'Richmond', 'Anchorage'],
        'Driver_Name': ['John Doe', 'John Doe', 'Mike Ross', 'Jane Smith', 'Jane Smith', 'Peter Pan'],
        'Distance_Miles': [7, 15, 20, 5, 15, 50],
        'Billed_Amount': [35, 40, 40, 38, 40, 40],
        'Driver_Pay': [25, 30, 32, 28, 30, 30],
        'Vehicle_Cost': [5, 5, 6, 4, 4, 7]
    }
    return pd.DataFrame(trip_data)

# --- Analysis Engine ---
def analyze_data(df_data, df_policies):
    df = df_data.copy()
    def get_policy_price(row):
        rules = df_policies[(df_policies['State'] == row['State']) & (row['Distance_Miles'] >= df_policies['Min_Miles']) & (row['Distance_Miles'] <= df_policies['Max_Miles'])]
        if not rules.empty:
            rule = rules.iloc[0]
            if rule['Per_Mile_Rate'] > 0:
                extra_miles = row['Distance_Miles'] - rule['Min_Miles']
                return rule['Base_Price'] + (extra_miles * rule['Per_Mile_Rate'])
            else:
                return rule['Base_Price']
        return 0
    df['Policy_Price'] = df.apply(get_policy_price, axis=1)
    df['Total_Cost'] = df['Driver_Pay'] + df['Vehicle_Cost']
    df['Trip_Profit'] = df['Billed_Amount'] - df['Total_Cost']
    df['Price_Variance'] = df['Billed_Amount'] - df['Policy_Price']
    df['Is_Violation'] = df['Price_Variance'] < 0
    return df

# --- User Interface ---
st.set_page_config(page_title="Trip Analyzer", layout="wide")
st.title("Beyond Transportation - Performance Analyzer")

policies = get_pricing_policies()
trip_data = get_sample_trip_data()
analyzed_df = analyze_data(trip_data, policies)

st.header("Key Performance Indicators")
col1, col2, col3 = st.columns(3)
col1.metric("Total Revenue", f"${analyzed_df['Billed_Amount'].sum():,.2f}")
col2.metric("Total Profit", f"${analyzed_df['Trip_Profit'].sum():,.2f}")
col3.metric("Pricing Violations", f"{analyzed_df['Is_Violation'].sum()} Trips")

st.header("Pricing Policy Violations")
violations_df = analyzed_df[analyzed_df['Is_Violation'] == True]
st.dataframe(violations_df)

with st.expander("View Full Analyzed Data"):
    st.dataframe(analyzed_df)
