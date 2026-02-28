import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import datetime
import io
import smtplib
import gspread
from google.oauth2.service_account import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# ================= GOOGLE SHEETS BACKEND =================

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

def ws(name):
    return sheet.worksheet(name)

# ================= BACKEND HELPERS =================

# Waiting List
def get_waiting():
    return ws("Waiting_List").col_values(1)

def add_waiting(name):
    ws("Waiting_List").append_row([name])

def remove_waiting(name):
    w = ws("Waiting_List")
    data = w.get_all_values()
    for i, row in enumerate(data):
        if row and row[0] == name:
            w.delete_rows(i+1)
            break

# Booths
def get_booths():
    data = ws("Booths").get_all_records()
    return {r["Cabin"]: r["Customer"] for r in data}

def assign_booth(cabin, cust):
    w = ws("Booths")
    cell = w.find(cabin)
    w.update_cell(cell.row, 2, cust)

def clear_booth(cabin):
    w = ws("Booths")
    cell = w.find(cabin)
    w.update_cell(cell.row, 2, "")

# Sold
def get_sold():
    return ws("Sold_Units").col_values(1)

def mark_sold(unit):
    ws("Sold_Units").append_row([unit])

# History
def add_history(data_dict):
    ws("Download_History").append_row(list(data_dict.values()))

def get_history():
    return pd.DataFrame(ws("Download_History").get_all_records())

# ================= INVENTORY UPDATE =================

def mark_inventory_sold(unit_id, customer):
    inv = ws("Inventory List")
    cell = inv.find(unit_id)
    headers = inv.row_values(1)

    cust_col = headers.index("Customer Allotted") + 1
    token_col = headers.index("Token Number") + 1

    inv.update_cell(cell.row, cust_col, customer)
    inv.update_cell(cell.row, token_col, "SOLD")

# ================= INVENTORY READ (FAST) =================

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

        st.title("📝 Stage 1: GRE Entry")

        df_master = load_inventory()
        customers = df_master["Customer Allotted"].dropna().unique().tolist()

        col_left, col_right = st.columns(2)

        with col_left:
            selected = st.selectbox("Database Customers", ["-- Select --"] + customers)
            if st.button("Add Selected"):
                if selected != "-- Select --":
                    add_waiting(selected)
                    st.rerun()

        with col_right:
            new_name = st.text_input("Walk-in Name")
            if st.button("Add Walk-in"):
                if new_name:
                    add_waiting(f"(WI) {new_name}")
                    st.rerun()

        st.subheader("Waiting List")
        for w in get_waiting():
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
                if st.button("Confirm Assignment"):
                    assign_booth(cabin, cust)
                    remove_waiting(cust)
                    st.rerun()

        st.subheader("Cabin Status")
        for b,c in booths.items():
            st.write(f"{b}: {c if c else 'FREE'}")

    # ================= SALES =================
    elif role == "Sales":

        st.title("🏙️ Stage 3: Sales Portal")

        booths = get_booths()
        sold_units = get_sold()

        my_cabin = st.selectbox("Select Your Cabin:", list(booths.keys()))
        cust_name = booths.get(my_cabin)

        if not cust_name:
            st.warning("Cabin Empty")
        else:
            st.success(f"Serving: {cust_name}")

            inventory = load_inventory()

            cols = st.columns(6)

            for i,row in inventory.iterrows():
                uid = str(row["ID"])
                is_sold = uid in sold_units or str(row.get("Token Number")) == "SOLD"

                if cols[i%6].button(
                    f"{uid}" if not is_sold else f"{uid} SOLD",
                    disabled=is_sold
                ):
                    st.session_state.selected_unit = uid

            if "selected_unit" in st.session_state:

                if st.button("✅ Finalize & Book"):
                    unit = st.session_state.selected_unit

                    mark_sold(unit)
                    mark_inventory_sold(unit, cust_name)

                    add_history({
                        "Date": str(datetime.date.today()),
                        "Unit": unit,
                        "Customer": cust_name
                    })

                    clear_booth(my_cabin)
                    del st.session_state.selected_unit

                    st.success("Booked Successfully & Cabin Freed")
                    st.rerun()

                if st.button("❌ Close / Release"):
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
                st.info("No sales recorded yet.")

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
            if st.button("💣 WIPE ALL DATA"):
                if pw == "Atharva Joshi":
                    ws("Waiting_List").clear()
                    ws("Sold_Units").clear()
                    ws("Download_History").clear()
                    st.success("System Reset")
                    st.rerun()
                else:
                    st.error("Incorrect Password")
