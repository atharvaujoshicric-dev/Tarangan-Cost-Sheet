import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# Safety import for num2words
try:
    from num2words import num2words
    NUM2WORDS_AVAILABLE = True
except ImportError:
    NUM2WORDS_AVAILABLE = False
    st.error("Please add 'num2words' to your requirements.txt file on GitHub.")

# ---------------------------------------------------------------------------
# SECRETS  —  stored in .streamlit/secrets.toml (never commit this file!)
#
# [email]
# sender        = "you@gmail.com"
# sender_name   = "Tarangan Cost Sheet"
# app_password  = "xxxx xxxx xxxx xxxx"   # rotate the old one NOW
# receiver      = "admin@gmail.com"
#
# [auth]
# Tarangan       = "Tarangan@0103"
# Sales          = "Sales@2026"
# GRE            = "Gre@2026"
# Manager        = "Manager@2026"
# reset_password = "YourResetPassword"
#
# [sheets]
# sheet_id = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
# tab_name = "Inventory List"
# ---------------------------------------------------------------------------

try:
    SENDER_EMAIL   = st.secrets["email"]["sender"]
    SENDER_NAME    = st.secrets["email"]["sender_name"]
    APP_PASSWORD   = st.secrets["email"]["app_password"]
    RECEIVER_EMAIL = st.secrets["email"]["receiver"]
    SHEET_ID       = st.secrets["sheets"]["sheet_id"]
    TAB_NAME       = st.secrets["sheets"]["tab_name"]
    RESET_PASSWORD = st.secrets["auth"]["reset_password"]
    CREDS = {
        "Tarangan": st.secrets["auth"]["Tarangan"],
        "Sales":    st.secrets["auth"]["Sales"],
        "GRE":      st.secrets["auth"]["GRE"],
        "Manager":  st.secrets["auth"]["Manager"],
    }
except Exception:
    # ── Fallback for local dev without secrets.toml ──────────────────────
    # Replace these once secrets.toml is set up; do NOT commit real values.
    SENDER_EMAIL   = "atharvaujoshi@gmail.com"
    SENDER_NAME    = "Tarangan Cost Sheet"
    APP_PASSWORD   = "REVOKE_AND_REPLACE"          # rotate the real one NOW
    RECEIVER_EMAIL = "spydarr1106@gmail.com"
    SHEET_ID       = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
    TAB_NAME       = "Inventory List"
    RESET_PASSWORD = "CHANGE_THIS"
    CREDS = {
        "Tarangan": "Tarangan@0103",
        "Sales":    "Sales@2026",
        "GRE":      "Gre@2026",
        "Manager":  "Manager@2026",
    }

CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

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
    remaining  = s[:-3]
    remaining  = re.sub(r'(\d+?)(?=(\d{2})+$)', r'\1,', remaining)
    return remaining + ',' + last_three


def amount_in_words(amount):
    if NUM2WORDS_AVAILABLE:
        try:
            return num2words(int(amount), lang='en_IN').title().replace(",", "")
        except Exception:
            pass
    return str(int(amount))


def calculate_negotiation(
    initial_agreement, pkg_discount=0, park_discount=0,
    use_parking=False, is_female=False
):
    parking_final_price = (200000 - park_discount) if use_parking else 0
    final_agreement     = initial_agreement - pkg_discount + parking_final_price
    sd_pct              = 0.06 if is_female else 0.07
    gst_pct             = 0.05 if final_agreement > 4500000 else 0.01
    REGISTRATION        = 30000
    sd_amt              = round(final_agreement * sd_pct, -2)
    gst_amt             = final_agreement * gst_pct
    total_package       = final_agreement + sd_amt + gst_amt + REGISTRATION
    return {
        "Final Agreement":   final_agreement,
        "Stamp Duty":        sd_amt,
        "SD_Pct":            sd_pct * 100,
        "GST":               gst_amt,
        "GST_Pct":           gst_pct * 100,
        "Registration":      REGISTRATION,
        "Total":             int(total_package),
        "Combined_Discount": int(pkg_discount + park_discount),
    }


def send_email(recipient_email, pdf_data, filename, details):
    try:
        msg            = MIMEMultipart()
        msg['From']    = formataddr((SENDER_NAME, SENDER_EMAIL))
        msg['To']      = recipient_email
        msg['Subject'] = (
            f"Tarangan Booking: {details['Unit No']} - {details['Customer Name']}"
        )
        msg.attach(MIMEText(
            f"Please find the attached cost sheet for {details['Customer Name']}.", 'plain'
        ))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.warning(f"Email could not be sent: {e}")
        return False


# ---------------------------------------------------------------------------
# SHARED STORAGE
# ---------------------------------------------------------------------------

@st.cache_resource
def get_global_storage():
    return {
        "sold_units":           set(),
        "download_history":     [],
        "activity_log":         [],
        "booths":               {letter: None for letter in "ABCDEFGHIJ"},
        "pending_requests":     {},   # cabin -> list of (unit, request_index)
        "approved_units":       {letter: [] for letter in "ABCDEFGHIJ"},
        "unblock_counts":       {letter: 0  for letter in "ABCDEFGHIJ"},
        "waiting_customers":    [],
        "opted_out":            [],
        "visited_customers":    set(),   # customer names who were assigned to a cabin
        "inventory_released":   False,   # True after Sales hits Close & Release
        # slot non-visit tracking: dict slot -> list of customer names
        "slot_snapshots":       {},      # {"Slot 1": [...], "Slot 2": [...], "Slot 3": [...]}
    }

