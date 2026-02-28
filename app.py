import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import datetime 
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# Safety import for num2words
try:
    from num2words import num2words
except ImportError:
    st.error("Please add 'num2words' to your requirements.txt file on GitHub.")

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "atharvaujoshi@gmail.com"
SENDER_NAME = "Tarangan Cost Sheet" 
APP_PASSWORD = "nybl zsnx zvdw edqr"
RECEIVER_EMAIL = "spydarr1106@gmail.com"

# --- HELPER FUNCTIONS ---
def clean_numeric(value):
    if pd.isna(value): return 0.0
    clean_val = re.sub(r'[^\d.]', '', str(value))
    return float(clean_val) if clean_val else 0.0

def format_indian_currency(number):
    s = str(int(number))
    if len(s) <= 3: return s
    last_three = s[-3:]
    remaining = s[:-3]
    remaining = re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', remaining)
    return remaining + ',' + last_three

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_final_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_final_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    REGISTRATION = 30000 
    sd_amt = round(final_agreement * sd_pct, -2)
    gst_amt = final_agreement * gst_pct
    total_package = final_agreement + sd_amt + gst_amt + REGISTRATION
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100, "Registration": REGISTRATION,
        "Total": int(total_package), "Combined_Discount": int(pkg_discount + park_discount)
    }

def send_email(recipient_email, pdf_data, filename, details):
    try:
        msg = MIMEMultipart()
        msg['From'] = formataddr((SENDER_NAME, SENDER_EMAIL))
        msg['To'] = recipient_email
        msg['Subject'] = f"Tarangan Booking: {details['Unit No']} - {details['Customer Name']}"
        body = f"Please find the attached cost sheet for {details['Customer Name']}."
        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={filename}")
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except: return False

# --- SHARED STORAGE ---
@st.cache_resource
def get_global_storage():
    return {
        "sold_units": set(), "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {}, 
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"}, 
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "waiting_customers": [], "opted_out": [], "visited_customers": set()
    }

storage = get_global_storage()

def reset_cabin_session(cabin):
    storage["booths"][cabin] = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    if cabin in storage["pending_requests"]: del storage["pending_requests"][cabin]

# --- DATA ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL); df.columns = [str(c).strip() for c in df.columns]; return df

