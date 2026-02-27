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
    # Added 'booths' for Stage 2/3 and 'hits' for Hot Selling
    return {
        "locks": {}, 
        "sold_units": set(), 
        "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"}, # Stage 2 storage
        "unit_hits": {} # For Hot Selling tracking
    }

storage = get_global_storage()

# --- 2. CONFIG & GOOGLE SHEET ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
encoded_tab_name = urllib.parse.quote(TAB_NAME)
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_tab_name}"

# --- 3. BACKEND LOGIC (Existing Functions preserved) ---
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
        "Final Agreement": final_agreement,
        "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100,
        "Registration": REGISTRATION,
        "Total": int(total_package),
        "Combined_Discount": int(pkg_discount + park_discount)
    }

# --- 4. PDF GENERATION (Preserved) ---
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
        tc_lines = ["1. Advocate charges will be Rs. 15,000/-.", "2. Agreement to be executed & registered within 15 days from the date of booking.", "3. The total cost mentioned here is all inclusive of GST, Registration, Stamp Duty and Legal charges", "4. GST, Stamp Duty, Registration and all applicable government charges are as per the current rates, and in future may change as per government notification which would be borne by the customer.", "5. Above areas are shown in square feet only to make it easy for the purchaser to understand. The sale of the said unit is on the basis of RERA carpet area only.", "6. All legal documents will be executed in square meter only.", "7. Subject to PCMC jurisdiction.", "8. Society Maintenance at Rs. 3 per sq.ft. per month for 2 years and will be taken at the time of possession.", "9. Loan facility available from all leading banks and home loan sanctioning is customers responsibility, developer however will assist in the process.", "10. The promoters reserve the right to change the above prices and the offer given at any time without prior notice. No verbal commitments to be accepted post booking.", "11. Booking is non-transferable.", "12. The information on this paper is provided in good faith and does not constitute part of the contract.", "13. Government taxes will be applicable at actual. Also, any other taxes not mentioned herein if levied later would be payable at actuals by the purchaser.", "14. Documents required: PAN Card, Adhar Card, Photocopy.", "15. If an external bank is opted for loan processing, an additional charge of Rs. 25,000/- shall be applicable and payable by the purchaser."]
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

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide") # Changed to wide for grid

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# --- 6. POP-UP DIALOG & CALLBACKS (Preserved) ---
@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time):
    st.write(f"Confirming booking for **Unit {unit_id}**")
    sales_name = st.text_input("Enter Sales Person Name:")
    if st.button("Confirm & Download"):
        if not sales_name.strip():
            st.error("Please enter Sales Person Name to proceed.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking)
            storage["download_history"].append({
                "Timestamp (IST)": ist_log_time, "Sales Person": sales_name, "Login User": st.session_state.get('user_id', 'Unknown'),
                "Flat ID": unit_id, "Customer": cust_name if cust_name else "N/A", "TOTAL": format_indian_currency(costs['Total'])
            })
            storage["sold_units"].add(unit_id)
            st.success("Unit Blocked Successfully!")
            st.download_button(label="📥 Click here to save PDF", data=pdf_bytes, file_name=f"Tarangan_{unit_id}.pdf", mime="application/pdf")

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]:
        del storage["locks"][unit_to_release]

# --- 7. LOGIN ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Login"):
        if (u == "Tarangan" and p == "Tarangan@0103") or (u.lower().startswith("user") and p == "Sales@2026"):
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, ("admin" if u == "Tarangan" else "user"), u
            st.rerun()
