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
    return re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', s[:-3]) + ',' + s[-3:]

def get_slot_info(token_str):
    try:
        if pd.isna(token_str) or token_str == "": return "Walk-in", "N/A"
        token_no = int(re.search(r'\d+', str(token_str)).group())
        if 21 <= token_no <= 45: return "Slot 1", "10:00 AM - 11:30 AM"
        elif 46 <= token_no <= 71: return "Slot 2", "1:00 PM - 2:30 PM"
        else: return "Slot 3", "5:00 PM - 6:00 PM"
    except: return "Walk-in", "N/A"

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    sd_amt = round(final_agreement * sd_pct, -2) 
    gst_amt = final_agreement * gst_pct
    reg = 30000
    total = int(final_agreement + sd_amt + gst_amt + reg)
    parking_text = "Parking Under Building" if use_parking else "1 Car Parking"
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct*100, 
        "GST": gst_amt, "GST_Pct": gst_pct*100, "Registration": reg, 
        "Total": total, "Combined_Discount": int(pkg_discount + park_discount),
        "Parking Text": parking_text
    }

def send_email(recipient_email, pdf_data, filename, details):
    try:
        msg = MIMEMultipart()
        msg['From'] = formataddr((SENDER_NAME, SENDER_EMAIL))
        msg['To'] = recipient_email
        msg['Subject'] = f"Tarangan Booking: {details['Unit No']} - {details['Customer Name']}"
        body = f"Cost sheet attached for {details['Customer Name']}."
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
        pdf.set_font("Arial", 'B', 12); pdf.cell(95, 10, "TOTAL", border=1); pdf.cell(95, 10, format_indian_currency(costs['Total']), border=1, ln=True)
    return pdf.output(dest='S').encode('latin-1')

st.set_page_config(page_title="Tarangan Dash", layout="wide")

if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    with st.form("login"):
        u, p = st.text_input("User"), st.text_input("Pass", type="password")
        if st.form_submit_button("Login"):
            creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
            if u in creds and p == creds[u]: st.session_state.authenticated, st.session_state.role = True, u; st.rerun()
