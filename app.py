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


if st.query_params.get("login") == "google":
    st.login("google")

if st.query_params.get("login") == "microsoft":
    st.login("microsoft")


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

    required_shared = [
        auth_redirect_uri,
        auth_cookie_secret,
    ]
    required_google = [
        google_client_id,
        google_client_secret,
        google_server_metadata_url,
    ]

    if not all(required_shared) or not all(required_google):
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
# APP CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Pricing App",
    page_icon="💎",
    layout="wide",
)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


# -------------------------------------------------
# UI STYLE
# -------------------------------------------------
st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    .app-hero {
        padding: 24px 28px;
        border-radius: 18px;
        background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
        color: white;
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.18);
    }

    .app-card {
        background: #111827;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 22px 24px;
        color: white;
        box-shadow: 0 8px 24px rgba(0,0,0,0.14);
    }

    .soft-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 16px 18px;
    }

    .muted {
        color: #9ca3af;
    }

    .metric-pill {
        display: inline-block;
        padding: 8px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.08);
        font-size: 14px;
        margin-top: 8px;
    }

    .section-title {
        margin-top: 8px;
        margin-bottom: 8px;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .locked-wrap {
        max-width: 760px;
        margin: 30px auto 0 auto;
        padding: 32px;
        border-radius: 22px;
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 20px 50px rgba(0,0,0,0.22);
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
        background: rgba(96,165,250,0.12);
        border: 1px solid rgba(96,165,250,0.25);
        color: #bfdbfe;
        font-size: 13px;
        margin-bottom: 18px;
    }

    .mini-note {
        font-size: 13px;
        color: #9ca3af;
        margin-top: 8px;
    }

    div[data-testid="stSidebar"] {
        border-right: 1px solid rgba(255,255,255,0.06);
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.06);
        padding: 10px 12px;
        border-radius: 16px;
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
        return st.user.get("email", "")
    except Exception:
        return ""


def auth_is_configured():
    return True


def show_login_screen():

    st.markdown("""
    <style>
    .login-container {
        max-width: 420px;
        margin: 60px auto;
        padding: 40px;
        border-radius: 20px;
        background: #111827;
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 20px 50px rgba(0,0,0,0.4);
        text-align: center;
        color: white;
    }

    .login-title {
        font-size: 30px;
        font-weight: 800;
        margin-bottom: 10px;
    }

    .login-subtitle {
        font-size: 14px;
        color: #9ca3af;
        margin-bottom: 30px;
    }

    .login-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        padding: 14px;
        border-radius: 12px;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        transition: all 0.2s ease;
        margin-bottom: 12px;
        font-size: 15px;
    }

    .google-btn {
        background: white;
        color: black;
    }

    .google-btn:hover {
        background: #f3f4f6;
    }

    .ms-btn {
        background: #2F2F2F;
        color: white;
        border: 1px solid rgba(255,255,255,0.1);
    }

    .ms-btn:hover {
        background: #3a3a3a;
    }

    .login-btn img {
        width: 20px;
        height: 20px;
    }

    .login-footer {
        margin-top: 20px;
        font-size: 12px;
        color: #6b7280;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-container">
        <div class="login-title">Pricing App</div>
        <div class="login-subtitle">
            Sign in to continue to your workspace
        </div>

        <a href="?login=google" class="login-btn google-btn">
            <img src="https://www.svgrepo.com/show/475656/google-color.svg">
            Continue with Google
        </a>

        <a href="?login=microsoft" class="login-btn ms-btn">
            <img src="https://www.svgrepo.com/show/448239/microsoft.svg">
            Continue with Microsoft
        </a>

        <div class="login-footer">
            Secure login • No passwords stored
        </div>
    </div>
    """, unsafe_allow_html=True)


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
# BILLING / STRIPE
# -------------------------------------------------
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
                "is_premium": False,
                "billing_status": "free",
                "trial_end": None,
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
                if sub.status in ["past_due", "unpaid", "canceled", "incomplete", "incomplete_expired"]:
                    preferred = sub
                    break

        if preferred is None:
            preferred = subs.data[0]

        trial_end = None
        if getattr(preferred, "trial_end", None):
            trial_end = datetime.fromtimestamp(preferred.trial_end, tz=timezone.utc)

        return {
            "email": email.strip().lower(),
            "is_premium": preferred.status == "active",
            "billing_status": preferred.status,
            "trial_end": trial_end,
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
# PERSISTENT STORAGE
# -------------------------------------------------
PERSIST_ROOT = Path(os.getenv("PERSIST_ROOT", "/var/data"))
PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

MAIN_CODES = ["SINIAT", "KNAUF", "SAINT_GOBAIN"]

user_id = (
    get_current_user_id()
    .replace("@", "_")
    .replace(".", "_")
    .replace("/", "_")
    .replace("\\", "_")
)

USER_DIR = PERSIST_ROOT / user_id
UPLOADS_DIR = USER_DIR / "uploads"
COMPANIES_FILE = USER_DIR / "companies.csv"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

ROOT_STORAGE = PERSIST_ROOT
ADMIN_DIR = ROOT_STORAGE / "_admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)

USERS_REGISTRY_FILE = ADMIN_DIR / "users_registry.json"
COMPANIES_REGISTRY_FILE = ADMIN_DIR / "companies_registry.json"
ADMIN_EMAILS = ["gmyl13@gmail.com"]

TEMPLATE_FILE = BASE_DIR / "templates" / "source_template_english.xlsx"


# -------------------------------------------------
# JSON / TIME HELPERS
# -------------------------------------------------
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


def now_utc():
    return datetime.utcnow()


# -------------------------------------------------
# USERS / ADMIN
# -------------------------------------------------
TRIAL_DAYS = 2
MAX_ACTIVE_SESSIONS = 2


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


def find_company_by_domain(companies, domain):
    domain = normalize_domain(domain)
    for company in companies:
        if normalize_domain(company.get("domain", "")) == domain:
            return company
    return None


def find_company_by_key(companies, company_key):
    for company in companies:
        if company.get("key") == company_key:
            return company
    return None


def get_company_user_count(company_key):
    users = load_users_registry()
    count = 0
    for row in users:
        if row.get("company_key") == company_key and row.get("status") != "blocked":
            count += 1
    return count


def format_company_seats(current_count, max_seats):
    return f"{current_count}/{max_seats}"


def ensure_user_billing_fields(user_row):
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

    return user_row


def find_user_index(users, email, sub):
    for i, row in enumerate(users):
        if row.get("email") == email and row.get("sub") == sub:
            return i
    return None


def get_current_user_registry_row():
    user = get_user_identity()
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return None, None, users

    users[idx] = ensure_user_billing_fields(users[idx])
    save_users_registry(users)
    return idx, users[idx], users


def trial_days_left(trial_end_value):
    dt = parse_iso(trial_end_value)
    if dt is None:
        return 0

    remaining = dt - now_utc()
    if remaining.total_seconds() <= 0:
        return 0

    return max(1, remaining.days + (1 if remaining.seconds > 0 else 0))


def get_current_session_id():
    if "app_session_id" not in st.session_state:
        st.session_state["app_session_id"] = str(uuid.uuid4())
    return st.session_state["app_session_id"]


def register_current_session():
    user = get_user_identity()
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return True, 0

    current_session_id = get_current_session_id()
    current_time = now_iso()

    sessions = users[idx].get("active_sessions", [])

    for s in sessions:
        if s.get("session_id") == current_session_id:
            s["last_seen"] = current_time
            users[idx]["active_sessions"] = sessions
            save_users_registry(users)
            return True, len(sessions)

    if len(sessions) >= MAX_ACTIVE_SESSIONS:
        return False, len(sessions)

    sessions.append(
        {
            "session_id": current_session_id,
            "last_seen": current_time,
        }
    )
    users[idx]["active_sessions"] = sessions
    save_users_registry(users)
    return True, len(sessions)


def unregister_current_session():
    user = get_user_identity()
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return

    current_session_id = get_current_session_id()
    sessions = users[idx].get("active_sessions", [])
    sessions = [s for s in sessions if s.get("session_id") != current_session_id]
    users[idx]["active_sessions"] = sessions
    save_users_registry(users)


def touch_current_session():
    user = get_user_identity()
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return

    current_session_id = get_current_session_id()
    sessions = users[idx].get("active_sessions", [])

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


def sync_paid_status_from_stripe(email: str):
    idx, row, users = get_current_user_registry_row()
    if row is None or not email:
        return False

    stripe_row = get_stripe_subscription_row(email)
    if not stripe_row:
        return False

    if stripe_row.get("billing_status") == "active":
        users[idx]["billing_status"] = "active"
        users[idx]["is_premium"] = True
        users[idx]["stripe_customer_id"] = stripe_row.get("stripe_customer_id")
        users[idx]["stripe_subscription_id"] = stripe_row.get("stripe_subscription_id")
        save_users_registry(users)
        return True

    if row.get("billing_status") == "active" and stripe_row.get("billing_status") != "active":
        users[idx]["billing_status"] = "expired"
        users[idx]["is_premium"] = False
        save_users_registry(users)

    return False


def is_admin_user():
    user = get_user_identity()
    return user["email"] in ADMIN_EMAILS


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
        users[idx]["stripe_customer_id"] = None
        users[idx]["stripe_subscription_id"] = None
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
        save_users_registry(users)


def format_sessions(count):
    if count >= MAX_ACTIVE_SESSIONS:
        return f"{count}/{MAX_ACTIVE_SESSIONS} 🔴"
    if count == MAX_ACTIVE_SESSIONS - 1:
        return f"{count}/{MAX_ACTIVE_SESSIONS} 🟠"
    return f"{count}/{MAX_ACTIVE_SESSIONS} 🟢"


def session_status_label(count):
    if count >= MAX_ACTIVE_SESSIONS:
        return "Full 🔴"
    if count == MAX_ACTIVE_SESSIONS - 1:
        return "Near Limit 🟠"
    return "Available 🟢"


def get_current_user_company():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return None

    company_key = row.get("company_key")
    if not company_key:
        return None

    companies = load_companies_registry()
    return find_company_by_key(companies, company_key)


def ensure_current_user_in_registry():
    user = get_user_identity()
    users = load_users_registry()

    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        status = "approved" if user["email"] in ADMIN_EMAILS else "pending"
        users.append(
            {
                "email": user["email"],
                "sub": user["sub"],
                "name": user["name"],
                "status": status,
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
            }
        )
    else:
        users[idx]["name"] = user["name"]
        users[idx]["last_login"] = now_iso()
        users[idx]["last_seen"] = now_iso()
        if user["email"] in ADMIN_EMAILS:
            users[idx]["status"] = "approved"
        users[idx] = ensure_user_billing_fields(users[idx])

    save_users_registry(users)


def sync_current_user_company_assignment():
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

    if not company.get("is_active", True):
        return {"status": "inactive", "company": company}

    existing_company_key = row.get("company_key")
    if existing_company_key == company.get("key"):
        return {"status": "assigned", "company": company}

    current_count = get_company_user_count(company.get("key"))
    max_seats = int(company.get("max_seats", 0) or 0)

    if max_seats > 0 and current_count >= max_seats:
        return {"status": "full", "company": company}

    users[idx]["company_key"] = company.get("key")
    users[idx]["company_name"] = company.get("name", company.get("key"))
    users[idx]["status"] = "approved"
    save_users_registry(users)

    return {"status": "assigned", "company": company}


def current_user_has_access():
    idx, row, users = get_current_user_registry_row()
    if row is None:
        return False

    company_key = row.get("company_key")
    if company_key:
        companies = load_companies_registry()
        company = find_company_by_key(companies, company_key)
        if company and company.get("is_active", True) and row.get("status") == "approved":
            return True

    user_email = get_current_user_email()

    if row.get("billing_status") == "active" or row.get("is_premium") is True:
        if row.get("is_premium") is True and row.get("stripe_subscription_id") is None:
            return True

        if user_email and sync_paid_status_from_stripe(user_email):
            return True

        if idx is not None and not row.get("is_premium", False):
            users[idx]["billing_status"] = "expired"
            users[idx]["is_premium"] = False
            save_users_registry(users)

    trial_end = parse_iso(row.get("trial_end", ""))
    if trial_end and now_utc() <= trial_end:
        return True

    if user_email and sync_paid_status_from_stripe(user_email):
        return True

    if idx is not None and not row.get("is_premium", False):
        users[idx]["billing_status"] = "expired"
        users[idx]["is_premium"] = False
        save_users_registry(users)

    return False


def touch_current_user():
    user = get_user_identity()
    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])
    if idx is not None:
        users[idx]["last_seen"] = now_iso()
        save_users_registry(users)