else:
    # Sidebar Role Selection for Stage logic
    st.sidebar.title(f"User: {st.session_state.user_id}")
    app_mode = st.sidebar.radio("Navigate to Stage:", ["Stage 1: GRE", "Stage 2: Manager", "Stage 3: Sales Portal", "Admin Records"])
    
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False; st.rerun()

    # --- STAGE 1: GRE ---
    if app_mode == "Stage 1: GRE":
        st.title("📝 Stage 1: GRE Entry")
        with st.form("gre_form"):
            c_name = st.text_input("Customer Name")
            if st.form_submit_button("Submit to Waiting List"):
                if "waiting_customers" not in storage: storage["waiting_customers"] = []
                storage["waiting_customers"].append(c_name)
                st.success(f"Added {c_name} to queue.")

    # --- STAGE 2: MANAGER ---
    elif app_mode == "Stage 2: Manager":
        st.title("👔 Stage 2: Manager Assignment")
        if "waiting_customers" in storage and storage["waiting_customers"]:
            selected_cust = st.selectbox("Assign Customer:", storage["waiting_customers"])
            free_booths = [b for b, v in storage["booths"].items() if v is None]
            selected_booth = st.selectbox("To Cabin:", free_booths)
            
            if st.button("Assign to Cabin"):
                storage["booths"][selected_booth] = selected_cust
                storage["waiting_customers"].remove(selected_cust)
                st.success(f"Assigned {selected_cust} to Cabin {selected_booth}")
                st.rerun()
        else:
            st.info("No customers in waiting list.")
        
        st.write("### Current Cabin Status")
        st.table([{"Cabin": k, "Customer": v if v else "Empty"} for k, v in storage["booths"].items()])
        if st.button("Clear All Cabins"):
            storage["booths"] = {letter: None for letter in "ABCDEFGHIJ"}
            st.rerun()

    # --- STAGE 3: SALES PORTAL ---
    elif app_mode == "Stage 3: Sales Portal":
        st.title("🏙️ Stage 3: Sales Portal")
        
        # Cabin Selection (Auto-fetches customer)
        my_cabin = st.selectbox("Select Your Cabin:", list(storage["booths"].keys()))
        current_customer = storage["booths"].get(my_cabin, "Unknown")
        st.info(f"Serving Customer: **{current_customer}** at Cabin **{my_cabin}**")

        inventory = load_data()
        
        # --- HOT SELLING LOGIC ---
        hot_units = sorted(storage["unit_hits"].items(), key=lambda x: x[1], reverse=True)[:3]
        if hot_units:
            st.subheader("🔥 Hot Selling Units")
            hc1, hc2, hc3 = st.columns(3)
            for i, (uid, hits) in enumerate(hot_units):
                with [hc1, hc2, hc3][i]:
                    st.error(f"Unit {uid} ({hits} Views)")

        # --- GRID VIEW ---
        st.subheader("Inventory Grid")
        cols = st.columns(6)
        for idx, row in inventory.iterrows():
            uid = str(row['ID'])
            is_sold = uid in storage["sold_units"]
            # Check if someone else is viewing this flat
            is_busy = uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
            
            with cols[idx % 6]:
                if is_sold:
                    st.button(f"🔴 {uid}\nSOLD", key=f"btn_{uid}", disabled=True, use_container_width=True)
                elif is_busy:
                    st.button(f"🟡 {uid}\nBUSY", key=f"btn_{uid}", disabled=True, use_container_width=True)
                else:
                    if st.button(f"🟢 {uid}\nFREE", key=f"btn_{uid}", use_container_width=True):
                        st.session_state.search_id_input = uid
                        # Increment Hits for Hot Selling
                        storage["unit_hits"][uid] = storage["unit_hits"].get(uid, 0) + 1
                        st.rerun()

        # --- SELECTION & CALCULATION ---
        search_id = st.text_input("🔍 Selected Flat ID:", key="search_id_input").strip().upper()
        ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        today_str, today_full_log = ist_now.strftime("%d/%m/%Y"), ist_now.strftime("%d/%m/%Y %H:%M:%S")

        if len(search_id) > 2:
            if search_id in storage["sold_units"]: st.error("Unit just got SOLD."); st.stop()
            if search_id in storage["locks"] and storage["locks"][search_id] != st.runtime.scriptrunner.get_script_run_ctx().session_id:
                st.warning("⚠️ This unit is currently being viewed by another salesperson."); st.stop()
            
            # Lock the unit to this session
            storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
            
            match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
            if not match.empty:
                row = match.iloc[0]
                # Calculation UI (Preserved)
                base_agr = clean_numeric(row.get('Agreement Value', 0))
                c1, c2, c3 = st.columns(3)
                with c1:
                    use_d = st.checkbox("Discount")
                    d_val = st.number_input("Amt:", value=0, step=1000) if use_d else 0
                with c2:
                    use_p = st.checkbox("Parking")
                    p_d_val = st.number_input("Park Disc:", value=0, step=1000) if use_p else 0
                with c3: is_f = st.checkbox("Female")
                
                res = calculate_negotiation(base_agr, d_val, p_d_val, use_p, is_f)
                
                # HTML Visual (Preserved)
                st.markdown(f"""
                    <div style="background:white; padding:20px; border:2px solid black; color:black;">
                        <h2 style="text-align:center;">TARANGAN COST SHEET</h2>
                        <p><b>Customer:</b> {current_customer}</p>
                        <p><b>Unit:</b> {search_id} | <b>Floor:</b> {row.get('Floor','N/A')}</p>
                        <hr>
                        <p>Total: Rs. {format_indian_currency(res['Total'])}</p>
                    </div>
                """, unsafe_allow_html=True)
                
                col_d, col_r = st.columns(2)
                with col_d:
                    if st.button("📥 Download & Block"):
                        download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET','N/A'), res, current_customer, today_str, use_p, today_full_log)
                with col_r:
                    if st.button("❌ Release Unit"):
                        release_unit_callback(search_id)
                        st.rerun()

    # --- ADMIN RECORDS ---
    elif app_mode == "Admin Records" and st.session_state.role == "admin":
        st.title("🛠️ Admin Records")
        if storage["download_history"]:
            st.dataframe(pd.DataFrame(storage["download_history"]))
            if st.button("⚠️ Global Reset"):
                storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear(); storage["unit_hits"].clear()
                st.rerun()
