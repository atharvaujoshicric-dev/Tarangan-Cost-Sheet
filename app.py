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
        "unit_hits": {},
        "waiting_customers": [],
        "activity_log": [] # New tracking for Admin Excel
    }

storage = get_global_storage()

def log_activity(user, action, details):
    ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    storage["activity_log"].append({
        "Timestamp": ist_now.strftime("%d/%m/%Y %H:%M:%S"),
        "User": user,
        "Action": action,
        "Details": details
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
    sd_amt = final_agreement * sd_pct
    gst_amt = final_agreement * gst_pct
    total_package = final_agreement + sd_amt + gst_amt + REGISTRATION
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100, "Registration": REGISTRATION,
        "Total": int(total_package), "Combined_Discount": int(pkg_discount + park_discount)
    }

# --- 4. PDF GENERATION (Kept Same) ---
def create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking):
    pdf = FPDF()
    for copy_label in ["Customer's Copy", "Sales Copy"]:
        pdf.add_page()
        pdf.set_font("Arial", 'I', 8); pdf.set_xy(10, 5); pdf.cell(0, 10, copy_label, ln=True)
        pdf.set_y(20); pdf.set_font("Arial", 'B', 20); pdf.cell(190, 10, "TARANGAN", ln=True, align='C')
        pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "COST SHEET", ln=True, align='C')
        pdf.set_font("Arial", '', 10); pdf.cell(190, 10, f"Date: {date_str}", ln=True, align='R')
        pdf.set_font("Arial", 'B', 11); pdf.cell(190, 10, f"Customer: {cust_name}", ln=True)
        pdf.cell(190, 10, f"Unit: {unit_id} | Floor: {floor} | Carpet: {carpet} sqft", ln=True)
        pdf.ln(5)
        pdf.cell(95, 10, "Description", border=1); pdf.cell(95, 10, "Amount (Rs.)", border=1, ln=True)
        pdf.set_font("Arial", '', 11)
        pdf.cell(95, 10, "Agreement Value", border=1); pdf.cell(95, 10, format_indian_currency(costs['Final Agreement']), border=1, ln=True)
        pdf.cell(95, 10, f"Stamp Duty ({int(costs['SD_Pct'])}%)", border=1); pdf.cell(95, 10, format_indian_currency(costs['Stamp Duty']), border=1, ln=True)
        pdf.cell(95, 10, f"GST ({int(costs['GST_Pct'])}%)", border=1); pdf.cell(95, 10, format_indian_currency(costs['GST']), border=1, ln=True)
        pdf.cell(95, 10, "Registration", border=1); pdf.cell(95, 10, format_indian_currency(costs['Registration']), border=1, ln=True)
        pdf.set_font("Arial", 'B', 12); pdf.cell(95, 12, "TOTAL", border=1); pdf.cell(95, 12, format_indian_currency(costs['Total']), border=1, ln=True)
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
            storage["download_history"].append({"Timestamp": ist_log_time, "Sales": sales_name, "Unit": unit_id, "Customer": cust_name, "Total": costs['Total']})
            storage["sold_units"].add(unit_id)
            log_activity(st.session_state.user_id, "BOOKING", f"Unit {unit_id} booked for {cust_name}")
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
            st.session_state.authenticated = True
            st.session_state.role = u.lower() if u != "Tarangan" else "admin"
            st.session_state.user_id = u
            log_activity(u, "LOGIN", "User logged into the portal")
            st.rerun()
        else: st.error("Invalid credentials.")