def create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking):
    pdf = FPDF()
    for copy_label in ["Customer's Copy", "Sales Copy"]:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "TARANGAN COST SHEET", ln=True, align='C')
        pdf.set_font("Arial", '', 10); pdf.cell(190, 10, f"Date: {date_str} | {copy_label}", ln=True, align='R')
        pdf.cell(190, 10, f"Customer Name: {cust_name}", ln=True)
        pdf.cell(190, 10, f"Unit No: {unit_id} | Floor: {floor} | Carpet: {carpet} sqft", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 11); pdf.cell(95, 10, "Description", border=1); pdf.cell(95, 10, "Amount (Rs.)", border=1, ln=True)
        pdf.set_font("Arial", '', 11)
        rows = [["Agreement Value", format_indian_currency(costs['Final Agreement'])], [f"Stamp Duty ({int(costs['SD_Pct'])}%)", format_indian_currency(costs['Stamp Duty'])], [f"GST ({int(costs['GST_Pct'])}%)", format_indian_currency(costs['GST'])], ["Registration", "30,000"]]
        for r in rows: pdf.cell(95, 10, r[0], border=1); pdf.cell(95, 10, r[1], border=1, ln=True)
        pdf.set_font("Arial", 'B', 13); pdf.cell(95, 12, "ALL INCLUSIVE TOTAL", border=1, align='C'); pdf.cell(95, 12, format_indian_currency(costs['Total']), border=1, ln=True, align='C')
        
        try:
            words = num2words(costs['Total'], lang='en_IN').title().replace(",", "")
            pdf.set_font("Arial", 'B', 9); pdf.ln(2); pdf.multi_cell(190, 8, f"Amount in words: Rupees {words} Only")
        except: pass
        
        pdf.ln(2); pdf.set_font("Arial", 'B', 8); pdf.cell(0, 5, "TERMS & CONDITIONS:", ln=True); pdf.set_font("Arial", '', 6.0)
        tc_lines = [
            "1. Advocate charges will be Rs. 15,000/-.",
            "2. Agreement to be executed & registered within 15 days from the date of booking.",
            "3. The total cost mentioned here is all inclusive of GST, Registration, Stamp Duty and Legal charges",
            "4. GST, Stamp Duty, Registration and all applicable government charges are as per the current rates, and in future may change as per government notification which would be borne by the customer.",
            "5. Above areas are shown in square feet only to make it easy for the purchaser to understand. The sale of the said unit is on the basis of RERA carpet area only.",
            "6. All legal documents will be executed in square meter only.",
            "7. Subject to PCMC jurisdiction.",
            "8. Society Maintenance at Rs. 3 per sq.ft. per month for 2 years and will be taken at the time of possession.",
            "9. Loan facility available from all leading banks and home loan sanctioning is customers responsibility, developer however will assist in the process.",
            "10. The promoters reserve the right to change the above prices and the offer given at any time without prior notice. No verbal commitments to be accepted post booking.",
            "11. Booking is non-transferable.",
            "12. The information on this paper is provided in good faith and does not constitute part of the contract.",
            "13. Government taxes will be applicable at actual. Also, any other taxes not mentioned herein if levied later would be payable at actuals by the purchaser.",
            "14. Documents required: PAN Card, Adhar Card, Photocopy.",
            "15. If an external bank is opted for loan processing, an additional charge of Rs. 25,000/- shall be applicable and payable by the purchaser."
        ]
        for line in tc_lines: pdf.multi_cell(0, 3.2, line)
        
        page_height, footer_y = pdf.h, pdf.h - 18 - 32
        pdf.set_y(footer_y)
        try:
            pdf.image("mahalaxmi_logo.png", x=10, y=footer_y, h=15); pdf.image("bw_logo.png", x=35, y=footer_y, h=15)
        except:
            pdf.set_font("Arial", 'I', 7); pdf.set_xy(10, footer_y); pdf.cell(60, 10, "[Logos Here]", ln=0)
        pdf.set_xy(0, footer_y + 5); pdf.set_font("Arial", 'B', 12); pdf.cell(210, 10, "Contact: 080 6452 3034", align='C')
        pdf.set_xy(150, footer_y); pdf.cell(45, 18, "", border=1)
        pdf.set_xy(150, footer_y + 19); pdf.set_font("Arial", '', 7); pdf.cell(45, 5, "Customer Signature", align='C')

    return pdf.output(dest='S').encode('latin-1')

# --- APP START ---
st.set_page_config(page_title="Tarangan Dash", layout="wide")

    # --- 6. LOGIN SYSTEM ---
if 'authenticated' not in st.session_state: 
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        # CHECK THIS LINE FOR CLOSING BRACKETS )
        creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
        
        if u in creds and p == creds[u]:
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, u, u
            st.rerun()
        else: 
            st.error("Invalid credentials.")

