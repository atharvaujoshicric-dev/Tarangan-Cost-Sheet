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

# ---------------- EMAIL CONFIGURATION ----------------
SENDER_EMAIL = "atharvaujoshi@gmail.com"
SENDER_NAME = "Tarangan Cost Sheet"
APP_PASSWORD = "nybl zsnx zvdw edqr"
RECEIVER_EMAIL = "spydarr1106@gmail.com"

# ---------------- HELPER FUNCTIONS ----------------

def clean_numeric(value):
    if pd.isna(value):
        return 0.0
    clean_val = re.sub(r'[^\d.]', '', str(value))
    return float(clean_val) if clean_val else 0.0


def format_indian_currency(number):
    s = str(int(number))
    if len(s) <= 3:
        return s
    last_three = s[-3:]
    remaining = s[:-3]
    remaining = re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', remaining)
    return remaining + ',' + last_three


def calculate_negotiation(initial_agreement, pkg_discount=0, park_discount=0,
                          use_parking=False, is_female=False):
    parking_final_price = (200000 - park_discount) if use_parking else 0
    final_agreement = initial_agreement - pkg_discount + parking_final_price
    sd_pct = 0.06 if is_female else 0.07
    gst_pct = 0.05 if final_agreement > 4500000 else 0.01
    REGISTRATION = 30000
    sd_amt = round(final_agreement * sd_pct, -2)
    gst_amt = final_agreement * gst_pct
    total_package = final_agreement + sd_amt + gst_amt + REGISTRATION

    return {
        "Final Agreement": final_agreement,
        "Stamp Duty": sd_amt,
        "SD_Pct": sd_pct * 100,
        "GST": gst_amt,
        "GST_Pct": gst_pct * 100,
        "Registration": REGISTRATION,
        "Total": int(total_package),
        "Combined_Discount": int(pkg_discount + park_discount)
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
    except:
        return False


# ---------------- SHARED STORAGE ----------------

@st.cache_resource
def get_global_storage():
    return {
        "sold_units": set(),
        "in_process_units": {},
        "download_history": [],
        "booths": {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests": {},
        "approved_units": {letter: [] for letter in "ABCDEFGHIJ"},
        "unblock_counts": {letter: 0 for letter in "ABCDEFGHIJ"},
        "waiting_customers": [],
        "visited_customers": set()
    }

storage = get_global_storage()


# ---------------- GOOGLE SHEET DATA ----------------

SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"


@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ---------------- APP CONFIG ----------------

st.set_page_config(page_title="Tarangan Dash", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "search_id_input" not in st.session_state:
    st.session_state.search_id_input = ""


# ---------------- LOGIN ----------------

if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        creds = {
            "Tarangan": "Tarangan@0103",
            "Sales": "Sales@2026",
            "GRE": "Gre@2026",
            "Manager": "Manager@2026"
        }

        if u in creds and p == creds[u]:
            st.session_state.authenticated = True
            st.session_state.role = u
            st.session_state.user_id = u
            st.rerun()
        else:
            st.error("Invalid credentials.")

# ---------------- DASHBOARDS ----------------

else:

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    role = st.session_state.role

    # ==========================================================
    # GRE DASHBOARD
    # ==========================================================
    if role == "GRE":
        st.title("📝 GRE: Guest Relations")

        with st.expander("➕ Add New Entry", expanded=True):
            new_name = st.text_input("Customer Full Name")
            if st.button("Add to Waiting List") and new_name:
                new_id = len(storage["waiting_customers"]) + 1
                storage["waiting_customers"].append({
                    "id": new_id,
                    "name": new_name
                })
                st.rerun()

        st.subheader("⏳ Current Waiting List")

        for idx, cust in enumerate(storage["waiting_customers"]):
            col1, col2 = st.columns([4, 1])
            with col1:
                new_val = st.text_input(
                    f"Name (ID: {cust['id']})",
                    value=cust["name"],
                    key=f"edit_{idx}"
                )
                storage["waiting_customers"][idx]["name"] = new_val

            with col2:
                if st.button("Remove", key=f"rem_{idx}"):
                    storage["waiting_customers"].pop(idx)
                    st.rerun()

    # ==========================================================
    # MANAGER DASHBOARD
    # ==========================================================
    elif role == "Manager":
        st.title("👔 Manager: Cabin Assignment")

        col_assign, col_status = st.columns(2)

        with col_assign:
            st.subheader("Assign Customer")

            if storage["waiting_customers"]:
                cust_to_assign = st.selectbox(
                    "Select from Waitlist",
                    storage["waiting_customers"],
                    format_func=lambda x: x["name"]
                )

                free_cabins = [
                    k for k, v in storage["booths"].items()
                    if v is None
                ]

                if free_cabins:
                    target_cabin = st.selectbox(
                        "Assign to Free Cabin",
                        free_cabins
                    )

                    if st.button("Confirm Assignment"):
                        storage["booths"][target_cabin] = cust_to_assign["name"]
                        storage["waiting_customers"].remove(cust_to_assign)
                        st.rerun()
                else:
                    st.warning("All cabins are currently occupied.")
            else:
                st.info("No customers in waiting list.")

        with col_status:
            st.subheader("Cabin Occupancy")

            for cab in "ABCDEFGH":
                occupant = storage["booths"][cab]
                status_color = "🔴" if occupant else "🟢 FREE"
                label = f"**Cabin {cab}:** {occupant if occupant else ''}"
                st.markdown(f"{status_color} {label}")

                if occupant:
                    if st.button(f"Clear Cabin {cab}", key=f"clr_{cab}"):
                        storage["booths"][cab] = None
                        storage["approved_units"][cab] = []
                        st.rerun()

    # ==========================================================
    # SALES DASHBOARD
    # ==========================================================
    elif role == "Sales":
        st.title("💼 Sales Dashboard")

        my_cabin = st.selectbox("Your Assigned Cabin:", list("ABCDEFGH"))
        current_cust = storage["booths"].get(my_cabin)

        if not current_cust:
            st.warning("Waiting for Manager to assign a customer...")
        else:
            st.header(f"Serving: {current_cust}")

            inv = load_data()
            st.subheader("🏢 Unit Selection")

            cols = st.columns(6)

            for i, row in inv.iterrows():
                uid = str(row["ID"]).strip()

                is_sold = (
                    uid in storage["sold_units"] or
                    (str(row.get("Token Number")).strip() not in ["", "nan"])
                )

                is_busy = (
                    uid in storage["in_process_units"] and
                    storage["in_process_units"][uid] != my_cabin
                )

                if is_sold:
                    cols[i % 6].button(
                        f"⛔ {uid}\nSOLD",
                        disabled=True,
                        key=f"btn_{uid}"
                    )
                elif is_busy:
                    cols[i % 6].button(
                        f"⏳ {uid}\nBUSY",
                        disabled=True,
                        key=f"btn_{uid}"
                    )
                else:
                    if cols[i % 6].button(
                        f"✅ {uid}\nSelect",
                        key=f"btn_{uid}"
                    ):
                        st.session_state.search_id_input = uid
                        storage["in_process_units"][uid] = my_cabin
                        st.rerun()

            # -------- COST SHEET SECTION --------
            search_id = st.session_state.search_id_input

            if search_id:
                match = inv[
                    inv["ID"].astype(str).str.upper() == search_id
                ]

                if not match.empty:
                    row = match.iloc[0]

                    st.info(
                        f"Unit {search_id} Selected. "
                        f"Agreement: {row.get('Agreement Value')}"
                    )

                    col_act1, col_act2 = st.columns(2)

                    with col_act1:
                        if st.button("✅ Finalize & Book"):
                            storage["sold_units"].add(search_id)
                            storage["in_process_units"].pop(search_id, None)
                            storage["booths"][my_cabin] = None
                            storage["approved_units"][my_cabin] = []
                            st.session_state.search_id_input = ""
                            st.success("Booked!")
                            st.rerun()

                    with col_act2:
                        if st.button("❌ Close / Release"):
                            storage["in_process_units"].pop(search_id, None)

                            if search_id in storage["approved_units"][my_cabin]:
                                storage["approved_units"][my_cabin].remove(search_id)

                            st.session_state.search_id_input = ""
                            st.rerun()

    # ==========================================================
    # ADMIN DASHBOARD
    # ==========================================================
    elif role == "Tarangan":
        st.title("Admin Control Panel")

        inv = load_data()
        st.subheader("Live Project View")

        a_cols = st.columns(8)

        for i, r in inv.iterrows():
            uid = str(r["ID"]).strip()

            is_sold = (
                uid in storage["sold_units"] or
                (str(r.get("Token Number")).strip() not in ["", "nan"])
            )

            if is_sold:
                color = "#dc3545"
                txt = "SOLD"
            elif uid in storage["in_process_units"]:
                color = "#ffc107"
                txt = "IN NEGOTIATION"
            else:
                color = "#28a745"
                txt = "OPEN"

            a_cols[i % 8].markdown(f"""
                <div style="
                    background:{color};
                    color:white;
                    padding:5px;
                    border-radius:3px;
                    text-align:center;
                    font-size:10px;
                    margin-bottom:5px;">
                    {uid}<br><b>{txt}</b>
                </div>
            """, unsafe_allow_html=True)
