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
    return {"locks": {}, "sold_units": set(), "download_history": []}

storage = get_global_storage()

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
        "Final Agreement": final_agreement,
        "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100,
        "Registration": REGISTRATION,
        "Total": int(total_package),
        "Combined_Discount": int(pkg_discount + park_discount)
    }

# --- 4. PDF GENERATION ---
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
        rows = [["Agreement Value", format_indian_currency(costs['Final Agreement'])], [f"Stamp Duty ({int(costs['SD_Pct'])}%)", format_indian_currency(costs['Stamp Duty'])], [f"GST ({int(costs['GST_Pct'])}%)", format_indian_currency(costs['GST'])], ["Registration", format_indian_currency(costs['Registration'])]]
        for r in rows:
            pdf.cell(95, 10, r[0], border=1, align='C'); pdf.cell(95, 10, r[1], border=1, ln=True, align='C')
        pdf.set_font("Arial", 'B', 13); pdf.cell(95, 12, "ALL INCLUSIVE TOTAL", border=1, align='C'); pdf.cell(95, 12, format_indian_currency(costs['Total']), border=1, ln=True, align='C')
        try:
            words = num2words(costs['Total'], lang='en_IN').title().replace(",", "")
            pdf.set_font("Arial", 'B', 9); pdf.ln(2); pdf.multi_cell(190, 8, f"Amount in words: Rupees {words} Only")
        except: pass
        pdf.ln(2); pdf.set_font("Arial", 'B', 8); pdf.cell(0, 5, "TERMS & CONDITIONS:", ln=True); pdf.set_font("Arial", '', 6.0)
        tc_lines = ["1. Advocate charges Rs. 15,000/-.", "2. Execution within 15 days.", "3. Total cost includes GST/SD/Reg.", "14. Docs: PAN, Adhar."]
        for line in tc_lines: pdf.multi_cell(0, 3.2, line)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

