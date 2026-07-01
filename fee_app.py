import streamlit as st
import pandas as pd
import gspread
import datetime
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System")

# --- 1. Cloud Connection ---
@st.cache_resource
def get_gspread_client():
    creds_dict = dict(st.secrets["gspread_json"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_all_data():
    client = get_gspread_client()
    sh = client.open("College_Admin_Database")
    
    # Load sheets
    students_df = pd.DataFrame(sh.worksheet("Student_Master").get_all_records())
    installments_df = pd.DataFrame(sh.worksheet("Installment_Log").get_all_records())
    
    # Clean headers
    for df in [students_df, installments_df]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    
    students_df["Student_ID"] = students_df["Student_ID"].astype(str).str.strip()
    installments_df["Student_ID"] = installments_df["Student_ID"].astype(str).str.strip()
    
    # Ensure necessary columns exist (Fill with 0 if missing)
    allotment_cols = ["Tuition_Allotted", "Hostel_Allotted", "Gymkhana_Allotted", "Travelling_Allotted"]
    for col in allotment_cols:
        if col not in students_df.columns:
            students_df[col] = 0
            
    return students_df, installments_df

# Load Data
try:
    students_df, installments_df = load_all_data()
except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

# --- 2. Dashboard Logic ---
tab_ops, tab_reports = st.tabs(["💼 Daily Transactions & Profiles", "📊 Batch & Year Reports"])

with tab_ops:
    st.sidebar.header("🔍 Student Search")
    search_query = st.sidebar.text_input("Name or Student ID:").strip()
    
    if search_query:
        filtered = students_df[students_df["Name"].str.contains(search_query, case=False, na=False) | 
                               students_df["Student_ID"].str.contains(search_query, case=False, na=False)]
    else:
        filtered = students_df

    if not filtered.empty:
        student_dict = dict(zip(filtered["Student_ID"] + " - " + filtered["Name"], filtered["Student_ID"]))
        selected = st.sidebar.selectbox("Select Student", list(student_dict.keys()))
        student_id = student_dict[selected]
        student_row = students_df[students_df["Student_ID"] == student_id].iloc[0]
        
        # Calculate Pending Fees
        student_payments = installments_df[installments_df["Student_ID"] == student_id]
        
        st.header(f"👤 Account: {student_row['Name']}")
        
        # Status Toggles
        is_tfws = str(student_row.get("TFWS", "No")).strip().lower() == "yes"
        st.subheader(f"Status: {'✅ TFWS Active' if is_tfws else '❌ TFWS Not Applicable'}")
        
        # --- PAYMENT FORM ---
        with st.expander("➕ Post New Payment", expanded=True):
            col1, col2, col3 = st.columns(3)
            fee_heads = ["Tuition_fee", "Hostel_fee", "Gymkhana_fee", "Travelling_fee", "Other"]
            fee_head = col1.selectbox("Fee Head", fee_heads)
            
            # Hostel AC Logic
            room_type = "None"
            if fee_head == "Hostel_fee":
                room_type = col2.radio("Room Type", ["Non-AC", "AC"], horizontal=True)
            
            amt = col2.number_input("Amount", min_value=0, step=100)
            pay_date = col3.date_input("Date", datetime.date.today())
            remarks = st.text_input("Remarks", value=room_type if fee_head == "Hostel_fee" else "")
            
            if st.button("Post Payment Record", type="primary"):
                # If TFWS and Tuition, force amount to 0
                final_amt = 0 if (fee_head == "Tuition_fee" and is_tfws) else amt
                
                client = get_gspread_client()
                ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                ws.append_row([str(student_id), int(final_amt), str(pay_date), 1, fee_head, remarks])
                st.success("Transaction saved!")
                st.rerun()

        # --- PENDING CALCULATION ---
        st.subheader("💳 Fee Summary")
        col_p1, col_p2, col_p3 = st.columns(3)
        
        # Simplified Pending Calculation
        paid_tuition = student_payments[student_payments["Fee_Head"] == "Tuition_fee"]["Amount_Paid"].sum()
        allotted_tuition = 0 if is_tfws else float(student_row.get("Tuition_Allotted", 0))
        
        col_p1.metric("Pending Tuition", f"₹{max(0, allotted_tuition - paid_tuition)}")
        col_p2.metric("Total Paid", f"₹{student_payments['Amount_Paid'].sum()}")
        
        # --- HISTORY ---
        st.subheader("📜 Payment History")
        if not student_payments.empty:
            for idx, row in student_payments.iterrows():
                cols = st.columns([3, 2, 2, 1])
                cols[0].write(f"{row['Date_Paid']} | {row['Fee_Head']}")
                cols[1].write(f"₹{row['Amount_Paid']}")
                cols[2].write(row['Remarks'])
                if cols[3].button("🗑️", key=f"del_{idx}"):
                    client = get_gspread_client()
                    ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                    ws.delete_rows(installments_df.index.get_loc(idx) + 2)
                    st.rerun()
        else:
            st.info("No records found.")

with tab_reports:
    st.header("📊 Reports")
    target_year = st.selectbox("Select Year", sorted(students_df['Admission_Year'].unique(), reverse=True))
    if st.button("Generate Report"):
        st.dataframe(students_df[students_df['Admission_Year'] == target_year])
        
    st.divider()
    
    st.subheader("📥 Export Journal Fee List")
    if st.button("Generate Journal Fee List"):
        j_df = installments_df[installments_df["Fee_Head"] == "Journal_fee"]
        if not j_df.empty:
            csv = j_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Journal Fee CSV", csv, "Journal_Fee_Report.csv", "text/csv")
