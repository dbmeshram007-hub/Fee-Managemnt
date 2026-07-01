import streamlit as st
import pandas as pd
import datetime

st.set_page_config(page_title="Pioneer Pharmacy Fee Dashboard", layout="wide")
st.title("🎓 Fee Reconciliation & Management System")

# --- 1. Load Data Sources ---
@st.cache_data
def load_base_data():
    students = pd.read_csv("Student_Master.csv")
    constants = pd.read_csv("Fee_Constants.csv")
    
    # Aggressive cleaning for headers to prevent KeyErrors
    students.columns = [str(c).strip().replace(" ", "_").replace("\r", "").replace("\n", "") for c in students.columns]
    constants.columns = [str(c).strip().replace(" ", "_").replace("\r", "").replace("\n", "") for c in constants.columns]
    
    students["Student_ID"] = students["Student_ID"].astype(str).str.strip()
    
    # Ensure TFWS column exists to prevent crashes if it hasn't been added to CSV yet
    if "TFWS" not in students.columns:
        students["TFWS"] = "No"
        
    return students, constants

try:
    students_df, constants_df = load_base_data()
except Exception as e:
    st.error(f"Missing required CSV files in this directory: {e}")
    st.stop()

# Handle live session state for installments log
if "installments" not in st.session_state:
    try:
        st.session_state.installments = pd.read_csv("Installment_Log.csv")
        st.session_state.installments.columns = [str(c).strip().replace(" ", "_") for c in st.session_state.installments.columns]
        st.session_state.installments["Student_ID"] = st.session_state.installments["Student_ID"].astype(str).str.strip()
    except:
        st.session_state.installments = pd.DataFrame(columns=["Student_ID", "Amount_Paid", "Date_Paid", "Installment_Number", "Fee_Head", "Remarks"])

for col in ["Fee_Head", "Remarks"]:
    if col not in st.session_state.installments.columns:
        st.session_state.installments[col] = "General"

# Create Top-Level Tabs
tab_ops, tab_reports = st.tabs(["💼 Daily Transactions & Profiles", "📊 Batch & Year Reports"])

