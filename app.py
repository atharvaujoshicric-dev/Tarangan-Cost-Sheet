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
        "admin_overrides": {letter: False for letter in "ABCDEFGHIJ"}, 
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
    parking_label = "Parking Under Building" if use_parking else "Parking Outside Building"
    for copy_label in ["Customer's Copy", "Sales Copy"]:
        pdf.add_page()
        pdf.set_font("Arial", 'I', 8); pdf.set_xy(10, 5); pdf.cell(0, 10, copy_label, ln=True)
        pdf.set_y(20); pdf.set_font("Arial", 'B', 20); pdf.cell(190, 10, "TARANGAN", ln=True, align='C')
        pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "COST SHEET", ln=True, align='C')
        pdf.set_font("Arial", '', 10); pdf.cell(190, 10, f"Date: {date_str}", ln=True, align='R')
        pdf.set_font("Arial", 'B', 12); pdf.cell(190, 10, f"Customer: {cust_name}", ln=True)
        pdf.cell(190, 10, f"Unit: {unit_id} | Floor: {floor} | Carpet: {carpet} sqft", ln=True)
        pdf.set_font("Arial", 'I', 10); pdf.cell(190, 10, f"Parking: {parking_label}", ln=True)
        pdf.ln(5)
        pdf.cell(95, 10, "Description", border=1, align='C'); pdf.cell(95, 10, "Amount (Rs.)", border=1, ln=True, align='C')
        pdf.set_font("Arial", '', 11)
        pdf.cell(95, 10, "Agreement Value", border=1, align='C'); pdf.cell(95, 10, format_indian_currency(costs['Final Agreement']), border=1, ln=True, align='C')
        pdf.cell(95, 10, f"Stamp Duty ({int(costs['SD_Pct'])}%)*", border=1, align='C'); pdf.cell(95, 10, format_indian_currency(costs['Stamp Duty']), border=1, ln=True, align='C')
        pdf.cell(95, 10, f"GST ({int(costs['GST_Pct'])}%)", border=1, align='C'); pdf.cell(95, 10, format_indian_currency(costs['GST']), border=1, ln=True, align='C')
        pdf.cell(95, 10, "Registration", border=1, align='C'); pdf.cell(95, 10, format_indian_currency(costs['Registration']), border=1, ln=True, align='C')
        pdf.set_font("Arial", 'B', 13); pdf.cell(95, 12, "TOTAL", border=1, align='C'); pdf.cell(95, 12, format_indian_currency(costs['Total']), border=1, ln=True, align='C')
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

# --- 6. LOGIN ---
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

    # --- GRE DASHBOARD ---
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        tab_add, tab_edit = st.tabs(["Add Customer", "Manage Waiting List"])
        with tab_add:
            with st.form("gre_add"):
                name = st.text_input("Customer Name").strip()
                if st.form_submit_button("Submit"):
                    if name and name.upper() not in [c.upper() for c in storage["waiting_customers"]]:
                        storage["waiting_customers"].append(name); st.success(f"Added {name}")
                    else: st.warning("Error.")
        with tab_edit:
            if storage["waiting_customers"]:
                sel = st.selectbox("Select Customer:", storage["waiting_customers"])
                new_n = st.text_input("Edit Name:", value=sel)
                c1, c2 = st.columns(2)
                if c1.button("Update"):
                    idx = storage["waiting_customers"].index(sel)
                    storage["waiting_customers"][idx] = new_n; st.rerun()
                if c2.button("Delete"):
                    storage["waiting_customers"].remove(sel); st.rerun()

    # --- MANAGER DASHBOARD ---
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

    # --- SALES DASHBOARD ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh Data"): st.rerun()
        my_cabin = st.selectbox("Select Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if not cust_name:
            st.warning(f"No customer assigned to Cabin {my_cabin}.")
        else:
            inventory = load_data()
            
            # --- TOKEN TO ID LOGIC ---
            # 1. Look for row where 'Token Number' matches current customer name
            # 2. Get the 'ID' (Flat Number) from that row
            token_row = inventory[inventory.iloc[:, 1].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            
            st.info(f"Serving: **{cust_name}** | Target Flat: **{assigned_id}**")

            # Admin Override check
            has_override = storage["admin_overrides"].get(my_cabin, False)
            if not has_override:
                if st.button("🔑 Request Access to View All Units"):
                    log_activity("Sales", "OVERRIDE_REQ", f"Cabin {my_cabin} requested universal access.")
                    st.toast("Request sent to Admin.")

            search_id = st.session_state.get("search_id_input", "").upper()
            
            # Inventory Grid
            with st.expander("📁 Inventory Selection Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    is_sold = uid in storage["sold_units"]
                    is_busy = uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                    
                    # LOGIC: Buttons are disabled unless it is the assigned_id OR admin override is on
                    is_blocked = True
                    if has_override: is_blocked = False
                    if uid == assigned_id: is_blocked = False

                    with grid_cols[idx % 6]:
                        if is_sold: lbl, btn_disabled = f"🟢 {uid}", True
                        elif is_busy: lbl, btn_disabled = f"🔴 BUSY", True
                        else:
                            lbl, btn_disabled = f"🟡 {uid}", is_blocked
                        
                        if st.button(lbl, key=f"btn_{uid}", use_container_width=True, disabled=btn_disabled):
                            st.session_state.search_id_input = uid
                            st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
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
                    park_label = "Parking Under Building" if use_p else "Parking Outside Building"

                    st.markdown(f"""
                        <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                            <div style="text-align:right;">Date: {ist_now.strftime("%d/%m/%Y")}</div>
                            <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN</h2>
                            <p><b>Customer:</b> {cust_name}</p>
                            <p><b>Unit:</b> {search_id} | <b>Parking:</b> {park_label}</p>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Agreement</span><span>Rs. {format_indian_currency(res['Final Agreement'])}</span></div>
                            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    col_d, col_r = st.columns(2)
                    with col_d:
                        if st.button("📥 Download PDF & Block"): 
                            download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, ist_now.strftime("%d/%m/%Y"), use_p, ist_now.strftime("%d/%m/%Y %H:%M:%S"))
                    with col_r: st.button("❌ Close", on_click=release_unit_callback, args=(search_id,))

    # --- ADMIN ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Dashboard")
        t1, t2, t3 = st.tabs(["Requests", "Management", "Reset"])
        
        with t1:
            st.subheader("Sales Access Overrides")
            for cabin, status in storage["admin_overrides"].items():
                if not status:
                    if st.button(f"✅ Approve All Units for Cabin {cabin}"):
                        storage["admin_overrides"][cabin] = True
                        st.rerun()
                else:
                    if st.button(f"🚫 Revoke Access for Cabin {cabin}"):
                        storage["admin_overrides"][cabin] = False
                        st.rerun()
        
        with t2:
            st.dataframe(pd.DataFrame(storage["download_history"]), use_container_width=True)
            unit_to_unblock = st.selectbox("Restore Unit:", list(storage["sold_units"]))
            if st.button("Unblock"): 
                storage["sold_units"].remove(unit_to_unblock)
                st.rerun()

        with t3:
            reset_p = st.text_input("Reset Password:", type="password")
            if st.button("⚠️ FULL RESET"):
                if reset_p == "Atharva Joshi":
                    storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear()
                    storage["waiting_customers"].clear(); storage["unit_hits"].clear()
                    storage["booths"] = {letter: None for letter in "ABCDEFGHIJ"}
                    st.success("System wiped."); st.rerun()
