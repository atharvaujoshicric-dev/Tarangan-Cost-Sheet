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
            "1. Advocate charges will be Rs. 15,000/-.",
            "2. Agreement to be executed & registered within 15 days from the date of booking.",
            "3. The total cost mentioned here is all inclusive of GST, Registration, Stamp Duty and Legal charges",
            "4. GST, Stamp Duty, Registration and all applicable government charges are as per the current rates, and in future may change as per government notification which would be borne by the customer.",
            "5. Above areas are shown in square feet only to make it easy for the purchaser to understand. The sale of the said unit is on the basis of RERA carpet area only.",
            "6. All legal documents will be executed in square meter only.",
            "7. Subject to PCMC jurisdiction.",
            "8. Society Maintenance at Rs. 3 per sq.ft. per month for 2 years and will be taken at the time of possession.",
            "9. Loan facility available from all leading banks and home loan sanctioning is customers responsibility, developer however will assist in the process.",
            "10. The promoters reserve the right to change the above prices and the offer given at any time without prior notice. No verbal commitments to be accepted post booking.",
            "11. Booking is non-transferable.",
            "12. The information on this paper is provided in good faith and does not constitute part of the contract.",
            "13. Government taxes will be applicable at actual. Also, any other taxes not mentioned herein if levied later would be payable at actuals by the purchaser.",
            "14. Documents required: PAN Card, Adhar Card, Photocopy.",
            "15. If an external bank is opted for loan processing, an additional charge of Rs. 25,000/- shall be applicable and payable by the purchaser."
        ]
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
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3.2em; font-weight: bold; transition: 0.3s; }
    
    /* SOLD - Green */
    div[data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
        background-color: #28a745 !important;
        color: white !important;
        border: none !important;
    }
    
    /* BUSY - Yellow */
    div[data-testid="stHorizontalBlock"] button:disabled:not(.refuge-btn) {
        background-color: #ffc107 !important;
        color: black !important;
        opacity: 1 !important;
    }

    /* REFUGE - Grey (Special Class) */
    .refuge-btn {
        background-color: #6c757d !important;
        color: #ffffff !important;
        cursor: not-allowed !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

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
            storage["download_history"].append({
                "Timestamp (IST)": ist_log_time,
                "Sales Person": sales_name,
                "Login User": st.session_state.get('user_id', 'Unknown'),
                "Flat ID": unit_id,
                "Customer": cust_name if cust_name else "N/A",
                "Agreement": format_indian_currency(costs['Final Agreement']),
                "Stamp Duty": format_indian_currency(costs['Stamp Duty']),
                "GST": format_indian_currency(costs['GST']),
                "Registration": format_indian_currency(costs['Registration']),
                "TOTAL": format_indian_currency(costs['Total']),
                "Discount": format_indian_currency(costs['Combined_Discount'])
            })
            storage["sold_units"].add(unit_id)
            if unit_id in storage["locks"]: del storage["locks"][unit_id]
            st.success("Unit Blocked Successfully!")
            st.download_button(label="📥 Click here to save PDF", data=pdf_bytes, file_name=f"Tarangan_{unit_id}.pdf", mime="application/pdf")
            if st.button("Close"): 
                st.session_state.selected_unit = None
                st.rerun()

def release_unit_callback(unit_to_release):
    if unit_to_release in storage["locks"]:
        del storage["locks"][unit_to_release]
    st.session_state.selected_unit = None

# --- 7. LOGIN ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'selected_unit' not in st.session_state:
    st.session_state.selected_unit = None

REFUGE_FLATS = ["705", "1205"]

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
        t1, t2 = st.tabs(["Unit Management", "History"])
        with t1:
            blocked = list(storage["sold_units"])
            if blocked:
                uid = st.selectbox("Select Unit to Unblock", blocked)
                if st.button("Unblock"): 
                    storage["sold_units"].remove(uid)
                    st.rerun()
            if st.button("⚠️ Reset System"): storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear(); st.rerun()
        with t2:
            if storage["download_history"]:
                st.dataframe(pd.DataFrame(storage["download_history"]), use_container_width=True)
            else: st.info("No records recorded yet.")

    else:
        st.title("🏙️ Tarangan Sales Portal")
        inventory = load_data()
        
        # Legend
        l1, l2, l3, l4 = st.columns(4)
        l1.markdown("🟩 **Sold**")
        l2.markdown("🟨 **Busy**")
        l3.markdown("⬜ **Available**")
        l4.markdown("⬛ **Refuge (Blocked)**")
        
        # Grid Display
        floors = sorted(inventory['Floor'].unique(), reverse=True)
        for floor in floors:
            st.write(f"### Floor {floor}")
            floor_units = inventory[inventory['Floor'] == floor].sort_values('ID')
            cols = st.columns(6) 
            
            for idx, (_, row) in enumerate(floor_units.iterrows()):
                uid = str(row['ID'])
                is_sold = uid in storage["sold_units"]
                is_busy = uid in storage["locks"] and storage["locks"][uid] != st.runtime.scriptrunner.get_script_run_ctx().session_id
                is_refuge = uid in REFUGE_FLATS
                
                with cols[idx % 6]:
                    if is_refuge:
                        # Display Refuge as blocked grey button
                        st.markdown(f'<button class="stButton refuge-btn" disabled style="width:100%; height:3.2em; border-radius:5px; border:none;">REFUGE ({uid})</button>', unsafe_allow_html=True)
                    elif is_sold:
                        st.button(f"Unit {uid}", key=f"btn_{uid}", type="primary", disabled=True)
                    elif is_busy:
                        st.button(f"BUSY", key=f"btn_{uid}", disabled=True)
                    else:
                        if st.button(uid, key=f"btn_{uid}"):
                            st.session_state.selected_unit = uid
                            st.rerun()

        # Calculation Area
        if st.session_state.selected_unit:
            search_id = st.session_state.selected_unit
            storage["locks"][search_id] = st.runtime.scriptrunner.get_script_run_ctx().session_id
            
            match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
            if not match.empty:
                row = match.iloc[0]
                base_agr, carpet_area = clean_numeric(row.get('Agreement Value', 0)), row.get('CARPET','N/A')
                
                st.markdown("---")
                st.subheader(f"📍 Negotiating Unit: {search_id}")
                cust_name = st.text_input("👤 Customer Name:")
                
                ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                today_str, today_full_log = ist_now.strftime("%d/%m/%Y"), ist_now.strftime("%d/%m/%Y %H:%M:%S")

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
                        <p><b>Unit:</b> {search_id} | <b>Floor:</b> {row.get('Floor','N/A')} | <b>Carpet:</b> {carpet_area} sqft</p>
                        <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; border-top:2px solid black; margin-top:10px; padding:10px 0;"><span>TOTAL</span><span>Rs. {format_indian_currency(res['Total'])}</span></div>
                        <div style="color:red; font-weight:bold;">Total Discount: Rs. {format_indian_currency(res['Combined_Discount'])}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                col_d, col_r = st.columns(2)
                with col_d:
                    if st.button("📥 Download PDF & Block"):
                        download_dialog(search_id, row.get('Floor','N/A'), carpet_area, res, cust_name, today_str, use_p, today_full_log)
                with col_r:
                    st.button("❌ Release Unit", on_click=release_unit_callback, args=(search_id,))
