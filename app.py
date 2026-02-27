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

# Safety import for num2words
try:
    from num2words import num2words
except ImportError:
    st.error("Please add 'num2words' to your requirements.txt file on GitHub.")

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "atharvaujoshi@gmail.com"
SENDER_NAME = "Tarangan Cost Sheet" 
APP_PASSWORD = "nybl zsnx zvdw edqr"
RECEIVER_EMAIL = "sales@taranganbysmmahalaxmi.com"

# --- HELPER FUNCTIONS (DEFINED FIRST TO AVOID NAMEERROR) ---
def clean_numeric(value):
    if pd.isna(value): return 0.0
    clean_val = re.sub(r'[^\d.]', '', str(value))
    return float(clean_val) if clean_val else 0.0

def format_indian_currency(number):
    s = str(int(number))
    if len(s) <= 3: return s
    return re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', s[:-3]) + ',' + s[-3:]

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    sd_amt = round(final_agreement * sd_pct, -2) 
    total = int(final_agreement + sd_amt + (final_agreement * gst_pct) + 30000)
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct*100, 
        "GST": final_agreement*gst_pct, "GST_Pct": gst_pct*100, "Registration": 30000, 
        "Total": total, "Combined_Discount": int(pkg_discount + park_discount)
    }

def send_transaction_email_with_pdf(details, pdf_content, filename):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"Booking Confirmed: {details['Unit No']} - {details['Customer Name']}"
        body = f"A new booking has been confirmed.\n\nSummary:\n" + "\n".join([f"{k}: {v}" for k, v in details.items()])
        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_content)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}")
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
    except Exception as e:
        st.error(f"Email failed: {e}")

# --- 1. SHARED STORAGE ---
@st.cache_resource
def get_global_storage():
    return {
        "locks": {}, "sold_units": set(), "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {}, 
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"}, 
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "opted_out_customers": [], "waiting_customers": [], "activity_log": []
    }

storage = get_global_storage()

def reset_cabin_session(cabin):
    storage["booths"][cabin] = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    if cabin in storage["pending_requests"]:
        del storage["pending_requests"][cabin]

# --- 2. CONFIG & GOOGLE SHEET ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

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

# --- UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL); df.columns = [str(c).strip() for c in df.columns]; return df

@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time, cabin_key):
    st.write(f"Confirming booking for **Unit {unit_id}**")
    sales_name = st.text_input("Sales Person Name:")
    if st.button("Confirm & Download"):
        if not sales_name.strip(): st.error("Name required.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking)
            details = {"Timestamp": ist_log_time, "Sales Person": sales_name, "Unit No": unit_id, "Customer Name": cust_name, "Total Package": format_indian_currency(costs['Total']), "Discount Given": costs['Combined_Discount']}
            storage["download_history"].append(details); storage["sold_units"].add(unit_id)
            send_transaction_email_with_pdf(details, pdf_bytes, f"Tarangan_{unit_id}.pdf")
            reset_cabin_session(cabin_key)
            st.session_state.search_id_input = ""
            st.success("Booked!"); st.download_button("📥 Save PDF", pdf_bytes, f"Tarangan_{unit_id}.pdf", "application/pdf")

# --- LOGIN ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
            if u in creds and p == creds[u]:
                st.session_state.authenticated, st.session_state.role = True, u
                st.rerun()
            else: st.error("Invalid credentials.")
else:
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False; st.rerun()

    role = st.session_state.role

    if role == "GRE":
        st.title("📝 GRE Entry")
        if st.button("🔄 Refresh"): st.rerun()
        inventory = load_data()
        allotted = sorted(list(inventory['Customer Allotted'].dropna().unique()))
        name_sel = st.selectbox("Select Allotted Customer:", ["Select Name"] + allotted)
        if st.button("Add to List"):
            if name_sel != "Select Name": storage["waiting_customers"].append(name_sel); st.success(f"Added {name_sel}")

    elif role == "Manager":
        st.title("👔 Manager Assignment")
        if st.button("🔄 Refresh"): st.rerun()
        col1, col2 = st.columns(2)
        if storage["waiting_customers"]:
            sel_c = col1.selectbox("Customer:", storage["waiting_customers"])
            sel_b = col1.selectbox("Cabin:", [b for b, v in storage["booths"].items() if v is None])
            if col1.button("Assign"):
                storage["booths"][sel_b] = sel_c
                storage["waiting_customers"].remove(sel_c); st.rerun()
        col2.table([{"Cabin": k, "Customer": v if v else "Free"} for k, v in storage["booths"].items()])

    elif role == "Sales":
        st.title("🏙️ Sales Portal")
        if st.button("🔄 Refresh"): st.rerun()
        my_cabin = st.selectbox("Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        if cust_name:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            st.info(f"Serving: **{cust_name}** | Base Flat: **{assigned_id}**")

            rem = 2 - storage["unblock_counts"][my_cabin]
            if rem > 0:
                req = st.text_input("Request Flat Unblock (e.g. A-105):").upper()
                if st.button(f"Request ({rem} left)"):
                    if req: storage["pending_requests"][my_cabin] = req; st.toast("Sent.")
            
            if st.button("❌ Opted Out"): storage["opted_out_customers"].append(cust_name); reset_cabin_session(my_cabin); st.rerun()

            search_id = st.session_state.get("search_id_input", "").upper()
            with st.expander("📁 Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    unlocked = (uid == assigned_id) or (uid in storage["approved_units"][my_cabin])
                    with grid_cols[idx % 6]:
                        if st.button(f"🟡 {uid}" if unlocked else f"🔒 {uid}", use_container_width=True, disabled=not unlocked):
                            st.session_state.search_id_input = uid; st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), st.number_input("Discount:", value=0), 0, st.checkbox("Parking"), False)
                    st.markdown(f'<div style="background:white;padding:20px;border:2px solid black;color:black;"><b>Unit:</b> {search_id}<br><b>Total:</b> {format_indian_currency(res["Total"])}</div>', unsafe_allow_html=True)
                    if st.button("📥 Download"): download_dialog(search_id, row.get('Floor','N/A'), "N/A", res, cust_name, "2026", False, "2026", my_cabin)

    elif role == "Tarangan":
        st.title("🛠️ Admin Dashboard")
        if st.button("🔄 Refresh"): st.rerun()
        t1, t2, t3 = st.tabs(["Unit Requests", "Revoke Unblocks", "Reset"])
        with t1:
            for c, u in list(storage["pending_requests"].items()):
                st.write(f"Cabin {c} wants {u}")
                if st.button(f"Approve {u} for {c}"):
                    storage["approved_units"][c].append(u); storage["unblock_counts"][c] += 1
                    del storage["pending_requests"][c]; st.rerun()
        with t2:
            st.subheader("Revoke Manual Unblocks")
            for c, units in storage["approved_units"].items():
                if units:
                    st.write(f"**Cabin {c}** (Customer: {storage['booths'][c]})")
                    for u in units:
                        if st.button(f"Revoke {u}", key=f"rev_{c}_{u}"):
                            storage["approved_units"][c].remove(u)
                            storage["unblock_counts"][c] = max(0, storage["unblock_counts"][c] - 1)
                            st.rerun()
        with t3:
            if st.text_input("Reset Password", type="password") == "Atharva Joshi":
                if st.button("⚠️ FULL RESET"): storage["locks"].clear(); storage["sold_units"].clear(); st.rerun()
