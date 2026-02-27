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

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    sd_amt = round(final_agreement * sd_pct, -2) 
    gst_amt = final_agreement * gst_pct
    reg = 30000
    total = int(final_agreement + sd_amt + gst_amt + reg)
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct*100, 
        "GST": gst_amt, "GST_Pct": gst_pct*100, "Registration": reg, 
        "Total": total, "Combined_Discount": int(pkg_discount + park_discount)
    }

def send_email(recipient_email, pdf_data, filename, details):
    try:
        recipient_name = recipient_email.split('@')[0].replace('.', ' ').title()
        msg = MIMEMultipart()
        msg['From'] = formataddr((SENDER_NAME, SENDER_EMAIL))
        msg['To'] = recipient_email
        msg['Subject'] = f"Tarangan Booking: {details['Unit No']} - {details['Customer Name']}"
        body = f"Dear {recipient_name},\n\nPlease find the attached cost sheet analysis report.\n\nBooking Summary:\n1. Unit: {details['Unit No']}\n2. Customer: {details['Customer Name']}\n3. Total Package: Rs. {details['Total Package']}\n4. Sales Person: {details['Sales Person']}\n\nRegards,\nAtharva Joshi"
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
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return False

# --- SHARED STORAGE ---
@st.cache_resource
def get_global_storage():
    return {
        "locks": {}, "sold_units": set(), "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {}, 
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"}, 
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "waiting_customers": [], "opted_out_customers": []
    }

storage = get_global_storage()

def reset_cabin_session(cabin):
    storage["booths"][cabin] = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    if cabin in storage["pending_requests"]:
        del storage["pending_requests"][cabin]

# --- CONFIG & DATA ---
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
st.set_page_config(page_title="Tarangan Dash", layout="wide")