else:
    if st.sidebar.button("Logout"): 
        log_activity(st.session_state.user_id, "LOGOUT", "User logged out")
        st.session_state.authenticated = False; st.rerun()

    # --- STAGE 1: GRE ---
    if st.session_state.role == "gre":
        st.title("📝 Stage 1: GRE Entry")
        with st.form("gre_entry"):
            name = st.text_input("Customer Name").strip()
            if st.form_submit_button("Add to Queue"):
                if name and name.upper() not in [c.upper() for c in storage["waiting_customers"]]:
                    storage["waiting_customers"].append(name)
                    log_activity("GRE", "QUEUE_ADD", f"Added {name}")
                    st.success(f"Added {name}")
                else: st.warning("Name empty or already exists.")

    # --- STAGE 2: MANAGER ---
    elif st.session_state.role == "manager":
        st.title("👔 Stage 2: Manager Assignment")
        col1, col2 = st.columns(2)
        with col1:
            if storage["waiting_customers"]:
                sel_c = st.selectbox("Customer:", storage["waiting_customers"])
                sel_b = st.selectbox("Cabin:", [b for b, v in storage["booths"].items() if v is None])
                if st.button("Assign to Cabin"):
                    storage["booths"][sel_b] = sel_c
                    storage["waiting_customers"].remove(sel_c)
                    log_activity("Manager", "ASSIGN", f"{sel_c} -> Cabin {sel_b}")
                    st.rerun()
        with col2:
            st.write("Current Cabins:", storage["booths"])

    # --- STAGE 3: SALES ---
    elif st.session_state.role == "sales":
        st.title("🏙️ Stage 3: Sales Portal")
        my_cabin = st.selectbox("Select Your Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if cust_name:
            st.success(f"Client: {cust_name}")
            inventory = load_data()
            hot_list = [u for u, c in sorted(storage["unit_hits"].items(), key=lambda x: x[1], reverse=True)[:3]]
            
            # --- GRID COLLAPSE LOGIC ---
            search_id = st.session_state.get("search_id_input", "").upper()
            
            with st.expander("📂 View Inventory Grid", expanded=(search_id == "")):
                grid_cols = st.columns(8)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID'])
                    is_sold = uid in storage["sold_units"]
                    is_busy = uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                    is_hot = uid in hot_list
                    
                    # Color Logic
                    color = "secondary" # Default
                    if is_sold: color = "primary" # Greenish in Streamlit default or handled by label
                    
                    with grid_cols[idx % 8]:
                        btn_label = f"{uid}"
                        if is_sold: btn_label = f"✅ {uid}"
                        elif is_busy: btn_label = f"🟡 {uid}"
                        elif is_hot: btn_label = f"🔥 {uid}"

                        if st.button(btn_label, key=f"g_{uid}", use_container_width=True, disabled=is_sold or is_busy):
                            st.session_state.search_id_input = uid
                            storage["unit_hits"][uid] = storage["unit_hits"].get(uid, 0) + 1
                            log_activity("Sales", "VIEW_UNIT", f"Viewing {uid}")
                            st.rerun()

            if search_id:
                st.write("---")
                st.subheader(f"Cost Sheet: Unit {search_id}")
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
                    
                    # ON-SCREEN COST SHEET
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)))
                    
                    # Displaying visual Table
                    st.markdown(f"""
                    <div style="background-color:#f9f9f9; padding:20px; border-radius:10px; border:1px solid #ddd; color:black;">
                        <h2 style='text-align:center;'>TARANGAN</h2>
                        <table style="width:100%">
                            <tr><td><b>Customer:</b> {cust_name}</td><td style='text-align:right;'><b>Unit:</b> {search_id}</td></tr>
                            <tr><td><b>Floor:</b> {row.get('Floor','N/A')}</td><td style='text-align:right;'><b>Carpet:</b> {row.get('CARPET','N/A')} sqft</td></tr>
                        </table>
                        <hr>
                        <div style="display:flex; justify-content:space-between;"><span>Agreement Value</span><span>₹ {format_indian_currency(res['Final Agreement'])}</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>Stamp Duty ({int(res['SD_Pct'])}%)</span><span>₹ {format_indian_currency(res['Stamp Duty'])}</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>GST ({int(res['GST_Pct'])}%)</span><span>₹ {format_indian_currency(res['GST'])}</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>Registration</span><span>₹ {format_indian_currency(res['Registration'])}</span></div>
                        <div style="display:flex; justify-content:space-between; font-size:20px; font-weight:bold; margin-top:10px; border-top:2px solid black;"><span>TOTAL</span><span>₹ {format_indian_currency(res['Total'])}</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.ln(2)
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📥 Download & Book Unit"):
                            download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, cust_name, "2026", False, "2026")
                    with c2:
                        st.button("❌ Close / Release", on_click=release_unit_callback, args=(search_id,))

    # --- ADMIN ---
    elif st.session_state.role == "admin":
        st.title("🛠️ Admin Master Control")
        t1, t2 = st.tabs(["Activity Log (Excel Track)", "System Management"])
        
        with t1:
            if storage["activity_log"]:
                df_log = pd.DataFrame(storage["activity_log"])
                st.dataframe(df_log, use_container_width=True)
                
                # Excel Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_log.to_excel(writer, index=False, sheet_name='Activity')
                st.download_button("📊 Export Activity to Excel", output.getvalue(), "Tarangan_Activity_Log.xlsx")
            else: st.info("No activity logged.")

        with t2:
            if st.button("Clear All Locks"): storage["locks"].clear(); st.rerun()
            if st.button("RESET ENTIRE SYSTEM"):
                storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear()
                storage["activity_log"].clear(); storage["waiting_customers"].clear()
                storage["booths"] = {letter: None for letter in "ABCDEFGHIJ"}
                st.rerun()
