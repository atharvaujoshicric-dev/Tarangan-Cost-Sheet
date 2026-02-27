import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import datetime 
import io

# Safety import for num2words
try:
    from num2words import num2words
except ImportError:
    st.error("Please add 'num2words' to your requirements.txt file on GitHub.")

# --- 1. SHARED STORAGE ---
@st.cache_resource
def get_global_storage():
    return {
        "locks": {}, 
        "sold_units": set(), 
        "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "admin_overrides": {letter: False for letter in "ABCDEFGHIJ"}, # New: Admin permission tracker
        "unit_hits": {},
        "waiting_customers": [],
        "activity_log": []
    }

storage = get_global_storage()

def log_activity(user, action, details):
    ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    storage["activity_log"].append({
        "Timestamp": ist_now.strftime("%d/%m/%Y %H:%M:%S"),
        "User": user, "Action": action, "Details": details
    })

# --- 2. CONFIG & GOOGLE SHEET ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
encoded_tab_name = urllib.parse.quote(TAB_NAME)
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_tab_name}"

# --- 3. BACKEND LOGIC ---
def format_indian_currency(number):
    s = str(int(number))
    if len(s) <= 3: return s
    last_three = s[-3:]
    remaining = s[:-3]
    remaining = re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', remaining)
    return remaining + ',' + last_three

def clean_numeric(value):
    if pd.isna(value): return 0.0
    clean_val = re.sub(r'[^\d.]', '', str(value))
    return float(clean_val) if clean_val else 0.0

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_final_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_final_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    REGISTRATION = 30000 
    raw_sd = final_agreement * sd_pct
    sd_amt = round(raw_sd, -2) 
    gst_amt = final_agreement * gst_pct
    total_package = final_agreement + sd_amt + gst_amt + REGISTRATION
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100, "Registration": REGISTRATION,
        "Total": int(total_package), "Combined_Discount": int(pkg_discount + park_discount)
    }

# --- 4. PDF GENERATION ---
def create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking):
    pdf = FPDF()
    copies = ["Customer's Copy", "Sales Copy"]
    for copy_label in copies:
        pdf.add_page()
        pdf.set_font("Arial", 'I', 8); pdf.set_xy(10, 5); pdf.cell(0, 10, copy_label, ln=True, align='L')
        try:
            pdf.image("tarangan_logo.png", x=75, y=10, w=60)
            pdf.set_y(42); pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "COST SHEET", ln=True, align='C')
        except:
            pdf.set_y(20); pdf.set_font("Arial", 'B', 20); pdf.cell(190, 10, "TARANGAN", ln=True, align='C')
            pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "COST SHEET", ln=True, align='C')

        pdf.set_font("Arial", '', 10); pdf.cell(190, 10, f"Date: {date_str}", ln=True, align='R')
        pdf.set_font("Arial", 'B', 12); display_name = cust_name if cust_name.strip() else "____________________"
        pdf.cell(190, 10, f"Customer Name: {display_name}", ln=True)
        pdf.cell(190, 10, f"Unit No: {unit_id} | Floor: {floor} | Carpet: {carpet} sqft", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5)
        
        pdf.set_font("Arial", 'B', 11); pdf.cell(95, 10, "Description", border=1, align='C'); pdf.cell(95, 10, "Amount (Rs.)", border=1, ln=True, align='C')
        pdf.set_font("Arial", '', 11)
        rows = [
            ["Agreement Value", format_indian_currency(costs['Final Agreement'])],
            [f"Stamp Duty ({int(costs['SD_Pct'])}%)", format_indian_currency(costs['Stamp Duty'])],
            [f"GST ({int(costs['GST_Pct'])}%)", format_indian_currency(costs['GST'])],
            ["Registration", format_indian_currency(costs['Registration'])]
        ]
        for r in rows:
            pdf.cell(95, 10, r[0], border=1, align='C'); pdf.cell(95, 10, r[1], border=1, ln=True, align='C')
        
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

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time):
    st.write(f"Confirming booking for **Unit {unit_id}**")
    sales_name = st.text_input("Enter Sales Person Name:")
    if st.button("Confirm & Download"):
        if not sales_name.strip(): st.error("Name required.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking)
            storage["download_history"].append({
                "Timestamp": ist_log_time, "Sales Person": sales_name, "Unit ID": unit_id, 
                "Customer": cust_name, "Total Package": costs['Total']
            })
            storage["sold_units"].add(unit_id)
            st.session_state.search_id_input = ""
            st.success("Unit Booked!")
            st.download_button("📥 Save PDF", pdf_bytes, f"Tarangan_{unit_id}.pdf", "application/pdf")

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]: del storage["locks"][unit_to_release]
    st.session_state.search_id_input = ""

# --- 6. LOGIN SYSTEM ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Login"):
        creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
        if u in creds and p == creds[u]:
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, u, u
            st.rerun()
        else: st.error("Invalid credentials.")
