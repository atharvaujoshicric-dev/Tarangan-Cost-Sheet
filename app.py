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
        tc_lines = [
            "1. Advocate charges will be Rs. 15,000/-.", "2. Agreement to be registered within 15 days.", "3. Total cost inclusive of GST, Stamp Duty.", "4. Gov rates may change.", "5. Sale on RERA carpet area.", "6. Legal docs in SqM.", "7. PCMC Jurisdiction.", "8. Maintenance Rs 3/sqft for 2 years.", "9. Loan responsibility of customer.", "10. Promoters reserve right to change price.", "11. Non-transferable.", "12. Information provided in good faith.", "13. Other taxes payable by purchaser.", "14. Docs: PAN, Adhar.", "15. External bank fee Rs 25,000."
        ]
        for line in tc_lines: pdf.multi_cell(0, 3.2, line)
        
        pdf.set_y(pdf.h - 40)
        pdf.set_font("Arial", 'B', 12); pdf.cell(210, 10, "Contact: 080 6452 3034", align='C')

    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; border: 1px solid #444; }
    
    /* SOLD - Green */
    div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
        background-color: #28a745 !important; color: white !important; border: none !important;
    }
    
    /* BUSY - Yellow (Keep Flat ID visible) */
    div[data-testid="stHorizontalBlock"] button:disabled:not(.refuge-btn) {
        background-color: #ffc107 !important; color: black !important; opacity: 1 !important; border: none !important;
    }

    /* REFUGE - Dark Grey */
    .refuge-btn { background-color: #343a40 !important; color: #777 !important; border: 1px solid #222 !important; cursor: not-allowed !important; width: 100%; height: 3.5em; border-radius: 8px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    df['ID'] = df['ID'].astype(str).str.strip().str.upper()
    return df

# --- 6. GLOBALS & HELPERS ---
REFUGE_FLATS = ["705", "1205"]

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
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False; st.rerun()

    if st.session_state.role == "admin":
        st.title("🛠️ Admin Dashboard")
        blocked = list(storage["sold_units"])
        uid = st.selectbox("Select Unit to Unblock", [""] + blocked)
        if uid and st.button("Unblock"): 
            storage["sold_units"].remove(uid)
            st.rerun()
        if st.button("⚠️ Reset Entire System"): storage["locks"].clear(); storage["sold_units"].clear(); st.rerun()

    else:
        st.title("🏙️ Tarangan Sales Portal")
        inventory = load_data()
        
        # Legend
        l1, l2, l3, l4 = st.columns(4)
        l1.markdown("🟩 **Sold**")
        l2.markdown("🟨 **Busy (Locked)**")
        l3.markdown("⬜ **Available**")
        l4.markdown("⬛ **Refuge**")

        # GENERATE 13 FLOORS x 6 FLATS
        for f in range(13, 0, -1):
            st.write(f"### Floor {f}")
            cols = st.columns(6)
            for i in range(1, 7):
                # Construct Flat ID (e.g., A-101, A-102...)
                unit_id = f"A-{f}{i:02d}" 
                
                is_sold = unit_id in storage["sold_units"]
                is_busy = unit_id in storage["locks"] and storage["locks"][unit_id] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                is_refuge = str(f) + f"{i:02d}" in REFUGE_FLATS or unit_id in REFUGE_FLATS

                with cols[i-1]:
                    if is_refuge:
                        st.markdown(f'<button class="refuge-btn" disabled>{unit_id}</button>', unsafe_allow_html=True)
                    elif is_sold:
                        st.button(unit_id, key=f"btn_{unit_id}", type="primary", disabled=True)
                    elif is_busy:
                        # Fixed: Shows Unit ID but is Yellow/Disabled
                        st.button(unit_id, key=f"btn_{unit_id}", disabled=True)
                    else:
                        if st.button(unit_id, key=f"btn_{unit_id}"):
                            st.session_state.selected_unit = unit_id
                            st.rerun()

        # --- SELECTION & CALCULATION ---
        if st.session_state.selected_unit:
            search_id = st.session_state.selected_unit
            storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
            
            # Fetch details from CSV
            match = inventory[inventory['ID'] == search_id]
            
            st.markdown("---")
            st.subheader(f"📍 Unit: {search_id}")
            
            # Default values if flat isn't in CSV yet
            base_agr = clean_numeric(match.iloc[0]['Agreement Value']) if not match.empty else 0.0
            carpet_area = match.iloc[0]['CARPET'] if not match.empty else "N/A"
            floor_val = match.iloc[0]['Floor'] if not match.empty else search_id.split('-')[1][:-2]

            cust_name = st.text_input("👤 Customer Name:")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                use_d = st.checkbox("Discount")
                d_val = st.number_input("Amt:", value=0, step=1000) if use_d else 0
            with c2:
                use_p = st.checkbox("Parking")
                p_d_val = st.number_input("Park Disc:", value=0, step=1000) if use_p else 0
            with c3: is_f = st.checkbox("Female Buyer")
            
            res = calculate_negotiation(base_agr, d_val, p_d_val, use_p, is_f)
            
            st.markdown(f"""
                <div style="background:white; padding:30px; border:2px solid black; color:black; font-family:monospace; border-radius:10px;">
                    <h2 style="text-align:center; border-bottom:2px solid black;">TARANGAN COST SHEET</h2>
                    <p><b>Unit:</b> {search_id} | <b>Floor:</b> {floor_val} | <b>Carpet:</b> {carpet_area} sqft</p>
                    <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.4em; border-top:2px solid black; margin-top:10px; padding:10px 0;">
                        <span>TOTAL ALL-IN</span><span>Rs. {format_indian_currency(res['Total'])}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            col_d, col_r = st.columns(2)
            with col_d:
                @st.dialog("Confirm Booking")
                def confirm_dialog():
                    sales = st.text_input("Sales Person Name:")
                    if st.button("Save & Block"):
                        if sales:
                            pdf = create_pdf(search_id, floor_val, carpet_area, res, cust_name, "26/02/2026", use_p)
                            storage["sold_units"].add(search_id)
                            st.success("Blocked!")
                            st.download_button("Download PDF", pdf, f"{search_id}.pdf")
                        else: st.error("Name required")

                if st.button("📥 Book & Download"): confirm_dialog()
            with col_r:
                st.button("❌ Release Unit", on_click=release_unit_callback, args=(search_id,))
