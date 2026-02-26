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

# CSS Optimized for single-page view and uniform Refuge boxes
st.markdown("""
    <style>
    /* Reduce vertical spacing between elements */
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    
    /* Standardized height and font for all boxes to fit on one screen */
    .stButton>button, .refuge-box { 
        width: 100% !important; 
        height: 2.2em !important; 
        padding: 0px !important;
        font-size: 12px !important;
        border-radius: 4px !important; 
        font-weight: bold !important; 
        margin-bottom: 4px !important;
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

    /* REFUGE - Grey (Standardized Size) */
    .refuge-box { 
        background-color: #444 !important; 
        color: #bbb !important; 
        border: 1px solid #222 !important; 
        cursor: not-allowed;
    }
    
    /* Hide floor labels to save vertical space */
    h3 { margin-bottom: 0px !important; padding-top: 5px !important; font-size: 16px !important; }
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
    # --- GRID VIEW ---
    if st.session_state.selected_unit is None:
        st.title("🏙️ Tarangan Sales Portal")
        
        # Compact Legend on one line
        l_cols = st.columns(4)
        l_cols[0].markdown("🟩 **Sold**")
        l_cols[1].markdown("🟨 **Busy**")
        l_cols[2].markdown("⬜ **Available**")
        l_cols[3].markdown("⬛ **Refuge**")
        
        inventory = load_data()

        # Generate dense grid: 8 columns to reduce total page height
        for f in range(13, 0, -1):
            cols = st.columns(8) # Increased columns to save vertical space
            for i in range(1, 7):
                unit_id = f"A-{f}{i:02d}"
                is_sold = unit_id in storage["sold_units"]
                is_busy = unit_id in storage["locks"] and storage["locks"][unit_id] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                is_refuge = unit_id in REFUGE_FLATS

                with cols[i]: # Offset by 1 to leave room if needed
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
    
    # --- COST SHEET VIEW ---
    else:
        search_id = st.session_state.selected_unit
        storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
        inventory = load_data()
        match = inventory[inventory['ID'] == search_id]

        st.subheader(f"📍 Unit {search_id}")
        if st.button("⬅️ Back to Map"):
            release_unit_callback(search_id)
            st.rerun()

        row = match.iloc[0] if not match.empty else None
        base_agr = clean_numeric(row.get('Agreement Value', 0)) if row is not None else 0
        carpet_area = row.get('CARPET','N/A') if row is not None else "N/A"
        floor_txt = row.get('Floor','N/A') if row is not None else search_id.split('-')[1][:-2]

        cust_name = st.text_input("👤 Customer Name:")
        
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
            <div style="background:white; padding:20px; border:2px solid black; color:black; font-family:monospace;">
                <h2 style="text-align:center; border-bottom:2px solid black; margin:0;">TARANGAN</h2>
                <p><b>Unit:</b> {search_id} | <b>Floor:</b> {floor_txt} | <b>Carpet:</b> {carpet_area} sqft</p>
                <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; padding:10px 0;">
                    <span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        col_d, col_r = st.columns(2)
        with col_d:
            if st.button("📥 Block & Download"):
                # Dialog or Direct Download Logic
                storage["sold_units"].add(search_id)
                st.session_state.selected_unit = None
                st.rerun()
        with col_r:
            st.button("❌ Release Unit", on_click=release_unit_callback, args=(search_id,))