else:
    if st.sidebar.button("Logout"): st.session_state.authenticated = False; st.rerun()

    # --- GRE ---
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        name = st.text_input("Customer Name").strip()
        if st.button("Submit"):
            if name and name.upper() not in [c.upper() for c in storage["waiting_customers"]]:
                storage["waiting_customers"].append(name); st.success(f"Added {name}")
            else: st.warning("Error.")

    # --- MANAGER ---
    elif st.session_state.role == "Manager":
        st.title("👔 Stage 2: Manager Assignment")
        col1, col2 = st.columns(2)
        if storage["waiting_customers"]:
            sel_c = col1.selectbox("Select Customer:", storage["waiting_customers"])
            sel_b = col1.selectbox("Cabin:", [b for b, v in storage["booths"].items() if v is None])
            if col1.button("Assign"):
                storage["booths"][sel_b] = sel_c
                storage["waiting_customers"].remove(sel_c); st.rerun()
        col2.table([{"Cabin": k, "Customer": v if v else "Free"} for k, v in storage["booths"].items()])

    # --- SALES ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh Data"): st.rerun()
        my_cabin = st.selectbox("Select Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if not cust_name:
            st.warning(f"No customer in Cabin {my_cabin}.")
        else:
            inventory = load_data()
            
            # --- TOKEN LOGIC: Fetch assigned unit for this customer ---
            # Search for the customer in the Google Sheet's name-related column or logic
            # Assuming 'Token Number' column contains the ID (e.g. A-101)
            token_row = inventory[inventory.iloc[:, 1].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_unit = str(token_row['Token Number'].values[0]).upper() if not token_row.empty else "NONE"
            
            st.info(f"Serving: **{cust_name}** | Assigned Token Unit: **{assigned_unit}**")

            # Admin Override Request
            has_override = storage["admin_overrides"].get(my_cabin, False)
            if not has_override:
                if st.button("🔑 Request Admin to Unblock Other Units"):
                    log_activity("Sales", "OVERRIDE_REQ", f"Cabin {my_cabin} requested access.")
                    st.toast("Request sent to Admin.")

            search_id = st.session_state.get("search_id_input", "").upper()
            with st.expander("📁 Inventory Selection Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    is_sold, is_busy = uid in storage["sold_units"], uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                    
                    # BLOCKING LOGIC: Only allow assigned_unit unless override is active
                    is_locked = True
                    if has_override: is_locked = False
                    if uid == assigned_unit: is_locked = False

                    with grid_cols[idx % 6]:
                        if is_sold: lbl, clr = f"🟢 {uid}", True
                        elif is_busy: lbl, clr = f"🔴 BUSY", True
                        elif is_locked: lbl, clr = f"🔒 LOCKED", True
                        else: lbl, clr = f"🟡 {uid}", False
                        
                        if st.button(lbl, key=f"btn_{uid}", use_container_width=True, disabled=clr):
                            st.session_state.search_id_input = uid
                            st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
                    d_val = st.number_input("Amt:", value=0, step=1000)
                    p_val = st.number_input("Park Disc:", value=0, min_value=0, max_value=100000, step=1000)
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), d_val, p_val, st.checkbox("Parking"), False)

                    st.markdown(f"""
                        <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                            <h2 style="text-align:center;">TARANGAN</h2>
                            <p><b>Customer:</b> {cust_name} | <b>Unit:</b> {search_id}</p>
                            <div style="display:flex; justify-content:space-between;"><span>Total</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("📥 Download"): 
                        download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, "2026", False, "2026")
                    st.button("❌ Close", on_click=release_unit_callback, args=(search_id,))

    # --- ADMIN ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Dashboard")
        t1, t2, t3 = st.tabs(["Requests", "Management", "Reset"])
        
        with t1:
            st.subheader("Sales Cabin Access Requests")
            for cabin, status in storage["admin_overrides"].items():
                if not status:
                    if st.button(f"✅ Approve Universal Access for Cabin {cabin}"):
                        storage["admin_overrides"][cabin] = True
                        log_activity("Admin", "OVERRIDE_APP", f"Approved Cabin {cabin}")
                        st.rerun()
                else:
                    if st.button(f"🚫 Revoke Access for Cabin {cabin}"):
                        storage["admin_overrides"][cabin] = False
                        st.rerun()
        
        with t2:
            st.dataframe(pd.DataFrame(storage["download_history"]), use_container_width=True)
            unit_to_unblock = st.selectbox("Restore Unit:", list(storage["sold_units"]))
            if st.button("Unblock"): storage["sold_units"].remove(unit_to_unblock); st.rerun()

        with t3:
            if st.button("⚠️ RESET"): storage["locks"].clear(); storage["sold_units"].clear(); st.rerun()
