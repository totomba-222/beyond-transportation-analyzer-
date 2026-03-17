import pandas as pd
import streamlit as st

# ==============================================================================
#  1. PRICING POLICIES & ANALYSIS ENGINE
# ==============================================================================
@st.cache_data
def get_pricing_policies():
    # This function holds the official pricing rules for all states.
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
    ]
    return pd.DataFrame(policies_data)

def get_policy_price(row, df_policies):
    # Calculates the official price for a single trip based on its state and distance.
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
    # The main analysis function. Takes raw trip data and returns a fully analyzed DataFrame.
    df = df_data.copy()
    df['Policy_Price'] = df.apply(get_policy_price, axis=1, df_policies=df_policies)
    df['Margin'] = df['Gross_Pay'] - df['Net_Pay']
    df['Price_Variance'] = df['Gross_Pay'] - df['Policy_Price']
    # **CORRECTION**: Now identifies trips with HIGHER price than policy.
    df['Is_High_Margin'] = df['Price_Variance'] > 0
    df['Margin_%'] = df.apply(lambda row: (row['Margin'] / row['Gross_Pay']) if row['Gross_Pay'] > 0 else 0, axis=1)
    return df

# ==============================================================================
#  2. PAGE SETUP & UI FUNCTIONS
# ==============================================================================
st.set_page_config(page_title="Beyond Transportation Analyzer", layout="wide")

def page_home_and_upload():
    st.title("📊 Beyond Transportation - Performance Analyzer")
    st.header("Step 1: Upload Trip Data")
    st.markdown("Upload the Excel file. Required columns: `Trip_Date`, `State`, `Driver_Name`, `Distance_Miles`, `Gross_Pay`, `Net_Pay`")
    
    uploaded_file = st.file_uploader("Choose an .xlsx file", type="xlsx", key="uploader")
    
    if uploaded_file is not None:
        try:
            trips_df = pd.read_excel(uploaded_file, engine='openpyxl')
            required_cols = ['Trip_Date', 'State', 'Driver_Name', 'Distance_Miles', 'Gross_Pay', 'Net_Pay']
            if not all(col in trips_df.columns for col in required_cols):
                st.error(f"File is missing one or more required columns. Please ensure it contains: {', '.join(required_cols)}")
                return

            trips_df['Trip_Date'] = pd.to_datetime(trips_df['Trip_Date'], errors='coerce')
            numeric_cols = ['Distance_Miles', 'Gross_Pay', 'Net_Pay']
            for col in numeric_cols:
                trips_df[col] = pd.to_numeric(trips_df[col], errors='coerce').fillna(0)
            
            policies = get_pricing_policies()
            st.session_state.analyzed_df = analyze_data(trips_df, policies)
            st.success("File processed successfully! You can now navigate to other pages using the sidebar.")
        except Exception as e:
            st.error(f"An error occurred during file processing: {e}")

def page_state_analysis():
    st.title("🏢 State-Level Analysis")
    if 'analyzed_df' not in st.session_state:
        st.warning("Please upload a data file on the 'Home / Data Upload' page first.")
        return

    df = st.session_state.analyzed_df
    state_list = sorted(df['State'].unique().tolist())
    selected_state = st.selectbox("Choose a State to Analyze:", state_list)

    if selected_state:
        display_df = df[df['State'] == selected_state]
        st.header(f"Analysis for: {selected_state}")

        st.subheader("Financial Performance")
        total_gross = display_df['Gross_Pay'].sum()
        total_margin = display_df['Margin'].sum()
        avg_margin_percent = total_margin / total_gross if total_gross > 0 else 0
        
        summary_data = {
            'Metric': ['Total Trips', 'Total Gross Pay (Revenue)', 'Total Net Pay (Driver Cost)', 'Total Margin (Profit)', 'Average Margin %'],
            'Value': [
                f"{len(display_df)}",
                f"${total_gross:,.2f}",
                f"${display_df['Net_Pay'].sum():,.2f}",
                f"${total_margin:,.2f}",
                f"{avg_margin_percent:.2%}" # **NEW**: Added Margin %
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        st.table(summary_df.set_index('Metric'))

        # **CORRECTED**: Now shows high-margin trips instead of violations.
        st.subheader("High-Margin Trips (Billed > Policy)")
        high_margin_trips = display_df[display_df['Is_High_Margin']]
        if high_margin_trips.empty:
            st.info("No trips found with a billed amount higher than the policy price.")
        else:
            st.dataframe(high_margin_trips[['Trip_Date', 'Driver_Name', 'Distance_Miles', 'Gross_Pay', 'Policy_Price', 'Price_Variance']])

def page_driver_analysis():
    st.title("👤 Driver Statement")
    if 'analyzed_df' not in st.session_state:
        st.warning("Please upload a data file on the 'Home / Data Upload' page first.")
        return

    df = st.session_state.analyzed_df
    driver_list = sorted(df['Driver_Name'].unique().tolist())
    
    if driver_list:
        selected_driver = st.selectbox("Select a Driver:", driver_list)
        min_date = df['Trip_Date'].min().date()
        max_date = df['Trip_Date'].max().date()
        start_date = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
        end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)

        if st.button(f"Generate Statement for {selected_driver}"):
            driver_df = df[(df['Driver_Name'] == selected_driver) & (df['Trip_Date'].dt.date >= start_date) & (df['Trip_Date'].dt.date <= end_date)].copy()
            
            if driver_df.empty:
                st.warning("No trips found for this driver in the selected date range.")
            else:
                # **NEW**: Professional report layout matching your sample.
                st.subheader("Beyond Transportation Inc.")
                st.text("18051 SW Lower Boones Ferry Rd, Unit # 342, Tigard, OR 97224")
                st.markdown("---")
                st.subheader(f"Statement for: {selected_driver}")
                st.text(f"Period: {start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}")
                
                # Prepare data for the report table
                driver_df['DATE'] = driver_df['Trip_Date'].dt.strftime('%m/%d/%Y')
                driver_df['MEMO/DESCRIPTION'] = "Trip Payment - " + driver_df['State'] + " - " + driver_df['Distance_Miles'].astype(str) + " miles"
                driver_df['AMOUNT'] = driver_df['Net_Pay']
                
                report_table = driver_df[['DATE', 'MEMO/DESCRIPTION', 'AMOUNT']]
                st.table(report_table.style.format({'AMOUNT': '${:,.2f}'}))
                
                total_pay = driver_df['AMOUNT'].sum()
                st.markdown(f"**Total for {selected_driver}: ${total_pay:,.2f}**")

# ==============================================================================
#  3. MAIN APP ROUTER
# ==============================================================================
PAGES = {
    "Home / Data Upload": page_home_and_upload,
    "State Analysis": page_state_analysis,
    "Driver Statement": page_driver_analysis,
}

st.sidebar.title("Navigation")
selection = st.sidebar.radio("Go to", list(PAGES.keys()))
page = PAGES[selection]
page()
