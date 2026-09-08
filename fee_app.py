import streamlit as st
import pandas as pd
import datetime
import os
from fpdf import FPDF
import io
import gspread
from google.oauth2.service_account import Credentials
import numpy as np

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")

# ==========================================
# 0. UNIVERSAL DATA CLEANER (The Bug Fix)
# ==========================================
def safe_int(val):
    """Safely converts any weird Google Sheets value (NaN, "", text) into a clean integer 0"""
    try:
        num = pd.to_numeric(val, errors='coerce')
        return int(num) if pd.notnull(num) else 0
    except Exception:
        return 0

# ==========================================
# 1. GLOBAL CONFIGURATION & LOCAL FILES
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STUDENT_FILE = os.path.join(BASE_DIR, "Student_Master.csv")
CONSTANTS_FILE = os.path.join(BASE_DIR, "Fee_Constants.csv")
ALLOTMENTS_FILE = os.path.join(BASE_DIR, "Facility_Allotments.csv")

# ==========================================
# 2. CLOUD DATABASE CONNECTION (GOOGLE SHEETS)
# ==========================================
def get_gsheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def get_live_installments():
    try:
        client = get_gsheets_client()
        sheet = client.open("Pioneer_Fee_Database").worksheet("Installment_Log")
        records = sheet.get_all_records()
        if not records:
             return pd.DataFrame(columns=["Student_ID", "Semester", "Amount_Paid", "Date_Paid", "Installment_Number", "Fee_Head", "Remarks", "Entry_By"])
        df = pd.DataFrame(records)
        df["Student_ID"] = df["Student_ID"].astype(str).str.strip()
        return df
    except Exception as e:
        # THE FIX: Stop the app completely if the network fails so it can't overwrite data
        st.error(f"🚨 Cloud Network Glitch: {e}. Please refresh the page.")
        st.stop()
def save_installments(df):
    try:
        client = get_gsheets_client()
        sheet = client.open("Pioneer_Fee_Database").worksheet("Installment_Log")
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())

        st.cache_data.clear()
        
        return True, ""
    except Exception as e:
        return False, f"Database Write Error: {e}"

@st.cache_data(ttl=600)
def load_cloud_overrides():
    try:
        client = get_gsheets_client()
        sheet = client.open("Pioneer_Fee_Database").worksheet("Fee_Overrides")
        records = sheet.get_all_records()
        if records:
            df = pd.DataFrame(records)
            df['Student_ID'] = df['Student_ID'].astype(str).str.strip()
            df['Semester'] = df['Semester'].astype(str).str.strip()
            return df
        return pd.DataFrame(columns=['Student_ID', 'Semester', 'Travel_Override', 'Gymkhana_Override', 'Hostel_Override', 'Tuition_Discount', 'College_Deposit_Manual'])
    except Exception as e:
        # THE FIX: Stop the app completely if the network fails
        st.error(f"🚨 Cloud Network Glitch: {e}. Please refresh the page.")
        st.stop()
def save_cloud_overrides(df):
    try:
        client = get_gsheets_client()
        sheet = client.open("Pioneer_Fee_Database").worksheet("Fee_Overrides")
        sheet.clear()
        
        # --- THE FIX STARTS HERE ---
        # We clean the data: replace all 'NaN' values with an empty string
        df_clean = df.fillna('')
        # --- THE FIX ENDS HERE ---
        
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())

        st.cache_data.clear()
        
        return True
    except Exception as e:
        st.error(f"Failed to save overrides to cloud: {e}")
        return False

def append_new_installment(new_row_dict):
    try:
        client = get_gsheets_client()
        sheet = client.open("Pioneer_Fee_Database").worksheet("Installment_Log")
        
        # FIXED: This now matches your Google Sheet columns exactly left-to-right
        row_data = [
            new_row_dict["Student_ID"],          # Column 1
            new_row_dict["Amount_Paid"],         # Column 2
            new_row_dict["Date_Paid"],           # Column 3
            new_row_dict["Installment_Number"],  # Column 4
            new_row_dict["Fee_Head"],            # Column 5
            new_row_dict["Remarks"],             # Column 6
            new_row_dict["Semester"],            # Column 7
            new_row_dict["Entry_By"]             # Column 8
        ]
        
        sheet.append_row(row_data)

        st.cache_data.clear()
        
        return True, ""
    except Exception as e:
        return False, f"Database Write Error: {e}"
# ==========================================
# 3. LOGIN GATE & ACCOUNTABILITY
# ==========================================
USER_CREDENTIALS = {
    "Admin": "admin123",       
    "Assistant": "assist2026"  
}

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""

