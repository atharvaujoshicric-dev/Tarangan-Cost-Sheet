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
        "sold_units": set(), 
        "in_process_units": {}, # Tracks Unit ID -> Cabin Letter
        "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {}, 
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"}, 
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "waiting_customers": [], "visited_customers": set()
    }

storage = get_global_storage()

# --- DATA ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL); df.columns = [str(c).strip() for c in df.columns]; return df

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
            "1. Advocate charges will be Rs. 15,000/-, at the time of agreement.",
            "2. Agreement to be executed & registered within 15 days from the date of booking.",
            "3. The total cost mentioned here is all inclusive of GST, Registration, Stamp Duty.",
            "4. GST, Stamp Duty, Registration and all applicable government charges are as per the current rates.",
            "5. Sale is on the basis of RERA carpet area only.",
            "6. All legal documents will be executed in square meter only.",
            "7. Subject to PCMC jurisdiction.",
            "8. Society Maintenance at Rs. 3 per sq.ft. per month for 2 years.",
            "9. Loan facility available; home loan sanctioning is customers responsibility.",
            "10. Promoters reserve the right to change prices without prior notice.",
            "11. Booking is non-transferable.",
            "12. Information provided in good faith and does not constitute a contract.",
            "13. Government taxes will be applicable at actual.",
            "14. Documents required: PAN Card, Adhar Card, Photocopy.",
            "15. External bank loan processing charge: Rs. 25,000/-.",
            "16. Developer reserves right to modify Terms and Conditions."
        ]
        for line in tc_lines: pdf.multi_cell(0, 3.2, line)
        
        footer_y = pdf.h - 50
        pdf.set_y(footer_y + 5); pdf.set_font("Arial", 'B', 12); pdf.cell(210, 10, "Contact: 080 6452 3034", align='C')
        pdf.set_xy(150, footer_y); pdf.cell(45, 18, "", border=1)
        pdf.set_xy(150, footer_y + 19); pdf.set_font("Arial", '', 7); pdf.cell(45, 5, "Customer Signature", align='C')

    return pdf.output(dest='S').encode('latin-1')

# --- APP START ---
st.set_page_config(page_title="Tarangan Dash", layout="wide")

if 'authenticated' not in st.session_state: 
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
        if u in creds and p == creds[u]:
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, u, u
            st.rerun()
        else: st.error("Invalid credentials.")

