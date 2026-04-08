import os
import io
import json
import re
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st
import stripe
from supabase import create_client, Client
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Pricing App",
    page_icon="💎",
    layout="wide",
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


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
    auth_redirect_uri = os.getenv("AUTH_REDIRECT_URI", "")
    auth_cookie_secret = os.getenv("AUTH_COOKIE_SECRET", "")
    google_client_id = os.getenv("AUTH_CLIENT_ID", "")
    google_client_secret = os.getenv("AUTH_CLIENT_SECRET", "")
    google_server_metadata_url = os.getenv("AUTH_SERVER_METADATA_URL", "")
    ms_client_id = os.getenv("MS_CLIENT_ID", "")
    ms_client_secret = os.getenv("MS_CLIENT_SECRET", "")
    ms_server_metadata_url = os.getenv("MS_SERVER_METADATA_URL", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")

    if not all(
        [
            auth_redirect_uri,
            auth_cookie_secret,
            google_client_id,
            google_client_secret,
            google_server_metadata_url,
        ]
    ):
        return

    content = f'''SUPABASE_URL = "{_escape_toml(supabase_url)}"
SUPABASE_KEY = "{_escape_toml(supabase_key)}"

[auth]
redirect_uri = "{_escape_toml(auth_redirect_uri)}"
cookie_secret = "{_escape_toml(auth_cookie_secret)}"

[auth.google]
client_id = "{_escape_toml(google_client_id)}"
client_secret = "{_escape_toml(google_client_secret)}"
server_metadata_url = "{_escape_toml(google_server_metadata_url)}"
'''

    if ms_client_id and ms_client_secret and ms_server_metadata_url:
        content += f'''
[auth.microsoft]
client_id = "{_escape_toml(ms_client_id)}"
client_secret = "{_escape_toml(ms_client_secret)}"
server_metadata_url = "{_escape_toml(ms_server_metadata_url)}"
'''

    SECRETS_FILE.write_text(content, encoding="utf-8")


ensure_render_secrets_file()


# -------------------------------------------------
# UI STYLE
# -------------------------------------------------
st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1420px;
    }

    .app-hero {
        padding: 28px 32px;
        border-radius: 22px;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 45%, #1e3a8a 100%);
        color: white;
        border: 1px solid rgba(255,255,255,0.14);
        margin-bottom: 1.2rem;
        box-shadow: 0 14px 34px rgba(0,0,0,0.20);
    }

    .app-card {
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 18px;
        padding: 22px 24px;
        color: white;
        box-shadow: 0 8px 22px rgba(0,0,0,0.14);
        margin-bottom: 14px;
    }

    .locked-wrap {
        max-width: 760px;
        margin: 30px auto 0 auto;
        padding: 32px;
        border-radius: 22px;
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        border: 1px solid rgba(255,255,255,0.10);
        box-shadow: 0 20px 50px rgba(0,0,0,0.24);
        text-align: center;
        color: white;
    }

    .locked-title {
        font-size: 32px;
        font-weight: 800;
        margin-bottom: 10px;
        letter-spacing: -0.03em;
    }

    .locked-subtitle {
        font-size: 16px;
        color: #cbd5e1;
        line-height: 1.65;
        margin-bottom: 22px;
    }

    .locked-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(96,165,250,0.16);
        border: 1px solid rgba(96,165,250,0.28);
        color: #dbeafe;
        font-size: 13px;
        margin-bottom: 18px;
    }

    .login-shell {
        max-width: 560px;
        margin: 60px auto 20px auto;
        padding: 42px 40px 34px 40px;
        border-radius: 24px;
        background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
        border: 1px solid rgba(255,255,255,0.10);
        box-shadow: 0 20px 60px rgba(0,0,0,0.35);
        text-align: center;
        color: white;
    }

    .login-shell h1 {
        margin: 0 0 10px 0;
        font-size: 44px;
        font-weight: 900;
        letter-spacing: -0.03em;
        color: white;
    }

    .login-shell p {
        margin: 0;
        font-size: 18px;
        color: #94a3b8;
    }

    .login-note {
        text-align: center;
        margin-top: 16px;
        font-size: 13px;
        color: #94a3b8;
    }

    .provider-chip {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.10);
        color: #cbd5e1;
        font-size: 13px;
        margin-bottom: 18px;
    }

    div[data-testid="stSidebar"] {
        border-right: 1px solid rgba(255,255,255,0.08);
        background: #020617;
    }

    div[data-baseweb="input"] input {
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,0.35) !important;
        background-color: #0f172a !important;
        color: white !important;
    }

    div[data-baseweb="select"] > div {
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,0.35) !important;
        background-color: #0f172a !important;
        color: white !important;
    }

    textarea {
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,0.35) !important;
        background-color: #0f172a !important;
        color: white !important;
    }

    div[data-testid="stNumberInput"] input {
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,0.35) !important;
        background-color: #0f172a !important;
        color: white !important;
    }

    div[data-testid="stDateInput"] input {
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,0.35) !important;
        background-color: #0f172a !important;
        color: white !important;
    }

    div[data-testid="stFileUploader"] section {
        border-radius: 14px !important;
        border: 1px dashed rgba(96,165,250,0.45) !important;
        background: rgba(37,99,235,0.06) !important;
    }

    div[data-testid="stButton"] > button {
        border-radius: 12px;
        font-size: 15px;
        font-weight: 700;
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        color: white;
        border: 1px solid rgba(255,255,255,0.08);
        transition: all 0.2s ease;
        box-shadow: 0 6px 16px rgba(37,99,235,0.22);
    }

    div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 20px rgba(37,99,235,0.30);
    }

    div[data-testid="stDownloadButton"] > button {
        border-radius: 12px;
        font-size: 15px;
        font-weight: 700;
        background: linear-gradient(135deg, #059669, #047857);
        color: white;
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 6px 16px rgba(5,150,105,0.20);
    }

    div[data-testid="stDownloadButton"] > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 20px rgba(5,150,105,0.28);
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.02) 100%);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 12px 14px;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.10);
    }

    .stDataFrame {
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 6px 18px rgba(0,0,0,0.10);
    }

    .stAlert {
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
    }

    h2, h3 {
        letter-spacing: -0.02em;
    }

    hr {
        border-color: rgba(255,255,255,0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------------------------------
# AUTH / USER HELPERS
# -------------------------------------------------
def is_logged_in():
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def get_current_user_id():
    try:
        return st.user.get("sub") or st.user.get("email") or "anonymous"
    except Exception:
        return "anonymous"


def get_current_user_email():
    try:
        return st.user.get("email", "").strip().lower()
    except Exception:
        return ""


def get_current_user_name():
    try:
        return st.user.get("name", "").strip()
    except Exception:
        return ""


def show_login_screen():
    top_left, top_mid, top_right = st.columns([1.1, 2.2, 1.1])

    with top_mid:
        st.markdown(
            """
            <div class="login-shell">
                <h1>Pricing App</h1>
                <p>Sign in to continue to your workspace</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    btn_left, btn_mid, btn_right = st.columns([1.25, 2.0, 1.25])

    with btn_mid:
        st.markdown(
            '<div class="provider-chip">Secure sign-in with Google or Microsoft</div>',
            unsafe_allow_html=True,
        )

        if st.button(
            "Continue with Google",
            use_container_width=True,
            key="login_google_button",
        ):
            st.login("google")

        st.write("")

        if st.button(
            "Continue with Microsoft",
            use_container_width=True,
            key="login_microsoft_button",
        ):
            st.login("microsoft")

        st.markdown(
            '<div class="login-note">Secure login • No passwords stored</div>',
            unsafe_allow_html=True,
        )


# -------------------------------------------------
# SUPABASE
# -------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


# -------------------------------------------------
# FILE STORAGE
# -------------------------------------------------
PERSIST_ROOT = Path(os.getenv("PERSIST_ROOT", "/var/data"))
PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

ROOT_STORAGE = PERSIST_ROOT
ADMIN_DIR = ROOT_STORAGE / "_admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)

USERS_REGISTRY_FILE = ADMIN_DIR / "users_registry.json"
COMPANIES_REGISTRY_FILE = ADMIN_DIR / "companies_registry.json"

MAIN_CODES = ["SINIAT", "KNAUF", "SAINT_GOBAIN"]
ADMIN_EMAILS = ["gmyl13@gmail.com"]

TEMPLATE_FILE = BASE_DIR / "templates" / "source_template_english.xlsx"


# -------------------------------------------------
# JSON HELPERS
# -------------------------------------------------
def now_iso():
    return datetime.utcnow().isoformat()


def now_utc():
    return datetime.utcnow()


def parse_iso(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def load_users_registry():
    if not USERS_REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(USERS_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_users_registry(data):
    USERS_REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_companies_registry():
    if not COMPANIES_REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(COMPANIES_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_companies_registry(data):
    COMPANIES_REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# -------------------------------------------------
# BILLING / PLANS
# -------------------------------------------------
TRIAL_DAYS = 2
MAX_ACTIVE_SESSIONS = 2


def get_stripe_subscription_row(email: str):
    if not email:
        return None

    try:
        customers = stripe.Customer.list(email=email.strip().lower(), limit=1)
        if not customers.data:
            return None

        customer = customers.data[0]
        subs = stripe.Subscription.list(customer=customer.id, status="all", limit=20)

        if not subs.data:
            return {
                "email": email.strip().lower(),
                "is_active": False,
                "billing_status": "free",
                "stripe_customer_id": customer.id,
                "stripe_subscription_id": None,
            }

        preferred = None

        for sub in subs.data:
            if sub.status == "active":
                preferred = sub
                break

        if preferred is None:
            for sub in subs.data:
                if sub.status in [
                    "trialing",
                    "past_due",
                    "unpaid",
                    "canceled",
                    "incomplete",
                    "incomplete_expired",
                ]:
                    preferred = sub
                    break

        if preferred is None:
            preferred = subs.data[0]

        return {
            "email": email.strip().lower(),
            "is_active": preferred.status == "active",
            "billing_status": preferred.status,
            "stripe_customer_id": customer.id,
            "stripe_subscription_id": preferred.id,
        }

    except Exception as e:
        print("STRIPE BILLING CHECK ERROR:", repr(e))
        return None


from billing import create_checkout_session


def get_checkout_url(user_email: str):
    if not user_email:
        return None

    cache_email = st.session_state.get("checkout_email")
    cache_url = st.session_state.get("checkout_url")
    cache_ts = st.session_state.get("checkout_created_at")

    if cache_email == user_email and cache_url and cache_ts:
        try:
            created_at = datetime.fromisoformat(cache_ts)
            if datetime.utcnow() - created_at < timedelta(minutes=20):
                return cache_url
        except Exception:
            pass

    try:
        url = create_checkout_session(user_email)
        st.session_state["checkout_email"] = user_email
        st.session_state["checkout_url"] = url
        st.session_state["checkout_created_at"] = datetime.utcnow().isoformat()
        return url
    except Exception as e:
        st.error(f"Stripe error: {e}")
        return None


# -------------------------------------------------
# USER / COMPANY HELPERS
# -------------------------------------------------
def normalize_domain(domain: str) -> str:
    return str(domain).strip().lower().replace("@", "")


def normalize_company_key(text: str) -> str:
    text = str(text).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def get_email_domain(email: str) -> str:
    email = str(email).strip().lower()
    if "@" not in email:
        return ""
    return email.split("@", 1)[1]


def find_user_index(users, email, sub):
    for i, row in enumerate(users):
        if row.get("email") == email and row.get("sub") == sub:
            return i
    return None


def find_company_index(companies, company_key):
    for i, row in enumerate(companies):
        if row.get("key") == company_key:
            return i
    return None


def find_company_by_key(companies, company_key):
    for row in companies:
        if row.get("key") == company_key:
            return row
    return None


def find_company_by_domain(companies, domain):
    domain = normalize_domain(domain)
    for row in companies:
        if normalize_domain(row.get("domain", "")) == domain:
            return row
    return None


def ensure_user_fields(user_row):
    if "trial_start" not in user_row:
        user_row["trial_start"] = now_iso()
    if "trial_end" not in user_row:
        user_row["trial_end"] = (now_utc() + timedelta(days=TRIAL_DAYS)).isoformat()
    if "billing_status" not in user_row:
        user_row["billing_status"] = "trialing"
    if "is_premium" not in user_row:
        user_row["is_premium"] = False
    if "active_sessions" not in user_row:
        user_row["active_sessions"] = []
    if "company_key" not in user_row:
        user_row["company_key"] = None
    if "company_name" not in user_row:
        user_row["company_name"] = None
    if "role" not in user_row:
        user_row["role"] = "member"
    return user_row


def ensure_company_fields(company_row):
    if "billing_status" not in company_row:
        company_row["billing_status"] = "trialing"
    if "max_seats" not in company_row:
        company_row["max_seats"] = 0
    if "is_active" not in company_row:
        company_row["is_active"] = True
    if "trial_start" not in company_row:
        company_row["trial_start"] = now_iso()
    if "trial_end" not in company_row:
        company_row["trial_end"] = (now_utc() + timedelta(days=7)).isoformat()
    if "stripe_customer_id" not in company_row:
        company_row["stripe_customer_id"] = None
    if "stripe_subscription_id" not in company_row:
        company_row["stripe_subscription_id"] = None
    if "owner_email" not in company_row:
        company_row["owner_email"] = ""
    return company_row


def get_current_user_registry_row():
    user = {
        "email": get_current_user_email(),
        "sub": get_current_user_id() if get_current_user_id() != "anonymous" else "",
    }
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return None, None, users

    users[idx] = ensure_user_fields(users[idx])
    save_users_registry(users)
    return idx, users[idx], users


def get_current_user_company():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return None
    company_key = row.get("company_key")
    if not company_key:
        return None
    companies = load_companies_registry()
    company = find_company_by_key(companies, company_key)
    if company:
        company = ensure_company_fields(company)
    return company


def trial_days_left(trial_end_value):
    dt = parse_iso(trial_end_value)
    if dt is None:
        return 0
    remaining = dt - now_utc()
    if remaining.total_seconds() <= 0:
        return 0
    return max(1, remaining.days + (1 if remaining.seconds > 0 else 0))


def company_user_count(company_key):
    users = load_users_registry()
    count = 0
    for row in users:
        if row.get("company_key") == company_key and row.get("status") != "blocked":
            count += 1
    return count


def company_has_available_seat(company):
    if not company:
        return True
    max_seats = int(company.get("max_seats", 0) or 0)
    if max_seats <= 0:
        return True
    used = company_user_count(company["key"])
    return used < max_seats


def format_company_seats(company):
    if not company:
        return "-"
    used = company_user_count(company["key"])
    max_seats = int(company.get("max_seats", 0) or 0)
    return f"{used}/{max_seats}"


def is_admin_user():
    return get_current_user_email() in ADMIN_EMAILS


def current_user_status():
    if is_admin_user():
        return "approved"
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return "pending"
    return row.get("status", "pending")


def current_user_is_blocked():
    return current_user_status() == "blocked"


def current_user_is_approved():
    return current_user_status() == "approved"


def online_status_from_last_seen(last_seen_value):
    dt = parse_iso(last_seen_value)
    if dt is None:
        return "Offline"
    if datetime.utcnow() - dt <= timedelta(minutes=2):
        return "Online"
    return "Offline"


def set_user_status(email, sub, new_status):
    users = load_users_registry()
    idx = find_user_index(users, email, sub)
    if idx is not None:
        users[idx]["status"] = new_status
        save_users_registry(users)


def set_user_premium(email, sub, is_premium=True):
    users = load_users_registry()
    idx = find_user_index(users, email, sub)
    if idx is not None:
        users[idx]["is_premium"] = bool(is_premium)
        users[idx]["billing_status"] = "active" if is_premium else "expired"
        if is_premium:
            users[idx]["status"] = "approved"
        save_users_registry(users)


def reset_user_sessions(email, sub):
    users = load_users_registry()
    idx = find_user_index(users, email, sub)
    if idx is not None:
        users[idx]["active_sessions"] = []
        save_users_registry(users)


def remove_user_from_company(email, sub):
    users = load_users_registry()
    idx = find_user_index(users, email, sub)
    if idx is not None:
        users[idx]["company_key"] = None
        users[idx]["company_name"] = None
        users[idx]["role"] = "member"
        save_users_registry(users)


def get_current_session_id():
    if "app_session_id" not in st.session_state:
        st.session_state["app_session_id"] = str(uuid.uuid4())
    return st.session_state["app_session_id"]


def register_current_session():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return True, 0

    current_session_id = get_current_session_id()
    sessions = row.get("active_sessions", [])

    for s in sessions:
        if s.get("session_id") == current_session_id:
            s["last_seen"] = now_iso()
            users[idx]["active_sessions"] = sessions
            save_users_registry(users)
            return True, len(sessions)

    if len(sessions) >= MAX_ACTIVE_SESSIONS:
        return False, len(sessions)

    sessions.append({"session_id": current_session_id, "last_seen": now_iso()})
    users[idx]["active_sessions"] = sessions
    save_users_registry(users)
    return True, len(sessions)


def unregister_current_session():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return
    current_session_id = get_current_session_id()
    sessions = row.get("active_sessions", [])
    sessions = [s for s in sessions if s.get("session_id") != current_session_id]
    users[idx]["active_sessions"] = sessions
    save_users_registry(users)


def touch_current_user():
    idx, row, users = get_current_user_registry_row()
    if row is not None:
        users[idx]["last_seen"] = now_iso()
        save_users_registry(users)


def touch_current_session():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return
    current_session_id = get_current_session_id()
    sessions = row.get("active_sessions", [])
    changed = False
    for s in sessions:
        if s.get("session_id") == current_session_id:
            s["last_seen"] = now_iso()
            changed = True
            break
    if changed:
        users[idx]["active_sessions"] = sessions
        save_users_registry(users)


def logout_current_user():
    unregister_current_session()
    st.logout()


def ensure_current_user_in_registry():
    email = get_current_user_email()
    sub = get_current_user_id()
    name = get_current_user_name()

    users = load_users_registry()
    idx = find_user_index(users, email, sub)

    if idx is None:
        users.append(
            {
                "email": email,
                "sub": sub,
                "name": name,
                "status": "approved" if email in ADMIN_EMAILS else "pending",
                "first_seen": now_iso(),
                "last_login": now_iso(),
                "last_seen": now_iso(),
                "trial_start": now_iso(),
                "trial_end": (now_utc() + timedelta(days=TRIAL_DAYS)).isoformat(),
                "billing_status": "trialing",
                "is_premium": False,
                "active_sessions": [],
                "company_key": None,
                "company_name": None,
                "role": "member",
            }
        )
    else:
        users[idx]["name"] = name
        users[idx]["last_login"] = now_iso()
        users[idx]["last_seen"] = now_iso()
        if email in ADMIN_EMAILS:
            users[idx]["status"] = "approved"
        users[idx] = ensure_user_fields(users[idx])

    save_users_registry(users)


def sync_company_assignment_from_domain():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return {"status": "none", "company": None}

    email = row.get("email", "")
    domain = get_email_domain(email)
    if not domain:
        return {"status": "none", "company": None}

    companies = load_companies_registry()
    company = find_company_by_domain(companies, domain)
    if not company:
        return {"status": "none", "company": None}

    company = ensure_company_fields(company)
    if not company.get("is_active", True):
        return {"status": "inactive", "company": company}

    existing_company_key = row.get("company_key")
    if existing_company_key == company.get("key"):
        return {"status": "assigned", "company": company}

    if not company_has_available_seat(company):
        return {"status": "full", "company": company}

    users[idx]["company_key"] = company.get("key")
    users[idx]["company_name"] = company.get("name", company.get("key"))
    users[idx]["status"] = "approved"

    if company.get("owner_email") == email:
        users[idx]["role"] = "company_admin"

    save_users_registry(users)
    return {"status": "assigned", "company": company}


def sync_individual_status_from_stripe(email: str):
    idx, row, users = get_current_user_registry_row()
    if row is None or not email:
        return False

    stripe_row = get_stripe_subscription_row(email)
    if not stripe_row:
        return False

    if stripe_row.get("billing_status") == "active":
        users[idx]["billing_status"] = "active"
        users[idx]["is_premium"] = True
        save_users_registry(users)
        return True

    if row.get("billing_status") == "active":
        users[idx]["billing_status"] = "expired"
        users[idx]["is_premium"] = False
        save_users_registry(users)

    return False


def company_has_access(company):
    if not company:
        return False

    if not company.get("is_active", True):
        return False

    if company.get("billing_status") == "active":
        return True

    trial_end = parse_iso(company.get("trial_end", ""))
    if trial_end and now_utc() <= trial_end:
        return True

    return False


def current_user_has_access():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return False

    company = get_current_user_company()
    if company and company_has_access(company):
        return True

    if row.get("billing_status") == "active" or row.get("is_premium") is True:
        return True

    trial_end = parse_iso(row.get("trial_end", ""))
    if trial_end and now_utc() <= trial_end:
        return True

    user_email = get_current_user_email()
    if user_email and sync_individual_status_from_stripe(user_email):
        return True

    if idx is not None:
        users[idx]["billing_status"] = "expired"
        users[idx]["is_premium"] = False
        save_users_registry(users)

    return False


def upsert_company(
    company_key,
    name,
    domain,
    max_seats=0,
    is_active=True,
    billing_status="trialing",
    owner_email="",
):
    companies = load_companies_registry()
    normalized_key = normalize_company_key(company_key)
    idx = find_company_index(companies, normalized_key)

    payload = {
        "key": normalized_key,
        "name": str(name).strip(),
        "domain": normalize_domain(domain),
        "max_seats": int(max_seats),
        "is_active": bool(is_active),
        "billing_status": billing_status,
        "trial_start": now_iso(),
        "trial_end": (now_utc() + timedelta(days=7)).isoformat(),
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "owner_email": owner_email.strip().lower(),
        "updated_at": now_iso(),
    }

    if idx is None:
        payload["created_at"] = now_iso()
        companies.append(payload)
    else:
        existing = companies[idx]
        payload["created_at"] = existing.get("created_at", now_iso())
        payload["stripe_customer_id"] = existing.get("stripe_customer_id")
        payload["stripe_subscription_id"] = existing.get("stripe_subscription_id")
        payload["trial_start"] = existing.get("trial_start", payload["trial_start"])
        payload["trial_end"] = existing.get("trial_end", payload["trial_end"])
        if not owner_email:
            payload["owner_email"] = existing.get("owner_email", "")
        companies[idx] = payload

    save_companies_registry(companies)


def remove_company(company_key):
    companies = load_companies_registry()
    companies = [c for c in companies if c.get("key") != company_key]
    save_companies_registry(companies)


# -------------------------------------------------
# COMPANY / USER FILES
# -------------------------------------------------
def get_storage_slug_for_current_user():
    company = get_current_user_company()
    if company:
        slug = normalize_company_key(company.get("key", "workspace"))
    else:
        slug = (
            get_current_user_id()
            .replace("@", "_")
            .replace(".", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )
    return slug


WORKSPACE_SLUG = get_storage_slug_for_current_user()
WORKSPACE_DIR = PERSIST_ROOT / WORKSPACE_SLUG
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
COMPANIES_FILE = WORKSPACE_DIR / "companies.csv"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------
# SAFE COMPANIES LOADING
# -------------------------------------------------
def load_companies_safe():
    default = pd.DataFrame(
        [
            {"code": "SINIAT", "name": "Siniat"},
            {"code": "KNAUF", "name": "Knauf"},
            {"code": "SAINT_GOBAIN", "name": "Saint-Gobain"},
        ]
    )

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
# FILE / CATALOG HELPERS
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
                rows.append(
                    {
                        "Company Code": code,
                        "Company Name": name,
                        "Filename": f.name,
                        "Folder": str(folder),
                        "Full Path": str(f),
                        "Modified": pd.to_datetime(f.stat().st_mtime, unit="s"),
                    }
                )

    if rows:
        return (
            pd.DataFrame(rows)
            .sort_values("Modified", ascending=False)
            .reset_index(drop=True)
        )

    return pd.DataFrame(
        columns=[
            "Company Code",
            "Company Name",
            "Filename",
            "Folder",
            "Full Path",
            "Modified",
        ]
    )


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
            p *= 1 - d / 100
    return round(p, 2)


def format_total_discounts(discs):
    valid_discounts = []

    for d in discs:
        try:
            d = float(d)
        except Exception:
            continue

        if d > 0:
            if d.is_integer():
                valid_discounts.append(f"{int(d)}%")
            else:
                valid_discounts.append(f"{d:.1f}%")

    return ", ".join(valid_discounts)


def get_company_label(code):
    company_name_row = companies_df[companies_df["code"] == code]
    if company_name_row.empty:
        return code
    return company_name_row.iloc[0]["name"]


def compare_percent_text(a_name, a_price, b_name, b_price):
    if a_price is None or b_price is None:
        return ""

    try:
        a = float(a_price)
        b = float(b_price)
    except Exception:
        return ""

    if b == 0:
        return ""

    if round(a, 2) == round(b, 2):
        return f"Same price as {b_name}"

    if a < b:
        pct = ((b - a) / b) * 100
        return f"{pct:.1f}% cheaper than {b_name}"

    pct = ((a - b) / b) * 100
    return f"{pct:.1f}% more expensive than {b_name}"


def build_comparison_summary(final_prices, selected_codes):
    summaries = {}

    for code in selected_codes:
        label = get_company_label(code)
        a_price = final_prices.get(code)
        notes = []

        for other_code in selected_codes:
            if other_code == code:
                continue

            other_label = get_company_label(other_code)
            other_price = final_prices.get(other_code)

            note = compare_percent_text(label, a_price, other_label, other_price)
            if note:
                notes.append(note)

        summaries[code] = " | ".join(notes)

    return summaries


def get_catalog_row(df, display_value):
    if df is None or df.empty or not display_value:
        return None

    rows = df[df["DISPLAY"] == display_value]
    if rows.empty:
        return None

    return rows.iloc[0]


def row_result_dict(visible_index, row_id, catalogs, selected_codes):
    result = {"Row": visible_index + 1}
    final_prices = {}

    for code in selected_codes:
        label = get_company_label(code)

        df = catalogs.get(code)
        selected_product = st.session_state.get(f"row_{row_id}_{code}_product", "")
        row = get_catalog_row(df, selected_product)

        discs = []
        for d in range(1, 6):
            discs.append(st.session_state.get(f"row_{row_id}_{code}_disc_{d}", 0.0))

        if row is not None:
            base_price = round(float(row["Price"]), 2)
            final_price = apply_discounts(row["Price"], discs)
            final_prices[code] = final_price
            total_discounts_text = format_total_discounts(discs)

            result[f"{label} Product"] = row["Product"]
            result[f"{label} SAP"] = row["SAP"]
            result[f"{label} MM"] = row["MM"]
            result[f"{label} Package"] = row["Package"]
            result[f"{label} Base Price"] = base_price
            result[f"{label} Total Discounts"] = total_discounts_text

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
            result[f"{label} Total Discounts"] = format_total_discounts(discs)

            for i in range(1, 6):
                result[f"{label} Disc{i}"] = st.session_state.get(
                    f"row_{row_id}_{code}_disc_{i}", 0.0
                )

            result[f"{label} Final Price"] = ""

    comparison_summaries = build_comparison_summary(final_prices, selected_codes)

    combined_comparisons = []
    for code in selected_codes:
        label = get_company_label(code)
        summary = comparison_summaries.get(code, "")
        if summary:
            combined_comparisons.append(f"{label}: {summary}")

    result["Comparisons"] = " || ".join(combined_comparisons)

    valid = {k: v for k, v in final_prices.items() if v is not None}
    if valid:
        best_code = min(valid, key=valid.get)
        result["Best Price"] = get_company_label(best_code)
    else:
        result["Best Price"] = ""

    return result


def build_export_dataframe(row_ids, catalogs, selected_codes):
    rows = []
    for visible_index, row_id in enumerate(row_ids):
        rows.append(row_result_dict(visible_index, row_id, catalogs, selected_codes))
    return pd.DataFrame(rows)


# -------------------------------------------------
# EXPORT FIELD SELECTION
# -------------------------------------------------
EXPORT_FIELD_OPTIONS = [
    "Product",
    "SAP",
    "MM",
    "Package",
    "Base Price",
    "Total Discounts",
    "Final Price",
    "Comparison %",
    "Best Price",
]


def filter_export_dataframe(export_df, selected_codes, selected_fields, companies_df):
    if export_df.empty:
        return export_df

    columns_to_keep = ["Row"]

    for code in selected_codes:
        company_name_row = companies_df[companies_df["code"] == code]
        label = code if company_name_row.empty else company_name_row.iloc[0]["name"]

        for field in selected_fields:
            if field in ["Best Price", "Comparison %"]:
                continue

            col_name = f"{label} {field}"
            if col_name in export_df.columns:
                columns_to_keep.append(col_name)

    if "Comparison %" in selected_fields and "Comparisons" in export_df.columns:
        columns_to_keep.append("Comparisons")

    if "Best Price" in selected_fields and "Best Price" in export_df.columns:
        columns_to_keep.append("Best Price")

    columns_to_keep = [c for c in columns_to_keep if c in export_df.columns]
    return export_df[columns_to_keep]


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
        elif str(header) in ["Best Price", "Comparisons"]:
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

        adjusted_width = min(max(max_len + 2, 12), 45)
        ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width


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
# APP FLOW
# -------------------------------------------------
if not is_logged_in():
    show_login_screen()
    st.stop()

ensure_current_user_in_registry()
touch_current_user()

company_result = sync_company_assignment_from_domain()

if company_result["status"] == "full":
    company = company_result["company"]
    st.markdown(
        """
        <div class="locked-wrap">
            <div class="locked-badge">Company seat limit reached</div>
            <div class="locked-title">No available company seats</div>
            <div class="locked-subtitle">
                Your company account has reached the maximum number of active users allowed for this plan.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1.6, 1])
    with c2:
        st.warning(
            f"{company.get('name', 'This company')} is using all seats ({format_company_seats(company)})."
        )
        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="company_full_logout",
        )
    st.stop()