if not st.session_state["logged_in"]:
    st.title("🔐 Pioneer Pharmacy College - Admin Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["role"] = "admin" if username == "Admin" else "assistant"
                st.success(f"Welcome back, {username}!")
                st.rerun()
            else:
                st.error("Invalid Username or Password. Please try again.")
    st.stop()

st.sidebar.write(f"👤 **Logged in as:** {st.session_state.get('username', 'Unknown')}")

if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""
    st.rerun()

# --- PASTE THE NEW REFRESH BUTTON HERE ---
if st.sidebar.button("🔄 Sync with Cloud"):
    st.cache_data.clear()  # Wipes the 10-minute memory
    st.rerun()             # Reloads the page with fresh data
# ------------------------------------------

st.sidebar.markdown("---")
# ==========================================
# 4. DATA LOADING & HELPER FUNCTIONS
# ==========================================
st.title("🎓 Fee Reconciliation & Management System")

overrides_df = load_cloud_overrides()

try:
    allotments_df = pd.read_csv(ALLOTMENTS_FILE)
    allotments_df['Student_ID'] = allotments_df['Student_ID'].astype(str) 
except Exception:
    allotments_df = pd.DataFrame(columns=['Student_ID', 'Hostel_Allotted', 'Transport_Allotted'])

try:
    fee_constants_df = pd.read_csv(CONSTANTS_FILE)
    fee_constants_df.columns = fee_constants_df.columns.str.strip()
except Exception as e:
    st.error(f"⚠️ Error loading Fee Constants: {e}")
    fee_constants_df = pd.DataFrame()

def get_expected_fee(course, semester, fee_head, category, admission_year):
    if fee_constants_df.empty: return 0
    c_course, c_sem, c_head, c_cat, c_year = str(course).strip(), str(semester).strip(), str(fee_head).strip(), str(category).strip(), str(admission_year).strip()
    df_course, df_sem, df_head, df_cat = fee_constants_df['Course'].astype(str).str.strip(), fee_constants_df['Semester'].astype(str).str.strip(), fee_constants_df['Fee_Head'].astype(str).str.strip(), fee_constants_df['Category_Condition'].astype(str).str.strip()
    filtered = fee_constants_df[(df_course == c_course) & (df_sem == c_sem) & (df_head == c_head) & (df_cat == c_cat)]
    if filtered.empty: return 0
    year_match = filtered[filtered['Admission_Year'].astype(str).str.strip() == c_year]
    if not year_match.empty: return safe_int(year_match.iloc[0]['Amount_Due'])
    default_match = filtered[filtered['Admission_Year'].astype(str).str.strip().str.lower() == 'default']
    if not default_match.empty: return safe_int(default_match.iloc[0]['Amount_Due'])
    return 0

def generate_noc_pdf(student_info, transactions_df, total_amount):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt="PIONEER PHARMACY COLLEGE", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt="Fee Clearance & No-Objection Certificate (NOC)", ln=True, align='C')
    pdf.line(10, 30, 200, 30)
    pdf.ln(5)
    today_str = datetime.date.today().strftime("%d-%m-%Y")
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 8, txt=f"Date of Issue: {today_str}", ln=True, align='R')
    pdf.ln(2)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, txt=f"Student Name: {student_info['Name']}", ln=True)
    pdf.cell(0, 8, txt=f"Enrollment / Student ID: {student_info['Student_ID']}", ln=True)
    pdf.cell(0, 8, txt=f"Course: {student_info['Course']} (Admitted: {student_info['Admission_Year']})", ln=True)
    tfws_status = str(student_info.get('TFW_Status', 'No'))
    pdf.cell(0, 8, txt=f"TFWS Beneficiary: {tfws_status}", ln=True)
    pdf.cell(0, 8, txt=f"Current Status: {student_info['Status']}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(30, 10, 'Date', border=1, fill=True, align='C')
    pdf.cell(20, 10, 'Sem', border=1, fill=True, align='C')
    pdf.cell(100, 10, 'Fee Head', border=1, fill=True, align='C')
    pdf.cell(40, 10, 'Amount Paid', border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_font("Arial", size=9)
    for _, row in transactions_df.iterrows():
        pdf.cell(30, 8, str(row['Date_Paid']), border=1, align='C')
        pdf.cell(20, 8, str(row.get('Semester', '1')), border=1, align='C')
        fee_head_clean = str(row['Fee_Head']).replace("_", " ")[:45]
        pdf.cell(100, 8, fee_head_clean, border=1)
        pdf.cell(40, 8, f"Rs {safe_int(row['Amount_Paid']):,}", border=1, align='R')
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, txt=f"Total Lifetime Fees Collected: Rs {total_amount:,}", ln=True, align='R')
    pdf.ln(20)
    pdf.set_font("Arial", size=10)
    pdf.cell(100, 10, txt="__________________________", ln=False)
    pdf.cell(90, 10, txt="__________________________", ln=True, align='R')
    pdf.cell(100, 10, txt="Clerk / Accounts Signature", ln=False)
    pdf.cell(90, 10, txt="Authorized Signatory (Admin)", ln=True, align='R')
    return pdf.output(dest='S').encode('latin-1')

def load_base_data():
    if not os.path.exists(STUDENT_FILE) or not os.path.exists(CONSTANTS_FILE):
        st.error(f"Required files missing in: {BASE_DIR}")
        st.stop()
    students = pd.read_csv(STUDENT_FILE)
    students.columns = students.columns.str.replace('\ufeff', '').str.strip().str.replace(" ", "_")
    students.rename(columns={"Student_ID": "Student_ID", "Name": "Name"}, inplace=True)
    students["Student_ID"] = students["Student_ID"].astype(str).str.strip()
    constants = pd.read_csv(CONSTANTS_FILE)
    constants.columns = [str(c).strip().replace(" ", "_") for c in constants.columns]
    return students, constants

try:
    students_df, constants_df = load_base_data()
    master_df = students_df
except Exception as e:
    st.error(f"Failed to load required data: {e}")
    st.stop()

# ==========================================
# 5. DASHBOARD TABS
# ==========================================
tab_ops, tab_reports = st.tabs(["💼 Daily Transactions & Profiles", "📊 Batch & Year Reports"])

with tab_ops:
    st.sidebar.header("🔍 Student Search Engine")
    col_a, col_b = st.sidebar.columns(2)
    course_filter = col_a.selectbox("Course", ["All", "B. Pharm", "M. Pharm"])
    status_filter = col_b.selectbox("Status", ["Active", "Alumni", "Dropped", "Active(Re-Admitted)"])
    
    filtered = students_df[students_df["Status"] == status_filter]
    if course_filter != "All": filtered = filtered[filtered["Course"] == course_filter]
        
    search_query = st.sidebar.text_input("Type Name or Student ID:").strip()
    if search_query:
        filtered = filtered[filtered["Name"].astype(str).str.contains(search_query, case=False, na=False) | 
                           filtered["Student_ID"].astype(str).str.contains(search_query, case=False, na=False)]

    selected_student_str = None
    student_id = None
    if not filtered.empty:
        student_dict = dict(zip(filtered["Student_ID"].astype(str) + " - " + filtered["Name"], filtered["Student_ID"].astype(str)))
        selected_student_str = st.sidebar.selectbox("Matching Results", list(student_dict.keys()))
        student_id = student_dict[selected_student_str] 
    else:
        st.sidebar.warning("No matches found.")

    if selected_student_str:
        student_row = master_df[master_df["Student_ID"] == student_id].iloc[0]
        st.header(f"👤 Account Profile: {student_row['Name']}")
        
        admission_type = str(student_row.get('Admission_Type', 'Regular')).strip().upper()
        try:
            starting_sem = int(student_row.get('Starting_Semester', 1))
        except (ValueError, TypeError):
            starting_sem = 1
        if admission_type == "D2D" and starting_sem == 1: starting_sem = 3

        current_year = 2026
        elapsed_years = current_year - int(student_row["Admission_Year"])
        calculated_sem = max(starting_sem, (elapsed_years * 2) + 1)
        max_sem = 8 if "b." in str(student_row["Course"]).lower() else 4
        calculated_sem = min(max(starting_sem, calculated_sem), max_sem)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Student ID", str(student_row["Student_ID"]))
        col2.metric("Course", f"{student_row['Course']} ({admission_type})")
        col3.metric("Admission Year", int(student_row["Admission_Year"]))
        selected_sem = col4.number_input("Target Semester Look-up", min_value=starting_sem, max_value=max_sem, value=calculated_sem, step=1)
        st.markdown("---")

        all_payments_df = get_live_installments()
        all_payments_df['Semester'] = all_payments_df['Semester'].astype(str).str.extract(r'(\d+)')[0]
        clean_student_id = str(student_id).strip()
        student_payments_lifetime = all_payments_df[all_payments_df['Student_ID'] == clean_student_id].copy()

        student_admission_year = str(int(student_row.get('Admission_Year', 2026))).strip()
        student_course = str(student_row.get('Course', 'B. Pharm')).strip()
        student_quota = str(student_row.get("Quota", "Govt_Quota")).strip()
        
        lt_debits_tuition = lt_debits_travel = lt_debits_hostel = lt_debits_college_deposit = lt_debits_hostel_deposit = 0

        student_allotment = allotments_df[allotments_df['Student_ID'] == str(student_id)]
        if not student_allotment.empty:
            default_transport = str(student_allotment.iloc[0].get('Transport_Allotted', 'None')).strip()
            default_hostel = str(student_allotment.iloc[0].get('Hostel_Allotted', 'None')).strip()
        else:
            default_transport = default_hostel = "None"
            
        if default_transport in ["nan", "", "NaN"]: default_transport = "None"
        if default_hostel in ["nan", "", "NaN"]: default_hostel = "None"
        
        for s in range(starting_sem, int(selected_sem) + 1):
            sem_str = str(s)
            calculated_tuition = 0
            if str(student_row.get("TFW_Status", "No")).strip().lower() != "yes":
                if "m." in student_course.lower() and "pharm" in student_course.lower():
                    if "management" in student_quota.lower():
                        calculated_tuition = get_expected_fee(student_course, sem_str, 'Tuition_fee', 'Management_Quota', student_admission_year)
                    else:
                        calculated_tuition = get_expected_fee(student_course, sem_str, 'Tuition_fee', 'Govt_Quota', student_admission_year)
                else:
                    calculated_tuition = get_expected_fee(student_course, sem_str, 'Tuition_fee', 'Default', student_admission_year)
            
            hist_override = overrides_df[(overrides_df['Student_ID'] == str(student_id)) & (overrides_df['Semester'] == sem_str)]
            if not hist_override.empty:
                hist_discount = safe_int(hist_override.iloc[0].get('Tuition_Discount'))
            else:
                hist_discount = 0
            
            lt_debits_tuition += max(0, calculated_tuition - hist_discount)
            
            if not hist_override.empty:
                travel_val = hist_override.iloc[0].get('Travel_Override')
                if pd.notnull(travel_val) and str(travel_val).strip() != "": lt_debits_travel += safe_int(travel_val)
                elif default_transport != "None": lt_debits_travel += get_expected_fee(student_course, sem_str, 'Travelling_Fee', default_transport, student_admission_year)
            elif default_transport != "None":
                lt_debits_travel += get_expected_fee(student_course, sem_str, 'Travelling_Fee', default_transport, student_admission_year)

            if not hist_override.empty:
                hostel_val = hist_override.iloc[0].get('Hostel_Override')
                if pd.notnull(hostel_val) and str(hostel_val).strip() != "": lt_debits_hostel += safe_int(hostel_val)
                elif default_hostel != "None": lt_debits_hostel += get_expected_fee(student_course, sem_str, 'Hostel_fee', default_hostel, student_admission_year)
            elif default_hostel != "None":
                lt_debits_hostel += get_expected_fee(student_course, sem_str, 'Hostel_fee', default_hostel, student_admission_year)

            if s == starting_sem and admission_type != "TRANSFER":
                lt_debits_college_deposit += get_expected_fee(student_course, '1', 'College_Refundable_Deposit', 'Sem_1', student_admission_year)
                if default_hostel in ["Hostel_AC", "Hostel_NonAC"]:
                    lt_debits_hostel_deposit += get_expected_fee(student_course, '1', 'Hostel_Refundable_Deposit', 'Sem_1', student_admission_year)
            
            if not hist_override.empty:
                lt_debits_college_deposit += safe_int(hist_override.iloc[0].get('College_Deposit_Manual'))
        if not student_payments_lifetime.empty:
            def calculate_clean_sum(amount_series):
                clean_strings = amount_series.astype(str).str.replace(r'[^\d.]', '', regex=True)
                return int(pd.to_numeric(clean_strings, errors='coerce').fillna(0).sum())
                
            paid_tuition = calculate_clean_sum(student_payments_lifetime[student_payments_lifetime["Fee_Head"].isin(["Tuition_fee", "Tuition_Fees_/_College_Fees"])]['Amount_Paid'])
            paid_travel = calculate_clean_sum(student_payments_lifetime[student_payments_lifetime["Fee_Head"].isin(["Travelling_Fee", "Travelling_Fees"])]['Amount_Paid'])
            paid_hostel = calculate_clean_sum(student_payments_lifetime[student_payments_lifetime["Fee_Head"].isin(["Hostel_fee", "Hostel_Fees"])]['Amount_Paid'])
            paid_col_dep = calculate_clean_sum(student_payments_lifetime[student_payments_lifetime["Fee_Head"].isin(["College_Refundable_Deposit", "College_Deposit(Refundable)"])]['Amount_Paid'])
            paid_hos_dep = calculate_clean_sum(student_payments_lifetime[student_payments_lifetime["Fee_Head"].isin(["Hostel_Refundable_Deposit", "Hostel_Deposit(Refundable)"])]['Amount_Paid'])
        else:
            paid_tuition = paid_travel = paid_hostel = paid_col_dep = paid_hos_dep = 0
        
        tuition_pending = max(0, lt_debits_tuition - paid_tuition)
        travel_pending = max(0, lt_debits_travel - paid_travel)
        hostel_pending = max(0, lt_debits_hostel - paid_hostel)
        col_dep_pending = max(0, lt_debits_college_deposit - paid_col_dep)
        hos_dep_pending = max(0, lt_debits_hostel_deposit - paid_hos_dep)
        
        lt_pending = tuition_pending + travel_pending + hostel_pending + col_dep_pending + hos_dep_pending

        breakdown_items = []
        if tuition_pending > 0: breakdown_items.append(f"Tuition: ₹{tuition_pending:,}")
        if travel_pending > 0: breakdown_items.append(f"Travel: ₹{travel_pending:,}")
        if hostel_pending > 0: breakdown_items.append(f"Hostel: ₹{hostel_pending:,}")
        if col_dep_pending > 0: breakdown_items.append(f"Col. Deposit: ₹{col_dep_pending:,}")
        if hos_dep_pending > 0: breakdown_items.append(f"Hos. Deposit: ₹{hos_dep_pending:,}")
        breakdown_str = " | ".join(breakdown_items)

        if lt_pending > 0:
            st.error(f"🚨 **ACCOUNT ALERT: Outstanding Balance: ₹{lt_pending:,} ({breakdown_str})** - Calculated from Sem {starting_sem} to Sem {selected_sem}")
        else:
            st.success(f"✅ **ACCOUNT CLEAR: No historical dues pending from Sem {starting_sem} to Sem {selected_sem}.**")
        st.markdown("---")

        st.subheader("⚙️ Fee Variable Configurations")
        
        is_tfws = str(student_row.get("TFW_Status", "No")).strip().lower() == "yes"
        unified_tfws = st.selectbox("Tuition Fee Waiver (TFWS)", ["No", "Yes"], index=1 if is_tfws else 0)

        col_h, col_t = st.columns(2)
        hostel_options = ["None", "Hostel_AC", "Hostel_NonAC"]
        transport_options = ["None", "Travel_City", "Travel_Outside"]

        h_index = hostel_options.index(default_hostel) if default_hostel in hostel_options else 0
        t_index = transport_options.index(default_transport) if default_transport in transport_options else 0

        with col_h: hostel_selection = st.selectbox("Hostel Status", hostel_options, index=h_index)
        with col_t: transport_selection = st.selectbox("Travelling Route Category", transport_options, index=t_index)
           
        st.subheader("💸 Debit Modifiers & Discounts")
        safe_sem_str = str(int(selected_sem)).strip()
        student_overrides = overrides_df[(overrides_df['Student_ID'] == str(student_id)) & (overrides_df['Semester'] == safe_sem_str)]
        
        if not student_overrides.empty:
            saved_travel = safe_int(student_overrides.iloc[0].get('Travel_Override'))
            saved_gymkhana = safe_int(student_overrides.iloc[0].get('Gymkhana_Override'))
            saved_hostel = safe_int(student_overrides.iloc[0].get('Hostel_Override'))
            saved_discount = safe_int(student_overrides.iloc[0].get('Tuition_Discount'))
            # ADDED: Remember the manual deposit
            saved_col_dep = safe_int(student_overrides.iloc[0].get('College_Deposit_Manual')) 
        else:
            saved_travel = get_expected_fee(student_course, safe_sem_str, 'Travelling_Fee', default_transport, student_admission_year) if default_transport != "None" else 0
            saved_hostel = get_expected_fee(student_course, safe_sem_str, 'Hostel_fee', default_hostel, student_admission_year) if default_hostel != "None" else 0
            saved_gymkhana = 0
            saved_discount = 0
            saved_col_dep = 0 # ADDED

        col_mod1, col_mod2, col_mod3, col_mod4 = st.columns(4)
        travel_override = col_mod1.number_input("Travelling Fee (Override)", min_value=0, value=saved_travel, step=500, key=f"travel_override_{student_id}_{selected_sem}")
        hostel_override = col_mod2.number_input("Hostel Fee (Override)", min_value=0, value=saved_hostel, step=500, key=f"hostel_override_{student_id}_{selected_sem}")
        gymkhana_override = col_mod3.number_input("Gymkhana (Manual Entry)", min_value=0, value=saved_gymkhana, step=100, key=f"gymkhana_override_{student_id}_{selected_sem}")
        tuition_discount = col_mod4.number_input("Tuition Discount (-)", min_value=0, value=saved_discount, step=500, key=f"discount_{student_id}_{selected_sem}")

        col_mod5 = st.columns(4)[0] 
        # UPDATED: Use 'saved_col_dep' instead of 0
        college_deposit_manual = st.number_input("Manual College Deposit", min_value=0, value=saved_col_dep, step=1000, key=f"col_dep_{student_id}_{selected_sem}")       
        if st.button("💾 Save Debit Modifiers"):
            overrides_df = overrides_df[~((overrides_df['Student_ID'] == str(student_id)) & (overrides_df['Semester'] == safe_sem_str))]
            new_record = pd.DataFrame([{
                'Student_ID': str(student_id),
                'Semester': safe_sem_str,
                'Travel_Override': travel_override,
                'Hostel_Override': hostel_override,
                'Gymkhana_Override': gymkhana_override,
                'Tuition_Discount': tuition_discount,
                'College_Deposit_Manual': college_deposit_manual # ADD THIS
            }])
            
            overrides_df = pd.concat([overrides_df, new_record], ignore_index=True)
            if save_cloud_overrides(overrides_df):
                st.success("✅ Modifiers and Discounts saved permanently to Cloud!")
                st.rerun()
        
        tuition_debit = hostel_debit = transport_debit = gymkhana_debit = college_deposit = hostel_deposit = 0

        if unified_tfws == "Yes":
            tuition_debit = 0 
            st.info("✅ TFWS Active: Tuition Fee Waived")
        else:
            if "m." in student_course.lower() and "pharm" in student_course.lower():
                if "management" in student_quota.lower():
                    tuition_debit = get_expected_fee(student_course, selected_sem, 'Tuition_fee', 'Management_Quota', student_admission_year)
                else:
                    tuition_debit = get_expected_fee(student_course, selected_sem, 'Tuition_fee', 'Govt_Quota', student_admission_year)
            else:
                tuition_debit = get_expected_fee(student_course, selected_sem, 'Tuition_fee', 'Default', student_admission_year)
                
        if tuition_discount > 0:
            tuition_debit = max(0, tuition_debit - tuition_discount)
            st.success(f"🎉 Applied Tuition Discount of -₹{tuition_discount:,} for Sem {selected_sem}.")

        if not student_overrides.empty:
            hostel_val = student_overrides.iloc[0].get('Hostel_Override')
            if pd.notnull(hostel_val) and str(hostel_val).strip() != "": hostel_debit = safe_int(hostel_val)
            elif hostel_selection != "None": hostel_debit = get_expected_fee(student_course, str(selected_sem), 'Hostel_fee', hostel_selection, student_admission_year)
        elif hostel_selection != "None":
            hostel_debit = get_expected_fee(student_course, str(selected_sem), 'Hostel_fee', hostel_selection, student_admission_year)

        if not student_overrides.empty:
            travel_val = student_overrides.iloc[0].get('Travel_Override')
            if pd.notnull(travel_val) and str(travel_val).strip() != "": transport_debit = safe_int(travel_val)
            elif transport_selection != "None": transport_debit = get_expected_fee(student_course, str(selected_sem), 'Travelling_Fee', transport_selection, student_admission_year)
        elif transport_selection != "None":
            transport_debit = get_expected_fee(student_course, str(selected_sem), 'Travelling_Fee', transport_selection, student_admission_year)

        gymkhana_debit = gymkhana_override

        if selected_sem == starting_sem:
            college_deposit = get_expected_fee(student_course, '1', 'College_Refundable_Deposit', 'Sem_1', student_admission_year)
            if hostel_selection in ["Hostel_AC", "Hostel_NonAC"]:
                hostel_deposit = get_expected_fee(student_course, '1', 'Hostel_Refundable_Deposit', 'Sem_1', student_admission_year)

        # Ensure you include the manual deposit in your sum:
        total_debits_this_sem = tuition_debit + hostel_debit + transport_debit + gymkhana_debit + college_deposit + hostel_deposit + college_deposit_manual 
        
        student_payments_lifetime['Semester_Safe'] = student_payments_lifetime['Semester'].astype(str).str.strip()
        payments_this_sem = student_payments_lifetime[student_payments_lifetime['Semester_Safe'] == safe_sem_str].copy()
        
        valid_heads_current = [
            "Tuition_fee", "Tuition_Fees_/_College_Fees",
            "College_Refundable_Deposit", "College_Deposit(Refundable)",
            "Travelling_Fee", "Travelling_Fees",
            "Hostel_fee", "Hostel_Fees",
            "Hostel_Refundable_Deposit", "Hostel_Deposit(Refundable)"
        ]
        main_payments = payments_this_sem[payments_this_sem["Fee_Head"].isin(valid_heads_current)].copy()
        record_book_payments = payments_this_sem[payments_this_sem["Fee_Head"] == "Practical_Record_Book"].copy()
        alumni_fee_payments = student_payments_lifetime[student_payments_lifetime["Fee_Head"] == "Alumni_Fee"].copy()
        
        def calculate_clean_sum(amount_series):
            clean_strings = amount_series.astype(str).str.replace(r'[^\d.]', '', regex=True)
            return int(pd.to_numeric(clean_strings, errors='coerce').fillna(0).sum())

        total_paid_this_sem = calculate_clean_sum(main_payments['Amount_Paid'])
        record_book_total = calculate_clean_sum(record_book_payments['Amount_Paid'])
        alumni_fee_total = calculate_clean_sum(alumni_fee_payments['Amount_Paid'])

        net_pending = total_debits_this_sem - total_paid_this_sem
        if net_pending < 0: net_pending = 0 
            
        st.markdown("---")
        st.subheader(f"💳 Financial Ledger Status (Sem {selected_sem})")
        col_L1, col_L2, col_L3, col_L4, col_L5 = st.columns(5)

        col_L1.metric("Total Debits (This Sem)", f"₹{total_debits_this_sem:,}")
        col_L2.metric("Main Payments (This Sem)", f"₹{total_paid_this_sem:,}")

        if net_pending > 0:
            col_L3.metric("Net Pending (This Sem)", f"₹{net_pending:,}", f"-₹{net_pending:,} Outstanding", delta_color="inverse")
        else:
            col_L3.metric("Net Pending (This Sem)", f"₹0", "Clearance Achieved", delta_color="normal")
            
        col_L4.metric("Record Book Paid", f"₹{record_book_total:,}", "Misc. Item", delta_color="off")
        col_L5.metric("Alumni Fee Paid", f"₹{alumni_fee_total:,}", "One-Time", delta_color="off")
        
        st.markdown("### 📝 Record Payment Transaction")
        inst_col1, inst_col2, inst_col3, inst_col4 = st.columns(4)
        
        fee_head_paid = inst_col1.selectbox(
            "Fee Head Component Paid", 
            ["Tuition_fee", "Hostel_fee", "College_Refundable_Deposit", "Hostel_Refundable_Deposit", "Travelling_Fee", "Gymkhana_Fee", "Practical_Record_Book", "Alumni_Fee"]
        )
        amt_to_pay = inst_col2.number_input("Amount Collected (Rs)", min_value=0, step=1, key="live_payment_value")
        pay_date = inst_col3.date_input("Date of Receipt", datetime.date.today())
        inst_num = inst_col4.selectbox("Installment Index Sequence", [1, 2, 3])
        payment_remarks = st.text_input("Remarks / Payment Details:", key="live_remarks").strip()
        
        if st.button("Post Payment Record", type="primary") and amt_to_pay > 0:
            new_trx = {
                "Student_ID": str(student_id).strip(),
                "Semester": str(selected_sem),  
                "Amount_Paid": int(amt_to_pay),
                "Date_Paid": str(pay_date),
                "Installment_Number": int(inst_num),
                "Fee_Head": fee_head_paid,
                "Remarks": payment_remarks if payment_remarks else "Paid",
                "Entry_By": st.session_state["username"] 
            }
            
            # Use the new ultra-safe append function
            success, message = append_new_installment(new_trx)
            if success:
                st.success(f"Successfully posted receipt of ₹{int(amt_to_pay):,} under {fee_head_paid} to the Cloud!")
                st.rerun()
            else:
                st.error(message)
        
        st.subheader("⚙️ Account Management")
        current_status = str(student_row['Status'])
        status_options = ["Active", "Alumni", "Dropped", "Active(Re-Admitted)"]
        if current_status not in status_options: status_options.append(current_status)

        if st.session_state.get("role") == "admin":
            new_status = st.selectbox("Update Student Status", status_options, index=status_options.index(current_status), key=f"status_select_{student_id}")
            if st.button("Save Status Change", key=f"status_btn_{student_id}"):
                students_df.loc[students_df['Student_ID'] == student_id, 'Status'] = new_status
                students_df.to_csv(STUDENT_FILE, index=False)
                st.success("Status updated!")
                st.rerun()
        else:
            st.text_input("Current Student Status", value=current_status, disabled=True, key=f"status_read_{student_id}")

        st.markdown("---")
        with st.expander("📜 Generate Full NOC / Complete Payment History", expanded=False):
            st.info(f"Showing all lifetime transactions for {student_row['Name']}.")
            if not student_payments_lifetime.empty:
                display_cols = [col for col in ["Date_Paid", "Semester", "Fee_Head", "Installment_Number", "Amount_Paid", "Entry_By", "Remarks"] if col in student_payments_lifetime.columns]
                st.dataframe(student_payments_lifetime[display_cols], use_container_width=True)
            
                grand_total = int(pd.to_numeric(student_payments_lifetime['Amount_Paid'], errors='coerce').fillna(0).sum())
                st.success(f"Total Lifetime Collection (All Heads): ₹{grand_total:,}")
            
                pdf_bytes = generate_noc_pdf(student_row, student_payments_lifetime, grand_total)
                st.download_button(
                    label="📥 Download Official NOC (PDF)",
                    data=pdf_bytes,
                    file_name=f"NOC_{student_row['Name'].replace(' ', '_')}_{student_id}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.warning("No payments on record.")

        if not student_payments_lifetime.empty:
            st.subheader("⚙️ Manage Recent Transactions (Delete/Void)")
            live_df_for_display = get_live_installments() 
            for idx in student_payments_lifetime.index:
                row = live_df_for_display.loc[idx]
                c_label, c_btn = st.columns([5, 1])
                c_label.write(f"🏷️ **Inst #{row['Installment_Number']}** (Sem {row.get('Semester', '1')}) | `{row['Fee_Head']}` | **₹{safe_int(row['Amount_Paid']):,}** | Date: `{row['Date_Paid']}`")
                
                if st.session_state.get("role") == "admin":
                    if c_btn.button("🗑️ Delete", key=f"del_{idx}"):
                        live_installments_for_delete = get_live_installments()
                        temp_installments = live_installments_for_delete.drop(idx).reset_index(drop=True)
                        success, message = save_installments(temp_installments)
                        if success:
                            st.rerun()
                        else:
                            st.error(message)
                else:
                    c_btn.markdown("<div style='margin-top: 10px; color: gray;'>🚫 Locked</div>", unsafe_allow_html=True)

with tab_reports:
    st.header("📊 Batch Outstanding Balance Report")
    rep_col1, rep_col2 = st.columns(2)
    target_year = rep_col1.selectbox("Select Admission Year", sorted(students_df['Admission_Year'].unique(), reverse=True), key="fee_year")
    target_course = rep_col2.selectbox("Select Course", ["B. Pharm", "M. Pharm"], key="fee_course")
    
    if st.button("Generate Batch Fee Report", type="primary"):
        with st.spinner("Calculating ledgers from Cloud Data..."):
            batch_students = students_df[(students_df['Admission_Year'] == target_year) & (students_df['Course'] == target_course) & (students_df['Status'] == "Active")]
            if batch_students.empty:
                st.warning("No active students found for this combination.")
            else:
                report_data = []
                all_logs = get_live_installments()
                all_logs["Student_ID"] = all_logs["Student_ID"].astype(str).str.strip()
                
                elapsed = 2026 - int(target_year)
                batch_sem = max(1, (elapsed * 2) + 1)
                max_s = 8 if target_course == "B. Pharm" else 4
                batch_sem = min(batch_sem, max_s)
                base_tuition = get_expected_fee(target_course, batch_sem, 'Tuition_fee', 'Default', target_year)
                
                for _, student in batch_students.iterrows():
                    sid = str(student["Student_ID"])
                    s_payments = all_logs[(all_logs["Student_ID"] == sid) & (all_logs["Semester"].astype(str) == str(batch_sem))]
                    is_tfws = (str(student.get("TFW_Status", "No")).strip().lower() == "yes")
                    student_tuition_due = 0 if is_tfws else base_tuition
                    
                    paid_tuition = pd.to_numeric(s_payments[s_payments["Fee_Head"].isin(["Tuition_fee", "Tuition_Fees_/_College_Fees"])]["Amount_Paid"], errors='coerce').sum()
                    paid_hostel = pd.to_numeric(s_payments[s_payments["Fee_Head"].isin(["Hostel_fee", "Hostel_Fees"])]["Amount_Paid"], errors='coerce').sum()
                    fee_payments_only = s_payments[~s_payments["Fee_Head"].isin(["Practical_Record_Book", "Alumni_Fee"])]
                    paid_total_fees = pd.to_numeric(fee_payments_only["Amount_Paid"], errors='coerce').sum()
                    
                    report_data.append({
                        "Student ID": sid,
                        "Name": student["Name"],
                        "TFWS Waiver": "Yes" if is_tfws else "No",
                        "Tuition Due (Adj)": student_tuition_due,
                        "Tuition Paid": paid_tuition,
                        "Tuition Pending": max(0, student_tuition_due - paid_tuition),
                        "Hostel Paid": paid_hostel,
                        "Total Fee Payments (This Sem)": paid_total_fees
                    })
                
                report_df = pd.DataFrame(report_data)
                st.success(f"Report generated! Assumed active semester: {batch_sem}")
                st.dataframe(report_df, use_container_width=True)
                st.download_button("📥 Download Fee Report as CSV", data=report_df.to_csv(index=False).encode('utf-8'), file_name=f"Pending_Fee_Report_{target_course}_{target_year}.csv", mime="text/csv")

    st.markdown("---")
    st.header("📘 Practical Record Book Payment Report")
    pr_col1, pr_col2 = st.columns(2)
    pr_target_year = pr_col1.selectbox("Select Admission Year (Journal)", sorted(students_df['Admission_Year'].unique(), reverse=True), key="pr_year")
    pr_target_course = pr_col2.selectbox("Select Course (Journal)", ["B. Pharm", "M. Pharm"], key="pr_course")
    
    if st.button("Generate Record Book Report", type="secondary"):
        with st.spinner("Checking journal payments from Cloud..."):
            pr_batch_students = students_df[(students_df['Admission_Year'] == pr_target_year) & (students_df['Course'] == pr_target_course) & (students_df['Status'] == "Active")]
            if pr_batch_students.empty:
                st.warning("No active students found for this combination.")
            else:
                pr_report_data = []
                all_logs = get_live_installments()
                all_logs["Student_ID"] = all_logs["Student_ID"].astype(str).str.strip()
                pr_logs = all_logs[all_logs["Fee_Head"] == "Practical_Record_Book"]
                
                for _, student in pr_batch_students.iterrows():
                    sid = str(student["Student_ID"])
                    total_pr_paid = pd.to_numeric(pr_logs[pr_logs["Student_ID"] == sid]["Amount_Paid"], errors='coerce').sum()
                    pr_report_data.append({
                        "Student ID": sid,
                        "Name": student["Name"],
                        "Amount Paid (Journal)": total_pr_paid,
                        "Status": "✅ Paid" if total_pr_paid > 0 else "❌ Pending"
                    })
                
                pr_report_df = pd.DataFrame(pr_report_data)
                st.dataframe(pr_report_df, use_container_width=True)
                st.download_button("📥 Download Record Book Report as CSV", data=pr_report_df.to_csv(index=False).encode('utf-8'), file_name=f"Record_Book_{pr_target_year}.csv", mime="text/csv")

    st.markdown("---")
    st.title("📊 Global Defaulters Analytics")
    report_course = st.selectbox("Select Course to Audit", ["B. Pharm", "M. Pharm", "All Courses"])

    if st.button("🔍 Generate Defaulters Report"):
        with st.spinner("Calculating lifetime ledgers via Cloud Database..."):
           report_data = []
        audit_students = master_df if report_course == "All Courses" else master_df[master_df['Course'] == report_course]
        
        current_year = 2026
        all_payments_df = get_live_installments()
        all_payments_df.columns = all_payments_df.columns.str.strip()
        all_payments_df['Student_ID'] = all_payments_df['Student_ID'].astype(str).str.strip()
        
        for index, student in audit_students.iterrows():
            s_id, s_name, s_course, s_quota, admission_year = str(student['Student_ID']).strip(), student['Name'], student['Course'], str(student.get('Quota', 'Govt_Quota')).strip(), int(student['Admission_Year'])
            admission_type = str(student.get('Admission_Type', 'Regular')).strip().upper()
            starting_sem = int(student.get('Starting_Semester', 1)) if pd.notnull(student.get('Starting_Semester')) else 1
            if admission_type == "D2D" and starting_sem == 1: starting_sem = 3
            
            current_sem = min(max(1, ((current_year - admission_year) * 2) + 1), 8 if s_course == "B. Pharm" else 4)
            s_payments = all_payments_df[all_payments_df['Student_ID'] == s_id]
            
            student_allotment = allotments_df[allotments_df['Student_ID'] == str(s_id)]
            default_transport = str(student_allotment.iloc[0].get('Transport_Allotted', 'None')).strip() if not student_allotment.empty else "None"
            default_hostel = str(student_allotment.iloc[0].get('Hostel_Allotted', 'None')).strip() if not student_allotment.empty else "None"
            if default_transport in ["nan", "", "NaN"]: default_transport = "None"
            if default_hostel in ["nan", "", "NaN"]: default_hostel = "None"
            
            lt_debits_tuition = lt_debits_travel = lt_debits_hostel = lt_debits_col_dep = lt_debits_hos_dep = 0
            
            for s in range(starting_sem, current_sem + 1):
                sem_str = str(s)
                calculated_tuition = 0
                if str(student.get("TFW_Status", "No")).strip().lower() != "yes":
                    if "m." in s_course.lower() and "pharm" in s_course.lower():
                        calculated_tuition = get_expected_fee(s_course, sem_str, 'Tuition_fee', 'Management_Quota' if "management" in s_quota.lower() else 'Govt_Quota', str(admission_year))
                    else:
                        calculated_tuition = get_expected_fee(s_course, sem_str, 'Tuition_fee', 'Default', str(admission_year))
                
                hist_override = overrides_df[(overrides_df['Student_ID'] == str(s_id)) & (overrides_df['Semester'] == sem_str)]
                hist_discount = safe_int(hist_override.iloc[0].get('Tuition_Discount')) if not hist_override.empty else 0
                lt_debits_tuition += max(0, calculated_tuition - hist_discount)

                travel_val = hist_override.iloc[0].get('Travel_Override') if not hist_override.empty else None
                if travel_val is not None and str(travel_val).strip() != "": lt_debits_travel += safe_int(travel_val)
                elif default_transport != "None": lt_debits_travel += get_expected_fee(s_course, sem_str, 'Travelling_Fee', default_transport, str(admission_year))

                hostel_val = hist_override.iloc[0].get('Hostel_Override') if not hist_override.empty else None
                if hostel_val is not None and str(hostel_val).strip() != "": lt_debits_hostel += safe_int(hostel_val)
                elif default_hostel != "None": lt_debits_hostel += get_expected_fee(s_course, sem_str, 'Hostel_fee', default_hostel, str(admission_year))

                if s == starting_sem:
                    lt_debits_col_dep += get_expected_fee(s_course, '1', 'College_Refundable_Deposit', 'Sem_1', str(admission_year))
                    if default_hostel in ["Hostel_AC", "Hostel_NonAC"]: lt_debits_hos_dep += get_expected_fee(s_course, '1', 'Hostel_Refundable_Deposit', 'Sem_1', str(admission_year))

                if not hist_override.empty: lt_debits_col_dep += safe_int(hist_override.iloc[0].get('College_Deposit_Manual'))
            if not s_payments.empty:
                def get_sum(heads): return int(pd.to_numeric(s_payments[s_payments["Fee_Head"].isin(heads)]['Amount_Paid'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0).sum())
                paid_tuition = get_sum(["Tuition_fee", "Tuition_Fees_/_College_Fees"])
                paid_travel = get_sum(["Travelling_Fee", "Travelling_Fees"])
                paid_hostel = get_sum(["Hostel_fee", "Hostel_Fees"])
                paid_col_dep = get_sum(["College_Refundable_Deposit", "College_Deposit(Refundable)"])
                paid_hos_dep = get_sum(["Hostel_Refundable_Deposit", "Hostel_Deposit(Refundable)"])
            else:
                paid_tuition = paid_travel = paid_hostel = paid_col_dep = paid_hos_dep = 0
            
            tuition_pending = max(0, lt_debits_tuition - paid_tuition)
            travel_pending = max(0, lt_debits_travel - paid_travel)
            hostel_pending = max(0, lt_debits_hostel - paid_hostel)
            col_dep_pending = max(0, lt_debits_col_dep - paid_col_dep)
            hos_dep_pending = max(0, lt_debits_hos_dep - paid_hos_dep)
            
            lifetime_pending = tuition_pending + travel_pending + hostel_pending + col_dep_pending + hos_dep_pending
                
            if lifetime_pending > 0:
                report_data.append({
                    "Student ID": s_id, "Name": s_name, "Course": s_course, "Current Sem": current_sem,
                    "Lifetime Debits": f"₹{lt_debits_tuition + lt_debits_travel + lt_debits_hostel + lt_debits_col_dep + lt_debits_hos_dep:,}",
                    "Lifetime Paid": f"₹{paid_tuition + paid_travel + paid_hostel + paid_col_dep + paid_hos_dep:,}",
                    "Tuition Pending": f"₹{tuition_pending:,}", "Travel Pending": f"₹{travel_pending:,}",
                    "Hostel Pending": f"₹{hostel_pending:,}", "Col. Dep. Pending": f"₹{col_dep_pending:,}",
                    "Hos. Dep. Pending": f"₹{hos_dep_pending:,}", "Total Pending": f"₹{lifetime_pending:,}"
                })

        if report_data:
            report_df = pd.DataFrame(report_data)
            st.error(f"⚠️ Found {len(report_df)} students with pending balances in {report_course}.")
            st.dataframe(report_df, use_container_width=True)
        else:
            st.success(f"✅ All students in {report_course} are fully cleared!")