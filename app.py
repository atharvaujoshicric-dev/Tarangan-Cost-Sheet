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
        if st.button("🔄 Refresh System"): st.rerun()
        if st.button("🚪 Logout"): st.session_state.authenticated = False; st.rerun()

    # --- GRE DASHBOARD ---
    if st.session_state.role == "GRE":
        st.title("📝 GRE Dashboard")
        inventory = load_data()
        allotted = sorted(list(inventory['Customer Allotted'].dropna().unique()))
        
        tab_add, tab_manage = st.tabs(["➕ Add Customer", "⚙️ Manage Waiting List"])
        
        with tab_add:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("From Allotted List")
                name_sel = st.selectbox("Select Customer:", ["Select"] + allotted)
                if st.button("Add Allotted to Queue"):
                    if name_sel != "Select":
                        if name_sel not in storage["waiting_customers"]:
                            storage["waiting_customers"].append(name_sel)
                            storage["visited_customers"].add(name_sel)
                            st.success(f"Added {name_sel}")
                        else: st.warning("Customer already in queue.")
            
            with col_b:
                st.subheader("Walk-in Customer")
                walkin_name = st.text_input("Enter Walk-in Name:")
                if st.button("Add Walk-in to Queue"):
                    if walkin_name.strip():
                        storage["waiting_customers"].append(walkin_name.strip())
                        storage["visited_customers"].add(walkin_name.strip())
                        st.success(f"Added Walk-in: {walkin_name}")
                    else: st.error("Please enter a name.")

        with tab_manage:
            if storage["waiting_customers"]:
                st.subheader("Edit / Change Name")
                # Option for GRE to change the name
                edit_idx = st.selectbox("Select Customer to Edit:", range(len(storage["waiting_customers"])), 
                                        format_func=lambda x: storage["waiting_customers"][x])
                
                new_name = st.text_input("Change Name to:", value=storage["waiting_customers"][edit_idx])
                
                c1, c2 = st.columns(2)
                if c1.button("✅ Update Name"):
                    if new_name.strip():
                        storage["waiting_customers"][edit_idx] = new_name.strip()
                        st.success("Name updated.")
                        st.rerun()
                
                if c2.button("🗑️ Remove from Queue"):
                    storage["waiting_customers"].pop(edit_idx)
                    st.rerun()
            else:
                st.info("The waiting list is currently empty.")

    # --- MANAGER DASHBOARD ---
    # --- MANAGER DASHBOARD ---
    elif st.session_state.role == "Manager":
        st.title("👔 Manager Assignment")
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
    elif st.session_state.role == "Sales":
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh Data"): st.rerun()
        
        my_cabin = st.selectbox("Select Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if not cust_name:
            st.warning(f"No customer in Cabin {my_cabin}.")
        else:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            
            st.success(f"Serving: {cust_name} | Assigned: {assigned_id}")

            # --- UNBLOCK REQUEST LOGIC (2 CHANCES) ---
            chances_used = storage["unblock_counts"].get(my_cabin, 0)
            st.write(f"Unblock Chances Used: **{chances_used}/2**")

            if chances_used < 2:
                req_id = st.text_input("Request Unblock for Unit ID:").upper()
                if st.button("Submit Request"):
                    if req_id:
                        storage["pending_requests"][my_cabin] = req_id
                        st.info(f"Request for {req_id} sent to Admin.")
            else:
                st.error("Maximum (2) unblock chances used for this customer.")

            st.write("---")

            search_id = st.session_state.get("search_id_input", "").upper()
            with st.expander("📁 Inventory Selection Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    # A unit is clickable ONLY IF it is the assigned one OR approved by admin
                    is_unlocked = (uid == assigned_id) or (uid in storage["approved_units"].get(my_cabin, []))
                    is_sold = uid in storage["sold_units"]
                    
                    label = f"🟡 {uid}" if is_unlocked else (f"⛔ SOLD" if is_sold else f"🔒 {uid}")
                    if grid_cols[idx % 6].button(label, key=f"btn_{uid}", disabled=not is_unlocked):
                        st.session_state.search_id_input = uid
                        st.rerun()

            if search_id:
                # [KEEP EXISTING COST SHEET & CALCULATE_NEGOTIATION LOGIC HERE]
                # ... (rest of the cost sheet display as provided previously)
                st.button("❌ Close / Release", on_click=lambda: st.session_state.update({"search_id_input": ""}))

                    # --- RESTORED ORIGINAL MONOSPACE COST SHEET ---
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
                            <div style="color:red; font-weight:bold; margin-top:10px;">Total Discount Availed: Rs. {format_indian_currency(res['Combined_Discount'])}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.write("")
                    col_act1, col_act2 = st.columns(2)
                    if col_act1.button("✅ Finalize & Send"):
                        pdf_bytes = create_pdf(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, "28/02/2026", use_p)
                        details = {"Unit No": search_id, "Customer Name": cust_name, "Total": format_indian_currency(res['Total'])}
                        if send_email(RECEIVER_EMAIL, pdf_bytes, f"{search_id}.pdf", details):
                            storage["sold_units"].add(search_id); storage["download_history"].append(details)
                            reset_cabin_session(my_cabin); st.session_state.search_id_input = ""; st.rerun()
                    
                    if col_act2.button("❌ Close / Release"):
                        st.session_state.search_id_input = ""; st.rerun()

    # --- ADMIN DASHBOARD ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Master Control")
        t1, t2, t3 = st.tabs(["Pending Requests", "Manage Unblocks", "System Overview"])

        with t1:
            st.subheader("Unblock Requests")
            if storage["pending_requests"]:
                for cab, unit in list(storage["pending_requests"].items()):
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"**Cabin {cab}** requests unit **{unit}**")
                    if col_b.button(f"Approve {unit}", key=f"app_{cab}"):
                        if cab not in storage["approved_units"]: storage["approved_units"][cab] = []
                        storage["approved_units"][cab].append(unit)
                        storage["unblock_counts"][cab] = storage["unblock_counts"].get(cab, 0) + 1
                        del storage["pending_requests"][cab]
                        st.success(f"Approved {unit} for Cabin {cab}")
                        st.rerun()
            else:
                st.info("No pending unblock requests.")

        with t2:
            st.subheader("Revoke Unblocked Units")
            active_unblocks = False
            for cab, units in storage["approved_units"].items():
                for u in units:
                    if u not in storage["sold_units"]: # Only revoke if not yet sold
                        active_unblocks = True
                        c1, c2 = st.columns([2, 1])
                        c1.write(f"Cabin {cab} has access to **{u}**")
                        if c2.button(f"Revoke {u}", key=f"rev_{cab}_{u}"):
                            storage["approved_units"][cab].remove(u)
                            # Optional: Decide if revoking restores the "chance" count
                            # storage["unblock_counts"][cab] -= 1 
                            st.rerun()
            if not active_unblocks:
                st.info("No active unblocked units to revoke.")