if current_user_is_blocked():
    st.error("Access denied. Your account has been blocked.")
    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="blocked_logout",
    )
    st.stop()

if not current_user_is_approved():
    st.warning("Your account is pending admin approval.")
    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="pending_logout",
    )
    st.stop()

if not is_admin_user():
    session_allowed, active_count = register_current_session()
    if not session_allowed:
        st.markdown(
            """
            <div class="locked-wrap">
                <div class="locked-badge">Device limit reached</div>
                <div class="locked-title">Too many active devices</div>
                <div class="locked-subtitle">
                    Your account is already active on the maximum allowed number of devices/browsers.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="device_limit_logout",
        )
        st.stop()
    else:
        touch_current_session()

user_email = get_current_user_email()
current_company = get_current_user_company()
user_idx, user_row, _users = get_current_user_registry_row()

if (not is_admin_user()) and (not current_user_has_access()):
    checkout_url = get_checkout_url(user_email)

    st.markdown(
        """
        <div class="locked-wrap">
            <div class="locked-badge">Access required</div>
            <div class="locked-title">Your access is currently locked</div>
            <div class="locked-subtitle">
                Activate an individual plan to continue using all features.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    days_left = trial_days_left(user_row.get("trial_end")) if user_row else 0
    if days_left > 0:
        st.info(f"Your free trial is still active. Days left: {days_left}")
    else:
        st.warning("Your 2-day free trial has expired.")

    if checkout_url:
        st.link_button("Subscribe €10/month", checkout_url, use_container_width=True)

    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="locked_logout",
    )
    st.stop()


# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.markdown("### Account")
    st.success("Logged in")
    st.write(f"User: {get_current_user_email() or get_current_user_id()}")

    if is_admin_user():
        st.success("Admin: Full Access")
    else:
        company = get_current_user_company()

        if company:
            st.success(f"Workspace: {company.get('name')}")
            st.info(f"Seats: {format_company_seats(company)}")
        elif user_row and user_row.get("billing_status") == "active":
            st.success("Plan: Premium")
        else:
            trial_left = trial_days_left(user_row.get("trial_end")) if user_row else 0
            if trial_left > 0:
                st.info(f"Trial: {trial_left} day(s) left")
            else:
                st.warning("Plan: Locked")

    st.markdown("---")
    st.subheader("💳 Billing")

    if not is_admin_user():
        if current_company:
            if current_company.get("billing_status") == "active":
                st.success("Your company subscription is active.")
            else:
                st.info("Your access is managed through your company workspace.")
        elif user_row and user_row.get("billing_status") == "active":
            st.success("Your individual subscription is active.")
        else:
            checkout_url = get_checkout_url(user_email)
            if checkout_url:
                st.link_button(
                    "Individual €10/month",
                    checkout_url,
                    use_container_width=True,
                )

    st.markdown("---")

    if not is_admin_user():
        active_sessions_count = len(user_row.get("active_sessions", [])) if user_row else 0
        st.warning("⚠️ Please logout before closing the app to free your session.")
        st.caption(f"Active sessions: {active_sessions_count}/{MAX_ACTIVE_SESSIONS}")

    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="logout_button",
    )


