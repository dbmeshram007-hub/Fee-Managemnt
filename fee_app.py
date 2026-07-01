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

@st.cache_data(ttl=30)
def load_all_data():
    client = get_gspread_client()
    sh = client.open("College_Admin_Database")
    
    # Load and force string type immediately to prevent UFuncNoLoopError
    students_data = pd.DataFrame(sh.worksheet("Student_Master").get_all_records())
    installments_data = pd.DataFrame(sh.worksheet("Installment_Log").get_all_records())
    
    # Clean headers & Force String Types
    for df in [students_data, installments_data]:
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
    # Set default values if columns missing
    if "TFWS" not in students_data.columns: students_data["TFWS"] = "No"
    
    return students_data, installments_data

# --- 2. Logic ---
try:
    students_df, installments_df = load_all_data()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

tab_ops, tab_reports = st.tabs(["💼 Transactions & Profiles", "📊 Reports"])

with tab_ops:
    st.sidebar.header("🔍 Student Search")
    search_query = st.sidebar.text_input("Name or ID:").strip()
    
    filtered = students_df
    if search_query:
        filtered = students_df[students_df["Name"].str.contains(search_query, case=False, na=False) | 
                               students_df["Student_ID"].str.contains(search_query, case=False, na=False)]
    
    if not filtered.empty:
        # Create Labels safely
        labels = filtered["Student_ID"] + " - " + filtered["Name"]
        selected = st.sidebar.selectbox("Select Student", labels.tolist())
        student_id = selected.split(" - ")[0]
        student_row = students_df[students_df["Student_ID"] == student_id].iloc[0]
        
        st.header(f"👤 {student_row['Name']}")
        is_tfws = student_row.get("TFWS", "No").lower() == "yes"
        st.subheader(f"TFWS Status: {'✅ Active' if is_tfws else '❌ Not Applicable'}")
        
        # --- Payment Entry ---
        with st.expander("➕ Post New Payment", expanded=True):
            col1, col2, col3 = st.columns(3)
            fee_heads = ["Tuition_fee", "Hostel_fee", "Gymkhana_fee", "Travelling_fee", "Other"]
            fee_head = col1.selectbox("Fee Head", fee_heads)
            
            # Conditional Logic
            room_type = "None"
            if fee_head == "Hostel_fee":
                room_type = col2.radio("Room Type", ["Non-AC", "AC"], horizontal=True)
            
            amt = col2.number_input("Amount", min_value=0, step=100)
            pay_date = col3.date_input("Date", datetime.date.today())
            remarks = st.text_input("Remarks", value=room_type if fee_head == "Hostel_fee" else "")
            
            if st.button("Post Payment Record", type="primary"):
                # TFW Logic: If Tuition and TFWS, force 0
                final_amt = 0 if (fee_head == "Tuition_fee" and is_tfws) else amt
                
                client = get_gspread_client()
                ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                ws.append_row([str(student_id), str(final_amt), str(pay_date), "1", fee_head, remarks])
                st.success("Transaction saved!")
                st.rerun()

        # --- History ---
        st.subheader("📜 Payment History")
        history = installments_df[installments_df["Student_ID"] == student_id]
        if not history.empty:
            for idx, row in history.iterrows():
                cols = st.columns([3, 2, 2, 1])
                cols[0].write(f"{row['Date_Paid']} | {row['Fee_Head']}")
                cols[1].write(f"₹{row['Amount_Paid']}")
                cols[2].write(row['Remarks'])
                if cols[3].button("🗑️", key=f"del_{idx}"):
                    client = get_gspread_client()
                    ws = client.open("College_Admin_Database").worksheet("Installment_Log")
                    # Note: Row index in sheet is DataFrame Index + 2
                    ws.delete_rows(int(idx) + 2)
                    st.rerun()
        else:
            st.info("No records found.")

with tab_reports:
    st.header("📥 Data Exports")
    if st.button("Generate Journal Fee List"):
        j_df = installments_df[installments_df["Fee_Head"] == "Journal_fee"]
        if not j_df.empty:
            st.download_button("Download CSV", j_df.to_csv(index=False), "Journal_Fee.csv", "text/csv")
        else:
            st.warning("No records found.")
