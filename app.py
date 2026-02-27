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
        if pd.isna(token_str) or str(token_str).strip() == "": return "Walk-in", "N/A"
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
        pdf.set_font("Arial", 'B', 12); pdf.cell(95, 10, "TOTAL", border=1); pdf.cell(95, 10, format_indian_currency(costs['Total']), border=1, ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- APP START ---
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
        st.title(f"Role: {st.session_state.role}")
        if st.button("🚪 Logout"): st.session_state.authenticated = False; st.rerun()
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
            if st.button("Add to Queue"):
                if name_sel != "Select":
                    storage["waiting_customers"].append(name_sel); storage["visited_customers"].add(name_sel); st.success("Added.")
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
                c_sel = st.selectbox("Assign Customer:", storage["waiting_customers"])
                b_avail = [k for k, v in storage["booths"].items() if v is None]
                if b_avail:
                    b_sel = st.selectbox("To Cabin:", b_avail)
                    if st.button("Assign Now"):
                        storage["booths"][b_sel] = c_sel; storage["waiting_customers"].remove(c_sel); st.rerun()
        with col2:
            st.subheader("Booth Status")
            for b, c in storage["booths"].items():
                if c:
                    st.write(f"**Cabin {b}:** {c}")
                    c1, c2 = st.columns(2)
                    if c1.button(f"Unassign {b}", key=f"un_{b}"): storage["waiting_customers"].append(c); storage["booths"][b] = None; st.rerun()
                    if c2.button(f"Delete {b}", key=f"del_{b}"): storage["booths"][b] = None; st.rerun()
                else: st.write(f"Cabin {b}: 🟢 Free")

    # --- SALES DASHBOARD ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Sales Portal")
        my_cabin = st.selectbox("Cabin Selection:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if cust_name:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            
            st.info(f"Customer: {cust_name} | Target: {assigned_id}")

            if "search_id_input" not in st.session_state: st.session_state.search_id_input = ""
            search_id = st.session_state.search_id_input.upper()

            with st.expander("📁 View Inventory Grid", expanded=(not search_id)):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    unlocked = (uid == assigned_id) or (uid in storage["approved_units"][my_cabin])
                    is_sold = uid in storage["sold_units"]
                    label = f"🟡 {uid}" if unlocked else (f"⛔ {uid}" if is_sold else f"🔒 {uid}")
                    if grid_cols[idx % 6].button(label, key=f"b_{uid}", disabled=not unlocked):
                        st.session_state.search_id_input = uid; st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    
                    # --- RESTORED DISCOUNT & FEMALE OPTIONS ---
                    c1, c2, c3 = st.columns(3)
                    with c1: use_p = st.checkbox("Include Parking", value=True)
                    with c2: is_fem = st.checkbox("Female Owner (6% SD)")
                    with c3: pkg_disc = st.number_input("Package Discount", value=0, step=5000)
                    
                    park_disc = st.number_input("Parking Discount", value=0, step=5000) if use_p else 0
                    
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), pkg_disc, park_disc, use_p, is_fem)
                    
                    # --- UPDATED RECEIPT STYLE COST SHEET ---
                    st.markdown(f"""
                        <div style="background:#fffef0; padding:20px; border:1px solid #ddd; border-top:10px solid #222; max-width:400px; color:black; font-family:'Courier New', Courier, monospace; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); margin:auto;">
                            <h2 style="text-align:center; margin-bottom:0;">TARANGAN</h2>
                            <p style="text-align:center; font-size:12px; margin-top:0;">*** BOOKING RECEIPT ***</p>
                            <p style="text-align:center; font-size:10px;">Date: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
                            <p>---------------------------------</p>
                            <p><b>CUSTOMER:</b> {cust_name}</p>
                            <p><b>UNIT NO:</b> {search_id}</p>
                            <p><b>FLOOR  :</b> {row.get('Floor','N/A')}</p>
                            <p><b>CARPET :</b> {row.get('CARPET','N/A')} SQFT</p>
                            <p>---------------------------------</p>
                            <div style="display:flex; justify-content:space-between;"><span>AGREEMENT VAL:</span><span>{format_indian_currency(res['Final Agreement'])}</span></div>
                            <div style="display:flex; justify-content:space-between;"><span>STAMP DUTY ({int(res['SD_Pct'])}%):</span><span>{format_indian_currency(res['Stamp Duty'])}</span></div>
                            <div style="display:flex; justify-content:space-between;"><span>GST ({int(res['GST_Pct'])}%):</span><span>{format_indian_currency(res['GST'])}</span></div>
                            <div style="display:flex; justify-content:space-between;"><span>REGISTRATION :</span><span>30,000</span></div>
                            <p>---------------------------------</p>
                            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:18px;"><span>TOTAL ALL IN:</span><span>{format_indian_currency(res['Total'])}</span></div>
                            <p>---------------------------------</p>
                            <p style="font-size:10px; text-align:center;">PARKING: {res['Parking Text']}</p>
                            <p style="text-align:center; margin-top:20px;">THANK YOU!</p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.write("")
                    col_act1, col_act2 = st.columns(2)
                    if col_act1.button("✅ Finalize & Send Email"):
                        pdf_bytes = create_pdf(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, "28/02/2026", use_p)
                        details = {"Unit No": search_id, "Customer Name": cust_name, "Total": format_indian_currency(res['Total'])}
                        if send_email(RECEIVER_EMAIL, pdf_bytes, f"{search_id}.pdf", details):
                            storage["sold_units"].add(search_id); storage["download_history"].append(details)
                            reset_cabin_session(my_cabin); st.session_state.search_id_input = ""; st.rerun()
                    
                    if col_act2.button("🔓 Release Unit Selection"):
                        st.session_state.search_id_input = ""; st.rerun()

            st.write("---")
            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                req = st.text_input("Request Unblock (Unit ID):").upper()
                if st.button("Send Request"): storage["pending_requests"][my_cabin] = req; st.toast("Sent.")
            with col_opt2:
                opt_reason = st.text_input("Opt-Out Reason:")
                if st.button("Mark Opted Out"):
                    storage["opted_out"].append({"Customer": cust_name, "Reason": opt_reason})
                    reset_cabin_session(my_cabin); st.rerun()

    # --- ADMIN DASHBOARD ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master")
        t1, t2, t3, t4 = st.tabs(["Requests", "Sales & Opt-Outs", "Release Sold", "Non-Visited"])
        with t1:
            for c, u in list(storage["pending_requests"].items()):
                st.write(f"Cabin {c} -> Unit {u}")
                if st.button(f"Approve {u}", key=f"ap_{c}"):
                    storage["approved_units"][c].append(u); storage["unblock_counts"][c]+=1; del storage["pending_requests"][c]; st.rerun()
        with t2:
            st.subheader("Sales History"); st.table(storage["download_history"])
            st.subheader("Opted Out List"); st.table(storage["opted_out"])
        with t3:
            u_rel = st.selectbox("Release Unit:", sorted(list(storage["sold_units"])))
            if st.button("Unlock Unit"): storage["sold_units"].remove(u_rel); st.rerun()
        with t4:
            inventory = load_data()
            tok_key = next((c for c in inventory.columns if 'TOKEN' in c.upper()), None)
            if tok_key:
                allotted_list = inventory.dropna(subset=['Customer Allotted'])
                for s in ["Slot 1", "Slot 2", "Slot 3"]:
                    st.write(f"### {s}")
                    nv = [{"Customer": r['Customer Allotted'], "Token": r[tok_key]} for _, r in allotted_list.iterrows() if get_slot_info(r[tok_key])[0] == s and r['Customer Allotted'] not in storage["visited_customers"]]
                    st.table(nv if nv else [{"Customer": "None", "Token": "-"}])
