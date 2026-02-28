import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import datetime 
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# Safety import for num2words
try:
    from num2words import num2words
except ImportError:
    st.error("Please add 'num2words' to your requirements.txt file on GitHub.")

# --- EMAIL CONFIGURATION ---
SENDER_EMAIL = "atharvaujoshi@gmail.com"
SENDER_NAME = "Tarangan Cost Sheet" 
APP_PASSWORD = "nybl zsnx zvdw edqr"
RECEIVER_EMAIL = "spydarr1106@gmail.com"

# --- HELPER FUNCTIONS ---
def clean_numeric(value):
    if pd.isna(value): return 0.0
    clean_val = re.sub(r'[^\d.]', '', str(value))
    return float(clean_val) if clean_val else 0.0

def format_indian_currency(number):
    s = str(int(number))
    if len(s) <= 3: return s
    last_three = s[-3:]
    remaining = s[:-3]
    remaining = re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', remaining)
    return remaining + ',' + last_three

def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0, use_parking=False, is_female=False):
    parking_final_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_final_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    REGISTRATION = 30000 
    sd_amt = round(final_agreement * sd_pct, -2)
    gst_amt = final_agreement * gst_pct
    total_package = final_agreement + sd_amt + gst_amt + REGISTRATION
    return {
        "Final Agreement": final_agreement, "Stamp Duty": sd_amt, "SD_Pct": sd_pct * 100,
        "GST": gst_amt, "GST_Pct": gst_pct * 100, "Registration": REGISTRATION,
        "Total": int(total_package), "Combined_Discount": int(pkg_discount + park_discount)
    }

def send_email(recipient_email, pdf_data, filename, details):
    try:
        msg = MIMEMultipart()
        msg['From'] = formataddr((SENDER_NAME, SENDER_EMAIL))
        msg['To'] = recipient_email
        msg['Subject'] = f"Tarangan Booking: {details['Unit No']} - {details['Customer Name']}"
        body = f"Please find the attached cost sheet for {details['Customer Name']}."
        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={filename}")
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except: return False

# --- SHARED STORAGE ---
@st.cache_resource
def get_global_storage():
    return {
        "sold_units": set(), "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {}, 
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"}, 
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "waiting_customers": [], "opted_out": [], "visited_customers": set()
    }

storage = get_global_storage()

def reset_cabin_session(cabin):
    storage["booths"][cabin] = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    if cabin in storage["pending_requests"]: del storage["pending_requests"][cabin]

# --- DATA ---
SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List" 
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# --- APP START ---
st.set_page_config(page_title="Tarangan Dash", layout="wide")

if 'authenticated' not in st.session_state: 
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        creds = {"Tarangan": "Tarangan@0103", "Sales": "Sales@2026", "GRE": "Gre@2026", "Manager": "Manager@2026"}
        if u in creds and p == creds[u]:
            st.session_state.authenticated = True
            st.session_state.role = u
            st.session_state.user_id = u
            st.rerun()
        else:
            st.error("Invalid credentials.")

else:

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    # ================= GRE =================
    if st.session_state.role == "GRE":
        st.title("📝 Stage 1: GRE Entry")

        df_master = load_data()
        df_master.columns = df_master.columns.str.strip()

        names_in_waiting = [str(c).upper() for c in storage.get("waiting_customers", [])]
        names_in_cabins = [str(v).upper() for v in storage.get("booths", {}).values() if v is not None]
        all_active_names = names_in_waiting + names_in_cabins

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("📋 Database List")
            target_column = "Customer Allotted"

            if target_column in df_master.columns:
                db_list = df_master[target_column].dropna().unique().tolist()
                filtered_db = [cust for cust in db_list if str(cust).upper() not in all_active_names]

                selected_cust = st.selectbox("Search & Select Customer:", ["-- Select --"] + sorted(filtered_db))

                if st.button("Add Selected"):
                    if selected_cust != "-- Select --":
                        if selected_cust.upper() in all_active_names:
                            st.warning("Customer already in system!")  # 🔥 NEW
                        else:
                            storage["waiting_customers"].append(selected_cust)
                            st.success(f"Added {selected_cust}")
                            st.rerun()

        with col_right:
            st.subheader("🚶 Walk-in")
            with st.form("walkin_form", clear_on_submit=True):
                new_name = st.text_input("Enter Name").strip()
                if st.form_submit_button("Add Walk-in"):
                    if new_name:
                        walkin_name = f"(WI) {new_name}"  # 🔥 NEW PREFIX
                        if walkin_name.upper() in all_active_names:
                            st.warning("Customer already in system!")  # 🔥 NEW
                        else:
                            storage["waiting_customers"].append(walkin_name)
                            st.success(f"Added {walkin_name}")
                            st.rerun()

        st.divider()
        st.subheader("📊 Live Waiting List")
        for i, cust in enumerate(storage["waiting_customers"]):
            c1, c2 = st.columns([5, 1])
            c1.write(f"{i+1}. **{cust}**")
            if c2.button("🗑️", key=f"rm_{i}"):
                storage["waiting_customers"].remove(cust)
                st.rerun()

    # ================= SALES =================
    elif st.session_state.role == "Sales":

        if "search_id_input" not in st.session_state:
            st.session_state.search_id_input = ""

        search_id = st.session_state.search_id_input.upper()
        my_cabin = st.selectbox("Select Your Cabin:", list("ABCDEFGHIJ"), key="sales_cabin_sel")
        cust_name = storage["booths"].get(my_cabin)

        if cust_name and search_id:
            col_act1, col_act2 = st.columns(2)

            with col_act2:
                if st.button("❌ Close / Release", use_container_width=True):

                    # 🔥 AUTO CLEAR CABIN ON RELEASE
                    reset_cabin_session(my_cabin)

                    st.session_state.search_id_input = ""
                    st.warning(f"Released. Cabin {my_cabin} is now FREE.")
                    st.rerun()
