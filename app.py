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
        
        # --- SOUTH CALIFORNIA (S.CA) ---
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 4, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 4.01, 'Max_Miles': 8, 'Policy_Pay': 40.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 8.01, 'Max_Miles': 16, 'Policy_Pay': 43.0, 'Note': 'Flat Rate'},
        {'State': 'S.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 16.01, 'Max_Miles': 999, 'Policy_Pay': 43.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 43 + (Miles - 16) * 1.25'},
        
        # --- NORTH CALIFORNIA (N.CA) ---
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 0, 'Max_Miles': 6, 'Policy_Pay': 38.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 6.01, 'Max_Miles': 14, 'Policy_Pay': 42.0, 'Note': 'Flat Rate'},
        {'State': 'N.CA', 'Vehicle_Type': 'ANY', 'Min_Miles': 14.01, 'Max_Miles': 999, 'Policy_Pay': 38.0, 'Per_Mile_Rate': 1.25, 'Note': 'Base 38 + (Miles - 14) * 1.25'},
        
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
    """Normalize text for flexible matching (remove spaces, lowercase, remove special chars)."""
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    # Remove extra spaces and non-alphanumeric characters for English/Arabic
    text = re.sub(r'\s+', ' ', text)
    return text

def is_wheelchair_driver(driver_name):
    """Check if driver is one of the special wheelchair drivers (flexible matching)."""
    cleaned_name = clean_text(driver_name)
    # Target names in English and Arabic
    targets = [
        "mohamed omar ali", "mohamed elbashir", 
        "محمد عمر علي", "محمد البشير",
        "mohammed omar ali", "mohammed elbashir"
    ]
    for target in targets:
        if target in cleaned_name:
            return True
    return False

def calculate_policy_pay(row, selected_state, df_policies):
    """Calculate the policy pay based on miles and selected state."""
    miles = float(row.get('Distance_Miles', 0))
    gross_pay = float(row.get('Gross_Pay', 0))
    driver_name = str(row.get('Driver_Name', ''))

    # 1. WHEELCHAIR SPECIAL CASE (N.CA ONLY)
    if selected_state == 'N.CA' and is_wheelchair_driver(driver_name) and abs(gross_pay - 100.0) < 0.01:
        return 75.0

    # 2. STATE SPECIFIC LOGIC
    if selected_state == 'OR':
        if miles <= 8: return 35.0
        if miles <= 16: return 40.0
        return 37.0 + (max(0, miles - 16.01) * 1.75)

    if selected_state == 'S.CA':
        if miles <= 4: return 38.0
        if miles <= 8: return 40.0
        if miles <= 16: return 43.0
        return 43.0 + (max(0, miles - 16) * 1.25)

    if selected_state == 'N.CA':
        if miles <= 6: return 38.0
        if miles <= 14: return 42.0
        return 38.0 + (max(0, miles - 14) * 1.25)

    # 3. GENERAL FALLBACK FROM POLICY TABLE
    state_policies = df_policies[df_policies['State'] == selected_state]
    if state_policies.empty:
        return 0.0

    # Find matching range
    match = state_policies[(miles >= state_policies['Min_Miles']) & (miles <= state_policies['Max_Miles'])]
    if not match.empty:
        rule = match.iloc[0]
        base = float(rule['Policy_Pay'])
        rate = float(rule.get('Per_Mile_Rate', 0))
        if rate > 0:
            extra = max(0, miles - float(rule['Min_Miles']))
            return base + (extra * rate)
        return base

    # Absolute Fallback: First available policy for the state
    return float(state_policies.iloc[0]['Policy_Pay'])

def analyze_data(df_data, selected_state, df_policies):
    df = df_data.copy()
    df.columns = df.columns.str.strip()
    
    # Mapping for common column names
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
    
    # Convert to numeric
    for col in ['Distance_Miles', 'Gross_Pay', 'Net_Pay']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            df[col] = 0.0

    # Calculate Policy Pay
    df['Policy_Driver_Pay'] = df.apply(calculate_policy_pay, axis=1, selected_state=selected_state, df_policies=df_policies)
    
    # Ensure no zeros if miles > 0 (Safety Net)
    state_min = df_policies[df_policies['State'] == selected_state]['Policy_Pay'].min() if not df_policies[df_policies['State'] == selected_state].empty else 0
    df.loc[(df['Policy_Driver_Pay'] == 0) & (df['Distance_Miles'] > 0), 'Policy_Driver_Pay'] = state_min

    df['Loss_Amount'] = (df['Net_Pay'] - df['Policy_Driver_Pay']).clip(lower=0)
    df['Is_Non_Compliant'] = df['Loss_Amount'] > 0.05
    
    return df

# ==============================================================================
#  3. UI INTERFACE
# ==============================================================================

def main():
    st.sidebar.title("Navigation")
    STATES = {
        "OR": "Oregon", 
        "S.CA": "South California", 
        "N.CA": "North California", 
        "AK": "Alaska", 
        "IL": "Illinois", 
        "NM": "New Mexico", 
        "NE": "Nebraska", 
        "CAN": "Canada"
    }
    selected_state = st.sidebar.radio("Select State", list(STATES.keys()), format_func=lambda x: STATES[x])
    
    st.title(f"📊 {STATES[selected_state]} Analysis")
    
    all_policies = get_pricing_policies()
    state_policy_df = all_policies[all_policies['State'] == selected_state].drop(columns=['State'])
    
    with st.expander("View Current Pricing Policy"):
        st.table(state_policy_df)

    uploaded_file = st.file_uploader("Upload Excel File (.xlsx)", type="xlsx")

    if uploaded_file:
        try:
            raw_df = pd.read_excel(uploaded_file)
            analyzed_df = analyze_data(raw_df, selected_state, all_policies)
            
            # Summary Metrics
            m1, m2, m3 = st.columns(3)
            total_rev = analyzed_df['Gross_Pay'].sum()
            total_cost = analyzed_df['Net_Pay'].sum()
            total_loss = analyzed_df['Loss_Amount'].sum()
            
            m1.metric("Total Revenue", f"${total_rev:,.2f}")
            m2.metric("Total Driver Pay", f"${total_cost:,.2f}")
            m3.metric("Total Loss (Overpaid)", f"${total_loss:,.2f}", delta_color="inverse")

            # Compliance Table
            st.subheader("Detailed Analysis")
            display_df = analyzed_df[['Driver_Name', 'Distance_Miles', 'Gross_Pay', 'Net_Pay', 'Policy_Driver_Pay', 'Loss_Amount']]
            
            # Highlight non-compliant rows
            def highlight_loss(s):
                return ['background-color: #ffcccc' if v > 0 else '' for v in s]
            
            st.dataframe(display_df.style.apply(highlight_loss, subset=['Loss_Amount']))
            
            # Download Result
            output = analyzed_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("Download Analysis as CSV", output, "analysis_result.csv", "text/csv")
            
        except Exception as e:
            st.error(f"Error processing file: {e}")

if __name__ == "__main__":
    main()