def get_current_user_status():
    user = get_user_identity()

    if user["email"] in ADMIN_EMAILS:
        return "approved"

    users = load_users_registry()
    idx = find_user_index(users, user["email"], user["sub"])

    if idx is None:
        return "pending"

    return users[idx].get("status", "pending")


def current_user_is_blocked():
    return get_current_user_status() == "blocked"


def current_user_is_approved():
    return get_current_user_status() == "approved"


def online_status_from_last_seen(last_seen_value):
    dt = parse_iso(last_seen_value)
    if dt is None:
        return "Offline"

    if datetime.utcnow() - dt <= timedelta(minutes=2):
        return "Online"

    return "Offline"


def upsert_company(company_key, name, domain, max_seats, is_active=True):
    companies = load_companies_registry()
    normalized_key = normalize_company_key(company_key)
    idx = None
    for i, company in enumerate(companies):
        if company.get("key") == normalized_key:
            idx = i
            break

    payload = {
        "key": normalized_key,
        "name": str(name).strip(),
        "domain": normalize_domain(domain),
        "max_seats": int(max_seats),
        "is_active": bool(is_active),
        "updated_at": now_iso(),
    }

    if idx is None:
        payload["created_at"] = now_iso()
        companies.append(payload)
    else:
        payload["created_at"] = companies[idx].get("created_at", now_iso())
        companies[idx] = payload

    save_companies_registry(companies)