st.markdown("""
    <style>
    /* COMPACT VIEW TO AVOID SCROLLING */
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    
    /* UNIVERSAL BOX SIZE FOR BUTTONS AND REFUGE */
    .stButton>button, .refuge-box {
        width: 100% !important;
        height: 2.3em !important;
        padding: 0px !important;
        font-size: 13px !important;
        border-radius: 5px !important;
        margin-bottom: 5px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-weight: bold !important;
    }

    /* SOLD - Green */
    div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
        background-color: #28a745 !important; color: white !important; border: none !important;
    }
    
    /* BUSY - Yellow */
    div[data-testid="stHorizontalBlock"] button:disabled:not(.refuge-box) {
        background-color: #ffc107 !important; color: black !important; opacity: 1 !important; border: none !important;
    }

    /* REFUGE - Grey (Strictly same size via CSS) */
    .refuge-box {
        background-color: #343a40 !important;
        color: #777 !important;
        border: 1px solid #222 !important;
        cursor: not-allowed;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=2)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        df.columns = [str(c).strip() for c in df.columns]
        df['ID'] = df['ID'].astype(str).str.strip().str.upper()
        return df
    except:
        return pd.DataFrame(columns=['ID', 'Agreement Value', 'CARPET', 'Floor'])

# --- 6. POP-UP DIALOG & CALLBACKS ---
@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time):
    st.write(f"Confirming booking for **Unit {unit_id}**")
    sales_name = st.text_input("Enter Sales Person Name:")
    if st.button("Confirm & Download"):
        if not sales_name.strip():
            st.error("Please enter Sales Person Name to proceed.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking)
            storage["download_history"].append({"Timestamp (IST)": ist_log_time, "Sales Person": sales_name, "Login User": st.session_state.get('user_id', 'Unknown'), "Flat ID": unit_id, "Customer": cust_name if cust_name else "N/A", "TOTAL": format_indian_currency(costs['Total'])})
            storage["sold_units"].add(unit_id)
            if unit_id in storage["locks"]: del storage["locks"][unit_id]
            st.success("Blocked!")
            st.download_button(label="📥 Download PDF", data=pdf_bytes, file_name=f"Tarangan_{unit_id}.pdf")
            if st.button("Close"): 
                st.session_state.selected_unit = None
                st.rerun()

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]: del storage["locks"][unit_to_release]
    st.session_state.selected_unit = None

# --- 7. LOGIN & LOGIC ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'selected_unit' not in st.session_state: st.session_state.selected_unit = None

REFUGE_FLATS = ["A-705", "A-1205", "705", "1205"]

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Login"):
        if (u == "Tarangan" and p == "Tarangan@0103") or (u.lower().startswith("user") and p == "Sales@2026"):
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, ("admin" if u == "Tarangan" else "user"), u
            st.rerun()
else:
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False; st.rerun()

    if st.session_state.role == "admin":
        st.title("🛠️ Admin Dashboard")
        blocked = list(storage["sold_units"])
        uid = st.selectbox("Unblock Unit", [""] + blocked)
        if uid and st.button("Unblock"): 
            storage["sold_units"].remove(uid)
            st.rerun()
    else:
        # --- SALES PORTAL TOGGLE ---
        if st.session_state.selected_unit is None:
            st.title("🏙️ Tarangan Sales Portal")
            
            # Compact Legend
            l_cols = st.columns(4)
            l_cols[0].markdown("🟩 **Sold**")
            l_cols[1].markdown("🟨 **Busy**")
            l_cols[2].markdown("⬜ **Available**")
            l_cols[3].markdown("⬛ **Refuge**")
            
            inventory = load_data()
            
            # GRID: 13 Floors x 6 Units
            for f in range(13, 0, -1):
                cols = st.columns(6)
                for i in range(1, 7):
                    unit_id = f"A-{f}{i:02d}"
                    is_sold = unit_id in storage["sold_units"]
                    is_busy = unit_id in storage["locks"] and storage["locks"][unit_id] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                    is_refuge = unit_id in REFUGE_FLATS

                    with cols[i-1]:
                        if is_refuge:
                            st.markdown(f'<div class="refuge-box">{unit_id}</div>', unsafe_allow_html=True)
                        elif is_sold:
                            st.button(unit_id, key=f"btn_{unit_id}", type="primary", disabled=True)
                        elif is_busy:
                            st.button(unit_id, key=f"btn_{unit_id}", disabled=True)
                        else:
                            if st.button(unit_id, key=f"btn_{unit_id}"):
                                st.session_state.selected_unit = unit_id
                                st.rerun()
        
        else:
            # --- COST SHEET SCREEN (Original UI logic) ---
            search_id = st.session_state.selected_unit
            storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
            inventory = load_data()
            match = inventory[inventory['ID'] == search_id]
            
            st.subheader(f"📍 Unit: {search_id}")
            if st.button("⬅️ Back to Flats"):
                release_unit_callback(search_id)
                st.rerun()
            
            cust_name = st.text_input("👤 Customer Name:")
            ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            today_str, today_full_log = ist_now.strftime("%d/%m/%Y"), ist_now.strftime("%d/%m/%Y %H:%M:%S")

            row = match.iloc[0] if not match.empty else None
            base_agr = clean_numeric(row.get('Agreement Value', 0)) if row is not None else 0
            carpet_area = row.get('CARPET','N/A') if row is not None else "N/A"
            floor_txt = row.get('Floor','N/A') if row is not None else search_id.split('-')[1][:-2]

            c1, c2, c3 = st.columns(3)
            with c1:
                use_d = st.checkbox("Discount")
                d_val = st.number_input("Amt:", value=0, step=1000) if use_d else 0
            with c2:
                use_p = st.checkbox("Parking")
                p_d_val = st.number_input("Park Disc:", value=0, step=1000) if use_p else 0
            with c3: is_f = st.checkbox("Female")
            
            res = calculate_negotiation(base_agr, d_val, p_d_val, use_p, is_f)
            
            st.markdown(f"""
                <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                    <div style="text-align:right;">Date: {today_str}</div>
                    <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN</h2>
                    <p><b>Unit:</b> {search_id} | <b>Floor:</b> {floor_txt} | <b>Carpet:</b> {carpet_area} sqft</p>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Agreement</span><span>Rs. {format_indian_currency(res['Final Agreement'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Stamp Duty ({int(res['SD_Pct'])}%)</span><span>Rs. {format_indian_currency(res['Stamp Duty'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>GST ({int(res['GST_Pct'])}%)</span><span>Rs. {format_indian_currency(res['GST'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Registration</span><span>Rs. {format_indian_currency(res['Registration'])}</span></div>
                    <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                </div>
            """, unsafe_allow_html=True)
            
            col_d, col_r = st.columns(2)
            with col_d:
                if st.button("📥 Download & Block"):
                    download_dialog(search_id, floor_txt, carpet_area, res, cust_name, today_str, use_p, today_full_log)
            with col_r:
                st.button("❌ Release Unit", on_click=release_unit_callback, args=(search_id,))
