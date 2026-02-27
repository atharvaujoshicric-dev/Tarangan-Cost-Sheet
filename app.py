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
        "opted_out_customers": [],
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
    sd_amt = round(raw_sd, -2) # Round to nearest 100
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
        pdf.set_font("Arial", 'B', 20); pdf.cell(190, 10, "TARANGAN", ln=True, align='C')
        pdf.set_font("Arial", 'B', 12); pdf.cell(190, 10, f"Customer: {cust_name}", ln=True)
        pdf.cell(190, 10, f"Unit: {unit_id} | Floor: {floor} | Parking: {parking_label}", ln=True)
        pdf.cell(95, 10, "Total Package", border=1); pdf.cell(95, 10, format_indian_currency(costs['Total']), border=1, ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time, cabin_key):
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
            storage["booths"][cabin_key] = None # AUTO-CLEAR CABIN
            st.session_state.search_id_input = ""
            if unit_id in storage["locks"]: del storage["locks"][unit_id]
            st.success("Unit Booked! Cabin is now Free.")
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

    # --- GRE ---
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        inventory = load_data()
        allotted_list = sorted(list(inventory['Customer Allotted'].dropna().unique()))
        
        st.subheader("Add Allotted Customer")
        name_sel = st.selectbox("Search/Select Allotted Name:", ["Select Name"] + allotted_list)
        if st.button("Add Allotted to Waiting List"):
            if name_sel != "Select Name":
                if name_sel.upper() not in [c.upper() for c in storage["waiting_customers"]]:
                    storage["waiting_customers"].append(name_sel); st.success(f"Added {name_sel}")
                else: st.warning("Already in queue.")
        
        st.write("---")
        st.subheader("Add New (Walk-in) Customer")
        new_name = st.text_input("Enter New Customer Name:").strip()
        if st.button("Add New Customer"):
            if new_name:
                if new_name.upper() not in [c.upper() for c in storage["waiting_customers"]]:
                    storage["waiting_customers"].append(new_name); st.success(f"Added New: {new_name}")
                else: st.warning("Name already in queue.")
            else: st.error("Please enter a name.")

    # --- MANAGER ---
    elif st.session_state.role == "Manager":
        st.title("👔 Stage 2: Manager Assignment")
        if st.button("🔄 Refresh"): st.rerun()
        col1, col2 = st.columns(2)
        if storage["waiting_customers"]:
            sel_c = col1.selectbox("Select Customer:", storage["waiting_customers"])
            sel_b = col1.selectbox("Cabin:", [b for b, v in storage["booths"].items() if v is None])
            if col1.button("Assign"):
                storage["booths"][sel_b] = sel_c
                storage["waiting_customers"].remove(sel_c); st.rerun()
        col2.table([{"Cabin": k, "Customer": v if v else "Free"} for k, v in storage["booths"].items()])

    # --- SALES ---
    elif st.session_state.role == "Sales":
        st.title("🏙️ Stage 3: Sales Portal")
        if st.button("🔄 Refresh"): st.rerun()
        my_cabin = st.selectbox("Select Cabin:", list("ABCDEFGHIJ"))
        cust_name = storage["booths"].get(my_cabin)
        
        if not cust_name:
            st.warning(f"No customer assigned to Cabin {my_cabin}.")
        else:
            inventory = load_data()
            token_row = inventory[inventory['Customer Allotted'].astype(str).str.contains(cust_name, case=False, na=False)]
            assigned_id = str(token_row['ID'].values[0]).upper() if not token_row.empty else "NONE"
            
            st.info(f"Serving: **{cust_name}** | Target Flat: **{assigned_id}**")

            if st.button("❌ Customer Opted Out"):
                storage["opted_out_customers"].append(cust_name)
                storage["booths"][my_cabin] = None
                st.error(f"{cust_name} marked as Opt-Out. Cabin cleared.")
                st.rerun()

            search_id = st.session_state.get("search_id_input", "").upper()
            with st.expander("📁 Inventory Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row in inventory.iterrows():
                    uid = str(row['ID']).upper()
                    is_sold = uid in storage["sold_units"]
                    is_busy = uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                    is_blocked = not (storage["admin_overrides"].get(my_cabin) or uid == assigned_id)
                    with grid_cols[idx % 6]:
                        if is_sold: lbl, dis = f"🟢 {uid}", True
                        elif is_busy: lbl, dis = f"🔴 BUSY", True
                        else: lbl, dis = f"🟡 {uid}", is_blocked
                        if st.button(lbl, key=f"btn_{uid}", use_container_width=True, disabled=dis):
                            st.session_state.search_id_input = uid; st.rerun()

            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]
                    storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
                    res = calculate_negotiation(clean_numeric(row.get('Agreement Value', 0)), 0, 0, st.checkbox("Parking"), False)
                    if st.button("📥 Download"): 
                        download_dialog(search_id, row.get('Floor','N/A'), "N/A", res, cust_name, "2026", False, "2026", my_cabin)
                    st.button("❌ Close", on_click=release_unit_callback, args=(search_id,))

    # --- ADMIN ---
    elif st.session_state.role == "Tarangan":
        st.title("🛠️ Admin Dashboard")
        t1, t2, t3 = st.tabs(["Requests", "Opt-Out List", "Reset"])
        with t1:
            for cabin, status in storage["admin_overrides"].items():
                if st.button(f"{'🚫 Revoke' if status else '✅ Approve'} Cabin {cabin}"):
                    storage["admin_overrides"][cabin] = not status; st.rerun()
        with t2:
            if storage["opted_out_customers"]:
                rev_c = st.selectbox("Revoke Opt-Out:", storage["opted_out_customers"])
                if st.button("Move back to Waiting Room"):
                    storage["waiting_customers"].append(rev_c)
                    storage["opted_out_customers"].remove(rev_c); st.rerun()
            else: st.info("No opt-outs.")
        with t3:
            if st.text_input("Password", type="password") == "Atharva Joshi":
                if st.button("⚠️ FULL RESET"): storage["locks"].clear(); storage["sold_units"].clear(); st.rerun()
