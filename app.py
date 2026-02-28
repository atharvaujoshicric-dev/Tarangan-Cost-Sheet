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

# ================= CONFIG =================

SENDER_EMAIL = "atharvaujoshi@gmail.com"
SENDER_NAME = "Tarangan Cost Sheet"
APP_PASSWORD = "nybl zsnx zvdw edqr"
RECEIVER_EMAIL = "spydarr1106@gmail.com"

SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

# ================= HELPERS =================

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

# ================= STORAGE =================

@st.cache_resource
def get_storage():
    return {
        "sold_units": set(),
        "booths": {l: None for l in "ABCDEFGHIJ"},
        "waiting_customers": [],
        "approved_units": {l: [] for l in "ABCDEFGHIJ"},
        "unblock_counts": {l: 0 for l in "ABCDEFGHIJ"},
        "pending_requests": {},
        "download_history": []
    }

storage = get_storage()

def reset_cabin(cabin):
    storage["booths"][cabin] = None
    storage["approved_units"][cabin] = []
    storage["unblock_counts"][cabin] = 0
    if cabin in storage["pending_requests"]:
        del storage["pending_requests"][cabin]

# ================= DATA =================

@st.cache_data(ttl=2)
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = df.columns.str.strip()
    return df

# ================= APP =================

st.set_page_config(page_title="Tarangan Dash", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# ================= LOGIN =================

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
            st.rerun()
        else:
            st.error("Invalid credentials.")

# ================= MAIN =================

else:

    role = st.session_state.get("role", "")

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.role = ""
        st.rerun()

    # =====================================================
    # GRE DASHBOARD
    # =====================================================
    if role == "GRE":

        st.title("📝 Stage 1: GRE Entry")

        df_master = load_data()

        active = [str(x).upper() for x in storage["waiting_customers"]]
        active += [str(x).upper() for x in storage["booths"].values() if x]

        col1, col2 = st.columns(2)

        with col1:
            if "Customer Allotted" in df_master.columns:
                db_list = df_master["Customer Allotted"].dropna().unique().tolist()
                db_list = [c for c in db_list if str(c).upper() not in active]

                selected = st.selectbox("Select Customer", ["-- Select --"] + sorted(db_list))

                if st.button("Add Selected"):
                    if selected != "-- Select --":
                        storage["waiting_customers"].append(selected)
                        st.success("Added")
                        st.rerun()

        with col2:
            name = st.text_input("Walk-in Name")
            if st.button("Add Walk-in"):
                if name:
                    walk = f"(WI) {name}"
                    if walk.upper() in active:
                        st.warning("Already exists")
                    else:
                        storage["waiting_customers"].append(walk)
                        st.success("Added")
                        st.rerun()

        st.subheader("Waiting List")
        for i, cust in enumerate(storage["waiting_customers"]):
            c1, c2 = st.columns([5,1])
            c1.write(cust)
            if c2.button("❌", key=f"rm_{i}"):
                storage["waiting_customers"].pop(i)
                st.rerun()

    # =====================================================
    # MANAGER DASHBOARD  ✅ FIXED
    # =====================================================
    elif role == "Manager":

        st.title("👔 Manager Assignment")

        col1, col2 = st.columns(2)

        with col1:
            if storage["waiting_customers"]:
                cust = st.selectbox("Select Customer", storage["waiting_customers"])
                free = [k for k,v in storage["booths"].items() if v is None]

                if free:
                    cabin = st.selectbox("Assign Cabin", free)
                    if st.button("Assign"):
                        storage["booths"][cabin] = cust
                        storage["waiting_customers"].remove(cust)
                        st.success("Assigned")
                        st.rerun()
                else:
                    st.warning("All cabins occupied.")

        with col2:
            for b, c in storage["booths"].items():
                if c:
                    st.write(f"Cabin {b}: {c}")
                    if st.button(f"Clear {b}", key=f"clr_{b}"):
                        reset_cabin(b)
                        st.rerun()
                else:
                    st.write(f"Cabin {b}: FREE")

    # =====================================================
    # SALES DASHBOARD
    # =====================================================
    elif role == "Sales":

        st.title("🏙️ Sales Portal")

        my_cabin = st.selectbox("Select Cabin", list("ABCDEFGHIJ"))
        cust = storage["booths"].get(my_cabin)

        if not cust:
            st.warning("Cabin Empty")
        else:
            st.success(f"Serving: {cust}")

            df = load_data()
            if "ID" in df.columns:
                selected_unit = st.selectbox("Select Unit", df["ID"].astype(str).tolist())

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("Finalize & Book"):
                        storage["sold_units"].add(selected_unit)
                        reset_cabin(my_cabin)
                        st.success("Booked & Cabin Freed")
                        st.rerun()

                with col2:
                    if st.button("Close / Release"):
                        reset_cabin(my_cabin)
                        st.warning("Released & Cabin Freed")
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