storage = get_global_storage()


def reset_cabin(cabin):
    """Single source of truth for freeing a cabin — use this everywhere."""
    storage["booths"][cabin]         = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    storage["pending_requests"].pop(cabin, None)


# ---------------------------------------------------------------------------
# TOKEN / SLOT HELPERS
# ---------------------------------------------------------------------------

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

SLOTS = [
    {"name": "Slot 1", "token_range": (21, 45),  "start": (10, 0),  "end": (11, 30)},
    {"name": "Slot 2", "token_range": (46, 71),  "start": (13, 0),  "end": (14, 30)},
    {"name": "Slot 3", "token_range": (72, 9999), "start": (17, 0),  "end": (18, 0)},
]


def get_slot_for_token(token_no):
    """Return slot dict for a given token number, or None."""
    try:
        t = int(token_no)
    except (ValueError, TypeError):
        return None
    for slot in SLOTS:
        lo, hi = slot["token_range"]
        if lo <= t <= hi:
            return slot
    return None


def current_slot(ist_now=None):
    """Return the currently active slot dict, or None if outside all windows."""
    if ist_now is None:
        ist_now = datetime.datetime.now(IST)
    h, m = ist_now.hour, ist_now.minute
    mins = h * 60 + m
    for slot in SLOTS:
        s_mins = slot["start"][0] * 60 + slot["start"][1]
        e_mins = slot["end"][0]   * 60 + slot["end"][1]
        if s_mins <= mins <= e_mins:
            return slot
    return None


def slot_label(slot):
    if slot is None:
        return "No active slot"
    s, e = slot["start"], slot["end"]
    return (
        f"{slot['name']}  |  Tokens {slot['token_range'][0]}–{slot['token_range'][1]}"
        f"  |  {s[0]:02d}:{s[1]:02d} – {e[0]:02d}:{e[1]:02d} IST"
    )