# -------------------------------------------------
# MAIN UI
# -------------------------------------------------
st.markdown(
    """
    <div class="app-hero">
        <div style="font-size:38px;font-weight:900;letter-spacing:-0.03em;">Pricing App</div>
        <div style="font-size:16px;color:#dbeafe;margin-top:8px;">
            Upload supplier sources, compare products and export polished Excel reports.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.query_params.get("payment") == "success":
    st.success("Payment completed successfully. Refreshing access may take a few seconds.")
elif st.query_params.get("payment") == "cancel":
    st.info("Checkout was cancelled.")


# 1. COMPANY MANAGER
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 1. Company Manager")

add_c1, add_c2, add_c3 = st.columns(3)
with add_c1:
    new_code = st.text_input(
        "Code", key="new_company_code", placeholder="TECHNOGIPS"
    )
with add_c2:
    new_name = st.text_input(
        "Name", key="new_company_name", placeholder="Technogips"
    )
with add_c3:
    st.write("")
    st.write("")
    if st.button("Add Company", key="add_company_button", use_container_width=True):
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
                [companies_df, pd.DataFrame([{"code": code, "name": name}])],
                ignore_index=True,
            )
            save_companies(updated_df)
            get_company_folder(code)
            st.success(f"Company {name} was added successfully.")
            st.rerun()

st.dataframe(companies_df, use_container_width=True, hide_index=True)

st.markdown("### Delete Company")

company_delete_options = {
    f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
}

del_c1, del_c2 = st.columns([2, 1])
with del_c1:
    delete_company_display = st.selectbox(
        "Select Company to Delete",
        [""] + list(company_delete_options.keys()),
        key="delete_company_display",
    )
with del_c2:
    st.write("")
    st.write("")
    if st.button(
        "Delete Company", key="delete_company_button", use_container_width=True
    ):
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
st.markdown("</div>", unsafe_allow_html=True)


# 2. SAVE SOURCE
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 2. Save Source")

company_display_map = {
    f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
}

s1, s2, s3 = st.columns(3)
with s1:
    selected_company_display = st.selectbox(
        "Company",
        list(company_display_map.keys()),
        key="save_company",
    )
    company_code = company_display_map[selected_company_display]

with s2:
    date_val = st.date_input("Date", value=date.today(), key="save_date")

with s3:
    file = st.file_uploader("Upload Source", type=["xlsx", "xlsm"], key="save_file")

if st.button("Save", key="save_source_button", use_container_width=True):
    if file is None:
        st.error("Please upload a source file first.")
    else:
        name = get_next_version_filename(company_code, date_val, file.name)
        path = get_company_folder(company_code) / name
        with open(path, "wb") as f:
            f.write(file.getbuffer())
        st.success(f"Saved as: {name}")
        st.rerun()

st.info(
    "Download the source template, fill in your products, and upload it back to the platform."
)

if TEMPLATE_FILE.exists():
    with open(TEMPLATE_FILE, "rb") as f:
        st.download_button(
            "Download Source Template",
            data=f.read(),
            file_name="source_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_source_template",
            use_container_width=True,
        )
else:
    st.warning("Template file not found.")
st.markdown("</div>", unsafe_allow_html=True)


# 3. SOURCE LIBRARY
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 3. Source Library")

saved_df = list_saved_sources()
if not saved_df.empty:
    st.dataframe(
        saved_df.drop(columns=["Full Path"]),
        use_container_width=True,
        hide_index=True,
    )
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
        key="delete_source_display",
    )
with src_d2:
    st.write("")
    st.write("")
    if st.button(
        "Delete Source", key="delete_source_button", use_container_width=True
    ):
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
st.markdown("</div>", unsafe_allow_html=True)


# 4. SELECT SAVED SOURCES
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 4. Select Saved Sources for Comparison")

company_options = {
    f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
}

selected_company_displays = st.multiselect(
    "Select up to 3 companies to compare",
    options=list(company_options.keys()),
    default=[],
    max_selections=3,
    key="comparison_company_selection",
)

selected_codes = [company_options[x] for x in selected_company_displays]

if not selected_codes:
    st.info("Please select at least 1 company for comparison.")

selected = {}
catalogs = {}

if selected_codes:
    cols = st.columns(len(selected_codes))
    for i, code in enumerate(selected_codes):
        with cols[i]:
            files = get_company_files(code)
            selected[code] = st.selectbox(
                f"{code} source file",
                [""] + files,
                key=f"select_{code}",
            )

    for code in selected_codes:
        if selected.get(code):
            df = load_data(get_company_folder(code) / selected[code])
            catalogs[code] = prepare_catalog(df)
        else:
            catalogs[code] = None
st.markdown("</div>", unsafe_allow_html=True)


# 5. DEBUG
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 5. Debug")

if selected_codes:
    dbg_cols = st.columns(len(selected_codes))
    for i, code in enumerate(selected_codes):
        with dbg_cols[i]:
            st.write(f"Selected {code} file:", selected.get(code, ""))
            if catalogs.get(code) is not None:
                st.write(f"{code} prepared rows:", len(catalogs[code]))
else:
    st.info("No comparison companies selected yet.")
st.markdown("</div>", unsafe_allow_html=True)


# 6. MULTI-LINE COMPARISON
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 6. Multi-Line Comparison")

if not selected_codes:
    st.info("Select companies first to start comparison.")
else:
    b1, b2 = st.columns([1, 3])

    with b1:
        if st.button("Add Row", key="add_row_button", use_container_width=True):
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
            if st.button(
                "Delete This Row",
                key=f"delete_row_{row_id}",
                use_container_width=True,
            ):
                st.session_state.row_ids = [
                    r for r in st.session_state.row_ids if r != row_id
                ]
                st.rerun()

        row_cols = st.columns(len(selected_codes))
        row_final_prices = {}

        for col_idx, code in enumerate(selected_codes):
            with row_cols[col_idx]:
                label = get_company_label(code)

                st.write(f"#### {label}")

                df = catalogs.get(code)
                if df is not None and not df.empty:
                    options = [""] + df["DISPLAY"].tolist()
                    selected_product = st.selectbox(
                        f"{label} product",
                        options,
                        key=f"row_{row_id}_{code}_product",
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
                                f"{label} Disc {j}",
                                min_value=0.0,
                                max_value=100.0,
                                value=0.0,
                                step=0.1,
                                key=f"row_{row_id}_{code}_disc_{j}",
                            )
                            discs.append(disc_val)

                        final = apply_discounts(row["Price"], discs)
                        row_final_prices[code] = final
                        st.success(f"Final Price: {final}")
                    else:
                        for j in range(1, 6):
                            st.number_input(
                                f"{label} Disc {j}",
                                min_value=0.0,
                                max_value=100.0,
                                value=0.0,
                                step=0.1,
                                key=f"row_{row_id}_{code}_disc_{j}",
                            )
                        row_final_prices[code] = None
                        st.info("No product selected")
                else:
                    row_final_prices[code] = None
                    st.info("No data")

        if row_final_prices:
            valid = {k: v for k, v in row_final_prices.items() if v is not None}
            if valid:
                best_code = min(valid, key=valid.get)
                best_label = get_company_label(best_code)
            else:
                best_label = "-"

            st.metric(f"Row {visible_index + 1} Best Price", best_label)

            comparison_summaries = build_comparison_summary(
                row_final_prices, selected_codes
            )

            has_comparisons = any(v for v in comparison_summaries.values())
            if has_comparisons:
                st.markdown("**Price Difference %**")
                for code in selected_codes:
                    label = get_company_label(code)
                    summary = comparison_summaries.get(code, "")
                    if summary:
                        st.write(f"**{label}:** {summary}")

        st.markdown("---")
st.markdown("</div>", unsafe_allow_html=True)


# 7. EXPORT
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.markdown("## 7. Export Excel Report")

full_export_df = build_export_dataframe(
    st.session_state.row_ids, catalogs, selected_codes
)

selected_export_fields = st.multiselect(
    "Choose columns for Excel export",
    options=EXPORT_FIELD_OPTIONS,
    default=["Product", "Total Discounts", "Final Price", "Comparison %", "Best Price"],
    key="selected_export_fields",
)

if not selected_export_fields:
    st.warning("Please select at least one export field.")
else:
    export_df = filter_export_dataframe(
        full_export_df,
        selected_codes,
        selected_export_fields,
        companies_df,
    )

    if not export_df.empty:
        st.dataframe(export_df, use_container_width=True, hide_index=True)

        excel_bytes = to_excel_bytes(export_df)
        st.download_button(
            "Download Excel Report",
            data=excel_bytes,
            file_name="comparison_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel_report",
            use_container_width=True,
        )
    else:
        st.info("No data available for export yet.")
st.markdown("</div>", unsafe_allow_html=True)


# 8. ADMIN PANEL
if is_admin_user():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("## 8. Admin Panel")

    users_registry = load_users_registry()
    if users_registry:
        users_for_view = []
        for row in users_registry:
            sessions_count = len(row.get("active_sessions", []))
            users_for_view.append(
                {
                    "Email": row.get("email", ""),
                    "Name": row.get("name", ""),
                    "Status": row.get("status", "pending"),
                    "Billing": row.get("billing_status", "trialing"),
                    "Premium": row.get("is_premium", False),
                    "Company": row.get("company_name", "") or "",
                    "Role": row.get("role", "member"),
                    "Active Sessions": f"{sessions_count}/{MAX_ACTIVE_SESSIONS}",
                    "First Seen": row.get("first_seen", ""),
                    "Last Login": row.get("last_login", ""),
                    "Last Seen": row.get("last_seen", ""),
                    "Online": online_status_from_last_seen(row.get("last_seen", "")),
                    "Sub": row.get("sub", ""),
                }
            )

        users_df = pd.DataFrame(users_for_view)
        st.dataframe(users_df, use_container_width=True, hide_index=True)

        user_options = {}
        for row in users_registry:
            label = f"{row.get('email', '')} | {row.get('status', '')}"
            user_options[label] = row

        selected_user_label = st.selectbox(
            "Select user",
            [""] + list(user_options.keys()),
            key="admin_selected_user_to_manage",
        )

        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

        with c1:
            if st.button(
                "Approve User", key="approve_user_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_status(
                        row.get("email", ""),
                        row.get("sub", ""),
                        "approved",
                    )
                    st.success(f"Approved: {row.get('email', '')}")
                    st.rerun()

        with c2:
            if st.button(
                "Block User", key="block_user_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_status(
                        row.get("email", ""),
                        row.get("sub", ""),
                        "blocked",
                    )
                    st.success(f"Blocked: {row.get('email', '')}")
                    st.rerun()

        with c3:
            if st.button(
                "Set Pending", key="pending_user_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_status(
                        row.get("email", ""),
                        row.get("sub", ""),
                        "pending",
                    )
                    st.success(f"Set to pending: {row.get('email', '')}")
                    st.rerun()

        with c4:
            if st.button(
                "Give Premium", key="give_premium_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_premium(
                        row.get("email", ""),
                        row.get("sub", ""),
                        True,
                    )
                    st.success(f"Premium granted to: {row.get('email', '')}")
                    st.rerun()

        with c5:
            if st.button(
                "Remove Premium",
                key="remove_premium_button",
                use_container_width=True,
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_premium(
                        row.get("email", ""),
                        row.get("sub", ""),
                        False,
                    )
                    st.success(f"Premium removed from: {row.get('email', '')}")
                    st.rerun()

        with c6:
            if st.button(
                "Reset Sessions",
                key="reset_sessions_button",
                use_container_width=True,
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    reset_user_sessions(row.get("email", ""), row.get("sub", ""))
                    st.success(f"Sessions reset for: {row.get('email', '')}")
                    st.rerun()

        with c7:
            if st.button(
                "Remove From Company",
                key="remove_from_company_button",
                use_container_width=True,
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    remove_user_from_company(row.get("email", ""), row.get("sub", ""))
                    st.success(f"User removed from company: {row.get('email', '')}")
                    st.rerun()

    st.markdown("---")
    st.markdown("### Company Workspaces")

    companies_registry = load_companies_registry()
    companies_for_view = []
    for company in companies_registry:
        company = ensure_company_fields(company)
        companies_for_view.append(
            {
                "Key": company.get("key", ""),
                "Name": company.get("name", ""),
                "Domain": company.get("domain", ""),
                "Billing": company.get("billing_status", ""),
                "Seats": format_company_seats(company),
                "Max Seats": company.get("max_seats", 0),
                "Owner Email": company.get("owner_email", ""),
                "Active": company.get("is_active", True),
                "Trial End": company.get("trial_end", ""),
            }
        )

    if companies_for_view:
        st.dataframe(
            pd.DataFrame(companies_for_view),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No company workspaces found yet.")

    st.markdown("#### Create / Update Company Workspace")

    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        company_key_input = st.text_input(
            "Company Key",
            key="company_key_input",
            placeholder="knauf_team",
        )
    with cc2:
        company_name_input = st.text_input(
            "Company Name",
            key="company_name_input",
            placeholder="Knauf",
        )
    with cc3:
        company_domain_input = st.text_input(
            "Company Domain",
            key="company_domain_input",
            placeholder="knauf.com",
        )
    with cc4:
        company_max_seats_input = st.number_input(
            "Max Seats",
            min_value=0,
            max_value=1000,
            value=3,
            step=1,
            key="company_max_seats_input",
        )

    company_owner_email = st.text_input(
        "Owner Email",
        key="company_owner_email",
        placeholder="owner@company.com",
    )
    company_active_input = st.checkbox(
        "Company Workspace Active",
        value=True,
        key="company_active_input",
    )

    ccu1, ccu2 = st.columns(2)

    with ccu1:
        if st.button(
            "Save Company Workspace",
            key="save_company_plan_button",
            use_container_width=True,
        ):
            if not company_key_input.strip():
                st.warning("Please enter a company key.")
            elif not company_name_input.strip():
                st.warning("Please enter a company name.")
            elif not company_domain_input.strip():
                st.warning("Please enter a company domain.")
            else:
                upsert_company(
                    company_key_input,
                    company_name_input,
                    company_domain_input,
                    company_max_seats_input,
                    company_active_input,
                    "trialing",
                    company_owner_email,
                )
                st.success(f"Company workspace saved: {company_name_input}")
                st.rerun()

    company_options_for_delete = {
        f"{c.get('name', '')} ({c.get('domain', '')})": c.get("key")
        for c in companies_registry
    }

    with ccu2:
        selected_company_to_delete = st.selectbox(
            "Delete Company Workspace",
            [""] + list(company_options_for_delete.keys()),
            key="selected_company_to_delete",
        )
        if st.button(
            "Delete Company Workspace",
            key="delete_company_plan_button",
            use_container_width=True,
        ):
            if selected_company_to_delete:
                remove_company(company_options_for_delete[selected_company_to_delete])
                st.success(
                    f"Company workspace deleted: {selected_company_to_delete}"
                )
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)