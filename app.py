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
import gspread
from google.oauth2.service_account import Credentials

# ================= GOOGLE SHEETS SETUP =================

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

gc = gspread.authorize(creds)

SPREADSHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
sheet = gc.open_by_key(SPREADSHEET_ID)

# ================= BACKEND HELPERS =================

def get_ws(name):
    try:
        return sheet.worksheet(name)
    except:
        ws = sheet.add_worksheet(title=name, rows="1000", cols="20")
        return ws

# ---------- WAITING LIST ----------
def get_waiting():
    ws = get_ws("Waiting_List")
    return ws.col_values(1)

def add_waiting(name):
    ws = get_ws("Waiting_List")
    ws.append_row([name])

def remove_waiting(name):
    ws = get_ws("Waiting_List")
    data = ws.get_all_values()
    for i, row in enumerate(data):
        if row and row[0] == name:
            ws.delete_rows(i + 1)
            break

# ---------- BOOTHS ----------
def init_booths():
    ws = get_ws("Booths")
    if not ws.get_all_values():
        ws.append_row(["Cabin", "Customer"])
        for cabin in "ABCDEFGHIJ":
            ws.append_row([cabin, ""])

def get_booths():
    ws = get_ws("Booths")
    data = ws.get_all_records()
    return {row["Cabin"]: row["Customer"] for row in data}

def assign_booth(cabin, customer):
    ws = get_ws("Booths")
    cell = ws.find(cabin)
    ws.update_cell(cell.row, 2, customer)

def clear_booth(cabin):
    ws = get_ws("Booths")
    cell = ws.find(cabin)
    ws.update_cell(cell.row, 2, "")

# ---------- SOLD ----------
def get_sold():
    ws = get_ws("Sold_Units")
    return ws.col_values(1)

def mark_sold(unit):
    ws = get_ws("Sold_Units")
    ws.append_row([unit])

# ---------- HISTORY ----------
def add_history(date, unit, customer, total):
    ws = get_ws("Download_History")
    ws.append_row([date, unit, customer, total])

def get_history():
    ws = get_ws("Download_History")
    data = ws.get_all_records()
    return pd.DataFrame(data)

# ================= INVENTORY (READ ONLY) =================

SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
TAB_NAME = "Inventory List"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(TAB_NAME)}"

@st.cache_data(ttl=5)
def load_inventory():
    df = pd.read_csv(CSV_URL)
    df.columns = df.columns.str.strip()
    return df

# ================= LOGIN =================

st.set_page_config(page_title="Tarangan Dash", layout="wide")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
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
            st.session_state.auth = True
            st.session_state.role = u
            init_booths()
            st.rerun()
        else:
            st.error("Invalid credentials.")

else:
    role = st.session_state.role

    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()

    # ================= GRE =================
    if role == "GRE":
        st.title("📝 GRE Entry")

        waiting = get_waiting()

        col1, col2 = st.columns(2)

        with col1:
            df = load_inventory()
            customers = df["Customer Allotted"].dropna().unique().tolist()
            selected = st.selectbox("Database Customers", ["-- Select --"] + customers)
            if st.button("Add Selected"):
                if selected != "-- Select --":
                    add_waiting(selected)
                    st.rerun()

        with col2:
            name = st.text_input("Walk-in Name")
            if st.button("Add Walk-in"):
                if name:
                    add_waiting(f"(WI) {name}")
                    st.rerun()

        st.subheader("Waiting List")
        for w in waiting:
            st.write(w)

    # ================= MANAGER =================
    elif role == "Manager":
        st.title("👔 Manager Assignment")

        waiting = get_waiting()
        booths = get_booths()

        if waiting:
            cust = st.selectbox("Select Customer", waiting)
            free = [k for k,v in booths.items() if not v]

            if free:
                cabin = st.selectbox("Assign Cabin", free)
                if st.button("Assign"):
                    assign_booth(cabin, cust)
                    remove_waiting(cust)
                    st.rerun()

        st.subheader("Cabin Status")
        for b,c in booths.items():
            st.write(f"{b}: {c if c else 'FREE'}")

    # ================= SALES =================
    elif role == "Sales":
        st.title("🏙️ Sales Portal")

        booths = get_booths()
        sold = get_sold()

        my_cabin = st.selectbox("Select Cabin", list(booths.keys()))
        cust = booths.get(my_cabin)

        if not cust:
            st.warning("Cabin Empty")
        else:
            st.success(f"Serving: {cust}")
            inv = load_inventory()

            cols = st.columns(6)
            for i,row in inv.iterrows():
                uid = str(row["ID"])
                disabled = uid in sold
                if cols[i%6].button(uid if not disabled else "SOLD", disabled=disabled):
                    st.session_state.selected_unit = uid

            if "selected_unit" in st.session_state:
                if st.button("Finalize"):
                    mark_sold(st.session_state.selected_unit)
                    add_history(str(datetime.date.today()), st.session_state.selected_unit, cust, 0)
                    clear_booth(my_cabin)
                    del st.session_state.selected_unit
                    st.success("Booked & Cabin Freed")
                    st.rerun()

                if st.button("Release"):
                    clear_booth(my_cabin)
                    del st.session_state.selected_unit
                    st.rerun()

    # ================= ADMIN =================
    elif role == "Tarangan":
        st.title("🛠 Admin Master Control")

        tab1, tab2, tab3 = st.tabs(["📊 Sales Report", "🏢 Booth Status", "🚨 Reset"])

        with tab1:
            df = get_history()
            if not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No sales yet.")

        with tab2:
            booths = get_booths()
            sold = get_sold()

            st.subheader("Cabins")
            for b,c in booths.items():
                st.write(f"{b}: {c if c else 'FREE'}")

            st.subheader("Sold Units")
            for s in sold:
                st.write(s)

        with tab3:
            pw = st.text_input("Reset Password", type="password")
            if st.button("WIPE ALL DATA"):
                if pw == "Atharva Joshi":
                    get_ws("Waiting_List").clear()
                    get_ws("Sold_Units").clear()
                    get_ws("Download_History").clear()
                    ws = get_ws("Booths")
                    ws.clear()
                    init_booths()
                    st.success("System Reset")
                    st.rerun()
                else:
                    st.error("Incorrect Password")