@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, ist_now, cabin_key):
    st.write(f"Finalizing **Unit {unit_id}**")
    sales_name = st.text_input("Sales Person Name:")
    if st.button("Finalize & Email"):
        if not sales_name.strip(): st.error("Enter Name.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name)
            details = {"Timestamp": ist_now, "Sales Person": sales_name, "Unit No": unit_id, "Customer Name": cust_name, "Total Package": format_indian_currency(costs['Total'])}
            if send_email(RECEIVER_EMAIL, pdf_bytes, f"Tarangan_{unit_id}.pdf", details):
                storage["download_history"].append(details); storage["sold_units"].add(unit_id)
                reset_cabin_session(cabin_key); st.session_state.search_id_input = ""
                st.success("✅ Email Sent!"); st.download_button("📥 Save PDF", pdf_bytes, f"Tarangan_{unit_id}.pdf")

# --- LOGIN ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    with st.form("login"):
        u, p = st.text_input("User"), st.text_input("Pass", type="password")
        if st.form_submit_button("Login"):
            creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
            if u in creds and p == creds[u]: st.session_state.authenticated, st.session_state.role = True, u; st.rerun()
else:
    if st.sidebar.button("Logout"): st.session_state.authenticated = False; st.rerun()

    # --- STAGE 1: GRE ---
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        if st.button("🔄 Refresh"): st.rerun()
        tab1, tab2 = st.tabs(["Add Customer", "Waiting List"])
        with tab1:
            inventory = load_data()
            allotted = sorted(list(inventory['Customer Allotted'].dropna().unique()))
            name_sel = st.selectbox("Select Allotted Customer:", ["Select Name"] + allotted)
            if st.button("Add Allotted"):
                if name_sel != "Select Name": storage["waiting_customers"].append(name_sel); st.success(f"Added {name_sel}")
            st.write("---")
            walkin_name = st.text_input("Walk-in Name:")
            if st.button("Add Walk-in"):
                if walkin_name: storage["waiting_customers"].append(walkin_name); st.success(f"Added {walkin_name}")
        with tab2:
            if storage["waiting_customers"]:
                for i, cust in enumerate(storage["waiting_customers"]):
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"**{i+1}. {cust}**")
                    if col_b.button("Remove", key=f"rem_{i}"): storage["waiting_customers"].pop(i); st.rerun()

    # --- STAGE 2: MANAGER (FIXED ASSIGNMENT) ---
    elif st.session_state.role == "Manager":
        st.title("👔 Stage 2: Manager Assignment")
        if st.button("🔄 Refresh Data"): st.rerun()
        
        t_m1, t_m2 = st.tabs(["Assign Cabin", "Active Cabins Status"])
        
        with t_m1:
            col_assign, col_status = st.columns([2, 1])
            with col_assign:
                st.subheader("Assign Next Customer")
                if storage["waiting_customers"]:
                    cust_to_assign = st.selectbox("Select Customer from List:", storage["waiting_customers"])
                    available_cabins = [k for k, v in storage["booths"].items() if v is None]
                    
                    if available_cabins:
                        cabin_to_assign = st.selectbox("Select Available Cabin:", available_cabins)
                        if st.button("Confirm Assignment"):
                            # Perform the assignment
                            storage["booths"][cabin_to_assign] = cust_to_assign
                            storage["waiting_customers"].remove(cust_to_assign)
                            st.success(f"Assigned {cust_to_assign} to Cabin {cabin_to_assign}")
                            st.rerun()
                    else:
                        st.warning("All cabins are currently occupied.")
                else:
                    st.info("Waiting list is empty. GRE needs to add customers.")
            
            with col_status:
                st.subheader("Live Overview")
                status_data = [{"Cabin": k, "Customer": v if v else "🟢 Available"} for k, v in storage["booths"].items()]
                st.table(status_data)

        with t_m2:
            occupied = {k: v for k, v in storage["booths"].items() if v}
            if occupied:
                st.subheader("Manage Occupied Cabins")
                for c_id, c_cust in occupied.items():
                    with st.expander(f"Cabin {c_id}: {c_cust}"):
                        c1, c2 = st.columns(2)
                        if c1.button(f"Revert {c_id} to Waiting List", key=f"rev_list_{c_id}"):
                            storage["waiting_customers"].append(c_cust)
                            reset_cabin_session(c_id)
                            st.rerun()
                        if c2.button(f"Clear Cabin {c_id} (End Session)", key=f"clear_{c_id}"):
                            reset_cabin_session(c_id)
                            st.rerun()
            else:
                st.info("No cabins are currently active.")

    # --- STAGE 3: SALES ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh"): st.rerun()
        my_cabin = st.selectbox("Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        if cust_name:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            st.info(f"Customer: {cust_name} | Target: {assigned_id}")

            rem = 2 - storage["unblock_counts"][my_cabin]
            if rem > 0:
                req = st.text_input("Request Unit Unblock:").upper()
                if st.button(f"Request Unblock ({rem} left)"):
                    if req: storage["pending_requests"][my_cabin] = req; st.toast("Sent.")
            
            if st.button("❌ Opt-Out"):
                storage["opted_out_customers"].append(cust_name); reset_cabin_session(my_cabin); st.rerun()

            if "search_id_input" not in st.session_state: st.session_state.search_id_input = ""
            search_id = st.session_state.search_id_input.upper()

            with st.expander("📁 Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    unlocked = (uid == assigned_id) or (uid in storage["approved_units"][my_cabin])
                    is_sold = uid in storage["sold_units"]
                    label = f"🟡 {uid}" if unlocked else (f"⛔ {uid}" if is_sold else f"🔒 {uid}")
                    with grid_cols[idx % 6]:
                        if st.button(label, key=f"b_{uid}", disabled=unlocked==False, use_container_width=True):
                            st.session_state.search_id_input = uid; st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                    st.write("---")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        use_d = st.checkbox("Discount")
                        d_val = st.number_input("Amt:", value=0, step=1000) if use_d else 0
                    with c2:
                        use_p = st.checkbox("Parking")
                        p_val = st.number_input("Park Disc:", value=0, min_value=0, max_value=100000, step=1000) if use_p else 0
                    with c3: is_f = st.checkbox("Female")
                    
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), d_val, p_val, use_p, is_f)
                    
                    st.markdown(f"""
                        <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                            <div style="text-align:right;">Date: {ist_now.strftime("%d/%m/%Y")}</div>
                            <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN</h2>
                            <p><b>Customer:</b> {cust_name}</p>
                            <p><b>Unit:</b> {search_id} | <b>Floor:</b> {row.get('Floor','N/A')} | <b>Carpet:</b> {row.get('CARPET','N/A')} sqft</p>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Agreement</span><span>Rs. {format_indian_currency(res['Final Agreement'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Stamp Duty ({int(res['SD_Pct'])}%)</span><span>Rs. {format_indian_currency(res['Stamp Duty'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>GST ({int(res['GST_Pct'])}%)</span><span>Rs. {format_indian_currency(res['GST'])}</span></div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Registration</span><span>Rs. {format_indian_currency(res['Registration'])}</span></div>
                            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                            <div style="font-style:italic; margin-top:5px;">Rupees {num2words(res['Total'], lang='en_IN').title().replace(",","")} Only</div>
                            <div style="color:red; font-weight:bold; margin-top:10px;">Total Discount Availed: Rs. {format_indian_currency(res['Combined_Discount'])}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("📥 Download & Email"):
                        download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, ist_now.strftime("%d/%m/%Y %H:%M"), my_cabin)
                    st.button("❌ Close", on_click=lambda: st.session_state.update({"search_id_input": ""}))

    # --- ADMIN (TARANGAN) ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master Dashboard")
        if st.button("🔄 Global Refresh"): st.rerun()
        t1, t2, t3, t4, t5 = st.tabs(["Requests", "Sales Report", "Revoke Unblocks", "Release Sold Units", "System Reset"])
        
        with t1:
            for c, u in list(storage["pending_requests"].items()):
                if st.button(f"Approve {u} for Cabin {c}"):
                    storage["approved_units"][c].append(u); storage["unblock_counts"][c] += 1
                    del storage["pending_requests"][c]; st.rerun()
        with t2:
            if storage["download_history"]: st.dataframe(pd.DataFrame(storage["download_history"]), use_container_width=True)
        with t3:
            for c, units in storage["approved_units"].items():
                if units:
                    st.write(f"**Cabin {c}:**")
                    for u in units:
                        if st.button(f"Revoke {u}", key=f"rev_{c}_{u}"):
                            storage["approved_units"][c].remove(u); storage["unblock_counts"][c] = max(0, storage["unblock_counts"][c]-1); st.rerun()
        with t4:
            if storage["sold_units"]:
                to_release = st.selectbox("Select Sold Unit to Revert:", sorted(list(storage["sold_units"])))
                if st.button("Release Unit & Wipe Report"):
                    storage["sold_units"].remove(to_release)
                    storage["download_history"] = [d for d in storage["download_history"] if d.get("Unit No") != to_release]
                    st.success(f"Unit {to_release} Released."); st.rerun()
        with t5:
            st.warning("🚨 SYSTEM-WIDE RESET")
            if st.text_input("Enter Admin Password:", type="password") == "Atharva Joshi":
                if st.button("🚨 WIPE ALL SYSTEM DATA"):
                    storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear()
                    storage["waiting_customers"].clear(); storage["pending_requests"].clear()
                    for b in storage["booths"]: storage["booths"][b] = None
                    for b in storage["approved_units"]: storage["approved_units"][b] = []
                    for b in storage["unblock_counts"]: storage["unblock_counts"][b] = 0
                    st.success("System wiped."); st.rerun()
