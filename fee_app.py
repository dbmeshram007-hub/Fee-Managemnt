import streamlit as st
import pandas as pd
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System")

# --- 1. Cloud Connection (Using gspread) ---
@st.cache_resource
def get_gspread_client():
    creds_dict = dict(st.secrets["gspread_json"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=600)
def load_all_data():
    client = get_gspread_client()
    sh = client.open("College_Admin_Database")
    
    # Load all sheets
    students_df = pd.DataFrame(sh.worksheet("Student_Master").get_all_records())
    constants_df = pd.DataFrame(sh.worksheet("Fee_Constants").get_all_records())
    installments_df = pd.DataFrame(sh.worksheet("Installment_Log").get_all_records())
    
    # Cleaning headers
    for df in [students_df, constants_df, installments_df]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    
    students_df["Student_ID"] = students_df["Student_ID"].astype(str).str.strip()
    if "TFWS" not in students_df.columns:
        students_df["TFWS"] = "No"
        
    return students_df, constants_df, installments_df

# Load data
try:
    students_df, constants_df, installments_df = load_all_data()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

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
        is_tfws = str(student_row.get("TFWS", "No")).strip().lower() == "yes"
        st.subheader(f"TFWS Status: {'✅ Active' if is_tfws else '❌ Not Applicable'}")
        
        # --- NEW PAYMENT ENTRY ---
        with st.expander("➕ Post New Payment", expanded=True):
            col1, col2, col3 = st.columns(3)
            fee_head = col1.selectbox("Fee Head", ["Tuition_fee", "Hostel_fee", "Practical_Record_Book", "Other"])
            amt_to_pay = col2.number_input("Amount", min_value=0, step=100)
            pay_date = col3.date_input("Date", datetime.date.today())
            remarks = st.text_input("Remarks")
            
            if st.button("Post Payment Record", type="primary"):
                client = get_gspread_client()
                ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                ws.append_row([str(student_id), int(amt_to_pay), str(pay_date), 1, fee_head, remarks])
                st.success("Transaction saved!")
                st.rerun()

        # --- NEW PAYMENT HISTORY TABLE ---
        st.subheader("📜 Payment History")
        # Filter installments for this specific student
        history = installments_df[installments_df["Student_ID"].astype(str) == str(student_id)]
        
        if not history.empty:
            for idx, row in history.iterrows():
                cols = st.columns([3, 2, 2, 1])
                cols[0].write(f"{row['Date_Paid']} | {row['Fee_Head']}")
                cols[1].write(f"₹{row['Amount_Paid']}")
                cols[2].write(row['Remarks'])
                
                # DELETE BUTTON
                if cols[3].button("🗑️", key=f"del_{idx}"):
                    client = get_gspread_client()
                    ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                    # +2 accounts for the header row and 0-indexing of DataFrame
                    ws.delete_rows(idx + 2) 
                    st.warning("Entry deleted! Refreshing...")
                    st.rerun()
        else:
            st.info("No payment history found for this student.")

with tab_reports:
    st.header("📊 Batch Outstanding Balance Report")
    target_year = st.selectbox("Select Year", sorted(students_df['Admission_Year'].unique(), reverse=True))
    
    if st.button("Generate Report"):
        batch = students_df[students_df['Admission_Year'] == target_year]
        st.dataframe(batch)
