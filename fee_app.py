import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System")

# --- 1. Robust Cloud Connection ---
@st.cache_resource
def get_gspread_client():
    # Load credentials from Streamlit Secrets
    # Ensure your Secrets contains a section [gspread] with your JSON credentials as a string
    creds_dict = dict(st.secrets["gspread_json"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def load_data_from_sheet(sheet_name, worksheet_name):
    client = get_gspread_client()
    sh = client.open(sheet_name)
    ws = sh.worksheet(worksheet_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)

# Usage
try:
    students_df = load_data_from_sheet("College_Admin_Database", "Student_Master")
    constants_df = load_data_from_sheet("College_Admin_Database", "Fee_Constants")
    installments_df = load_data_from_sheet("College_Admin_Database", "Installment_Log")
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

    # Cleaning headers
    for df in [students, constants, installments]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    
    students["Student_ID"] = students["Student_ID"].astype(str).str.strip()
    if "TFWS" not in students.columns:
        students["TFWS"] = "No"
        
    return students, constants, installments

# Initial Load
students_df, constants_df, installments_df = load_data()

if "installments" not in st.session_state:
    st.session_state.installments = installments_df

# --- 2. Dashboard Logic ---
tab_ops, tab_reports = st.tabs(["💼 Daily Transactions & Profiles", "📊 Batch & Year Reports"])

with tab_ops:
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
        
        st.header(f"👤 Account: {student_row['Name']}")
        
        # TFWS Logic
        is_tfws = str(student_row.get("TFWS", "No")).strip().lower() == "yes"
        st.subheader(f"TFWS Status: {'✅ Active' if is_tfws else '❌ Not Applicable'}")
        
        # Payment Inputs
        col1, col2, col3 = st.columns(3)
        fee_head = col1.selectbox("Fee Head", ["Tuition_fee", "Hostel_fee", "Practical_Record_Book", "Other"])
        amt_to_pay = col2.number_input("Amount", min_value=0, step=100)
        pay_date = col3.date_input("Date", datetime.date.today())
        remarks = st.text_input("Remarks")
        
        if st.button("Post Payment Record", type="primary"):
            new_trx = pd.DataFrame([{
                "Student_ID": str(student_id),
                "Amount_Paid": int(amt_to_pay),
                "Date_Paid": str(pay_date),
                "Installment_Number": 1,
                "Fee_Head": fee_head,
                "Remarks": remarks
            }])
            
            # Update Local Session
            st.session_state.installments = pd.concat([st.session_state.installments, new_trx], ignore_index=True)
            # Update Cloud Sheet
            conn.update(worksheet="Installment_Log", data=st.session_state.installments)
            
            st.success("Transaction saved to Cloud!")
            st.rerun()

with tab_reports:
    st.header("📊 Batch Outstanding Balance Report")
    target_year = st.selectbox("Select Year", sorted(students_df['Admission_Year'].unique(), reverse=True))
    
    if st.button("Generate Report"):
        batch = students_df[students_df['Admission_Year'] == target_year]
        st.dataframe(batch)
