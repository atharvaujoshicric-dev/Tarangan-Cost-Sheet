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
        st.title("📝 Stage 1: GRE Entry")
        
        # 1. Entry Form
        with st.form("gre_add", clear_on_submit=True):
            st.subheader("Add Walk-in Customer")
            name = st.text_input("Customer Name").strip()
            submit = st.form_submit_button("Submit")
            
            if submit:
                if not name:
                    st.error("Please enter a name.")
                else:
                    # CHECK 1: Is the name in the Waiting List?
                    in_waiting = name.upper() in [c.upper() for c in storage["waiting_customers"]]
                    
                    # CHECK 2: Is the name already in a Sales Cabin (Booths)?
                    in_cabins = name.upper() in [str(v).upper() for v in storage["booths"].values() if v is not None]

                    if in_waiting:
                        st.warning(f"DUPLICATE: '{name}' is already in the Waiting List.")
                    elif in_cabins:
                        st.warning(f"DUPLICATE: '{name}' is already inside a Sales Cabin.")
                    else:
                        # Success: Add to list
                        storage["waiting_customers"].append(name)
                        log_activity(st.session_state.user_id, "GRE_ENTRY", f"Added walk-in: {name}")
                        st.success(f"Customer '{name}' added to waiting list!")
                        st.rerun()

        st.divider()

        # 2. View/Manage Waiting List
        st.subheader("📋 Current Waiting List")
        if storage["waiting_customers"]:
            # Display as a list with a delete option
            for i, cust in enumerate(storage["waiting_customers"]):
                col1, col2 = st.columns([4, 1])
                col1.write(f"{i+1}. **{cust}**")
                if col2.button("🗑️ Remove", key=f"del_{i}"):
                    storage["waiting_customers"].remove(cust)
                    st.rerun()
        else:
            st.info("No customers currently waiting.")

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
        # INITIALIZE VARIABLES TO PREVENT NAMEERROR
        if "search_id_input" not in st.session_state:
            st.session_state.search_id_input = ""
        
        search_id = st.session_state.search_id_input  # Define search_id here
        ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh Data"): st.rerun()
        
        my_cabin = st.selectbox("Select Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if cust_name:
            inventory = load_data()
            # ... [Rest of your inventory grid logic] ...

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
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
                        pdf_bytes = create_pdf(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, ist_now.strftime("%d/%m/%Y"), use_p)
                        
                        # --- CAPTURE ALL DATA FOR REPORT ---
                        details = {
                            "Date": ist_now.strftime("%d/%m/%Y %H:%M"),
                            "Sales Person": st.session_state.role, # Or specific name if you have it
                            "Cabin": my_cabin,
                            "Customer Name": cust_name,
                            "Unit No": search_id,
                            "Floor": row.get('Floor','N/A'),
                            "Carpet Area": row.get('CARPET','N/A'),
                            "Agreement Value": res['Final Agreement'],
                            "Stamp Duty": res['Stamp Duty'],
                            "GST": res['GST'],
                            "Registration": res['Registration'],
                            "Total Package": res['Total'],
                            "Discount Given": res['Combined_Discount'],
                            "Parking": "Yes" if use_p else "No"
                        }
                        
                        if send_email(RECEIVER_EMAIL, pdf_bytes, f"{search_id}.pdf", details):
                            storage["sold_units"].add(search_id)
                            storage["download_history"].append(details) # Saves the full dictionary
                            reset_cabin_session(my_cabin)
                            st.session_state.search_id_input = ""
                            st.success("Booking Confirmed & Email Sent!")
                            st.rerun()
                
                if col_act2.button("❌ Close / Release"):
                    st.session_state.search_id_input = ""; st.rerun()

    # --- ADMIN DASHBOARD ---
    # --- ADMIN ---
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
            # [Keep your existing inventory unblock logic here]
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