else:
    if st.sidebar.button("Logout"): 
        st.session_state.authenticated = False
        st.rerun()

    # --- GRE DASHBOARD ---
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        df_master = load_data()
        all_active = [str(c).upper() for c in storage["waiting_customers"]] + [str(v).upper() for v in storage["booths"].values() if v]
        
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("📋 Database List")
            target_col = "Customer Allotted"
            if target_col in df_master.columns:
                db_list = df_master[target_col].dropna().unique().tolist()
                filtered = [cust for cust in db_list if str(cust).upper() not in all_active]
                sel = st.selectbox("Search Customer:", ["-- Select --"] + sorted(filtered))
                if st.button("Add Selected") and sel != "-- Select --":
                    storage["waiting_customers"].append(sel); st.rerun()
        with col_right:
            st.subheader("🚶 Walk-in")
            new_name = st.text_input("Enter Name").strip()
            if st.button("Add Walk-in") and new_name:
                storage["waiting_customers"].append(new_name); st.rerun()

    # --- MANAGER DASHBOARD ---
    elif st.session_state.role == "Manager":
        st.title("👔 Manager Assignment")
        col1, col2 = st.columns([1, 1.2])
        with col1:
            if storage["waiting_customers"]:
                sel_c = st.selectbox("Select Customer:", storage["waiting_customers"])
                b_avail = [k for k, v in storage["booths"].items() if v is None]
                if b_avail:
                    sel_b = st.selectbox("Assign to Cabin:", b_avail)
                    if st.button("Confirm"):
                        storage["booths"][sel_b] = sel_c
                        storage["waiting_customers"].remove(sel_c); st.rerun()
        with col2:
            st.subheader("Cabin Status")
            for b, c in storage["booths"].items():
                if c:
                    st.write(f"**Cabin {b}:** {c}")
                    if st.button(f"Release Cabin {b}", key=f"rel_{b}"):
                        storage["booths"][b] = None; st.rerun()

    # --- SALES DASHBOARD ---
    elif st.session_state.role == "Sales":
        if "search_id_input" not in st.session_state: st.session_state.search_id_input = ""
        my_cabin = st.selectbox("Select Your Cabin:", list("ABCDEFGHIJ"), key="sales_cabin_sel")
        cust_name = storage["booths"].get(my_cabin)
        
        st.title("🏙️ Stage 3: Sales Portal")
        
        if not cust_name:
            st.warning(f"Cabin {my_cabin} is empty. Wait for Manager.")
        else:
            st.success(f"👤 Serving: **{cust_name}**")
            inventory = load_data()
            
            # Request Unblock
            st.subheader("🔑 Request Inventory Unblock")
            chances = storage["unblock_counts"].get(my_cabin, 0)
            if chances < 2:
                req_unit = st.text_input("Unit ID:").strip().upper()
                if st.button("Send Request") and req_unit:
                    storage["pending_requests"][my_cabin] = req_unit
                    st.toast(f"Requested {req_unit}")
            
            # GRID
            st.subheader("🏢 Unit Inventory")
            grid_cols = st.columns(6)
            for idx, row_data in inventory.iterrows():
                uid = str(row_data['ID']).upper().strip()
                approved_list = storage["approved_units"].get(my_cabin, [])
                
                is_sold = uid in storage["sold_units"]
                is_busy = uid in storage["in_process_units"] and storage["in_process_units"][uid] != my_cabin
                is_unlocked = (uid in approved_list)
                
                btn_label = uid
                is_disabled = True
                
                if is_sold: btn_label, is_disabled = "⛔ SOLD", True
                elif is_busy: btn_label, is_disabled = "⏳ BUSY", True
                elif is_unlocked: btn_label, is_disabled = f"🔓 {uid}", False
                else: btn_label, is_disabled = f"🔒 {uid}", True

                if grid_cols[idx % 6].button(btn_label, key=f"btn_{uid}", disabled=is_disabled, use_container_width=True):
                    st.session_state.search_id_input = uid
                    storage["in_process_units"][uid] = my_cabin
                    st.rerun()

            # COST SHEET
            search_id = st.session_state.search_id_input
            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    # Simple display logic for brevity
                    st.info(f"Unit {search_id} Selected. Agreement: {row.get('Agreement Value')}")
                    
                    col_act1, col_act2 = st.columns(2)
                    with col_act1:
                        if st.button("✅ Finalize & Book"):
                            # Logic for Google Sheet Swap would go here
                            storage["sold_units"].add(search_id)
                            if search_id in storage["in_process_units"]: del storage["in_process_units"][search_id]
                            storage["booths"][my_cabin] = None
                            storage["approved_units"][my_cabin] = []
                            st.session_state.search_id_input = ""
                            st.success("Booked!"); st.rerun()

                    with col_act2:
                        if st.button("❌ Close / Release"):
                            # RELEASE LOGIC: Unlock for others, but re-lock for this salesperson
                            if search_id in storage["in_process_units"]:
                                del storage["in_process_units"][search_id]
                            if search_id in storage["approved_units"][my_cabin]:
                                storage["approved_units"][my_cabin].remove(search_id)
                            
                            st.session_state.search_id_input = ""
                            st.rerun()

    # --- ADMIN DASHBOARD ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master Control")
        t1, t2, t3 = st.tabs(["📊 Sales Report", "🔑 Pending Requests", "🏢 Unit Grid Status"])
        
        with t2:
            pending = storage.get("pending_requests", {})
            for cabin, unit in list(pending.items()):
                if st.button(f"Approve {unit} for Cabin {cabin}"):
                    storage["approved_units"][cabin].append(unit)
                    storage["unblock_counts"][cabin] += 1
                    del storage["pending_requests"][cabin]
                    st.rerun()
        
        with t3:
            st.subheader("Live Inventory Status")
            inv_data = load_data()
            stat_cols = st.columns(6)
            for idx, r in inv_data.iterrows():
                uid = str(r['ID']).upper().strip()
                if uid in storage["sold_units"]: color, txt = "#ff4b4b", "SOLD"
                elif uid in storage["in_process_units"]: color, txt = "#ffa500", f"PROCESS ({storage['in_process_units'][uid]})"
                else: color, txt = "#28a745", "AVAILABLE"
                
                stat_cols[idx % 6].markdown(f"""
                <div style="background:{color}; color:white; padding:10px; border-radius:5px; text-align:center; margin-bottom:5px;">
                <b>{uid}</b><br><small>{txt}</small></div>
                """, unsafe_allow_html=True)
