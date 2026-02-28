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
        st.title("📝 GRE: Guest Relations")
    
    # 1. Add New Customer
    with st.expander("➕ Add New Entry", expanded=True):
        new_name = st.text_input("Customer Full Name")
        if st.button("Add to Waiting List") and new_name:
            new_id = len(storage["waiting_customers"]) + 1
            storage["waiting_customers"].append({"id": new_id, "name": new_name})
            st.rerun()

    # 2. Edit/Manage Waiting List
    st.subheader("⏳ Current Waiting List")
    for idx, cust in enumerate(storage["waiting_customers"]):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            # Edit Name logic
            new_val = st.text_input(f"Name (ID: {cust['id']})", value=cust['name'], key=f"edit_{idx}")
            storage["waiting_customers"][idx]['name'] = new_val
        with col3:
            if st.button("Remove", key=f"rem_{idx}"):
                storage["waiting_customers"].pop(idx)
                st.rerun()

    # --- MANAGER DASHBOARD ---
            elif st.session_state.role == "Manager":
                st.title("👔 Manager: Cabin Assignment")
            
            col_assign, col_status = st.columns([1, 1])
            
            with col_assign:
                st.subheader("Assign Customer")
                if storage["waiting_customers"]:
                    cust_to_assign = st.selectbox("Select from Waitlist", 
                                                options=storage["waiting_customers"], 
                                                format_func=lambda x: x['name'])
                    free_cabins = [k for k, v in storage["booths"].items() if v is None]
                    
                    if free_cabins:
                        target_cabin = st.selectbox("Assign to Free Cabin", free_cabins)
                        if st.button("Confirm Assignment"):
                            storage["booths"][target_cabin] = cust_to_assign['name']
                            storage["waiting_customers"].remove(cust_to_assign)
                            st.rerun()
                    else:
                        st.warning("All cabins are currently occupied.")
                else:
                    st.info("No customers in waiting list.")
        
            with col_status:
                st.subheader("Cabin Occupancy")
                for cab in "ABCDEFGH":
                    occupant = storage["booths"][cab]
                    status_color = "🔴" if occupant else "🟢 FREE"
                    label = f"**Cabin {cab}:** {occupant if occupant else ''}"
                    st.markdown(f"{status_color} {label}")
                    if occupant:
                        if st.button(f"Clear Cabin {cab}", key=f"clr_{cab}"):
                            storage["booths"][cab] = None
                            storage["approved_units"][cab] = [] # Reset approvals on exit
                            st.rerun()

    # --- SALES DASHBOARD ---
                elif st.session_state.role == "Sales":
                    my_cabin = st.selectbox("Your Assigned Cabin:", list("ABCDEFGH"))
                    current_cust = storage["booths"].get(my_cabin)
                
                if not current_cust:
                    st.warning("Waiting for Manager to assign a customer to this cabin...")
                else:
                    st.header(f"Serving: {current_cust}")
                    inv = load_inventory()
                    
                    st.subheader("🏢 Unit Selection")
                    cols = st.columns(6)
                    
                    for i, row in inv.iterrows():
                        uid = str(row['ID']).strip()
                        # 1. Check if it's a Refuge Floor
                        if uid in ["A-705", "A-1205"]:
                            cols[i%6].button(f"🚫 {uid}\nRefuge", disabled=True, key=f"btn_{uid}")
                            continue
                        
                        # 2. Determine Status
                        is_sold = uid in storage["sold_units"] or (str(row['Token Number']).strip() != "" and str(row['Token Number']) != "nan")
                        is_open = (row['Customer Allotted'] == "" or pd.isna(row['Customer Allotted']))
                        is_approved = uid in storage["approved_units"].get(my_cabin, [])
                        is_busy = uid in storage["in_process_units"] and storage["in_process_units"][uid] != my_cabin
            
                        # 3. UI Logic
                        if is_sold:
                            cols[i%6].button(f"⛔ {uid}\nSOLD", disabled=True, key=f"btn_{uid}")
                        elif is_busy:
                            cols[i%6].button(f"⏳ {uid}\nBUSY", disabled=True, key=f"btn_{uid}")
                        elif is_open or is_approved:
                            # This unit is available to click
                            if cols[i%6].button(f"✅ {uid}\nSelect", key=f"btn_{uid}"):
                                st.session_state.search_id_input = uid
                                storage["in_process_units"][uid] = my_cabin
                                st.rerun()
                        else:
                            # Locked - requires Admin request
                            if cols[i%6].button(f"🔒 {uid}\nLocked", key=f"btn_{uid}"):
                                storage["pending_requests"][my_cabin] = uid
                                st.toast(f"Requesting unlock for {uid}")
            
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
            st.title("Admin Control Panel")
            inv = load_inventory()
            
            # Unit Grid Status
            st.subheader("Live Project View")
            a_cols = st.columns(8)
            for i, r in inv.iterrows():
                uid = str(r['ID']).strip()
                is_sold = uid in storage["sold_units"] or (str(r['Token Number']).strip() != "" and str(r['Token Number']) != "nan")
                is_open = (r['Customer Allotted'] == "" or pd.isna(r['Customer Allotted']))
                
                # Color Coding
                if uid in ["A-705", "A-1205"]: color, txt = "#6c757d", "REFUGE"
                elif is_sold: color, txt = "#dc3545", "SOLD"
                elif uid in storage["in_process_units"]: color, txt = "#ffc107", "IN NEGOTIATION"
                elif is_open: color, txt = "#28a745", "OPEN"
                else: color, txt = "#007bff", "LOCKED (DB)"
        
                a_cols[i%8].markdown(f"""
                    <div style="background:{color}; color:white; padding:5px; border-radius:3px; text-align:center; font-size:10px; margin-bottom:5px;">
                    {uid}<br><b>{txt}</b></div>
                """, unsafe_allow_html=True)
                
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