def remove_company(company_key):
    companies = load_companies_registry()
    companies = [c for c in companies if c.get("key") != company_key]
    save_companies_registry(companies)


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


def row_result_dict(visible_index, row_id, catalogs, selected_codes):
    result = {"Row": visible_index + 1}
    final_prices = {}

    for code in selected_codes:
        company_name_row = companies_df[companies_df["code"] == code]
        label = code
        if not company_name_row.empty:
            label = company_name_row.iloc[0]["name"]

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
                result[f"{label} Disc{i}"] = st.session_state.get(
                    f"row_{row_id}_{code}_disc_{i}", 0.0
                )

            result[f"{label} Final Price"] = ""

    valid = {k: v for k, v in final_prices.items() if v is not None}
    if valid:
        best_code = min(valid, key=valid.get)
        best_name_row = companies_df[companies_df["code"] == best_code]
        best_label = best_code if best_name_row.empty else best_name_row.iloc[0]["name"]
        result["Best Price"] = best_label
    else:
        result["Best Price"] = ""

    return result


def build_export_dataframe(row_ids, catalogs, selected_codes):
    rows = []
    for visible_index, row_id in enumerate(row_ids):
        rows.append(row_result_dict(visible_index, row_id, catalogs, selected_codes))
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
        elif str(header) in [
            "Best Price",
            "Knauf vs Siniat",
            "Saint-Gobain vs Siniat",
            "Saint-Gobain vs Knauf",
        ]:
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
        "Siniat Base Price",
        "Siniat Final Price",
        "Knauf Base Price",
        "Knauf Final Price",
        "Saint-Gobain Base Price",
        "Saint-Gobain Final Price",
    ]

    disc_headers = [
        "Siniat Disc1",
        "Siniat Disc2",
        "Siniat Disc3",
        "Siniat Disc4",
        "Siniat Disc5",
        "Knauf Disc1",
        "Knauf Disc2",
        "Knauf Disc3",
        "Knauf Disc4",
        "Knauf Disc5",
        "Saint-Gobain Disc1",
        "Saint-Gobain Disc2",
        "Saint-Gobain Disc3",
        "Saint-Gobain Disc4",
        "Saint-Gobain Disc5",
    ]

    for col_idx, header in enumerate(headers, start=1):
        if header in numeric_headers:
            for row_idx in range(2, ws.max_row + 1):
                ws.cell(row=row_idx, column=col_idx).number_format = "0.00"

        if header in disc_headers:
            for row_idx in range(2, ws.max_row + 1):
                ws.cell(row=row_idx, column=col_idx).number_format = "0.0"


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

