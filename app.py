import os
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
import re
import io


from supabase import create_client, Client
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# -------------------------------------------------
# RENDER -> CREATE .streamlit/secrets.toml FROM ENV
# -------------------------------------------------
BASE_DIR = Path(__file__).parent
STREAMLIT_DIR = BASE_DIR / ".streamlit"
STREAMLIT_DIR.mkdir(parents=True, exist_ok=True)
SECRETS_FILE = STREAMLIT_DIR / "secrets.toml"


def _escape_toml(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def ensure_render_secrets_file():
    if SECRETS_FILE.exists():
        return

    auth_redirect_uri = os.getenv("AUTH_REDIRECT_URI", "")
    auth_cookie_secret = os.getenv("AUTH_COOKIE_SECRET", "")
    auth_client_id = os.getenv("AUTH_CLIENT_ID", "")
    auth_client_secret = os.getenv("AUTH_CLIENT_SECRET", "")
    auth_server_metadata_url = os.getenv("AUTH_SERVER_METADATA_URL", "")

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")

    required = [
        auth_redirect_uri,
        auth_cookie_secret,
        auth_client_id,
        auth_client_secret,
        auth_server_metadata_url,
    ]

    if not all(required):
        return

    content = f'''SUPABASE_URL = "{_escape_toml(supabase_url)}"
SUPABASE_KEY = "{_escape_toml(supabase_key)}"

[auth]
redirect_uri = "{_escape_toml(auth_redirect_uri)}"
cookie_secret = "{_escape_toml(auth_cookie_secret)}"
client_id = "{_escape_toml(auth_client_id)}"
client_secret = "{_escape_toml(auth_client_secret)}"
server_metadata_url = "{_escape_toml(auth_server_metadata_url)}"
'''

    SECRETS_FILE.write_text(content, encoding="utf-8")


ensure_render_secrets_file()


# -------------------------------------------------
# APP CONFIG + AUTH + SUPABASE
# -------------------------------------------------
st.set_page_config(layout="wide")


@st.cache_resource
def get_supabase() -> Client:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    return create_client(supabase_url, supabase_key)


def get_current_user_id():
    try:
        return st.user.get("sub") or st.user.get("email") or "anonymous"
    except Exception:
        return "anonymous"


def get_current_user_email():
    try:
        return st.user.get("email", "")
    except Exception:
        return ""


def auth_is_configured():
    try:
        auth_cfg = st.secrets["auth"]
        required = [
            auth_cfg["redirect_uri"],
            auth_cfg["cookie_secret"],
            auth_cfg["client_id"],
            auth_cfg["client_secret"],
            auth_cfg["server_metadata_url"],
        ]
        return all(required)
    except Exception:
        return False


def is_logged_in():
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def show_login_screen():
    st.title("Pricing App v13 - Full Version")
    st.info("Please log in to continue.")

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.button(
            "Login with Google",
            on_click=st.login,
            use_container_width=True,
            key="login_google_button"
        )


if not auth_is_configured():
    st.error("Authentication is not configured correctly.")
    st.stop()
import json
from datetime import datetime, timedelta

from pathlib import Path

PERSIST_ROOT = Path(os.getenv("PERSIST_ROOT", "/var/data"))
PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

MAIN_CODES = ["SINIAT", "KNAUF", "SAINT_GOBAIN"]

user_id = get_current_user_id().replace("@", "_").replace(".", "_").replace("/", "_").replace("\\", "_")

USER_DIR = PERSIST_ROOT / user_id
UPLOADS_DIR = USER_DIR / "uploads"
COMPANIES_FILE = USER_DIR / "companies.csv"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

ROOT_STORAGE = PERSIST_ROOT
ADMIN_DIR = ROOT_STORAGE / "_admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)

USERS_REGISTRY_FILE = ADMIN_DIR / "users_registry.json"

ADMIN_EMAILS = [
    "gmyl13@gmail.com"
]


def load_json_data(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_data(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso():
    return datetime.utcnow().isoformat()


def parse_iso(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def get_user_identity():
    try:
        return {
            "email": st.user.get("email", "").strip(),
            "sub": st.user.get("sub", "").strip(),
            "name": st.user.get("name", "").strip(),
        }
    except Exception:
        return {
            "email": "",
            "sub": "",
            "name": "",
        }


def load_users_registry():
    if not USERS_REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(USERS_REGISTRY_FILE.read_text(encoding="utf-8"))
    except:
        return []


def save_users_registry(data):
    USERS_REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def is_admin_user():
    user = get_user_identity()
    return user["email"] in ADMIN_EMAILS


def find_user_index(users, email, sub):
    for i, row in enumerate(users):
        if row.get("email") == email and row.get("sub") == sub:
            return i
    return None


def ensure_current_user_in_registry():
    user = get_user_identity()
    users = load_users_registry()

    idx = find_user_index(users, user["email"], user["sub"])
    if idx is None:
        status = "approved" if user["email"] in ADMIN_EMAILS else "pending"
        users.append({
            "email": user["email"],
            "sub": user["sub"],
            "name": user["name"],
            "status": status,
            "first_seen": now_iso(),
            "last_login": now_iso(),
            "last_seen": now_iso(),
        })
    else:
        users[idx]["name"] = user["name"]
        users[idx]["last_login"] = now_iso()
        users[idx]["last_seen"] = now_iso()

        if user["email"] in ADMIN_EMAILS:
            users[idx]["status"] = "approved"

    save_users_registry(users)


def touch_current_user():
    user = get_user_identity()
    users = load_users_registry()

    idx = find_user_index(users, user["email"], user["sub"])
    if idx is not None:
        users[idx]["last_seen"] = now_iso()
        save_users_registry(users)


def get_current_user_status():
    user = get_user_identity()
    users = load_users_registry()

    idx = find_user_index(users, user["email"], user["sub"])
    if idx is None:
        return "pending"

    return users[idx].get("status", "pending")


def current_user_is_blocked():
    return get_current_user_status() == "blocked"


def current_user_is_approved():
    return get_current_user_status() == "approved"


def get_current_user_status():
    user = get_user_identity()

    if user["email"] in ADMIN_EMAILS:
        return "approved"

    users = load_users_registry()

    idx = find_user_index(users, user["email"], user["sub"])
    if idx is None:
        return "pending"

    return users[idx].get("status", "pending")


def online_status_from_last_seen(last_seen_value):
    dt = parse_iso(last_seen_value)
    if dt is None:
        return "Offline"

    if datetime.utcnow() - dt <= timedelta(minutes=2):
        return "Online"

    return "Offline"

if not is_logged_in():
    show_login_screen()
    st.stop()

touch_current_user()

if current_user_is_blocked():
    st.error("Access denied. Your account has been blocked.")
    st.button(
        "Logout",
        on_click=st.logout,
        use_container_width=True,
        key="blocked_logout_button"
    )
    st.stop()

if not current_user_is_approved():
    st.warning("Your account is pending admin approval.")
    st.button(
        "Logout",
        on_click=st.logout,
        use_container_width=True,
        key="pending_logout_button"
    )
    st.stop()

touch_current_user()

st.write("DEBUG EMAIL:", get_user_identity()["email"])
st.write("DEBUG ADMINS:", ADMIN_EMAILS)

if current_user_is_blocked():
    st.error("Access denied. Your account has been blocked.")
    st.button(
        "Logout",
        on_click=st.logout,
        use_container_width=True,
        key="blocked_logout_button"
    )
    st.stop()

if not current_user_is_approved():
    st.warning("Your account is pending admin approval.")
    st.button(
        "Logout",
        on_click=st.logout,
        use_container_width=True,
        key="pending_logout_button"
    )
    st.stop()


with st.sidebar:
    st.success("Logged in")
    st.write(f"User: {get_current_user_email() or get_current_user_id()}")

    st.button(
        "Logout",
        on_click=st.logout,
        use_container_width=True,
        key="logout_button"
    )

st.title("Pricing App v13 - Full Version")


# -------------------------------------------------
# APP CONFIG + AUTH + SUPABASE
# -------------------------------------------------


@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


def get_current_user_id():
    try:
        return st.user.get("sub") or st.user.get("email") or "anonymous"
    except Exception:
        return "anonymous"


def get_current_user_email():
    try:
        return st.user.get("email", "")
    except Exception:
        return ""


# -------------------------------------------------
# SAFE COMPANIES LOADING
# -------------------------------------------------
def load_companies_safe():
    default = pd.DataFrame([
        {"code": "SINIAT", "name": "Siniat"},
        {"code": "KNAUF", "name": "Knauf"},
        {"code": "SAINT_GOBAIN", "name": "Saint-Gobain"},
    ])

    if not COMPANIES_FILE.exists():
        default.to_csv(COMPANIES_FILE, index=False)
        return default

    try:
        df = pd.read_csv(COMPANIES_FILE)

        if "code" not in df.columns or "name" not in df.columns:
            default.to_csv(COMPANIES_FILE, index=False)
            return default

        df = df[["code", "name"]].copy()
        df["code"] = df["code"].astype(str).str.strip().str.upper()
        df["name"] = df["name"].astype(str).str.strip()

        if df.empty:
            default.to_csv(COMPANIES_FILE, index=False)
            return default

        return df

    except Exception:
        default.to_csv(COMPANIES_FILE, index=False)
        return default


def save_companies(df):
    df.to_csv(COMPANIES_FILE, index=False)


def normalize_code(text):
    text = str(text).strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


companies_df = load_companies_safe()

for _, row in companies_df.iterrows():
    (UPLOADS_DIR / row["code"]).mkdir(parents=True, exist_ok=True)


# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def get_company_folder(code):
    folder = UPLOADS_DIR / code
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_next_version_filename(company, dt, original_name):
    folder = get_company_folder(company)

    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    dd = dt.strftime("%d")

    ext = Path(original_name).suffix.lower()
    if ext not in [".xlsx", ".xlsm"]:
        ext = ".xlsx"

    existing = list(folder.glob(f"{company}_{yyyy}_{mm}_{dd}_v*{ext}"))

    max_v = 0
    for f in existing:
        try:
            v = int(f.stem.split("_v")[-1])
            max_v = max(max_v, v)
        except Exception:
            pass

    return f"{company}_{yyyy}_{mm}_{dd}_v{max_v + 1}{ext}"


def get_company_files(code):
    folder = get_company_folder(code)
    files = []
    for f in sorted(folder.glob("*.*"), reverse=True):
        if f.suffix.lower() in [".xlsx", ".xlsm"]:
            files.append(f.name)
    return files


def list_saved_sources():
    rows = []
    for _, row in companies_df.iterrows():
        code = row["code"]
        name = row["name"]
        folder = get_company_folder(code)

        for f in sorted(folder.glob("*.*"), reverse=True):
            if f.suffix.lower() in [".xlsx", ".xlsm"]:
                rows.append({
                    "Company Code": code,
                    "Company Name": name,
                    "Filename": f.name,
                    "Folder": str(folder),
                    "Full Path": str(f),
                    "Modified": pd.to_datetime(f.stat().st_mtime, unit="s")
                })

    if rows:
        return pd.DataFrame(rows).sort_values("Modified", ascending=False).reset_index(drop=True)

    return pd.DataFrame(columns=["Company Code", "Company Name", "Filename", "Folder", "Full Path", "Modified"])


def company_has_files(code):
    folder = get_company_folder(code)
    for f in folder.glob("*.*"):
        if f.suffix.lower() in [".xlsx", ".xlsm"]:
            return True
    return False


def load_data(file):
    try:
        df = pd.read_excel(file, sheet_name="PRICELIST")
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None


def find_col(df, names):
    cols = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in cols:
            return cols[n.lower()]
    return None


def prepare_catalog(df):
    if df is None:
        return None

    sap = find_col(df, ["SAP", "Κωδικός SAP"])
    prod = find_col(df, ["Product", "Προϊόν"])
    price = find_col(df, ["Price", "Τιμή €/ΜΜ", "Τιμή", "Price €/MM"])
    mm = find_col(df, ["ΜΜ πώλησης", "MM", "Unit", "ΜΜ"])
    pack = find_col(df, ["Συσκευασία", "Package", "pack"])
    category = find_col(df, ["Κατηγορία", "Category", "category"])

    if not sap or not prod or not price:
        return None

    out = pd.DataFrame()
    out["SAP"] = df[sap].astype(str).str.strip()
    out["Product"] = df[prod].astype(str).str.strip()
    out["Price"] = pd.to_numeric(df[price], errors="coerce")
    out["MM"] = df[mm].astype(str).str.strip() if mm else ""
    out["Package"] = df[pack].astype(str).str.strip() if pack else ""
    out["Category"] = df[category].astype(str).str.strip() if category else ""

    out = out.dropna(subset=["Price"])
    out = out[out["Price"] > 0]
    out = out.reset_index(drop=True)

    out["DISPLAY"] = out["Product"] + " | SAP " + out["SAP"]

    return out


def apply_discounts(price, discs):
    if price is None or pd.isna(price):
        return None

    p = float(price)
    for d in discs:
        if d is not None and d != 0:
            p *= (1 - d / 100)

    return round(p, 2)


def best_price(d):
    valid = {k: round(v, 2) for k, v in d.items() if v is not None and v > 0}

    if not valid:
        return ""

    min_val = min(valid.values())
    winners = [k for k, v in valid.items() if v == min_val]

    label_map = {
        "SINIAT": "SINIAT",
        "KNAUF": "KNAUF",
        "SAINT_GOBAIN": "SAINT-GOBAIN",
    }

    if len(winners) == 3:
        return "Same Price all"
    if len(winners) == 2:
        return " / ".join(label_map[w] for w in winners)
    return label_map[winners[0]]


def compare_note(a_name, a_price, b_name, b_price):
    if a_price is None or b_price is None:
        return ""
    a = round(a_price, 2)
    b = round(b_price, 2)
    if a == b:
        return "Same Price"
    if a > b:
        return f"{a_name} more expensive"
    return f"{a_name} cheaper"


def get_catalog_row(df, display_value):
    if df is None or df.empty or not display_value:
        return None
    rows = df[df["DISPLAY"] == display_value]
    if rows.empty:
        return None
    return rows.iloc[0]


def row_result_dict(visible_index, row_id, catalogs):
    result = {"Row": visible_index + 1}

    supplier_info = {
        "SINIAT": ("Siniat", catalogs.get("SINIAT")),
        "KNAUF": ("Knauf", catalogs.get("KNAUF")),
        "SAINT_GOBAIN": ("Saint-Gobain", catalogs.get("SAINT_GOBAIN")),
    }

    final_prices = {}

    for code, (label, df) in supplier_info.items():
        selected_product = st.session_state.get(f"row_{row_id}_{code}_product", "")
        row = get_catalog_row(df, selected_product)

        discs = []
        for d in range(1, 6):
            discs.append(st.session_state.get(f"row_{row_id}_{code}_disc_{d}", 0.0))

        if row is not None:
            base_price = round(float(row["Price"]), 2)
            final_price = apply_discounts(row["Price"], discs)
            final_prices[code] = final_price

            result[f"{label} Product"] = row["Product"]
            result[f"{label} SAP"] = row["SAP"]
            result[f"{label} MM"] = row["MM"]
            result[f"{label} Package"] = row["Package"]
            result[f"{label} Base Price"] = base_price
            for i, disc in enumerate(discs, start=1):
                result[f"{label} Disc{i}"] = disc
            result[f"{label} Final Price"] = final_price
        else:
            final_prices[code] = None
            result[f"{label} Product"] = ""
            result[f"{label} SAP"] = ""
            result[f"{label} MM"] = ""
            result[f"{label} Package"] = ""
            result[f"{label} Base Price"] = ""
            for i in range(1, 6):
                result[f"{label} Disc{i}"] = st.session_state.get(f"row_{row_id}_{code}_disc_{i}", 0.0)
            result[f"{label} Final Price"] = ""

    result["Best Price"] = best_price(final_prices)
    result["Knauf vs Siniat"] = compare_note("Knauf", final_prices.get("KNAUF"), "Siniat", final_prices.get("SINIAT"))
    result["Saint-Gobain vs Siniat"] = compare_note("Saint-Gobain", final_prices.get("SAINT_GOBAIN"), "Siniat", final_prices.get("SINIAT"))
    result["Saint-Gobain vs Knauf"] = compare_note("Saint-Gobain", final_prices.get("SAINT_GOBAIN"), "Knauf", final_prices.get("KNAUF"))

    return result


def build_export_dataframe(row_ids, catalogs):
    rows = []
    for visible_index, row_id in enumerate(row_ids):
        rows.append(row_result_dict(visible_index, row_id, catalogs))
    return pd.DataFrame(rows)


def style_excel_worksheet(ws):
    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    siniat_fill = PatternFill(fill_type="solid", fgColor="DDEBF7")
    knauf_fill = PatternFill(fill_type="solid", fgColor="E2F0D9")
    sg_fill = PatternFill(fill_type="solid", fgColor="FCE4D6")
    result_fill = PatternFill(fill_type="solid", fgColor="FFF2CC")

    ws.freeze_panes = "A2"

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = border

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = left_align

    headers = [cell.value for cell in ws[1]]

    for col_idx, header in enumerate(headers, start=1):
        if header is None:
            continue

        if str(header).startswith("Siniat "):
            fill = siniat_fill
        elif str(header).startswith("Knauf "):
            fill = knauf_fill
        elif str(header).startswith("Saint-Gobain "):
            fill = sg_fill
        elif str(header) in ["Best Price", "Knauf vs Siniat", "Saint-Gobain vs Siniat", "Saint-Gobain vs Knauf"]:
            fill = result_fill
        else:
            fill = None

        if fill:
            for row_idx in range(2, ws.max_row + 1):
                ws.cell(row=row_idx, column=col_idx).fill = fill

    for col_idx, column_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in column_cells:
            val = "" if cell.value is None else str(cell.value)
            if len(val) > max_len:
                max_len = len(val)

        adjusted_width = min(max(max_len + 2, 12), 30)
        ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

    numeric_headers = [
        "Siniat Base Price", "Siniat Final Price",
        "Knauf Base Price", "Knauf Final Price",
        "Saint-Gobain Base Price", "Saint-Gobain Final Price"
    ]
    disc_headers = [
        "Siniat Disc1", "Siniat Disc2", "Siniat Disc3", "Siniat Disc4", "Siniat Disc5",
        "Knauf Disc1", "Knauf Disc2", "Knauf Disc3", "Knauf Disc4", "Knauf Disc5",
        "Saint-Gobain Disc1", "Saint-Gobain Disc2", "Saint-Gobain Disc3", "Saint-Gobain Disc4", "Saint-Gobain Disc5"
    ]

    for col_idx, header in enumerate(headers, start=1):
        if header in numeric_headers:
            for row_idx in range(2, ws.max_row + 1):
                ws.cell(row=row_idx, column=col_idx).number_format = '0.00'
        if header in disc_headers:
            for row_idx in range(2, ws.max_row + 1):
                ws.cell(row=row_idx, column=col_idx).number_format = '0.0'


def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Comparison Report")
        ws = writer.book["Comparison Report"]
        style_excel_worksheet(ws)
    output.seek(0)
    return output.getvalue()


# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "row_ids" not in st.session_state:
    st.session_state.row_ids = [1]

if "next_row_id" not in st.session_state:
    st.session_state.next_row_id = 2


# -------------------------------------------------
# 1. COMPANY MANAGER
# -------------------------------------------------
st.markdown("## 1. Company Manager")

add_c1, add_c2, add_c3 = st.columns(3)

with add_c1:
    new_code = st.text_input("Code", key="new_company_code", placeholder="TECHNOGIPS")

with add_c2:
    new_name = st.text_input("Name", key="new_company_name", placeholder="Technogips")

with add_c3:
    st.write("")
    st.write("")
    if st.button("Add Company", key="add_company_button"):
        code = normalize_code(new_code)
        name = str(new_name).strip()

        if not code:
            st.error("Please enter a company code.")
        elif not name:
            st.error("Please enter a company name.")
        elif code in companies_df["code"].astype(str).str.upper().tolist():
            st.warning(f"Company {code} already exists.")
        else:
            updated_df = pd.concat(
                [
                    companies_df,
                    pd.DataFrame([{"code": code, "name": name}])
                ],
                ignore_index=True
            )

            save_companies(updated_df)
            get_company_folder(code)
            st.success(f"Company {name} was added successfully.")
            st.rerun()

st.dataframe(companies_df, use_container_width=True, hide_index=True)

st.markdown("### Delete Company")

company_delete_options = {
    f"{row['name']} ({row['code']})": row["code"]
    for _, row in companies_df.iterrows()
}

del_c1, del_c2 = st.columns([2, 1])

with del_c1:
    delete_company_display = st.selectbox(
        "Select Company to Delete",
        [""] + list(company_delete_options.keys()),
        key="delete_company_display"
    )

with del_c2:
    st.write("")
    st.write("")
    if st.button("Delete Company", key="delete_company_button"):
        if not delete_company_display:
            st.error("Please select a company.")
        else:
            delete_code = company_delete_options[delete_company_display]

            if delete_code in MAIN_CODES:
                st.warning("Core companies cannot be deleted at this stage.")
            elif company_has_files(delete_code):
                st.error("This company has source files. Delete the source files first.")
            else:
                updated_df = companies_df[companies_df["code"] != delete_code].copy()
                save_companies(updated_df)

                folder = get_company_folder(delete_code)
                try:
                    folder.rmdir()
                except Exception:
                    pass

                st.success(f"Company {delete_code} was deleted.")
                st.rerun()


# -------------------------------------------------
# 2. SAVE SOURCE
# -------------------------------------------------
st.markdown("---")
st.markdown("## 2. Save Source")

company_display_map = {
    f"{row['name']} ({row['code']})": row["code"]
    for _, row in companies_df.iterrows()
}

s1, s2, s3 = st.columns(3)

with s1:
    selected_company_display = st.selectbox("Company", list(company_display_map.keys()), key="save_company")
    company = company_display_map[selected_company_display]

with s2:
    date_val = st.date_input("Date", value=date.today(), key="save_date")

with s3:
    file = st.file_uploader("Upload Source", type=["xlsx", "xlsm"], key="save_file")

if st.button("Save", key="save_source_button"):
    if file is None:
        st.error("Please upload a source file first.")
    else:
        name = get_next_version_filename(company, date_val, file.name)
        path = get_company_folder(company) / name

        with open(path, "wb") as f:
            f.write(file.getbuffer())

        st.success(f"Saved as: {name}")
        st.rerun()


# -------------------------------------------------
# 3. SOURCE LIBRARY
# -------------------------------------------------
st.markdown("---")
st.markdown("## 3. Source Library")

saved_df = list_saved_sources()
if not saved_df.empty:
    st.dataframe(saved_df.drop(columns=["Full Path"]), use_container_width=True, hide_index=True)
else:
    st.info("No saved source files yet.")

st.markdown("### Delete Source")

source_delete_options = {}
if not saved_df.empty:
    for _, row in saved_df.iterrows():
        label = f"{row['Company Name']} | {row['Filename']}"
        source_delete_options[label] = row["Full Path"]

src_d1, src_d2 = st.columns([3, 1])

with src_d1:
    delete_source_display = st.selectbox(
        "Select Source to Delete",
        [""] + list(source_delete_options.keys()),
        key="delete_source_display"
    )

with src_d2:
    st.write("")
    st.write("")
    if st.button("Delete Source", key="delete_source_button"):
        if not delete_source_display:
            st.error("Please select a source.")
        else:
            full_path = Path(source_delete_options[delete_source_display])

            if full_path.exists():
                full_path.unlink()
                st.success(f"Source deleted: {full_path.name}")
                st.rerun()
            else:
                st.error("File not found.")


# -------------------------------------------------
# 4. SELECT SAVED SOURCES
# -------------------------------------------------
st.markdown("---")
st.markdown("## 4. Select Saved Sources for Comparison")

codes = MAIN_CODES
cols = st.columns(3)
selected = {}

for i, code in enumerate(codes):
    with cols[i]:
        if code in companies_df["code"].astype(str).str.upper().tolist():
            files = get_company_files(code)
            selected[code] = st.selectbox(code, [""] + files, key=f"select_{code}")
        else:
            selected[code] = ""
            st.info(f"{code} is not available in the company list.")

catalogs = {}

for code in codes:
    if selected[code]:
        df = load_data(get_company_folder(code) / selected[code])
        catalogs[code] = prepare_catalog(df)
    else:
        catalogs[code] = None


# -------------------------------------------------
# 5. DEBUG
# -------------------------------------------------
st.markdown("---")
st.markdown("## 5. Debug")

d1, d2, d3 = st.columns(3)

with d1:
    st.write("Selected Siniat file:", selected.get("SINIAT", ""))
    if catalogs["SINIAT"] is not None:
        st.write("Siniat prepared rows:", len(catalogs["SINIAT"]))

with d2:
    st.write("Selected Knauf file:", selected.get("KNAUF", ""))
    if catalogs["KNAUF"] is not None:
        st.write("Knauf prepared rows:", len(catalogs["KNAUF"]))

with d3:
    st.write("Selected Saint-Gobain file:", selected.get("SAINT_GOBAIN", ""))
    if catalogs["SAINT_GOBAIN"] is not None:
        st.write("Saint-Gobain prepared rows:", len(catalogs["SAINT_GOBAIN"]))


# -------------------------------------------------
# 6. MULTI-LINE COMPARISON
# -------------------------------------------------
st.markdown("---")
st.markdown("## 6. Multi-Line Comparison")

b1, b2 = st.columns([1, 3])

with b1:
    if st.button("Add Row", key="add_row_button"):
        st.session_state.row_ids.append(st.session_state.next_row_id)
        st.session_state.next_row_id += 1
        st.rerun()

with b2:
    st.info(f"Current rows: {len(st.session_state.row_ids)}")

for visible_index, row_id in enumerate(st.session_state.row_ids):
    top1, top2 = st.columns([4, 1])

    with top1:
        st.markdown(f"### Row {visible_index + 1}")

    with top2:
        st.write("")
        if st.button("Delete This Row", key=f"delete_row_{row_id}"):
            st.session_state.row_ids = [r for r in st.session_state.row_ids if r != row_id]
            st.rerun()

    row_cols = st.columns(3)
    row_final_prices = {}

    company_meta = {
        "SINIAT": {"label": "SINIAT", "catalog": catalogs.get("SINIAT")},
        "KNAUF": {"label": "KNAUF", "catalog": catalogs.get("KNAUF")},
        "SAINT_GOBAIN": {"label": "SAINT-GOBAIN", "catalog": catalogs.get("SAINT_GOBAIN")},
    }

    for col_idx, code in enumerate(codes):
        with row_cols[col_idx]:
            st.write(f"#### {company_meta[code]['label']}")
            df = company_meta[code]["catalog"]

            if df is not None and not df.empty:
                options = [""] + df["DISPLAY"].tolist()
                selected_product = st.selectbox(
                    f"{company_meta[code]['label']} product",
                    options,
                    key=f"row_{row_id}_{code}_product"
                )

                row = get_catalog_row(df, selected_product)

                if row is not None:
                    st.write("SAP:", row["SAP"])
                    st.write("MM:", row["MM"])
                    st.write("Package:", row["Package"])
                    st.write("Base Price:", round(float(row["Price"]), 2))

                    discs = []
                    for j in range(1, 6):
                        disc_val = st.number_input(
                            f"{company_meta[code]['label']} Disc {j}",
                            min_value=0.0,
                            max_value=100.0,
                            value=0.0,
                            step=0.1,
                            key=f"row_{row_id}_{code}_disc_{j}"
                        )
                        discs.append(disc_val)

                    final = apply_discounts(row["Price"], discs)
                    row_final_prices[code] = final
                    st.success(f"Final Price: {final}")
                else:
                    for j in range(1, 6):
                        st.number_input(
                            f"{company_meta[code]['label']} Disc {j}",
                            min_value=0.0,
                            max_value=100.0,
                            value=0.0,
                            step=0.1,
                            key=f"row_{row_id}_{code}_disc_{j}"
                        )
                    row_final_prices[code] = None
                    st.info("No product selected")
            else:
                row_final_prices[code] = None
                st.info("No data")

    best = best_price(row_final_prices)

    note_cols = st.columns(4)
    with note_cols[0]:
        st.metric(f"Row {visible_index + 1} Best Price", best if best else "-")
    with note_cols[1]:
        st.info(compare_note("Knauf", row_final_prices.get("KNAUF"), "Siniat", row_final_prices.get("SINIAT")) or "-")
    with note_cols[2]:
        st.info(compare_note("Saint-Gobain", row_final_prices.get("SAINT_GOBAIN"), "Siniat", row_final_prices.get("SINIAT")) or "-")
    with note_cols[3]:
        st.info(compare_note("Saint-Gobain", row_final_prices.get("SAINT_GOBAIN"), "Knauf", row_final_prices.get("KNAUF")) or "-")

    st.markdown("---")


# -------------------------------------------------
# 7. EXPORT
# -------------------------------------------------
st.markdown("## 7. Export Excel Report")

export_df = build_export_dataframe(st.session_state.row_ids, catalogs)

if not export_df.empty:
    st.dataframe(export_df, use_container_width=True, hide_index=True)

    excel_bytes = to_excel_bytes(export_df)

    st.download_button(
        "Download Excel Report",
        data=excel_bytes,
        file_name="comparison_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_report"
    )
else:
    st.info("No data available for export yet.")

# -------------------------------------------------
# 8. ADMIN PANEL
# -------------------------------------------------
if is_admin_user():
    st.markdown("---")
    st.markdown("## 8. Admin Panel")
    st.write("DEBUG REGISTRY FILE:", str(USERS_REGISTRY_FILE))
    st.write("DEBUG USERS:", load_users_registry())

    users_registry = load_users_registry()

    if users_registry:
        users_for_view = []
        for row in users_registry:
            users_for_view.append({
                "Email": row.get("email", ""),
                "Name": row.get("name", ""),
                "Status": row.get("status", "pending"),
                "First Seen": row.get("first_seen", ""),
                "Last Login": row.get("last_login", ""),
                "Last Seen": row.get("last_seen", ""),
                "Online": online_status_from_last_seen(row.get("last_seen", "")),
                "Sub": row.get("sub", ""),
            })

        users_df = pd.DataFrame(users_for_view)
        st.dataframe(users_df, use_container_width=True, hide_index=True)

        user_options = {}
        for row in users_registry:
            label = f"{row.get('email', '')} | {row.get('status', '')} | {online_status_from_last_seen(row.get('last_seen', ''))}"
            user_options[label] = row

        selected_user_label = st.selectbox(
            "Select user",
            [""] + list(user_options.keys()),
            key="admin_selected_user_to_manage"
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("Approve User", key="approve_user_button"):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "approved")
                    st.success(f"Approved: {row.get('email', '')}")
                    st.rerun()

        with c2:
            if st.button("Block User", key="block_user_button"):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "blocked")
                    st.success(f"Blocked: {row.get('email', '')}")
                    st.rerun()

        with c3:
            if st.button("Set Pending", key="pending_user_button"):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "pending")
                    st.success(f"Set to pending: {row.get('email', '')}")
                    st.rerun()
    else:
        st.info("No users found yet.")

# -------------------------------------------------
