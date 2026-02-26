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
        tc_lines = ["1. Advocate charges Rs. 15k.", "2. Register in 15 days.", "3. Incl GST/SD.", "4. Gov rates apply.", "5. Sqft for ease.", "6. Legal in Sqm.", "7. PCMC Jurisdiction.", "8. Maint Rs.3/sqft.", "9. Loan cust responsibility.", "10. Prices change.", "11. Non-transferable.", "12. Good faith.", "13. Other taxes at actual.", "14. KYC Req.", "15. Ext Bank fee 25k."]
        for line in tc_lines: pdf.multi_cell(0, 3.2, line)
        
        footer_y = pdf.h - 50
        pdf.set_y(footer_y)
        pdf.set_font("Arial", 'B', 12); pdf.cell(210, 10, "Contact: 080 6452 3034", align='C')
        pdf.set_xy(150, footer_y); pdf.cell(45, 18, "", border=1)
        pdf.set_xy(150, footer_y + 19); pdf.set_font("Arial", '', 7); pdf.cell(45, 5, "Customer Signature", align='C')

    return pdf.output(dest='S').encode('latin-1')

# --- 5. UI SETUP ---
st.set_page_config(page_title="Tarangan Dashboard", layout="wide")

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# --- 6. DIALOGS & CALLBACKS ---
@st.dialog("Booking Confirmation")
def download_dialog(unit_id, floor, carpet, costs, cust_name, date_str, use_parking, ist_log_time):
    st.write(f"Confirming booking for **Unit {unit_id}**")
    sales_name = st.text_input("Enter Sales Person Name:")
    if st.button("Confirm & Download"):
        if not sales_name.strip():
            st.error("Please enter Sales Person Name.")
        else:
            pdf_bytes = create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking)
            storage["download_history"].append({"Timestamp (IST)": ist_log_time, "Sales Person": sales_name, "Flat ID": unit_id, "Customer": cust_name or "N/A", "TOTAL": format_indian_currency(costs['Total'])})
            storage["sold_units"].add(unit_id)
            st.success("Unit Blocked!")
            st.download_button("📥 Save PDF", data=pdf_bytes, file_name=f"Tarangan_{unit_id}.pdf", mime="application/pdf")
            if st.button("Finish"): 
                st.session_state.selected_unit = None
                st.rerun()

# --- 7. MAIN APP ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'selected_unit' not in st.session_state: st.session_state.selected_unit = None

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Login"):
        if (u == "Tarangan" and p == "Tarangan@0103") or (u.lower().startswith("user") and p == "Sales@2026"):
            st.session_state.authenticated, st.session_state.role = True, ("admin" if u == "Tarangan" else "user")
            st.rerun()
else:
    if st.sidebar.button("Logout"): 
        st.session_state.authenticated = False
        st.rerun()

    if st.session_state.role == "admin":
        st.title("🛠️ Admin Dashboard")
        # (Admin logic remains same as your original)
        if st.button("⚠️ Reset System"): storage["locks"].clear(); storage["sold_units"].clear(); storage["download_history"].clear(); st.rerun()
        st.write("Sold Units:", list(storage["sold_units"]))
    else:
        st.title("🏙️ Tarangan Layout")
        inventory = load_data()
        
        # Grid Layout
        st.subheader("Select a Unit")
        # Define Grid (Floors 13 down to 6, Columns 1 to 6)
        floors = range(13, 5, -1)
        cols_idx = range(1, 7)

        for f in floors:
            cols = st.columns(6)
            for i, c_num in enumerate(cols_idx):
                unit_id = f"A-{f}{c_num:02d}"
                
                # Visual Logic
                btn_label = unit_id
                if unit_id in ["A-1205", "A-0705"]: # Refuge Area Logic
                    cols[i].markdown(f"<div style='text-align:center; padding:10px; background:#333; border-radius:5px; color:gray; font-size:0.7em;'>REFUGE {unit_id}</div>", unsafe_allow_html=True)
                elif unit_id in storage["sold_units"]:
                    cols[i].button(f"🔴 {unit_id}", key=unit_id, disabled=True, use_container_width=True)
                else:
                    if cols[i].button(unit_id, key=unit_id, use_container_width=True):
                        st.session_state.selected_unit = unit_id

        # --- Negotiation Section ---
        if st.session_state.selected_unit:
            search_id = st.session_state.selected_unit
            st.divider()
            st.subheader(f"Negotiation: {search_id}")
            
            cust_name = st.text_input("👤 Customer Name:")
            match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
            
            if not match.empty:
                row = match.iloc[0]
                base_agr = clean_numeric(row.get('Agreement Value', 0))
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    use_d = st.checkbox("Apply Discount")
                    d_val = st.number_input("Discount Amt:", value=0, step=1000) if use_d else 0
                with c2:
                    use_p = st.checkbox("Include Parking")
                    p_d_val = st.number_input("Parking Disc:", value=0, max_value=200000) if use_p else 0
                with c3: is_f = st.checkbox("Female Applicant")
                
                res = calculate_negotiation(base_agr, d_val, p_d_val, use_p, is_f)
                
                # Preview Box
                st.markdown(f"""
                    <div style="background:white; padding:20px; border:2px solid black; color:black; font-family:monospace;">
                        <h3 style="text-align:center;">QUOTATION: {search_id}</h3>
                        <p>Agreement: Rs. {format_indian_currency(res['Final Agreement'])}</p>
                        <p>Stamp Duty: Rs. {format_indian_currency(res['Stamp Duty'])}</p>
                        <p>GST: Rs. {format_indian_currency(res['GST'])}</p>
                        <p><b>TOTAL: Rs. {format_indian_currency(res['Total'])}</b></p>
                    </div>
                """, unsafe_allow_html=True)

                ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                if st.button("📥 Proceed to Block & PDF"):
                    download_dialog(search_id, row.get('Floor','N/A'), row.get('CARPET',0), res, cust_name, ist_now.strftime("%d/%m/%Y"), use_p, ist_now.strftime("%H:%M:%S"))
            
            if st.button("Cancel Selection"):
                st.session_state.selected_unit = None
                st.rerun()
