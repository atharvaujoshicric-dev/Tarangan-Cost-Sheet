import streamlit as st
import pandas as pd
import re
import urllib.parse
import sqlite3
from fpdf import FPDF
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# ================= DATABASE =================

DB_FILE = "tarangan.db"

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS waiting_customers (
                    name TEXT PRIMARY KEY
                )""")

    c.execute("""CREATE TABLE IF NOT EXISTS booths (
                    cabin TEXT PRIMARY KEY,
                    customer TEXT
                )""")

    c.execute("""CREATE TABLE IF NOT EXISTS sold_units (
                    unit TEXT PRIMARY KEY
                )""")

    c.execute("""CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    unit TEXT,
                    customer TEXT,
                    total INTEGER
                )""")

    for cabin in "ABCDEFGHIJ":
        c.execute("INSERT OR IGNORE INTO booths (cabin, customer) VALUES (?, ?)", (cabin, None))

    conn.commit()
    conn.close()

init_db()

# ================= HELPERS =================

def add_waiting(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO waiting_customers VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_waiting():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM waiting_customers", conn)
    conn.close()
    return df["name"].tolist()

def remove_waiting(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM waiting_customers WHERE name=?", (name,))
    conn.commit()
    conn.close()

def assign_booth(cabin, name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE booths SET customer=? WHERE cabin=?", (name, cabin))
    conn.commit()
    conn.close()

def get_booths():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM booths", conn)
    conn.close()
    return dict(zip(df["cabin"], df["customer"]))

def clear_booth(cabin):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE booths SET customer=NULL WHERE cabin=?", (cabin,))
    conn.commit()
    conn.close()

def mark_sold(unit):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO sold_units VALUES (?)", (unit,))
    conn.commit()
    conn.close()

def get_sold():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM sold_units", conn)
    conn.close()
    return df["unit"].tolist()

def add_history(date, unit, customer, total):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO download_history (date, unit, customer, total) VALUES (?, ?, ?, ?)",
              (date, unit, customer, total))
    conn.commit()
    conn.close()

def get_history():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM download_history", conn)
    conn.close()
    return df

# ================= INVENTORY =================

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
        st.title("📝 GRE Entry")

        waiting = get_waiting()
        booths = get_booths()

        col1, col2 = st.columns(2)

        with col1:
            df = load_inventory()
            customers = df["Customer Allotted"].dropna().unique().tolist()
            selected = st.selectbox("Database Customers", ["-- Select --"] + customers)
            if st.button("Add Selected"):
                if selected != "-- Select --":
                    add_waiting(selected)
                    st.success("Added")
                    st.rerun()

        with col2:
            name = st.text_input("Walk-in Name")
            if st.button("Add Walk-in"):
                if name:
                    add_waiting(f"(WI) {name}")
                    st.success("Added")
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
            free = [k for k,v in booths.items() if v is None]

            if free:
                cabin = st.selectbox("Assign Cabin", free)
                if st.button("Assign"):
                    assign_booth(cabin, cust)
                    remove_waiting(cust)
                    st.success("Assigned")
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
                    st.warning("Released")
                    st.rerun()

    # ================= ADMIN =================
    elif role == "Tarangan":
        st.title("🛠 Admin Master Control")

        tab1, tab2, tab3 = st.tabs(["📊 Sales Report", "🏢 Booth Status", "🚨 Reset System"])

        # ================= SALES REPORT =================
        with tab1:
            st.subheader("Sales Performance")

            history_df = get_history()

            if not history_df.empty:

                # Clean numeric
                history_df["total"] = pd.to_numeric(history_df["total"], errors="coerce").fillna(0)

                total_revenue = int(history_df["total"].sum())
                units_sold = len(history_df)

                m1, m2 = st.columns(2)
                m1.metric("Units Sold", units_sold)
                m2.metric("Total Revenue", f"₹ {total_revenue:,}")

                st.divider()
                st.dataframe(history_df, use_container_width=True)

                # Export
                csv = history_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Export Report (CSV)",
                    data=csv,
                    file_name="tarangan_sales_report.csv",
                    mime="text/csv"
                )

            else:
                st.info("No sales recorded yet.")

        # ================= BOOTH STATUS =================
        with tab2:
            st.subheader("Live Booth Status")

            booths = get_booths()
            sold_units = get_sold()

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Cabin Assignments")
                for cabin, customer in booths.items():
                    st.write(f"Cabin {cabin}: {customer if customer else 'FREE'}")

            with col2:
                st.markdown("### Sold Units")
                if sold_units:
                    for unit in sold_units:
                        st.write(f"Unit {unit}")
                else:
                    st.write("No units sold yet.")

        # ================= SYSTEM RESET =================
        with tab3:
            st.subheader("Danger Zone")

            reset_pw = st.text_input("Enter Reset Password", type="password")

            if st.button("💣 WIPE ALL DATA"):

                if reset_pw == "Atharva Joshi":

                    conn = get_connection()
                    c = conn.cursor()

                    # Clear all tables
                    c.execute("DELETE FROM waiting_customers")
                    c.execute("DELETE FROM sold_units")
                    c.execute("DELETE FROM download_history")
                    c.execute("UPDATE booths SET customer=NULL")

                    conn.commit()
                    conn.close()

                    st.success("System wiped successfully.")
                    st.rerun()

                else:
                    st.error("Incorrect Password")