company_result = sync_current_user_company_assignment()

if company_result["status"] == "full":
    company = company_result["company"]
    current_count = get_company_user_count(company.get("key"))
    max_seats = int(company.get("max_seats", 0) or 0)

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

    st.write("")
    c1, c2, c3 = st.columns([1, 1.7, 1])

    with c2:
        st.markdown('<div class="app-card">', unsafe_allow_html=True)
        st.subheader("No available seats")
        st.warning(
            f"{company.get('name', 'This company')} is currently using all available seats ({current_count}/{max_seats})."
        )
        st.info(
            "Please contact your company administrator if you need an additional seat "
            "or if an inactive user should be removed."
        )
        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="company_seat_limit_logout_button",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

if current_user_is_blocked():
    st.error("Access denied. Your account has been blocked.")
    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="blocked_logout_button",
    )
    st.stop()

if not current_user_is_approved():
    st.warning("Your account is pending admin approval.")
    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="pending_logout_button",
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

        st.write("")
        c1, c2, c3 = st.columns([1, 1.7, 1])

        with c2:
            st.markdown('<div class="app-card">', unsafe_allow_html=True)
            st.subheader("Maximum active devices reached")
            st.warning(f"This account allows up to {MAX_ACTIVE_SESSIONS} active devices/browsers at the same time.")
            st.info(
                "Example: if you are already logged in on your phone and your computer, "
                "you will need to logout from one of them before signing in on a third device."
            )
            st.warning("Please logout from another device/browser first, then try again.")

            st.button(
                "Logout",
                on_click=logout_current_user,
                use_container_width=True,
                key="session_limit_logout_button",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        st.stop()
    else:
        touch_current_session()

user_email = get_current_user_email()

if (not is_admin_user()) and (not current_user_has_access()):
    idx, row, users = get_current_user_registry_row()
    days_left = trial_days_left(row.get("trial_end")) if row else 0
    checkout_url = get_checkout_url(user_email) if user_email else None

    st.markdown(
        """
        <div class="locked-wrap">
            <div class="locked-badge">Premium access required</div>
            <div class="locked-title">Your free trial has ended</div>
            <div class="locked-subtitle">
                You can still log in, but access to the full app is now locked.
                To continue using all features, activate the monthly plan.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    c1, c2, c3 = st.columns([1, 1.6, 1])
    with c2:
        st.markdown('<div class="app-card">', unsafe_allow_html=True)
        st.subheader("Continue with Premium")
        st.write("Unlock full access for **€10/month** and continue using the app without restrictions.")
        if days_left > 0:
            st.info(f"Your free trial is still active. Days left: {days_left}")
        else:
            st.warning("Your 2-day free trial has expired.")

        if checkout_url:
            st.link_button(
                "💳 Subscribe for €10/month",
                checkout_url,
                use_container_width=True,
            )
            st.caption("Secure checkout powered by Stripe.")
        else:
            st.error("Unable to prepare checkout right now. Please try again.")

        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="locked_logout_button",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.markdown("### Account")
    st.success("Logged in")
    st.write(f"User: {get_current_user_email() or get_current_user_id()}")

    idx, row, users = get_current_user_registry_row()
    days_left = trial_days_left(row.get("trial_end")) if row else 0
    user_email = get_current_user_email()
    company = get_current_user_company()

    if is_admin_user():
        st.success("Admin: Full Access")
    else:
        if company:
            current_count = get_company_user_count(company.get("key"))
            max_seats = int(company.get("max_seats", 0) or 0)
            st.success(f"Company: {company.get('name', 'Company Plan')}")
            st.info(f"Seats: {format_company_seats(current_count, max_seats)}")
        elif row and row.get("billing_status") == "active":
            st.success("Plan: Premium")
        elif days_left > 0:
            st.info(f"Trial: {days_left} day(s) left")
        else:
            st.warning("Plan: Locked")

    st.markdown("---")
    st.subheader("💳 Billing")

    if not is_admin_user():
        if company:
            st.success("Your access is managed through your company plan.")
        elif row and row.get("billing_status") == "active":
            st.success("Your subscription is active.")
        elif days_left > 0:
            st.info("You are currently using the free 2-day trial.")
        elif user_email:
            checkout_url = get_checkout_url(user_email)
            if checkout_url:
                st.link_button(
                    "Subscribe €10/month",
                    checkout_url,
                    use_container_width=True,
                )
            else:
                st.error("Checkout unavailable.")

    st.markdown("---")

    if not is_admin_user():
        st.warning("⚠️ Please logout before closing the app to free your session.")
        active_sessions_count = len(row.get("active_sessions", [])) if row else 0
        st.caption(f"Active sessions: {format_sessions(active_sessions_count)}")

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
        <div style="font-size:34px;font-weight:800;letter-spacing:-0.03em;">Pricing App</div>
        <div style="font-size:16px;color:#d1d5db;margin-top:8px;">
            Upload supplier sources, compare products and export polished Excel reports.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.query_params.get("payment") == "success":
    st.success("Payment completed successfully. Your access will be available after the page refreshes.")
elif st.query_params.get("payment") == "cancel":
    st.info("Checkout was cancelled.")

# 1. COMPANY MANAGER
st.markdown("## 1. Company Manager")

add_c1, add_c2, add_c3 = st.columns(3)
with add_c1:
    new_code = st.text_input("Code", key="new_company_code", placeholder="TECHNOGIPS")
with add_c2:
    new_name = st.text_input("Name", key="new_company_name", placeholder="Technogips")
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
    if st.button("Delete Company", key="delete_company_button", use_container_width=True):
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


# 2. SAVE SOURCE
st.markdown("---")
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

st.info("Download the source template, fill in your products, and upload it back to the platform.")

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


# 3. SOURCE LIBRARY
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
        key="delete_source_display",
    )
with src_d2:
    st.write("")
    st.write("")
    if st.button("Delete Source", key="delete_source_button", use_container_width=True):
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


# 4. SELECT SAVED SOURCES
st.markdown("---")
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


# 5. DEBUG
st.markdown("---")
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


# 6. MULTI-LINE COMPARISON
st.markdown("---")
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
            if st.button("Delete This Row", key=f"delete_row_{row_id}", use_container_width=True):
                st.session_state.row_ids = [
                    r for r in st.session_state.row_ids if r != row_id
                ]
                st.rerun()

        row_cols = st.columns(len(selected_codes))
        row_final_prices = {}

        for col_idx, code in enumerate(selected_codes):
            with row_cols[col_idx]:
                company_name_row = companies_df[companies_df["code"] == code]
                label = code if company_name_row.empty else company_name_row.iloc[0]["name"]

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
                best_name_row = companies_df[companies_df["code"] == best_code]
                best_label = best_code if best_name_row.empty else best_name_row.iloc[0]["name"]
            else:
                best_label = "-"

            st.metric(f"Row {visible_index + 1} Best Price", best_label)

        st.markdown("---")


# 7. EXPORT
st.markdown("## 7. Export Excel Report")

export_df = build_export_dataframe(st.session_state.row_ids, catalogs, selected_codes)

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


# 8. ADMIN PANEL
if is_admin_user():
    st.markdown("---")
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
                    "Active Sessions": format_sessions(sessions_count),
                    "Session Status": session_status_label(sessions_count),
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
            sessions_count = len(row.get("active_sessions", []))
            label = (
                f"{row.get('email', '')} | "
                f"{row.get('status', '')} | "
                f"{session_status_label(sessions_count)}"
            )
            user_options[label] = row

        selected_user_label = st.selectbox(
            "Select user",
            [""] + list(user_options.keys()),
            key="admin_selected_user_to_manage",
        )

        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

        with c1:
            if st.button("Approve User", key="approve_user_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "approved")
                    st.success(f"Approved: {row.get('email', '')}")
                    st.rerun()

        with c2:
            if st.button("Block User", key="block_user_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "blocked")
                    st.success(f"Blocked: {row.get('email', '')}")
                    st.rerun()

        with c3:
            if st.button("Set Pending", key="pending_user_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_status(row.get("email", ""), row.get("sub", ""), "pending")
                    st.success(f"Set to pending: {row.get('email', '')}")
                    st.rerun()

        with c4:
            if st.button("Give Premium", key="give_premium_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_premium(row.get("email", ""), row.get("sub", ""), True)
                    st.success(f"Premium granted to: {row.get('email', '')}")
                    st.rerun()

        with c5:
            if st.button("Remove Premium", key="remove_premium_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    set_user_premium(row.get("email", ""), row.get("sub", ""), False)
                    st.success(f"Premium removed from: {row.get('email', '')}")
                    st.rerun()

        with c6:
            if st.button("Reset Sessions", key="reset_sessions_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    reset_user_sessions(row.get("email", ""), row.get("sub", ""))
                    st.success(f"Sessions reset for: {row.get('email', '')}")
                    st.rerun()

        with c7:
            if st.button("Remove From Company", key="remove_from_company_button", use_container_width=True):
                if not selected_user_label:
                    st.warning("Please select a user.")
                else:
                    row = user_options[selected_user_label]
                    remove_user_from_company(row.get("email", ""), row.get("sub", ""))
                    st.success(f"User removed from company: {row.get('email', '')}")
                    st.rerun()
    else:
        st.info("No users found yet.")

    st.markdown("---")
    st.markdown("### Company Plans")

    companies_registry = load_companies_registry()

    companies_for_view = []
    for company in companies_registry:
        current_count = get_company_user_count(company.get("key"))
        max_seats = int(company.get("max_seats", 0) or 0)
        companies_for_view.append(
            {
                "Key": company.get("key", ""),
                "Name": company.get("name", ""),
                "Domain": company.get("domain", ""),
                "Seats": format_company_seats(current_count, max_seats),
                "Max Seats": max_seats,
                "Active": company.get("is_active", True),
                "Created At": company.get("created_at", ""),
                "Updated At": company.get("updated_at", ""),
            }
        )

    if companies_for_view:
        st.dataframe(pd.DataFrame(companies_for_view), use_container_width=True, hide_index=True)
    else:
        st.info("No company plans found yet.")

    st.markdown("#### Create / Update Company")

    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        company_key_input = st.text_input("Company Key", key="company_key_input", placeholder="knaufteam")
    with cc2:
        company_name_input = st.text_input("Company Name", key="company_name_input", placeholder="Knauf")
    with cc3:
        company_domain_input = st.text_input("Company Domain", key="company_domain_input", placeholder="knauf.com")
    with cc4:
        company_max_seats_input = st.number_input(
            "Max Seats",
            min_value=1,
            max_value=1000,
            value=5,
            step=1,
            key="company_max_seats_input",
        )

    company_active_input = st.checkbox("Company Plan Active", value=True, key="company_active_input")

    ccu1, ccu2 = st.columns(2)

    with ccu1:
        if st.button("Save Company Plan", key="save_company_plan_button", use_container_width=True):
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
                )
                st.success(f"Company plan saved: {company_name_input}")
                st.rerun()

    company_options_for_delete = {
        f"{c.get('name', '')} ({c.get('domain', '')})": c.get("key")
        for c in companies_registry
    }

    with ccu2:
        selected_company_to_delete = st.selectbox(
            "Delete Company Plan",
            [""] + list(company_options_for_delete.keys()),
            key="selected_company_to_delete",
        )
        if st.button("Delete Company Plan", key="delete_company_plan_button", use_container_width=True):
            if not selected_company_to_delete:
                st.warning("Please select a company.")
            else:
                remove_company(company_options_for_delete[selected_company_to_delete])
                st.success(f"Company plan deleted: {selected_company_to_delete}")
                st.rerun()