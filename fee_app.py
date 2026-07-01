import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import datetime

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System (Cloud)")

# --- 1. Cloud Connection (Using Published CSV URL) ---
# NOTE: In Secrets, 'spreadsheet' must be your Published CSV Link
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=600)
def load_data():
    # Use the published CSV URLs defined in secrets
    students = conn.read(worksheet="Student_Master")
    constants = conn.read(worksheet="Fee_Constants")
    installments = conn.read(worksheet="Installment_Log")
    
    # Standardize column headers
    for df in [students, constants, installments]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    
    students["Student_ID"] = students["Student_ID"].astype(str).str.strip()
    if "TFWS" not in students.columns:
        students["TFWS"] = "No"
        
    return students, constants, installments

students_df, constants_df, installments_df = load_data()

if "installments" not in st.session_state:
    st.session_state.installments = installments_df
# --- 2. Tabs for Workflow ---
tab_ops, tab_reports = st.tabs(["💼 Daily Transactions & Profiles", "📊 Batch & Year Reports"])

with tab_ops:
    # Sidebar & Logic (Same as before, using 'students_df' loaded from Cloud)
    st.sidebar.header("🔍 Student Search")
    search_query = st.sidebar.text_input("Name or Student ID:").strip()
    
    filtered_students = students_df
    if search_query:
        filtered_students = students_df[students_df["Name"].str.contains(search_query, case=False, na=False) | 
                                        students_df["Student_ID"].str.contains(search_query, case=False, na=False)]
    
    if not filtered_students.empty:
        student_dict = dict(zip(filtered_students["Student_ID"] + " - " + filtered_students["Name"], filtered_students["Student_ID"]))
        selected = st.sidebar.selectbox("Select Student", list(student_dict.keys()))
        student_id = student_dict[selected]
        
        student_row = students_df[students_df["Student_ID"] == student_id].iloc[0]
        
        # [Dashboard UI remains identical to previous version...]
        # ... (Include all the metric, number_input, and logic blocks here) ...
        
        # --- 5. Installment Entry Engine (CLOUD UPDATE) ---
        if st.button("Post Payment Record", type="primary"):
            new_trx = pd.DataFrame([{
                "Student_ID": str(student_id),
                "Amount_Paid": int(amt_to_pay),
                "Date_Paid": str(pay_date),
                "Installment_Number": int(inst_num),
                "Fee_Head": fee_head_paid,
                "Remarks": payment_remarks
            }])
            
            # Append to session state and push to Cloud
            st.session_state.installments = pd.concat([st.session_state.installments, new_trx], ignore_index=True)
            conn.update(worksheet="Installment_Log", data=st.session_state.installments)
            st.success("Successfully pushed to Cloud!")
            st.rerun()

with tab_reports:
    # ... (Include Batch Report and Record Book Report logic here) ...
    # Ensure they use the 'st.session_state.installments' dataframe.
    pass
