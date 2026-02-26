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
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "TARANGAN COST SHEET", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(190, 10, f"Unit: {unit_id} | Floor: {floor}", ln=True)
    pdf.cell(190, 10, f"Customer: {cust_name}", ln=True)
    pdf.cell(190, 10, f"Total: Rs. {format_indian_currency(costs['Total'])}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

st.markdown("""
    <style>
    /* Standardized button size for all types */
    .stButton>button, .refuge-box { 
        width: 100% !important; 
        height: 3.5em !important; 
        border-radius: 8px !important; 
        font-weight: bold !important; 
        margin-bottom: 10px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    
    /* SOLD - Green */
    div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
        background-color: #28a745 !important; color: white !important; border: none !important;
    }
    
    /* BUSY - Yellow */
    div[data-testid="stHorizontalBlock"] button:disabled:not(.refuge-box) {
        background-color: #ffc107 !important; color: black !important; opacity: 1 !important; border: none !important;
    }

    /* REFUGE - Grey (Standard Size) */
    .refuge-box { 
        background-color: #343a40 !important; 
        color: #777 !important; 
        border: 1px solid #222 !important; 
        font-size: 14px;
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

# --- 6. GLOBALS & HELPERS ---
REFUGE_FLATS = ["A-705", "A-1205", "705", "1205"]

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]:
        del storage["locks"][unit_to_release]
    st.session_state.selected_unit = None

# --- 7. APP LOGIC ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'selected_unit' not in st.session_state: st.session_state.selected_unit = None

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Login"):
        if (u == "Tarangan" and p == "Tarangan@0103") or (u.lower().startswith("user") and p == "Sales@2026"):
            st.session_state.authenticated, st.session_state.role, st.session_state.user_id = True, ("admin" if u == "Tarangan" else "user"), u
            st.rerun()
else:
    # --- IF NO UNIT SELECTED: SHOW GRID ---
    if st.session_state.selected_unit is None:
        st.title("🏙️ Tarangan Sales Portal")
        inventory = load_data()
        
        # Legend
        l1, l2, l3, l4 = st.columns(4)
        l1.markdown("🟩 **Sold**")
        l2.markdown("🟨 **Busy**")
        l3.markdown("⬜ **Available**")
        l4.markdown("⬛ **Refuge**")
        st.write("---")

        # Generate continuous grid: 13 floors, 6 units each
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
    
    # --- IF UNIT SELECTED: HIDE GRID AND SHOW COST SHEET ---
    else:
        search_id = st.session_state.selected_unit
        storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
        inventory = load_data()
        match = inventory[inventory['ID'] == search_id]

        st.title(f"📍 Cost Sheet: Unit {search_id}")
        
        if st.button("⬅️ Back to All Flats"):
            release_unit_callback(search_id)
            st.rerun()

        st.write("---")
        
        base_agr = clean_numeric(match.iloc[0]['Agreement Value']) if not match.empty else 0.0
        carpet_area = match.iloc[0]['CARPET'] if not match.empty else "N/A"
        floor_val = match.iloc[0]['Floor'] if not match.empty else search_id.split('-')[1][:-2]

        cust_name = st.text_input("👤 Customer Name:")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            use_d = st.checkbox("Apply Discount")
            d_val = st.number_input("Discount Amount:", value=0, step=1000) if use_d else 0
        with c2:
            use_p = st.checkbox("Include Parking")
            p_d_val = st.number_input("Parking Discount:", value=0, step=1000) if use_p else 0
        with c3: is_f = st.checkbox("Female Buyer (6% SD)")
        
        res = calculate_negotiation(base_agr, d_val, p_d_val, use_p, is_f)
        
        st.markdown(f"""
            <div style="background:white; padding:40px; border:3px solid #222; color:black; font-family:monospace; border-radius:15px; margin-top:20px;">
                <h1 style="text-align:center; margin-bottom:0;">TARANGAN</h1>
                <p style="text-align:center; text-decoration:underline;">OFFICIAL COST SHEET</p>
                <hr style="border:1px solid black;">
                <table style="width:100%; font-size:1.2em;">
                    <tr><td><b>Unit No:</b> {search_id}</td><td style="text-align:right;"><b>Date:</b> {datetime.datetime.now().strftime('%d/%m/%Y')}</td></tr>
                    <tr><td><b>Floor:</b> {floor_val}</td><td style="text-align:right;"><b>Carpet:</b> {carpet_area} Sq.Ft.</td></tr>
                </table>
                <div style="background:#f9f9f9; padding:20px; border:1px solid #ddd; margin-top:20px;">
                    <div style="display:flex; justify-content:space-between; font-size:1.5em; font-weight:bold;">
                        <span>ALL-INCLUSIVE TOTAL:</span>
                        <span>Rs. {format_indian_currency(res['Total'])}</span>
                    </div>
                </div>
                <p style="margin-top:20px; color:red;">* Total Discount Applied: Rs. {format_indian_currency(res['Combined_Discount'])}</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.write("---")
        col_book, col_rel = st.columns(2)
        with col_book:
            if st.button("📥 Confirm Booking & Generate PDF"):
                # Simplified booking logic for demonstration
                storage["sold_units"].add(search_id)
                st.success(f"Unit {search_id} has been marked as SOLD.")
                if search_id in storage["locks"]: del storage["locks"][search_id]
                st.session_state.selected_unit = None
                st.rerun()
        with col_rel:
            st.button("❌ Cancel & Release Unit", on_click=release_unit_callback, args=(search_id,))