else:
    with st.sidebar:
        st.title(f"{st.session_state.role} Panel")
        if st.button("🚪 Logout"): st.session_state.authenticated = False; st.rerun()
        st.write("---")
        if st.button("🔄 Refresh Page"): st.rerun()

    # --- GRE DASHBOARD ---
    if st.session_state.role == "GRE":
        st.title("📝 GRE Dashboard")
        inventory = load_data()
        allotted = sorted(list(inventory['Customer Allotted'].dropna().unique()))
        t1, t2 = st.tabs(["Allotted", "Walk-in"])
        with t1:
            name_sel = st.selectbox("Select Customer:", ["Select"] + allotted)
            if name_sel != "Select":
                tok_key = next((c for c in inventory.columns if 'TOKEN' in c.upper()), None)
                if tok_key:
                    v = inventory[inventory['Customer Allotted'] == name_sel][tok_key].values[0]
                    slot, time = get_slot_info(v); st.info(f"Slot: {slot} | Timing: {time}")
            if st.button("Add Allotted"):
                if name_sel != "Select": storage["waiting_customers"].append(name_sel); storage["visited_customers"].add(name_sel); st.success("Added.")
        with t2:
            walkin = st.text_input("Walk-in Name:")
            if st.button("Add Walk-in"):
                if walkin: storage["waiting_customers"].append(walkin); storage["visited_customers"].add(walkin); st.success("Added.")

    # --- MANAGER DASHBOARD ---
    elif st.session_state.role == "Manager":
        st.title("👔 Manager Assignment")
        col1, col2 = st.columns(2)
        with col1:
            if storage["waiting_customers"]:
                c_sel = st.selectbox("Queue:", storage["waiting_customers"])
                b_avail = [k for k, v in storage["booths"].items() if v is None]
                if b_avail:
                    b_sel = st.selectbox("Cabin:", b_avail)
                    if st.button("Assign"): storage["booths"][b_sel] = c_sel; storage["waiting_customers"].remove(c_sel); st.rerun()
        with col2:
            st.subheader("Booth Status")
            for b, c in storage["booths"].items():
                if c:
                    st.write(f"**Cabin {b}:** {c}")
                    ca, cb = st.columns(2)
                    if ca.button(f"Unassign {b}", key=f"un_{b}"): storage["waiting_customers"].append(c); storage["booths"][b] = None; st.rerun()
                    if cb.button(f"Delete {b}", key=f"del_{b}"): storage["booths"][b] = None; st.rerun()
                else: st.write(f"Cabin {b}: 🟢 Free")

    # --- SALES DASHBOARD ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Sales Portal")
        my_cabin = st.selectbox("My Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        if cust_name:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            st.info(f"Customer: {cust_name} | Target: {assigned_id}")
            
            # Request Unblock
            req_id = st.text_input("Request Unit Unblock:").upper()
            if st.button("Send Unblock Request"):
                if req_id: storage["pending_requests"][my_cabin] = req_id; st.success("Requested.")

            # Opt out
            opt_reason = st.text_input("Opt-Out Reason:")
            if st.button("Mark as Opted Out"):
                storage["opted_out"].append({"Customer": cust_name, "Reason": opt_reason, "Date": "28/02/2026"})
                reset_cabin_session(my_cabin); st.rerun()

            # THE GRID (Fixed: Not inside expander to prevent collapse)
            st.write("### Inventory Grid")
            grid_cols = st.columns(10)
            if "search_id_input" not in st.session_state: st.session_state.search_id_input = ""
            
            for idx, row in inventory.iterrows():
                uid = str(row['ID']).upper()
                unlocked = (uid == assigned_id) or (uid in storage["approved_units"][my_cabin])
                is_sold = uid in storage["sold_units"]
                label = f"🟡 {uid}" if unlocked else (f"⛔ {uid}" if is_sold else f"🔒 {uid}")
                if grid_cols[idx % 10].button(label, key=f"btn_{uid}", disabled=not unlocked):
                    st.session_state.search_id_input = uid; st.rerun()

            # OLD ONSCREEN COST SHEET
            if st.session_state.search_id_input:
                match = inventory[inventory['ID'].astype(str).str.upper() == st.session_state.search_id_input]
                if not match.empty:
                    row = match.iloc[0]
                    use_p = st.checkbox("Include Parking")
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), 0, 0, use_p, False)
                    
                    st.markdown(f"""
                    <div style="background:white; padding:30px; border:3px solid black; color:black; font-family:serif;">
                        <h1 style="text-align:center;">TARANGAN</h1>
                        <hr>
                        <p><b>CUSTOMER NAME:</b> {cust_name}</p>
                        <p><b>UNIT NO:</b> {st.session_state.search_id_input} &nbsp;&nbsp; <b>FLOOR:</b> {row.get('Floor','N/A')} &nbsp;&nbsp; <b>CARPET:</b> {row.get('CARPET','N/A')} sqft</p>
                        <table style="width:100%; border-collapse: collapse;">
                            <tr style="border-bottom:1px solid black;"><td style="padding:10px;">Agreement Value</td><td style="text-align:right;">Rs. {format_indian_currency(res['Final Agreement'])}</td></tr>
                            <tr style="border-bottom:1px solid black;"><td style="padding:10px;">Stamp Duty ({int(res['SD_Pct'])}%)</td><td style="text-align:right;">Rs. {format_indian_currency(res['Stamp Duty'])}</td></tr>
                            <tr style="border-bottom:1px solid black;"><td style="padding:10px;">GST ({int(res['GST_Pct'])}%)</td><td style="text-align:right;">Rs. {format_indian_currency(res['GST'])}</td></tr>
                            <tr style="border-bottom:1px solid black;"><td style="padding:10px;">Registration</td><td style="text-align:right;">Rs. 30,000</td></tr>
                            <tr style="font-weight:bold; font-size:1.4em;"><td style="padding:10px;">TOTAL PACKAGE</td><td style="text-align:right;">Rs. {format_indian_currency(res['Total'])}</td></tr>
                        </table>
                        <p style="margin-top:10px;"><i>Parking: {res['Parking Text']}</i></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("Confirm & Download PDF"):
                        pdf_bytes = create_pdf(st.session_state.search_id_input, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, "28/02/2026", use_p)
                        details = {"Unit No": st.session_state.search_id_input, "Customer Name": cust_name, "Total": format_indian_currency(res['Total'])}
                        if send_email(RECEIVER_EMAIL, pdf_bytes, f"{st.session_state.search_id_input}.pdf", details):
                            storage["sold_units"].add(st.session_state.search_id_input)
                            storage["download_history"].append(details)
                            reset_cabin_session(my_cabin); st.session_state.search_id_input = ""; st.rerun()

    # --- ADMIN DASHBOARD ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master")
        t1, t2, t3, t4, t5 = st.tabs(["Unit Unblock", "Sales History", "Opted Out", "Release Inventory", "Non-Visited List"])
        
        with t1:
            st.subheader("Pending Requests")
            for c, u in list(storage["pending_requests"].items()):
                st.write(f"Cabin {c} requests to unblock Unit {u}")
                if st.button(f"Approve {u}", key=f"app_{c}"):
                    storage["approved_units"][c].append(u); storage["unblock_counts"][c]+=1; del storage["pending_requests"][c]; st.rerun()
            st.write("---")
            st.subheader("Revoke Approvals")
            for c, units in storage["approved_units"].items():
                for u in units:
                    if st.button(f"Revoke {u} (Cabin {c})", key=f"rev_{c}_{u}"): storage["approved_units"][c].remove(u); st.rerun()

        with t2: st.table(storage["download_history"])
        with t3: st.table(storage["opted_out"])
        
        with t4:
            st.subheader("Release Booked Inventory")
            u_rel = st.selectbox("Select Sold Unit to Release:", sorted(list(storage["sold_units"])))
            if st.button("🚨 Unblock & Release Unit"):
                storage["sold_units"].remove(u_rel); st.success(f"Unit {u_rel} is now free."); st.rerun()

        with t5:
            inventory = load_data(); tok_key = next((c for c in inventory.columns if 'TOKEN' in c.upper()), None)
            if tok_key:
                allotted_list = inventory.dropna(subset=['Customer Allotted'])
                for s in ["Slot 1", "Slot 2", "Slot 3"]:
                    st.write(f"### {s}"); nv = []
                    for _, row in allotted_list.iterrows():
                        slot, _ = get_slot_info(row[tok_key])
                        if slot == s and row['Customer Allotted'] not in storage["visited_customers"]:
                            nv.append({"Customer": row['Customer Allotted'], "Token": row[tok_key]})
                    st.table(nv if nv else [{"Customer": "No Pending Data", "Token": "-"}])
