import streamlit as st
import pandas as pd
import re
import urllib.parse
from fpdf import FPDF
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

# ================== CONFIG ==================

SHEET_ID = "1L-anmwniKOgT2DfNJMdqYkMsRw4slAcH2MUR5OPfcP0"
INVENTORY_TAB = "Inventory List"
CUSTOMER_TAB = "Customer Database"

INV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(INVENTORY_TAB)}"
CUST_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(CUSTOMER_TAB)}"

# ================== STORAGE ==================

@st.cache_resource
def get_storage():
    return {
        "waiting_customers": [],
        "booths": {l: None for l in "ABCDEFGH"},
        "sold_units": set(),
        "in_process_units": {},
        "pending_requests": {},
        "approved_units": {l: [] for l in "ABCDEFGH"},
    }

storage = get_storage()

# ================== LOAD DATA ==================

@st.cache_data(ttl=5)
def load_inventory():
    df = pd.read_csv(INV_URL)
    df.columns = df.columns.str.strip()
    return df

@st.cache_data(ttl=5)
@st.cache_data(ttl=5)
def load_customers():
    try:
        df = load_inventory()

        if "Customer Allotted" in df.columns:
            customers = (
                df["Customer Allotted"]
                .dropna()
                .astype(str)
                .str.strip()
            )

            # Remove empty & nan
            customers = customers[
                (customers != "") &
                (customers.str.lower() != "nan")
            ]

            # Remove duplicates & sort
            customers = sorted(customers.unique().tolist())

            return customers

        else:
            st.error("Column 'Customer Allotted' not found in Inventory List.")
            return []

    except Exception as e:
        st.error(f"Error loading customers: {e}")
        return []


# ================== APP CONFIG ==================

st.set_page_config("Tarangan Dashboard", layout="wide")

if "auth" not in st.session_state:
    st.session_state.auth = False

if "selected_unit" not in st.session_state:
    st.session_state.selected_unit = None

# ================== LOGIN ==================

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

        if u in creds and creds[u] == p:
            st.session_state.auth = True
            st.session_state.role = u
            st.rerun()
        else:
            st.error("Invalid credentials.")

# ================== MAIN APP ==================

else:

    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()

    role = st.session_state.role

    # ==========================================================
    # GRE DASHBOARD
    # ==========================================================

    if role == "GRE":

        st.title("📝 GRE Dashboard")

        with st.expander("➕ Add Customer Entry", expanded=True):

            entry_type = st.radio(
                "Select Entry Type",
                ["Existing Customer", "Walk-In Customer"],
                horizontal=True
            )

            # ---------------- EXISTING ----------------
            if entry_type == "Existing Customer":

                customers = load_customers()

                if customers:
                    selected = st.selectbox("Select Customer", customers)

                    if st.button("Add to Waiting List"):
                        storage["waiting_customers"].append({
                            "name": selected,
                            "type": "Existing"
                        })
                        st.success("Customer added.")
                        st.rerun()
                else:
                    st.warning("No customers found in database.")

            # ---------------- WALK-IN ----------------
            else:

                walkin_name = st.text_input("Enter Walk-In Name")

                if st.button("Add Walk-In") and walkin_name:
                    storage["waiting_customers"].append({
                        "name": f"(WI) {walkin_name}",
                        "type": "Walk-In"
                    })
                    st.success("Walk-In added.")
                    st.rerun()

        st.subheader("⏳ Waiting List")

        for i, cust in enumerate(storage["waiting_customers"]):
            col1, col2 = st.columns([4,1])

            col1.write(f"{cust['name']}")

            if col2.button("Remove", key=f"rem_{i}"):
                storage["waiting_customers"].pop(i)
                st.rerun()

    # ==========================================================
    # MANAGER DASHBOARD
    # ==========================================================

    elif role == "Manager":

        st.title("👔 Manager Dashboard")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Assign Customer")

            if storage["waiting_customers"]:

                selected = st.selectbox(
                    "Select Customer",
                    storage["waiting_customers"],
                    format_func=lambda x: x["name"]
                )

                free_cabins = [
                    k for k, v in storage["booths"].items()
                    if v is None
                ]

                if free_cabins:
                    cabin = st.selectbox("Assign Cabin", free_cabins)

                    if st.button("Confirm Assignment"):
                        storage["booths"][cabin] = selected["name"]
                        storage["waiting_customers"].remove(selected)
                        st.rerun()
                else:
                    st.warning("All cabins occupied.")

            else:
                st.info("No waiting customers.")

        with col2:
            st.subheader("Cabin Status")

            for cab, occ in storage["booths"].items():
                status = occ if occ else "FREE"
                st.write(f"Cabin {cab}: {status}")

                if occ:
                    if st.button(f"Clear {cab}", key=f"clear_{cab}"):
                        storage["booths"][cab] = None
                        st.rerun()

    # ==========================================================
    # SALES DASHBOARD
    # ==========================================================

    elif role == "Sales":

        st.title("💼 Sales Dashboard")

        my_cabin = st.selectbox("Select Your Cabin", list("ABCDEFGH"))
        current_customer = storage["booths"].get(my_cabin)

        if not current_customer:
            st.warning("Waiting for assignment.")
        else:
            st.success(f"Serving: {current_customer}")

            inv = load_inventory()
            cols = st.columns(6)

            for i, row in inv.iterrows():
                uid = str(row["ID"]).strip()

                is_sold = uid in storage["sold_units"]
                is_busy = uid in storage["in_process_units"] and \
                          storage["in_process_units"][uid] != my_cabin

                if is_sold:
                    cols[i%6].button(f"⛔ {uid}\nSOLD", disabled=True)
                elif is_busy:
                    cols[i%6].button(f"⏳ {uid}\nBUSY", disabled=True)
                else:
                    if cols[i%6].button(f"✅ {uid}", key=f"u_{uid}"):
                        storage["in_process_units"][uid] = my_cabin
                        st.session_state.selected_unit = uid
                        st.rerun()

            # Booking section
            if st.session_state.selected_unit:

                st.info(f"Selected Unit: {st.session_state.selected_unit}")

                colA, colB = st.columns(2)

                with colA:
                    if st.button("Finalize & Book"):
                        storage["sold_units"].add(st.session_state.selected_unit)
                        storage["in_process_units"].pop(
                            st.session_state.selected_unit, None
                        )
                        storage["booths"][my_cabin] = None
                        st.session_state.selected_unit = None
                        st.success("Unit Booked")
                        st.rerun()

                with colB:
                    if st.button("Release"):
                        storage["in_process_units"].pop(
                            st.session_state.selected_unit, None
                        )
                        st.session_state.selected_unit = None
                        st.rerun()

    # ==========================================================
    # ADMIN DASHBOARD
    # ==========================================================

    elif role == "Tarangan":

        st.title("🛠 Admin Dashboard")

        inv = load_inventory()
        cols = st.columns(6)

        for i, row in inv.iterrows():

            uid = str(row["ID"]).strip()

            if uid in storage["sold_units"]:
                color = "#ff4b4b"
                status = "SOLD"
            elif uid in storage["in_process_units"]:
                color = "#ffa500"
                status = "IN PROCESS"
            else:
                color = "#28a745"
                status = "AVAILABLE"

            cols[i%6].markdown(f"""
                <div style="
                    background:{color};
                    color:white;
                    padding:10px;
                    border-radius:5px;
                    text-align:center;">
                <b>{uid}</b><br>{status}
                </div>
            """, unsafe_allow_html=True)