with tab_ops:
    # --- 2. Sidebar Navigation & Global Search ---
    st.sidebar.header("🔍 Student Search Engine")
    course_filter = st.sidebar.selectbox("Filter Course", ["All", "B. Pharm", "M. Pharm"])
    
    filtered_students = students_df.copy()
    if course_filter != "All":
        filtered_students = filtered_students[filtered_students["Course"] == course_filter]

    search_query = st.sidebar.text_input("Type Name or Student ID:").strip()

    if search_query:
        filtered_students = filtered_students[
            filtered_students["Name"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_students["Student_ID"].astype(str).str.contains(search_query, case=False, na=False)
        ]

    if not filtered_students.empty:
        student_dict = dict(zip(
            filtered_students["Student_ID"].astype(str) + " - " + filtered_students["Name"], 
            filtered_students["Student_ID"].astype(str)
        ))
        selected_student_str = st.sidebar.selectbox(f"Matching Results ({len(filtered_students)})", list(student_dict.keys()))
        student_id = str(student_dict[selected_student_str]).strip()
    else:
        st.sidebar.warning("No matches found.")
        selected_student_str = None

    # --- 3. Processing Core Calculations ---
    if selected_student_str:
        student_row = students_df[students_df["Student_ID"] == student_id].iloc[0]
        
        st.header(f"👤 Account Profile: {student_row['Name']}")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Student ID", str(student_row["Student_ID"]))
        col2.metric("Course", student_row["Course"])
        col3.metric("Admission Year", int(student_row["Admission_Year"]))
        
        current_year = 2026
        elapsed_years = current_year - int(student_row["Admission_Year"])
        calculated_sem = max(1, (elapsed_years * 2) + 1)
        max_sem = 8 if student_row["Course"] == "B. Pharm" else 4
        calculated_sem = min(calculated_sem, max_sem)
        
        selected_sem = col4.number_input("Target Semester Look-up", min_value=1, max_value=max_sem, value=calculated_sem, step=1)

        st.markdown("---")
        
        st.subheader("⚙️ Fee Variable Configurations")
        c1, c2, c3 = st.columns(3)
        hostel_selection = c1.selectbox("Hostel Status", ["None", "Hostel_AC", "Hostel_NonAC"])
        travel_selection = c2.selectbox("Travelling Route Category", ["None", "Travel_City", "Travel_Outside"])
        
        # Determine default TFWS status from the master CSV
        default_tfws = "Yes" if str(student_row.get("TFWS", "No")).strip().lower() == "yes" else "No"
        tfws_selection = c3.selectbox("Tuition Fee Waiver (TFWS)", ["No", "Yes"], index=0 if default_tfws == "No" else 1)

        sem_rules = constants_df[(constants_df["Course"] == student_row["Course"]) & (constants_df["Semester"] == selected_sem)]
        
        def get_fee(fee_head, condition="Default"):
            if sem_rules.empty:
                return 0
            target_head = str(fee_head).strip().lower().replace("_", "").replace(" ", "")
            target_cond = str(condition).strip().lower().replace("_", "").replace(" ", "")
            
            for _, row in sem_rules.iterrows():
                row_head = str(row["Fee_Head"]).strip().lower().replace("_", "").replace(" ", "")
                row_cond = str(row["Category_Condition"]).strip().lower().replace("_", "").replace(" ", "")
                if (row_head == target_head or (target_head == "tuitionfee" and row_head == "tutionfee")) and (row_cond == target_cond):
                    try:
                        return int(row["Amount_Due"])
                    except KeyError:
                        return int(row.iloc[-1])
            return 0

        # Apply TFWS Logic
        if tfws_selection == "Yes":
            tuition_due = 0
            st.info("ℹ️ TFWS Scheme Active: Base Tuition Fee waived for this semester.")
        else:
            tuition_due = int(get_fee("Tuition_fee", "Default"))
            
        college_deposit = int(get_fee("College_Refundable_Deposit", "Default") if selected_sem in [1, 2] else 0)
        
        if hostel_selection == "None":
            hostel_due = 0
            hostel_deposit = 0
        else:
            hostel_due = int(get_fee("Hostel_fee", hostel_selection))
            hostel_deposit = int(get_fee("Hostel_Refundable_Deposit", "Sem_1") if selected_sem in [1, 2] else 0)

        default_travel = int(get_fee("Travelling_Fee", travel_selection))
        
        st.markdown("### 💸 Debit Modifiers")
        manual_travel = st.number_input("Travelling Fee (Override)", value=default_travel, step=1)
        manual_gymkhana = st.number_input("Gymkhana Fee (Manual Entry Only)", value=0, step=1)

        total_debit = int(tuition_due + hostel_due + college_deposit + hostel_deposit + manual_travel + manual_gymkhana)

        # --- 4. Payment Tracking ---
        st.markdown("---")
        st.subheader("💳 Financial Ledger Status")
        
        inst_df = st.session_state.installments.copy()
        inst_df["Student_ID"] = inst_df["Student_ID"].astype(str).str.strip()
        student_payments = inst_df[inst_df["Student_ID"] == student_id]
        
        tuition_related_payments = student_payments[student_payments["Fee_Head"] != "Practical_Record_Book"]
        total_paid = int(pd.to_numeric(tuition_related_payments["Amount_Paid"], errors='coerce').fillna(0).sum())
        
        pending_balance = int(total_debit - total_paid)
        record_book_paid = int(pd.to_numeric(student_payments[student_payments["Fee_Head"] == "Practical_Record_Book"]["Amount_Paid"], errors='coerce').fillna(0).sum())

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Total Debits Calculated", f"₹ {total_debit:,}")
        b2.metric("Payments Received (Fees)", f"₹ {total_paid:,}")
        b3.metric("Net Pending Balance", f"₹ {pending_balance:,}", delta_color="inverse", delta=f"₹ {pending_balance:,} Outstanding")
        b4.metric("Record Book Paid", f"₹ {record_book_paid:,}", delta="Misc. Item")

        # --- 5. Installment Entry Engine ---
        st.markdown("### 📝 Record Payment Transaction")
        
        inst_col1, inst_col2, inst_col3, inst_col4 = st.columns(4)
        fee_head_paid = inst_col1.selectbox(
            "Fee Head Component Paid", 
            ["Tuition_fee", "Hostel_fee", "College_Refundable_Deposit", "Hostel_Refundable_Deposit", "Travelling_Fee", "Gymkhana_Fee", "Practical_Record_Book"]
        )
        amt_to_pay = inst_col2.number_input("Amount Collected (Rs)", min_value=0, step=1, key="live_payment_value")
        pay_date = inst_col3.date_input("Date of Receipt", datetime.date.today())
        inst_num = inst_col4.selectbox("Installment Index Sequence", [1, 2, 3])
        payment_remarks = st.text_input("Remarks / Payment Details:", key="live_remarks").strip()
        
        submit_payment = st.button("Post Payment Record", type="primary")
        
        if submit_payment and amt_to_pay > 0:
            new_trx = pd.DataFrame([{
                "Student_ID": str(student_id).strip(),
                "Amount_Paid": int(amt_to_pay),
                "Date_Paid": str(pay_date),
                "Installment_Number": int(inst_num),
                "Fee_Head": fee_head_paid,
                "Remarks": payment_remarks if payment_remarks else "Paid"
            }])
            
            st.session_state.installments = pd.concat([st.session_state.installments, new_trx], ignore_index=True)
            st.session_state.installments["Student_ID"] = st.session_state.installments["Student_ID"].astype(str).str.strip()
            st.session_state.installments.to_csv("Installment_Log.csv", index=False)
            st.success(f"Successfully posted receipt of ₹{int(amt_to_pay):,} under {fee_head_paid}!")
            st.rerun()

        # --- NOC Generation Tool ---
        st.markdown("---")
        with st.expander("📜 Generate Full NOC / Complete Payment History", expanded=False):
            st.info(f"Showing all lifetime transactions for {student_row['Name']} to verify No-Objection Certificate (NOC) clearance.")
            if not student_payments.empty:
                st.dataframe(student_payments[["Date_Paid", "Fee_Head", "Installment_Number", "Amount_Paid", "Remarks"]], use_container_width=True)
                grand_total = int(pd.to_numeric(student_payments["Amount_Paid"], errors='coerce').fillna(0).sum())
                st.success(f"Total Lifetime Collection (All Heads): ₹{grand_total:,}")
            else:
                st.warning("No payments on record.")

        if not student_payments.empty:
            st.subheader("⚙️ Manage Recent Transactions (Delete/Void)")
            for idx in student_payments.index:
                row = st.session_state.installments.loc[idx]
                c_label, c_btn = st.columns([5, 1])
                c_label.write(f"🏷️ **Inst #{row['Installment_Number']}** | `{row['Fee_Head']}` | **₹{int(row['Amount_Paid']):,}** | Date: `{row['Date_Paid']}`")
                
                if c_btn.button("🗑️ Delete", key=f"del_{idx}"):
                    st.session_state.installments = st.session_state.installments.drop(idx).reset_index(drop=True)
                    st.session_state.installments.to_csv("Installment_Log.csv", index=False)
                    st.rerun()

# --- Batch Reporting Tab ---
with tab_reports:
    st.header("📊 Batch Outstanding Balance Report")
    st.write("Generate a list of students with pending balances for a specific admission year.")
    
    rep_col1, rep_col2 = st.columns(2)
    target_year = rep_col1.selectbox("Select Admission Year (Fee Report)", sorted(students_df['Admission_Year'].unique(), reverse=True), key="fee_year")
    target_course = rep_col2.selectbox("Select Course (Fee Report)", ["B. Pharm", "M. Pharm"], key="fee_course")
    
    if st.button("Generate Batch Fee Report", type="primary"):
        with st.spinner("Calculating ledgers for the entire batch..."):
            batch_students = students_df[(students_df['Admission_Year'] == target_year) & (students_df['Course'] == target_course)]
            
            if batch_students.empty:
                st.warning("No students found for this combination.")
            else:
                report_data = []
                all_logs = st.session_state.installments.copy()
                all_logs["Student_ID"] = all_logs["Student_ID"].astype(str).str.strip()
                
                elapsed = 2026 - int(target_year)
                batch_sem = max(1, (elapsed * 2) + 1)
                max_s = 8 if target_course == "B. Pharm" else 4
                batch_sem = min(batch_sem, max_s)
                
                sem_rules = constants_df[(constants_df["Course"] == target_course) & (constants_df["Semester"] == batch_sem)]
                
                def get_base_fee(fee_head):
                    target_head = str(fee_head).strip().lower().replace("_", "").replace(" ", "")
                    for _, row in sem_rules.iterrows():
                        row_head = str(row["Fee_Head"]).strip().lower().replace("_", "").replace(" ", "")
                        row_cond = str(row["Category_Condition"]).strip().lower().replace("_", "").replace(" ", "")
                        if row_head == target_head and row_cond == "default":
                            try:
                                return int(row["Amount_Due"])
                            except KeyError:
                                return int(row.iloc[-1])
                    return 0
                
                base_tuition = get_base_fee("Tuition_fee")
                
                for _, student in batch_students.iterrows():
                    sid = str(student["Student_ID"])
                    s_payments = all_logs[all_logs["Student_ID"] == sid]
                    
                    # Check TFWS status for this specific student
                    is_tfws = str(student.get("TFWS", "No")).strip().lower() == "yes"
                    student_tuition_due = 0 if is_tfws else base_tuition
                    
                    paid_tuition = pd.to_numeric(s_payments[s_payments["Fee_Head"] == "Tuition_fee"]["Amount_Paid"], errors='coerce').sum()
                    paid_hostel = pd.to_numeric(s_payments[s_payments["Fee_Head"] == "Hostel_fee"]["Amount_Paid"], errors='coerce').sum()
                    
                    fee_payments_only = s_payments[s_payments["Fee_Head"] != "Practical_Record_Book"]
                    paid_total_fees = pd.to_numeric(fee_payments_only["Amount_Paid"], errors='coerce').sum()
                    
                    # Pending is based on their specific TFWS status
                    pending_tuition = max(0, student_tuition_due - paid_tuition)
                    
                    report_data.append({
                        "Student ID": sid,
                        "Name": student["Name"],
                        "TFWS Waiver": "Yes" if is_tfws else "No",
                        "Tuition Due (Adj)": student_tuition_due,
                        "Tuition Paid": paid_tuition,
                        "Tuition Pending": pending_tuition,
                        "Hostel Paid": paid_hostel,
                        "Total Fee Payments": paid_total_fees
                    })
                
                report_df = pd.DataFrame(report_data)
                
                st.success(f"Report generated for {len(report_df)} students in {target_course} ({target_year}). Assumed active semester: {batch_sem}")
                st.dataframe(report_df, use_container_width=True)
                
                st.download_button(
                    label="📥 Download Fee Report as CSV",
                    data=report_df.to_csv(index=False).encode('utf-8'),
                    file_name=f"Pending_Fee_Report_{target_course}_{target_year}.csv",
                    mime="text/csv"
                )

    # --- Practical Record Book Report ---
    st.markdown("---")
    st.header("📘 Practical Record Book Payment Report")
    st.write("Generate a specific list of students to check who has paid for the Practical Journal/Record Book.")
    
    pr_col1, pr_col2 = st.columns(2)
    pr_target_year = pr_col1.selectbox("Select Admission Year (Journal)", sorted(students_df['Admission_Year'].unique(), reverse=True), key="pr_year")
    pr_target_course = pr_col2.selectbox("Select Course (Journal)", ["B. Pharm", "M. Pharm"], key="pr_course")
    
    if st.button("Generate Record Book Report", type="secondary"):
        with st.spinner("Checking journal payments..."):
            pr_batch_students = students_df[(students_df['Admission_Year'] == pr_target_year) & (students_df['Course'] == pr_target_course)]
            
            if pr_batch_students.empty:
                st.warning("No students found for this combination.")
            else:
                pr_report_data = []
                all_logs = st.session_state.installments.copy()
                all_logs["Student_ID"] = all_logs["Student_ID"].astype(str).str.strip()
                
                pr_logs = all_logs[all_logs["Fee_Head"] == "Practical_Record_Book"]
                
                for _, student in pr_batch_students.iterrows():
                    sid = str(student["Student_ID"])
                    s_pr_payments = pr_logs[pr_logs["Student_ID"] == sid]
                    
                    total_pr_paid = pd.to_numeric(s_pr_payments["Amount_Paid"], errors='coerce').sum()
                    
                    pr_report_data.append({
                        "Student ID": sid,
                        "Name": student["Name"],
                        "Amount Paid (Journal)": total_pr_paid,
                        "Status": "✅ Paid" if total_pr_paid > 0 else "❌ Pending"
                    })
                
                pr_report_df = pd.DataFrame(pr_report_data)
                
                st.success(f"Journal Payment Report generated for {len(pr_report_df)} students.")
                st.dataframe(pr_report_df, use_container_width=True)
                
                st.download_button(
                    label="📥 Download Record Book Report as CSV",
                    data=pr_report_df.to_csv(index=False).encode('utf-8'),
                    file_name=f"Record_Book_Report_{pr_target_course}_{pr_target_year}.csv",
                    mime="text/csv",
                    key="pr_download"
                )