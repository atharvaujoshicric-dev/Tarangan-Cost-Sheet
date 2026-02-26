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
    pdf.set_font("Arial", 'B', 16); pdf.cell(190, 10, "TARANGAN COST SHEET", ln=True, align='C')
    pdf.set_font("Arial", '', 12); pdf.cell(190, 10, f"Unit: {unit_id} | Floor: {floor}", ln=True)
    pdf.cell(190, 10, f"Customer: {cust_name}", ln=True)
    pdf.cell(190, 10, f"Total: Rs. {format_indian_currency(costs['Total'])}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

# CSS Optimized for single-page view and PERFECTLY uniform boxes
st.markdown("""
    <style>
    /* Remove unnecessary padding */
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    
    /* Standardized button height for ALL boxes */
    .stButton>button {
        width: 100% !important;
        height: 2.2em !important;
        padding: 0px !important;
        font-size: 13px !important;
        border-radius: 6px !important;
        font-weight: bold !important;
        margin-bottom: 0px !important;
    }
    
    /* REFUGE - Special Grey Style */
    div[data-testid="column"] button:has(div:contains("REFUGE")) {
        background-color: #343a40 !important;
        color: #6c757d !important;
        border: 1px solid #222 !important;
        pointer-events: none !important; /* Makes it unclickable */
    }

    /* SOLD - Green */
    button[data-testid="stBaseButton-primary"] {
        background-color: #28a745 !important; color: white !important; border: none !important;
    }
    
    /* BUSY - Yellow */
    button:disabled:not(:has(div:contains("REFUGE"))) {
        background-color: #ffc107 !important; color: black !important; opacity: 1 !important; border: none !important;
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
REF_IDS = ["705", "1205"] # The numbers identifying refuge flats

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]: del storage["locks"][unit_to_release]
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
        # --- GRID VIEW ---
        if st.session_state.selected_unit is None:
            st.title("🏙️ Tarangan Sales Portal")
            
            l_cols = st.columns(4)
            l_cols[0].markdown("🟩 **Sold**")
            l_cols[1].markdown("🟨 **Busy**")
            l_cols[2].markdown("⬜ **Available**")
            l_cols[3].markdown("⬛ **Refuge**")
            
            inventory = load_data()

            # The Grid Loop
            for f in range(13, 0, -1):
                cols = st.columns(6)
                for i in range(1, 7):
                    # Logical construction of Flat ID
                    flat_num = f"{f}{i:02d}"
                    unit_id = f"A-{flat_num}"
                    
                    is_refuge = flat_num in REF_IDS
                    is_sold = unit_id in storage["sold_units"]
                    is_busy = unit_id in storage["locks"] and storage["locks"][unit_id] != st.runtime.scriptrunner.get_script_run_ctx().session_id

                    with cols[i-1]:
                        if is_refuge:
                            # Using a real button with a unique label for CSS targeting
                            st.button(f"REFUGE {unit_id}", key=f"ref_{unit_id}", disabled=True)
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

            # Original On-Screen Cost Sheet Layout
            st.subheader(f"📍 Unit: {search_id}")
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
            
            # THE ORIGINAL ON-SCREEN COST SHEET
            ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            today_str = ist_now.strftime("%d/%m/%Y")
            
            st.markdown(f"""
                <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace;">
                    <div style="text-align:right;">Date: {today_str}</div>
                    <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN</h2>
                    <p><b>Customer:</b> {cust_name if cust_name else '________________'}</p>
                    <p><b>Unit:</b> {search_id} | <b>Floor:</b> {floor_txt} | <b>Carpet:</b> {carpet_area} sqft</p>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Agreement</span><span>Rs. {format_indian_currency(res['Final Agreement'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Stamp Duty ({int(res['SD_Pct'])}%)</span><span>Rs. {format_indian_currency(res['Stamp Duty'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>GST ({int(res['GST_Pct'])}%)</span><span>Rs. {format_indian_currency(res['GST'])}</span></div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dotted #888; padding:5px 0;"><span>Registration</span><span>Rs. {format_indian_currency(res['Registration'])}</span></div>
                    <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                    <div style="font-style:italic; margin-top:5px;">Rupees {num2words(res['Total'], lang='en_IN').title().replace(",","")} Only</div>
                    <div style="color:red; font-weight:bold; margin-top:10px;">Total Discount Availed: Rs. {format_indian_currency(res['Combined_Discount'])}</div>
                </div>
            """, unsafe_allow_html=True)
            
            col_d, col_r = st.columns(2)
            with col_d:
                if st.button("📥 Download & Block"):
                    # Record in history & save
                    storage["sold_units"].add(search_id)
                    st.session_state.selected_unit = None
                    st.rerun()
            with col_r:
                st.button("❌ Release Unit", on_click=release_unit_callback, args=(search_id,))