# This "else" belongs to "if not st.session_state.authenticated"
else:
    if st.sidebar.button("Logout"): 
        st.session_state.authenticated = False
        st.rerun()

    # --- GRE DASHBOARD ---
    elif st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        if st.sidebar.button("🔄 Global Refresh"): st.rerun()
        
        # 1. Load data and clean column names
        df_master = load_data()
        df_master.columns = df_master.columns.str.strip() # Removes hidden spaces
        
        # 2. Safety Check for Active Customers
        names_in_waiting = [str(c).upper() for c in storage.get("waiting_customers", [])]
        names_in_cabins = [str(v).upper() for v in storage.get("booths", {}).values() if v is not None]
        all_active_names = names_in_waiting + names_in_cabins

        col_left, col_right = st.columns(2)

        # --- LEFT SIDE: DATABASE LIST ---
        with col_left:
            st.subheader("📋 Database List")
            
            # Change "Customer Name" below to match your Excel/Sheet header exactly
            target_column = "Customer Allotted" 
            
            if target_column in df_master.columns:
                # Get unique names, drop empty rows
                db_list = df_master[target_column].dropna().unique().tolist()
                
                # Filter out people already in the list
                filtered_db = [cust for cust in db_list if str(cust).upper() not in all_active_names]
                
                selected_cust = st.selectbox("Search & Select Customer:", ["-- Select --"] + sorted(filtered_db))
                
                if st.button("Add Selected"):
                    if selected_cust != "-- Select --":
                        storage["waiting_customers"].append(selected_cust)
                        st.success(f"Added {selected_cust}")
                        st.rerun()
            else:
                # This helps you debug!
                st.error(f"Column '{target_column}' not found.")
                st.info(f"Available columns in your sheet are: {', '.join(df_master.columns)}")

        # --- RIGHT SIDE: WALK-IN ---
        with col_right:
            st.subheader("🚶 Walk-in")
            with st.form("walkin_form", clear_on_submit=True):
                new_name = st.text_input("Enter Name").strip()
                if st.form_submit_button("Add Walk-in"):
                    if new_name:
                        if new_name.upper() in all_active_names:
                            st.warning("Customer already in system!")
                        else:
                            storage["waiting_customers"].append(new_name)
                            st.success(f"Added {new_name}")
                            st.rerun()

        st.divider()
        st.subheader("📊 Live Waiting List")
        if storage.get("waiting_customers"):
            for i, cust in enumerate(storage["waiting_customers"]):
                c1, c2 = st.columns([5, 1])
                c1.write(f"{i+1}. **{cust}**")
                if c2.button("🗑️", key=f"rm_{i}"):
                    storage["waiting_customers"].remove(cust)
                    st.rerun()
                    
    # --- MANAGER DASHBOARD ---
    elif st.session_state.role == "Manager":
        st.title("👔 Manager Assignment")
        if st.sidebar.button("🔄 Global Refresh"): st.rerun()
        col1, col2 = st.columns([1, 1.2])
        
        with col1:
            st.subheader("Assign Cabin")
            if storage["waiting_customers"]:
                sel_c = st.selectbox("Select Customer:", storage["waiting_customers"])
                # Only show free booths
                b_avail = [k for k, v in storage["booths"].items() if v is None]
                if b_avail:
                    sel_b = st.selectbox("Assign to Cabin:", b_avail)
                    if st.button("Confirm Assignment"):
                        storage["booths"][sel_b] = sel_c
                        storage["waiting_customers"].remove(sel_c)
                        st.success(f"Assigned {sel_c} to Cabin {sel_b}")
                        st.rerun()
                else:
                    st.warning("All cabins are currently occupied.")
            else:
                st.info("No customers in waiting list.")

        with col2:
            st.subheader("Cabin Status & Controls")
            # Create a table-like view with action buttons
            for b, c in storage["booths"].items():
                if c:
                    with st.container():
                        st.markdown(f"**Cabin {b}:** `{c}`")
                        c1, c2 = st.columns(2)
                        # Option 1: Reassign (Send back to waiting list)
                        if c1.button(f"🔄 Reassign {b}", key=f"re_{b}", help="Moves customer back to waiting list"):
                            storage["waiting_customers"].append(c)
                            storage["booths"][b] = None
                            st.rerun()
                        # Option 2: Delete (Remove completely)
                        if c2.button(f"🗑️ Delete {b}", key=f"del_{b}", help="Removes customer from system"):
                            storage["booths"][b] = None
                            st.rerun()
                        st.markdown("---")
                else:
                    st.write(f"**Cabin {b}:** 🟢 Free")
                    
    # --- SALES DASHBOARD ---
    # --- SALES DASHBOARD ---
    elif st.session_state.role == "Sales":
        # 1. Initialize variables
        if "search_id_input" not in st.session_state:
            st.session_state.search_id_input = ""
        
        search_id = st.session_state.search_id_input.upper()
        my_cabin = st.selectbox("Select Your Cabin:", list("ABCDEFGHIJ"), key="sales_cabin_sel")
        cust_name = storage["booths"].get(my_cabin)
        ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        
        st.title("🏙️ Stage 3: Sales Portal")
        if st.sidebar.button("🔄 Global Refresh"): st.rerun()

        if not cust_name:
            st.warning(f"Cabin {my_cabin} is currently empty. Please wait for Manager assignment.")
        else:
            # 2. Status Header & Token Lookup
            inventory = load_data()
            assigned_unit_from_sheet = ""
            token_no = "N/A"
            
            if 'Customer Allotted' in inventory.columns:
                match = inventory[inventory['Customer Allotted'].astype(str).str.upper() == str(cust_name).upper()]
                if not match.empty:
                    assigned_unit_from_sheet = str(match.iloc[0].get('ID', '')).upper()
                    token_no = match.iloc[0].get('Token Number', 'N/A')

            st.success(f"👤 Serving: **{cust_name}** | 🎟️ Token: **{token_no}**")

            # --- 3. THE MISSING: REQUEST UNBLOCK UI ---
            st.write("---")
            st.subheader("🔑 Request Inventory Unblock")
            chances_used = storage.get("unblock_counts", {}).get(my_cabin, 0)
            
            if chances_used < 2:
                c_req, c_send = st.columns([3, 1])
                req_unit = c_req.text_input("Enter Unit ID (e.g., 1503):", key="manual_req").strip().upper()
                if c_send.button("Send Request", use_container_width=True):
                    if req_unit:
                        storage.setdefault("pending_requests", {})[my_cabin] = req_unit
                        st.toast(f"Request for {req_unit} sent to Admin!")
                    else:
                        st.error("Please enter an ID.")
            else:
                st.error("🚫 Maximum (2) unblock requests used for this customer.")

            st.write("---")

            # --- 4. INVENTORY GRID WITH REFUGE LOGIC ---
            st.subheader("🏢 Unit Inventory")
            with st.expander("📁 View Inventory Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row_data in inventory.iterrows():
                    uid = str(row_data['ID']).upper().strip()
                    
                    # REFUGE LOGIC
                    if uid in ["705", "1205"]:
                        btn_label = "🏥 REFUGE"
                        is_disabled = True
                    else:
                        approved_list = storage.get("approved_units", {}).get(my_cabin, [])
                        is_unlocked = (uid == assigned_unit_from_sheet) or (uid in approved_list) or (uid == search_id)
                        is_sold = uid in storage.get("sold_units", set())
                        
                        if is_sold and uid != search_id:
                            btn_label, is_disabled = "⛔ SOLD", True
                        elif is_unlocked:
                            prefix = "🟢" if uid == assigned_unit_from_sheet else "🟡"
                            btn_label, is_disabled = f"{prefix} {uid}", False
                        else:
                            btn_label, is_disabled = f"🔒 {uid}", True
                    
                    if grid_cols[idx % 6].button(btn_label, key=f"btn_{uid}", disabled=is_disabled, use_container_width=True):
                        st.session_state.search_id_input = uid
                        st.rerun()
            # 5. THE COST SHEET (Triggered after selection)
            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    
                    # Negotiation Inputs
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        use_d = st.checkbox("Discount")
                        d_val = st.number_input("Discount:", value=0, step=1000)
                    with c2: 
                        use_p = st.checkbox("Include Parking")
                        p_val = st.number_input("Park Disc:", value=0) if use_p else 0
                    with c3: is_f = st.checkbox("Female Registry")

                    # Calculate Costs
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), d_val, p_val, use_p, is_f)
                    park_loc_label = "Parking Under Building" if use_p else "1 Car Parking"

                    # DISPLAY COST SHEET
                    st.markdown(f"""
                        <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                            <div style="text-align:right;">Date: {ist_now.strftime("%d/%m/%Y")}</div>
                            <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN</h2>
                            <p><b>Customer:</b> {cust_name}</p>
                            <p><b>Unit:</b> {search_id} | <b>Floor:</b> {row.get('Floor','N/A')} | <b>Carpet:</b> {row.get('CARPET','N/A')} sqft</p>
                            <p><b>Parking Status:</b> {park_loc_label}</p>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Agreement</span><span>Rs. {format_indian_currency(res['Final Agreement'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Stamp Duty ({int(res['SD_Pct'])}%)</span><span>Rs. {format_indian_currency(res['Stamp Duty'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>GST ({int(res['GST_Pct'])}%)</span><span>Rs. {format_indian_currency(res['GST'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Registration</span><span>Rs. {format_indian_currency(res['Registration'])}</span></div>
                            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                            <div style="font-style:italic; margin-top:5px;">Rupees {num2words(res['Total'], lang='en_IN').title().replace(",","")} Only</div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Action Buttons
                    col_act1, col_act2 = st.columns(2)
                    with col_act1:
                        if st.button("✅ Finalize & Book"):
                            # Save to history and mark as sold
                            storage["sold_units"].add(search_id)
                            storage["download_history"].append({
                                "Unit No": search_id, "Customer": cust_name, "Total Package": res['Total'], "Sales Person": st.session_state.role
                            })
                            st.success("Unit Booked!")
                            st.session_state.search_id_input = ""
                            st.rerun()
                    with col_act2:
                        if st.button("❌ Close / Release"):
                            st.session_state.search_id_input = ""
                            st.rerun()

    # --- ADMIN DASHBOARD ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master Control")
        if st.sidebar.button("🔄 Global Refresh"): st.rerun()
        
        t1, t2, t3, t4 = st.tabs(["📊 Sales Report", "🕵️ Activity Tracker", "📦 Inventory", "🚨 Reset"])
        
        with t1:
            st.subheader("Project Sales Performance")
            # Safe retrieval of history
            history = storage.get("download_history", [])
            
            if history:
                df_report = pd.DataFrame(history)

                # --- 1. DATA ALIGNMENT (Fixes KeyErrors) ---
                if "Total" in df_report.columns and "Total Package" not in df_report.columns:
                    df_report = df_report.rename(columns={"Total": "Total Package"})
                
                # --- 2. NUMERIC CLEANING (Fixes ValueErrors) ---
                for col in ["Total Package", "Discount", "Agreement Value"]:
                    if col in df_report.columns:
                        df_report[col] = pd.to_numeric(
                            df_report[col].astype(str).str.replace(r'[^\d.]', '', regex=True), 
                            errors='coerce'
                        ).fillna(0)

                # --- 3. METRICS SUMMARY ---
                m1, m2, m3 = st.columns(3)
                t_rev = int(df_report["Total Package"].sum()) if "Total Package" in df_report.columns else 0
                t_disc = int(df_report["Discount"].sum()) if "Discount" in df_report.columns else 0
                
                m1.metric("Units Sold", len(df_report))
                m2.metric("Total Revenue", f"₹ {format_indian_currency(t_rev)}")
                m3.metric("Total Discounts", f"₹ {format_indian_currency(t_disc)}")

                st.divider()

                # --- 4. TABLE VIEW ---
                st.write("### Transaction Table")
                st.dataframe(df_report, use_container_width=True)
                
                # --- 5. EXPORT TO CSV ---
                csv = df_report.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export Report to CSV (Excel)",
                    data=csv,
                    file_name=f"Tarangan_Report_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No sales recorded yet. Data will appear after Sales 'Finalizes' a booking.")

        with t2:
            st.subheader("System Activity Logs")
            # Safe retrieval using .get() to prevent KeyError
            logs = storage.get("activity_log", [])
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
            else:
                st.info("No activity recorded.")

        with t3:
            # --- ADMIN / MANAGER DASHBOARD ---
    elif st.session_state.role in ["Admin"]:
        st.title("🛡️ Admin Control Panel")
        
        # Section: Handle Sales Requests
        st.subheader("🔑 Pending Unit Unblock Requests")
        
        pending = storage.get("pending_requests", {})
        
        if not pending:
            st.info("No pending unblock requests from Sales cabins.")
        else:
            # Create a table/list of requests
            for cabin, requested_unit in list(pending.items()):
                col1, col2, col3 = st.columns([2, 2, 2])
                
                with col1:
                    st.write(f"**Cabin {cabin}**")
                with col2:
                    st.warning(f"Requesting: **{requested_unit}**")
                with col3:
                    if st.button(f"✅ Approve {requested_unit}", key=f"app_{cabin}"):
                        # 1. Add to approved list for that cabin
                        if "approved_units" not in storage:
                            storage["approved_units"] = {}
                        if cabin not in storage["approved_units"]:
                            storage["approved_units"][cabin] = []
                            
                        storage["approved_units"][cabin].append(requested_unit)
                        
                        # 2. Increment the 'chances used' counter
                        if "unblock_counts" not in storage:
                            storage["unblock_counts"] = {}
                        storage["unblock_counts"][cabin] = storage["unblock_counts"].get(cabin, 0) + 1
                        
                        # 3. Remove from pending
                        del storage["pending_requests"][cabin]
                        
                        st.success(f"Unit {requested_unit} unlocked for Cabin {cabin}!")
                        st.rerun()

        st.divider()
        # (Rest of your Manager/Admin logic for assigning booths follows here...)
            pass

        with t4:
            st.subheader("System Reset")
            reset_pw = st.text_input("Reset Password:", type="password", key="admin_reset_final")
            if st.button("💣 WIPE ALL DATA"):
                if reset_pw == "Atharva Joshi":
                    # RE-INITIALIZE (Safety first)
                    storage["locks"] = {}
                    storage["sold_units"] = set()
                    storage["download_history"] = []
                    storage["activity_log"] = []
                    storage["waiting_customers"] = []
                    storage["unit_hits"] = {}
                    storage["booths"] = {letter: None for letter in "ABCDEFGHIJ"}
                    st.cache_resource.clear()
                    st.success("System Reset. Refreshing...")
                    st.rerun()
                else:
                    st.error("Incorrect Password")