@st.cache_data(ttl=30)   # 30 s avoids hammering the Sheets API on every rerun
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Failed to load inventory: {e}")
        st.stop()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def create_pdf(unit_id, floor, carpet, costs, cust_name, date_str, use_parking):
    pdf    = FPDF()
    copies = ["Customer's Copy", "Sales Copy"]

    for copy_label in copies:
        pdf.add_page()
        pdf.set_font("Arial", 'I', 8)
        pdf.set_xy(10, 5)
        pdf.cell(0, 10, copy_label, ln=True, align='L')

        try:
            pdf.image("tarangan_logo.png", x=75, y=10, w=60)
            pdf.set_y(42)
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(190, 10, "COST SHEET", ln=True, align='C')
        except Exception:
            pdf.set_y(20)
            pdf.set_font("Arial", 'B', 20)
            pdf.cell(190, 10, "TARANGAN", ln=True, align='C')
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(190, 10, "COST SHEET", ln=True, align='C')

        pdf.set_font("Arial", '', 10)
        pdf.cell(190, 10, f"Date: {date_str}", ln=True, align='R')
        pdf.set_font("Arial", 'B', 12)
        display_name = cust_name if cust_name.strip() else "____________________"
        pdf.cell(190, 10, f"Customer Name: {display_name}", ln=True)
        pdf.cell(190, 10, f"Unit No: {unit_id} | Floor: {floor} | Carpet: {carpet} sqft", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

        pdf.set_font("Arial", 'B', 11)
        pdf.cell(95, 10, "Description",  border=1, align='C')
        pdf.cell(95, 10, "Amount (Rs.)", border=1, ln=True, align='C')
        pdf.set_font("Arial", '', 11)

        rows = [
            ["Agreement Value",                      format_indian_currency(costs['Final Agreement'])],
            [f"Stamp Duty ({int(costs['SD_Pct'])}%)", format_indian_currency(costs['Stamp Duty'])],
            [f"GST ({int(costs['GST_Pct'])}%)",       format_indian_currency(costs['GST'])],
            ["Registration",                          format_indian_currency(costs['Registration'])],
        ]
        for r in rows:
            pdf.cell(95, 10, r[0], border=1, align='C')
            pdf.cell(95, 10, r[1], border=1, ln=True, align='C')

        pdf.set_font("Arial", 'B', 13)
        pdf.cell(95, 12, "ALL INCLUSIVE TOTAL",              border=1, align='C')
        pdf.cell(95, 12, format_indian_currency(costs['Total']), border=1, ln=True, align='C')

        pdf.set_font("Arial", 'B', 9)
        pdf.ln(2)
        pdf.multi_cell(190, 8, f"Amount in words: Rupees {amount_in_words(costs['Total'])} Only")

        pdf.ln(2)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(0, 5, "TERMS & CONDITIONS:", ln=True)
        pdf.set_font("Arial", '', 6.0)
        tc_lines = [
            "1. Advocate charges will be Rs. 15,000/-, at the time of agreement.",
            "2. Agreement to be executed & registered within 15 days from the date of booking.",
            "3. The total cost mentioned here is all inclusive of GST, Registration, Stamp Duty.",
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
            "15. If an external bank is opted for loan processing, an additional charge of Rs. 25,000/- shall be applicable and payable by the purchaser.",
            "16. The Developer reserves the right to modify, amend or revise the above Terms and Conditions at its sole discretion, subject to applicable Laws and Regulations.",
        ]
        for line in tc_lines:
            pdf.multi_cell(0, 3.2, line)

        footer_y = pdf.h - 18 - 32
        pdf.set_y(footer_y)
        try:
            pdf.image("mahalaxmi_logo.png", x=10, y=footer_y, h=15)
            pdf.image("bw_logo.png",        x=35, y=footer_y, h=15)
        except Exception:
            pdf.set_font("Arial", 'I', 7)
            pdf.set_xy(10, footer_y)
            pdf.cell(60, 10, "[Logos Here]", ln=0)

        pdf.set_xy(0, footer_y + 5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(210, 10, "Contact: 080 6452 3034", align='C')
        pdf.set_xy(150, footer_y)
        pdf.cell(45, 18, "", border=1)
        pdf.set_xy(150, footer_y + 19)
        pdf.set_font("Arial", '', 7)
        pdf.cell(45, 5, "Customer Signature", align='C')

    return pdf.output(dest='S').encode('latin-1')


# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Tarangan Dash", layout="wide")

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# ── LOGIN ──────────────────────────────────────────────────────────────────
if not st.session_state.authenticated:
    st.title("🔐 Tarangan Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        if u in CREDS and p == CREDS[u]:
            st.session_state.authenticated = True
            st.session_state.role          = u
            st.session_state.user_id       = u
            st.rerun()
        else:
            st.error("Invalid credentials.")

# ── AUTHENTICATED ──────────────────────────────────────────────────────────
else:
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    role = st.session_state.role   # avoids repeated dict lookups

    # ────────────────────────────────────────────────────────────────────────
    # GRE
    # ────────────────────────────────────────────────────────────────────────
    if role == "GRE":
        st.title("📝 Stage 1: GRE Entry")
        rc1, rc2 = st.columns([6, 1])
        with rc2:
            if st.button("🔄 Refresh", key="gre_refresh", use_container_width=True):
                st.rerun()
        if st.sidebar.button("🔄 Global Refresh"):
            st.rerun()

        df_master = load_data()

        names_in_waiting = [str(c).upper() for c in storage.get("waiting_customers", [])]
        names_in_cabins  = [str(v).upper() for v in storage["booths"].values() if v is not None]
        all_active_names = names_in_waiting + names_in_cabins

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("📋 Database List")
            target_column = "Customer Allotted"
            if target_column in df_master.columns:
                db_list     = df_master[target_column].dropna().unique().tolist()
                filtered_db = [c for c in db_list if str(c).upper() not in all_active_names]
                selected_cust = st.selectbox(
                    "Search & Select Customer:", ["-- Select --"] + sorted(filtered_db)
                )
                if st.button("Add Selected"):
                    if selected_cust != "-- Select --":
                        storage["waiting_customers"].append(selected_cust)
                        st.success(f"Added {selected_cust}")
                        st.rerun()
            else:
                st.error(f"Column '{target_column}' not found.")
                st.info(f"Available columns: {', '.join(df_master.columns)}")

        with col_right:
            st.subheader("🚶 Walk-in")
            with st.form("walkin_form", clear_on_submit=True):
                new_name = st.text_input("Enter Name").strip()
                if st.form_submit_button("Add Walk-in"):
                    if new_name:
                        if new_name.upper() in all_active_names:
                            st.warning("Customer already in system!")
                        else:
                            storage["waiting_customers"].append(new_name)
                            st.success(f"Added {new_name}")
                            st.rerun()

        st.divider()
        st.subheader("📊 Live Waiting List")
        if storage["waiting_customers"]:
            for i, cust in enumerate(storage["waiting_customers"]):
                c1, c2 = st.columns([5, 1])
                c1.write(f"{i+1}. **{cust}**")
                if c2.button("🗑️", key=f"rm_{i}"):
                    storage["waiting_customers"].remove(cust)
                    st.rerun()
        else:
            st.info("No customers in waiting list.")

    # ────────────────────────────────────────────────────────────────────────
    # MANAGER
    # ────────────────────────────────────────────────────────────────────────
    elif role == "Manager":
        st.title("👔 Manager Assignment")
        rc1, rc2 = st.columns([6, 1])
        with rc2:
            if st.button("🔄 Refresh", key="mgr_refresh", use_container_width=True):
                st.rerun()
        if st.sidebar.button("🔄 Global Refresh"):
            st.rerun()

        col1, col2 = st.columns([1, 1.2])

        with col1:
            st.subheader("Assign Cabin")
            if storage["waiting_customers"]:
                sel_c   = st.selectbox("Select Customer:", storage["waiting_customers"])
                b_avail = [k for k, v in storage["booths"].items() if v is None]
                if b_avail:
                    sel_b = st.selectbox("Assign to Cabin:", b_avail)
                    if st.button("Confirm Assignment"):
                        storage["booths"][sel_b] = sel_c
                        storage["waiting_customers"].remove(sel_c)
                        st.success(f"Assigned {sel_c} to Cabin {sel_b}")
                        st.rerun()
                else:
                    st.warning("All cabins are currently occupied.")
            else:
                st.info("No customers in waiting list.")

        with col2:
            st.subheader("Cabin Status & Controls")
            for b, c in storage["booths"].items():
                if c:
                    st.markdown(f"**Cabin {b}:** `{c}`")
                    c1, c2 = st.columns(2)
                    if c1.button(f"🔄 Reassign {b}", key=f"re_{b}",
                                 help="Moves customer back to waiting list"):
                        storage["waiting_customers"].append(c)
                        reset_cabin(b)
                        st.rerun()
                    if c2.button(f"🗑️ Remove {b}", key=f"del_{b}",
                                 help="Unassigns customer — sends back to waiting list"):
                        # Always move back to waiting list, never silently delete
                        storage["waiting_customers"].append(c)
                        reset_cabin(b)
                        st.info(f"{c} moved back to waiting list.")
                        st.rerun()
                    st.markdown("---")
                else:
                    st.write(f"**Cabin {b}:** 🟢 Free")


    # ────────────────────────────────────────────────────────────────────────
    # SALES
    # ────────────────────────────────────────────────────────────────────────
    elif role == "Sales":
        if "search_id_input" not in st.session_state:
            st.session_state.search_id_input = ""

        st.title("🏙️ Stage 3: Sales Portal")
        rc1, rc2 = st.columns([6, 1])
        with rc2:
            if st.button("🔄 Refresh", key="sales_refresh", use_container_width=True):
                st.rerun()
        if st.sidebar.button("🔄 Global Refresh"):
            st.rerun()

        my_cabin  = st.selectbox("Select Your Cabin:", list("ABCDEFGHIJ"), key="sales_cabin_sel")
        cust_name = storage["booths"].get(my_cabin)
        ist_now   = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        )

        if not cust_name:
            st.warning(
                f"Cabin {my_cabin} is currently empty. Please wait for Manager assignment."
            )

            # ── Close & Release button (only when cabin is empty / after booking) ──
            st.write("---")
            st.subheader("📢 Inventory Release Control")
            if storage["inventory_released"]:
                st.success("✅ Inventory is currently RELEASED — all cabins can see units (locked for selection)")
                if st.button("🔒 Lock Inventory Again"):
                    storage["inventory_released"] = False
                    st.rerun()
            else:
                st.info("Inventory is currently LOCKED (normal mode)")
                if st.button("🚀 Close & Release Inventory to All Cabins"):
                    storage["inventory_released"] = True
                    storage["activity_log"].append({
                        "Time":   datetime.datetime.now(IST).strftime("%H:%M:%S"),
                        "Action": "Inventory Released",
                        "By":     "Sales",
                        "Detail": "All cabins can now see inventory (locked for selection)",
                    })
                    st.success("Inventory released! All cabins can now see units. Customers must request admin to unlock.")
                    st.rerun()
        else:

            inventory = load_data()
            assigned_unit_from_sheet = ""
            token_no  = "N/A"

            if 'Customer Allotted' in inventory.columns:
                match = inventory[
                    inventory['Customer Allotted'].astype(str).str.upper()
                    == str(cust_name).upper()
                ]
                if not match.empty:
                    assigned_unit_from_sheet = str(match.iloc[0].get('ID', '')).upper()
                    token_no = match.iloc[0].get('Token Number', 'N/A')

            st.success(f"👤 Serving: **{cust_name}** | 🎟️ Token: **{token_no}**")

            # ── Slot info ──────────────────────────────────────────────────
            token_slot = get_slot_for_token(token_no)
            active_slot = current_slot(ist_now)
            if token_slot:
                st.info(f"📅 **{token_slot['name']}**  ·  "
                        f"Tokens {token_slot['token_range'][0]}–{token_slot['token_range'][1]}  ·  "
                        f"{token_slot['start'][0]:02d}:{token_slot['start'][1]:02d}–"
                        f"{token_slot['end'][0]:02d}:{token_slot['end'][1]:02d} IST")
            if active_slot:
                st.caption(f"🟢 Active now: {slot_label(active_slot)}")
            else:
                st.caption("⏸️ No slot active at this moment")

            # ── Inventory Released Banner ───────────────────────────────────
            if storage.get("inventory_released"):
                st.warning("📢 Inventory is RELEASED — units visible but locked. "
                           "Request admin to unblock specific units.")


            st.write("---")
            st.subheader("🔑 Request Inventory Unblock")
            chances_used = storage["unblock_counts"].get(my_cabin, 0)
            MAX_REQUESTS = 3

            st.caption(f"Requests used: **{chances_used} / {MAX_REQUESTS}**")

            if chances_used < MAX_REQUESTS:
                c_req, c_send = st.columns([3, 1])
                req_unit = c_req.text_input(
                    "Enter Unit ID to unlock (e.g., 1503):", key="manual_req"
                ).strip().upper()
                if c_send.button("Send Request", use_container_width=True):
                    if req_unit:
                        # pending_requests is now: cabin -> list of {"unit": ..., "cabin": ...}
                        if not isinstance(storage["pending_requests"].get(my_cabin), list):
                            storage["pending_requests"][my_cabin] = []
                        pending_units = [p["unit"] for p in storage["pending_requests"][my_cabin]]
                        if req_unit in pending_units:
                            st.warning(f"Request for {req_unit} already pending.")
                        elif req_unit in storage["approved_units"].get(my_cabin, []):
                            st.info(f"{req_unit} is already approved.")
                        else:
                            storage["pending_requests"][my_cabin].append({"unit": req_unit, "cabin": my_cabin})
                            storage["unblock_counts"][my_cabin] = chances_used + 1
                            storage["activity_log"].append({
                                "Time":   datetime.datetime.now(IST).strftime("%H:%M:%S"),
                                "Action": "Unblock Request",
                                "By":     f"Cabin {my_cabin}",
                                "Detail": f"Unit {req_unit} requested",
                            })
                            st.toast(f"Request for {req_unit} sent to Admin!")
                            st.rerun()
                    else:
                        st.error("Please enter a Unit ID.")
            else:
                st.error(f"🚫 Maximum ({MAX_REQUESTS}) unblock requests used for this customer.")

            # Show pending & approved
            if not isinstance(storage["pending_requests"].get(my_cabin), list):
                storage["pending_requests"][my_cabin] = []
            cabin_pending  = [p["unit"] for p in storage["pending_requests"].get(my_cabin, [])]
            cabin_approved = storage["approved_units"].get(my_cabin, [])
            if cabin_pending:
                st.caption(f"⏳ Pending admin approval: {', '.join(cabin_pending)}")
            if cabin_approved:
                st.caption(f"✅ Approved units: {', '.join(cabin_approved)}")

            st.write("---")

            # ── Inventory Grid ─────────────────────────────────────────────
            st.subheader("🏢 Unit Inventory")
            search_id = st.session_state.search_id_input.upper()

            # When inventory is released, show all units (locked); only assigned/approved selectable
            inventory_released = storage.get("inventory_released", False)

            with st.expander("📁 View Inventory Grid", expanded=(search_id == "")):
                grid_cols = st.columns(6)
                for idx, row_data in inventory.iterrows():
                    uid = str(row_data['ID']).upper().strip()

                    if uid in ["705", "1205"]:
                        btn_label   = "🏥 REFUGE"
                        is_disabled = True
                    else:
                        approved_list = storage["approved_units"].get(my_cabin, [])
                        is_unlocked   = (
                            uid == assigned_unit_from_sheet
                            or uid in approved_list
                            or uid == search_id
                        )
                        is_sold = uid in storage["sold_units"]

                        if is_sold and uid != search_id:
                            btn_label, is_disabled = "⛔ SOLD", True
                        elif is_unlocked:
                            prefix = "🟢" if uid == assigned_unit_from_sheet else "🟡"
                            btn_label, is_disabled = f"{prefix} {uid}", False
                        elif inventory_released:
                            # Visible but cannot be selected — show with 👁 to distinguish
                            btn_label, is_disabled = f"👁 {uid}", True
                        else:
                            btn_label, is_disabled = f"🔒 {uid}", True

                    if grid_cols[idx % 6].button(
                        btn_label, key=f"btn_{uid}",
                        disabled=is_disabled, use_container_width=True
                    ):
                        st.session_state.search_id_input = uid
                        st.rerun()

            # ── Cost Sheet ─────────────────────────────────────────────────
            if search_id:
                match = inventory[inventory['ID'].astype(str).str.upper() == search_id]
                if not match.empty:
                    row = match.iloc[0]

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        use_d = st.checkbox("Discount")
                        d_val = st.number_input(
                            "Package Discount:", min_value=0, max_value=250000,
                            value=0, step=5000,
                            help="Max allowed: 2,50,000"
                        )
                    with c2:
                        use_p = st.checkbox("Include Parking")
                        p_val = st.number_input(
                            "Parking Discount:", min_value=0, max_value=100000,
                            value=0, step=5000, disabled=not use_p,
                            help="Max allowed: 1,00,000"
                        )
                    with c3:
                        is_f = st.checkbox("Female Customer")

                    effective_d = d_val if use_d else 0
                    res = calculate_negotiation(
                        clean_numeric(row.get('Agreement Value', 0)),
                        effective_d, p_val, use_p, is_f
                    )
                    park_label = "Parking Under Building" if use_p else "1 Car Parking"

                    st.markdown(f"""
                        <div style="background:white;padding:30px;border:2px solid black;
                                    color:black;font-family:monospace;">
                            <div style="text-align:right;">Date: {ist_now.strftime("%d/%m/%Y")}</div>
                            <h2 style="text-align:center;border-bottom:2px solid black;">TARANGAN</h2>
                            <p><b>Customer:</b> {cust_name}</p>
                            <p><b>Unit:</b> {search_id} | <b>Floor:</b> {row.get('Floor','N/A')} |
                               <b>Carpet:</b> {row.get('CARPET','N/A')} sqft</p>
                            <p><b>Parking:</b> {park_label}</p>
                            <div style="display:flex;justify-content:space-between;
                                        border-bottom:1px dotted #888;padding:5px 0;">
                                <span>Agreement</span>
                                <span>Rs. {format_indian_currency(res['Final Agreement'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;
                                        border-bottom:1px dotted #888;padding:5px 0;">
                                <span>Stamp Duty ({int(res['SD_Pct'])}%)</span>
                                <span>Rs. {format_indian_currency(res['Stamp Duty'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;
                                        border-bottom:1px dotted #888;padding:5px 0;">
                                <span>GST ({int(res['GST_Pct'])}%)</span>
                                <span>Rs. {format_indian_currency(res['GST'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;
                                        border-bottom:1px dotted #888;padding:5px 0;">
                                <span>Registration</span>
                                <span>Rs. {format_indian_currency(res['Registration'])}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;
                                        font-weight:bold;font-size:1.2em;
                                        border-top:2px solid black;margin-top:10px;padding:10px 0;">
                                <span>TOTAL</span>
                                <span>Rs. {format_indian_currency(res['Total'])}</span>
                            </div>
                            <div style="text-align:right;color:red;font-weight:bold;
                                        font-size:0.9em;margin-top:-5px;">
                                (Total Discount Availed: Rs. {format_indian_currency(effective_d + p_val)})
                            </div>
                            <div style="font-style:italic;margin-top:5px;">
                                Rupees {amount_in_words(res['Total'])} Only
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    st.write("")
                    col_act1, col_act2 = st.columns(2)

                    with col_act1:
                        with st.popover("✅ Finalize & Book"):
                            st.subheader("Final Confirmation")
                            s_name = st.text_input(
                                "Enter Sales Person Name:", key="final_s_name"
                            )
                            if st.button("Confirm & Generate Cost Sheet", use_container_width=True):
                                if not s_name:
                                    st.error("Sales person name is required.")
                                elif search_id in storage["sold_units"]:
                                    # Double-booking guard
                                    st.error(f"Unit {search_id} has already been booked!")
                                else:
                                    try:
                                        pdf_bytes = create_pdf(
                                            search_id,
                                            row.get('Floor', 'N/A'),
                                            row.get('CARPET', 'N/A'),
                                            res, cust_name,
                                            ist_now.strftime("%d/%m/%Y"),
                                            use_p,
                                        )
                                    except Exception as e:
                                        st.error(f"PDF generation failed: {e}")
                                        pdf_bytes = None

                                    if pdf_bytes:
                                        # Mark unit sold & log it
                                        storage["sold_units"].add(search_id)
                                        storage["download_history"].append({
                                            "Date":             ist_now.strftime("%d/%m/%Y"),
                                            "Unit No":          search_id,
                                            "Floor":            row.get('Floor', 'N/A'),
                                            "Carpet (sqft)":    row.get('CARPET', 'N/A'),
                                            "Customer":         cust_name,
                                            "Agreement Value":  res['Final Agreement'],
                                            "Stamp Duty":       res['Stamp Duty'],
                                            "SD %":             res['SD_Pct'],
                                            "GST":              res['GST'],
                                            "GST %":            res['GST_Pct'],
                                            "Registration":     res['Registration'],
                                            "Total Package":    res['Total'],
                                            "Discount Given":   effective_d + p_val,
                                            "Parking Included": "Yes" if use_p else "No",
                                            "Sales Person":     s_name,
                                            "Timestamp":        ist_now.strftime("%H:%M:%S"),
                                        })

                                        # Free the cabin (single helper)
                                        reset_cabin(my_cabin)
                                        st.session_state.search_id_input = ""

                                        st.success(
                                            f"✅ Unit {search_id} Booked! "
                                            f"Cabin {my_cabin} is now FREE."
                                        )
                                        st.balloons()

                                        email_sent = send_email(
                                            RECEIVER_EMAIL, pdf_bytes,
                                            f"Cost_Sheet_{search_id}.pdf",
                                            {"Unit No": search_id, "Customer Name": cust_name},
                                        )
                                        if email_sent:
                                            st.toast("📧 Email sent to Admin!")

                                        st.download_button(
                                            label="📥 Download Cost Sheet PDF",
                                            data=pdf_bytes,
                                            file_name=f"Tarangan_{search_id}.pdf",
                                            mime="application/pdf",
                                            use_container_width=True,
                                        )

                    with col_act2:
                        if st.button("❌ Close / Release", use_container_width=True):
                            st.session_state.search_id_input = ""
                            st.rerun()

    # ────────────────────────────────────────────────────────────────────────
    # ADMIN
    # ────────────────────────────────────────────────────────────────────────
    elif role == "Tarangan":
        st.title("🛠️ Admin Master Control")
        rc1, rc2 = st.columns([6, 1])
        with rc2:
            if st.button("🔄 Refresh", key="admin_refresh", use_container_width=True):
                st.rerun()
        if st.sidebar.button("🔄 Global Refresh"):
            st.rerun()

        t1, t2, t3, t4, t5, t6 = st.tabs(
            ["📊 Sales Report", "🕵️ Activity Tracker", "📦 Unblock Requests",
             "🏢 Live Inventory", "🕐 Slot Tracker", "🚨 Reset"]
        )

        with t1:
            st.subheader("Project Sales Performance")
            history = storage.get("download_history", [])
            if history:
                df_report = pd.DataFrame(history)

                if "Total" in df_report.columns and "Total Package" not in df_report.columns:
                    df_report = df_report.rename(columns={"Total": "Total Package"})

                for col in ["Total Package", "Discount Given", "Agreement Value"]:
                    if col in df_report.columns:
                        df_report[col] = pd.to_numeric(
                            df_report[col].astype(str).str.replace(r'[^\d.]', '', regex=True),
                            errors='coerce'
                        ).fillna(0)

                m1, m2, m3 = st.columns(3)
                t_rev  = int(df_report["Total Package"].sum())  if "Total Package"  in df_report.columns else 0
                t_disc = int(df_report["Discount Given"].sum()) if "Discount Given" in df_report.columns else 0

                m1.metric("Units Sold",      len(df_report))
                m2.metric("Total Revenue",   f"₹ {format_indian_currency(t_rev)}")
                m3.metric("Total Discounts", f"₹ {format_indian_currency(t_disc)}")

                st.divider()
                st.write("### Transaction Table")
                st.dataframe(df_report, use_container_width=True)

                csv = df_report.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export Report to CSV",
                    data=csv,
                    file_name=f"Tarangan_Report_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("No sales recorded yet.")

        with t2:
            st.subheader("System Activity Logs")
            logs = storage.get("activity_log", [])
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
            else:
                st.info("No activity recorded.")

        # ── Tab 3: Unblock Requests ─────────────────────────────────────────
        with t3:
            st.subheader("🔑 Inventory Unblock Requests")

            # Inventory release toggle
            inv_released = storage.get("inventory_released", False)
            rel_col1, rel_col2 = st.columns([3, 1])
            rel_col1.info(
                f"📢 Inventory Status: **{'RELEASED 🟢' if inv_released else 'LOCKED 🔴'}**"
            )
            if inv_released:
                if rel_col2.button("🔒 Lock Inventory"):
                    storage["inventory_released"] = False
                    st.rerun()
            else:
                if rel_col2.button("🚀 Release Inventory"):
                    storage["inventory_released"] = True
                    st.rerun()

            st.divider()
            st.markdown("### Pending Requests")
            pending = storage.get("pending_requests", {})

            any_pending = False
            for cabin, req_list in list(pending.items()):
                # Normalise old string format to list
                if isinstance(req_list, str):
                    req_list = [{"unit": req_list, "cabin": cabin}]
                    storage["pending_requests"][cabin] = req_list
                for req in list(req_list):
                    any_pending = True
                    requested_unit = req["unit"]
                    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
                    c1.write(f"**Cabin {cabin}**")
                    c2.warning(f"Unit: {requested_unit}")
                    if c3.button(f"✅ Approve", key=f"app_{cabin}_{requested_unit}"):
                        storage["approved_units"].setdefault(cabin, [])
                        if requested_unit not in storage["approved_units"][cabin]:
                            storage["approved_units"][cabin].append(requested_unit)
                        req_list.remove(req)
                        if not req_list:
                            storage["pending_requests"].pop(cabin, None)
                        storage["activity_log"].append({
                            "Time":   datetime.datetime.now(IST).strftime("%H:%M:%S"),
                            "Action": "Unblock Approved",
                            "By":     "Admin",
                            "Detail": f"Unit {requested_unit} for Cabin {cabin}",
                        })
                        st.success(f"Approved {requested_unit} for Cabin {cabin}")
                        st.rerun()
                    if c4.button(f"❌ Reject", key=f"rej_{cabin}_{requested_unit}"):
                        req_list.remove(req)
                        if not req_list:
                            storage["pending_requests"].pop(cabin, None)
                        st.warning(f"Rejected {requested_unit} for Cabin {cabin}")
                        st.rerun()

            if not any_pending:
                st.info("No pending unblock requests.")

            st.divider()
            st.markdown("### Currently Unlocked Units")
            has_approved = False
            for cabin, units in storage.get("approved_units", {}).items():
                for unit in list(units):
                    has_approved = True
                    ca, cb, cc = st.columns([1, 1, 1])
                    ca.write(f"**Cabin {cabin}**")
                    cb.write(f"Unit: {unit}")
                    if cc.button(f"🚫 Revoke {unit}", key=f"rev_{cabin}_{unit}"):
                        storage["approved_units"][cabin].remove(unit)
                        st.error(f"Access Revoked for {unit}")
                        st.rerun()

            if not has_approved:
                st.write("No units are currently manually unlocked.")

        # ── Tab 4: Live Inventory ──────────────────────────────────────────
        with t4:
            st.subheader("🏢 Live Inventory Status")
            inv_data = load_data()

            if inv_data is not None and not inv_data.empty:
                sold_set  = storage.get("sold_units", set())
                booths    = storage.get("booths", {})
                # Build a display dataframe
                rows_disp = []
                for _, r in inv_data.iterrows():
                    uid = str(r.get('ID', '')).upper().strip()
                    if uid in ["705", "1205"]:
                        status = "🏥 Refuge"
                    elif uid in sold_set:
                        status = "⛔ Sold"
                    elif storage.get("inventory_released"):
                        status = "👁 Released (view only)"
                    else:
                        # Check if assigned to any cabin customer
                        cust_allotted = str(r.get('Customer Allotted', '')).strip()
                        cabin_assigned = None
                        for cb, cx in booths.items():
                            if cx and str(cx).upper() == str(cust_allotted).upper():
                                cabin_assigned = cb
                                break
                        if cabin_assigned:
                            status = f"🟢 Active – Cabin {cabin_assigned}"
                        else:
                            status = "🔒 Locked"
                    rows_disp.append({
                        "Unit ID":   uid,
                        "Floor":     r.get("Floor", ""),
                        "Carpet":    r.get("CARPET", ""),
                        "Status":    status,
                        "Customer":  r.get("Customer Allotted", ""),
                        "Agr. Value": r.get("Agreement Value", ""),
                    })

                df_live = pd.DataFrame(rows_disp)

                # Summary metrics
                total   = len(df_live)
                sold_c  = len(df_live[df_live["Status"].str.startswith("⛔")])
                active  = len(df_live[df_live["Status"].str.startswith("🟢")])
                locked  = len(df_live[df_live["Status"].str.startswith("🔒")])
                released= len(df_live[df_live["Status"].str.startswith("👁")])

                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                mc1.metric("Total Units", total)
                mc2.metric("⛔ Sold",     sold_c)
                mc3.metric("🟢 Active",   active)
                mc4.metric("🔒 Locked",   locked)
                mc5.metric("👁 Released", released)

                st.divider()
                # Filter
                filt = st.selectbox("Filter by status:", ["All", "⛔ Sold", "🟢 Active", "🔒 Locked", "👁 Released"])
                if filt != "All":
                    df_show = df_live[df_live["Status"].str.startswith(filt[:2])]
                else:
                    df_show = df_live

                st.dataframe(df_show, use_container_width=True)
            else:
                st.info("Inventory not loaded.")

        # ── Tab 5: Slot Tracker ────────────────────────────────────────────
        with t5:
            st.subheader("🕐 Token Slot Tracker")
            ist_now_admin = datetime.datetime.now(IST)
            active_s = current_slot(ist_now_admin)

            # Display all slots with timing
            for sl in SLOTS:
                is_active = active_s and active_s["name"] == sl["name"]
                badge = "🟢 **ACTIVE NOW**" if is_active else "⏸️"
                st.markdown(
                    f"**{sl['name']}** {badge}  ·  "
                    f"Tokens {sl['token_range'][0]}–{sl['token_range'][1] if sl['token_range'][1] < 9999 else '∞'}  ·  "
                    f"{sl['start'][0]:02d}:{sl['start'][1]:02d} – {sl['end'][0]:02d}:{sl['end'][1]:02d} IST"
                )

            st.divider()

            # Snapshot: admin can take a snapshot at end of a slot to record non-visited
            inv_data2 = load_data()
            st.markdown("### 📸 Take Slot Snapshot (Non-Visited Customers)")
            snap_slot = st.selectbox("Select Slot to Snapshot:", ["Slot 1", "Slot 2", "Slot 3"])

            if st.button(f"📸 Snapshot {snap_slot} Non-Visited Now"):
                # Determine token range for selected slot
                slot_def = next((s for s in SLOTS if s["name"] == snap_slot), None)
                if slot_def and inv_data2 is not None:
                    lo, hi = slot_def["token_range"]
                    visited = storage.get("visited_customers", set())
                    non_visited = []
                    if "Token Number" in inv_data2.columns and "Customer Allotted" in inv_data2.columns:
                        for _, r in inv_data2.iterrows():
                            try:
                                t_num = int(r.get("Token Number", 0))
                            except (ValueError, TypeError):
                                continue
                            if lo <= t_num <= hi:
                                cust = str(r.get("Customer Allotted", "")).strip()
                                if cust and str(cust).upper() not in {v.upper() for v in visited}:
                                    non_visited.append({
                                        "Token": t_num,
                                        "Customer": cust,
                                        "Unit": r.get("ID", ""),
                                    })
                    storage["slot_snapshots"][snap_slot] = non_visited
                    st.success(f"Snapshot taken: {len(non_visited)} non-visited customers in {snap_slot}")
                    st.rerun()

            st.divider()
            st.markdown("### Non-Visited Customers by Slot")
            snapshots = storage.get("slot_snapshots", {})
            if not snapshots:
                st.info("No snapshots taken yet. Use the button above at the end of each slot.")
            else:
                for sname, nv_list in snapshots.items():
                    with st.expander(f"{sname} — {len(nv_list)} non-visited", expanded=True):
                        if nv_list:
                            st.dataframe(pd.DataFrame(nv_list), use_container_width=True)
                        else:
                            st.success("All customers visited!")

        # ── Tab 6: Reset ───────────────────────────────────────────────────
        with t6:
            st.subheader("System Reset")
            st.warning("⚠️ This will erase ALL sales data, bookings, and cabin assignments.")
            reset_pw = st.text_input(
                "Reset Password:", type="password", key="admin_reset_final"
            )
            if st.button("💣 WIPE ALL DATA"):
                if reset_pw == RESET_PASSWORD:
                    storage["sold_units"]          = set()
                    storage["download_history"]    = []
                    storage["activity_log"]        = []
                    storage["waiting_customers"]   = []
                    storage["booths"]              = {letter: None for letter in "ABCDEFGHIJ"}
                    storage["pending_requests"]    = {}
                    storage["approved_units"]      = {letter: [] for letter in "ABCDEFGHIJ"}
                    storage["unblock_counts"]      = {letter: 0  for letter in "ABCDEFGHIJ"}
                    storage["visited_customers"]   = set()
                    storage["opted_out"]           = []
                    storage["inventory_released"]  = False
                    storage["slot_snapshots"]      = {}
                    st.cache_resource.clear()
                    st.success("System fully reset.")
                    st.rerun()
                else:
                    st.error("Incorrect reset password.")

