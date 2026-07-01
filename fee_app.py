import streamlit as st
import pandas as pd
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System")

# --- 1. Cloud Connection (gspread) ---
@st.cache_resource
def get_gspread_client():
    creds_dict = dict(st.secrets["gspread_json"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=60)
def load_all_data():
    client = get_gspread_client()
    sh = client.open("College_Admin_Database")
    
    # --- Load Students ---
    students_data = sh.worksheet("Student_Master").get_all_records()
    students_df = pd.DataFrame(students_data)
    
    # --- Load Installments (Defensive Load) ---
    ws_log = sh.worksheet("Installment_Log")
    installments_data = ws_log.get_all_records()
    
    if not installments_data:
        # Create an empty dataframe with expected columns if sheet is empty
        installments_df = pd.DataFrame(columns=["Student_ID", "Amount_Paid", "Date_Paid", "Installment_Number", "Fee_Head", "Remarks"])
    else:
        installments_df = pd.DataFrame(installments_data)
    
    # Cleaning headers
    for df in [students_df, installments_df]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    
    students_df["Student_ID"] = students_df["Student_ID"].astype(str).str.strip()
    installments_df["Student_ID"] = installments_df["Student_ID"].astype(str).str.strip()
    
    if "TFWS" not in students_df.columns:
        students_df["TFWS"] = "No"
        
    return students_df, installments_df
# Load Data
try:
    students_df, installments_df = load_all_data()
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
        st.subheader(f"Status: {'✅ TFWS Active' if is_tfws else '❌ TFWS Not Applicable'}")
        
        # --- PAYMENT FORM ---
        with st.expander("➕ Post New Payment", expanded=True):
            col1, col2, col3 = st.columns(3)
            fee_heads = ["Tuition_fee", "Hostel_fee", "Gymkhana_fee", "Journal_fee", "Travelling_fee"]
            fee_head = col1.selectbox("Fee Head", fee_heads)
            
            # Hostel & TFWS Logic
            room_type = "None"
            if fee_head == "Hostel_fee":
                room_type = col2.radio("Room Type", ["Non-AC", "AC"], horizontal=True)
            
            # TFW Button
            apply_tfw = False
            if fee_head == "Tuition_fee" and is_tfws:
                apply_tfw = col3.checkbox("Apply TFW (Waive Tuition Fee)", value=True)
            
            amt = col2.number_input("Amount", min_value=0, step=100, value=0 if apply_tfw else 1000)
            pay_date = col3.date_input("Date", datetime.date.today())
            remarks = st.text_input("Remarks", value=room_type if fee_head == "Hostel_fee" else "")
            
            if st.button("Post Payment Record", type="primary"):
                client = get_gspread_client()
                ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                ws.append_row([str(student_id), int(amt), str(pay_date), 1, fee_head, remarks])
                st.success("Transaction saved!")
                st.rerun()

        # --- PAYMENT HISTORY ---
        st.subheader("📜 Payment History")
        history = installments_df[installments_df["Student_ID"] == str(student_id)]
        
        if not history.empty:
            for idx, row in history.iterrows():
                cols = st.columns([3, 2, 2, 1])
                cols[0].write(f"{row['Date_Paid']} | {row['Fee_Head']}")
                cols[1].write(f"₹{row['Amount_Paid']}")
                cols[2].write(row['Remarks'])
                if cols[3].button("🗑️", key=f"del_{idx}"):
                    client = get_gspread_client()
                    ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                    # Note: Row index in sheet is DataFrame Index + 2 (Header row = 1)
                    ws.delete_rows(int(idx) + 2)
                    st.rerun()
        else:
            st.info("No records found.")

with tab_reports:
    st.header("📊 Reports")
    # Batch Report
    target_year = st.selectbox("Select Year", sorted(students_df['Admission_Year'].unique(), reverse=True))
    if st.button("Generate Batch Report"):
        st.dataframe(students_df[students_df['Admission_Year'] == target_year])
        
    st.divider()
    
    # Journal Fee Download
    st.subheader("📥 Journal Fee Records")
    if st.button("Generate Journal Fee List"):
        j_df = installments_df[installments_df["Fee_Head"] == "Journal_fee"]
        st.dataframe(j_df)
        if not j_df.empty:
            csv = j_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Journal Fee CSV", csv, "Journal_Fee.csv", "text/csv")
