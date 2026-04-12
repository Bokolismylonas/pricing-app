import os
import io
import base64
import json
import re
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import stripe
from supabase import create_client, Client
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from storage import (
    list_comparisons,
    save_new_comparison,
    update_comparison,
    get_comparison,
    delete_comparison,
    build_display_label,
)


BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"


def resolve_asset_path(filename: str) -> Path:
    candidates = [
        ASSETS_DIR / filename,
        BASE_DIR / filename,
        Path("/mnt/data") / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return ASSETS_DIR / filename


FULL_LOGO_PATH = resolve_asset_path("pricingtool-final-logo-dark.svg")
ICON_LOGO_PATH = resolve_asset_path("pricingtool-icon-dark.svg")
PAGE_ICON = str(ICON_LOGO_PATH) if ICON_LOGO_PATH.exists() else "💎"

# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Pricing Tool – Compare Products & Export Excel Reports",
    page_icon=PAGE_ICON,
    layout="wide",
)

st.markdown(
    """
    <meta name="description" content="Upload supplier data, compare products and export polished Excel reports instantly with Pricing Tool.">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="https://www.pricingtool.gr/">
    """,
    unsafe_allow_html=True,
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


# -------------------------------------------------
# RENDER -> CREATE .streamlit/secrets.toml FROM ENV
# -------------------------------------------------
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
        # Keep compatibility if env var typo not present
        content = content.replace(
            os.getenv("MS_SERVER_METADATA_URL", ""),
            _escape_toml(ms_server_metadata_url),
        )

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
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 48%, #1e3a8a 100%);
        color: white;
        border: 1px solid rgba(255,255,255,0.10);
        margin-bottom: 1.2rem;
        box-shadow: 0 14px 34px rgba(0,0,0,0.18);
    }

    .app-card {
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 22px 24px;
        color: white;
        box-shadow: 0 8px 22px rgba(0,0,0,0.12);
        margin-bottom: 14px;
    }

    .locked-wrap {
        max-width: 760px;
        margin: 30px auto 0 auto;
        padding: 32px;
        border-radius: 22px;
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        border: 1px solid rgba(255,255,255,0.10);
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

    
.login-shell {
        max-width: 620px;
        margin: 56px auto 18px auto;
        padding: 44px 42px 34px 42px;
        border-radius: 28px;
        background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 24px 60px rgba(0,0,0,0.30);
        text-align: center;
        color: white;
    }

    .login-shell .login-header-logo {
        margin: 0 0 14px 0;
    }

    .login-shell .login-header-logo img {
        height: 46px;
        width: auto;
        max-width: 100%;
        display: inline-block;
    }

    .login-shell p {
        margin: 0;
        font-size: 18px;
        color: #cbd5e1;
    }

    .login-badge {
        display: inline-block;
        padding: 7px 14px;
        border-radius: 999px;
        background: rgba(96,165,250,0.16);
        border: 1px solid rgba(147,197,253,0.28);
        color: #dbeafe;
        font-size: 13px;
        font-weight: 700;
        margin-bottom: 16px;
    }

    .login-shell-premium {
        background:
            radial-gradient(circle at top right, rgba(59,130,246,0.22), transparent 28%),
            linear-gradient(180deg, #020617 0%, #0f172a 100%);
    }

    .login-feature-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-top: 22px;
        text-align: left;
    }

    .login-feature-card {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
    }

    .login-feature-title {
        font-size: 14px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 6px;
    }

    .login-feature-text {
        font-size: 13px;
        line-height: 1.5;
        color: #cbd5e1;
    }

    .login-provider-preview {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-bottom: 16px;
    }

    .login-provider-card {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 16px;
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        color: #111827;
        text-align: left;
        box-shadow: 0 10px 22px rgba(15,23,42,0.10);
    }

    .login-provider-card-ms {
        background: #f8fafc;
    }

    .provider-logo-box {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }

    .provider-logo-box.ms-box {
        background: #ffffff;
    }

    .provider-logo-google {
        width: 20px;
        height: 20px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 15px;
        font-weight: 800;
        color: #4285f4;
        background: #ffffff;
    }

    .provider-logo-microsoft {
        width: 18px;
        height: 18px;
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2px;
    }

    .provider-logo-microsoft span:nth-child(1) { background: #f25022; }
    .provider-logo-microsoft span:nth-child(2) { background: #7fba00; }
    .provider-logo-microsoft span:nth-child(3) { background: #00a4ef; }
    .provider-logo-microsoft span:nth-child(4) { background: #ffb900; }

    .provider-logo-microsoft span {
        display: block;
        width: 8px;
        height: 8px;
        border-radius: 1px;
    }

    .provider-meta {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    .provider-title {
        font-size: 14px;
        font-weight: 800;
        color: #111827;
        line-height: 1.2;
    }

    .provider-subtitle {
        font-size: 12px;
        color: #6b7280;
        line-height: 1.3;
    }

    .login-actions-label {
        text-align: center;
        margin: 4px 0 12px 0;
        font-size: 13px;
        color: #94a3b8;
        font-weight: 600;
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
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.08);
        color: #cbd5e1;
        font-size: 13px;
        margin-bottom: 18px;
    }

    div[data-testid="stSidebar"] {
        border-right: 1px solid rgba(255,255,255,0.08);
    }

    div[data-testid="stButton"] > button {
        border-radius: 12px;
        font-size: 15px;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,0.10);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    div[data-testid="stButton"] > button:hover {
        border: 1px solid rgba(59,130,246,0.55);
        box-shadow: 0 6px 14px rgba(59,130,246,0.16);
    }

    div[data-testid="stDownloadButton"] > button {
        border-radius: 12px;
        font-size: 15px;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,0.10);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    div[data-testid="stDownloadButton"] > button:hover {
        border: 1px solid rgba(16,185,129,0.55);
        box-shadow: 0 6px 14px rgba(16,185,129,0.16);
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 10px 12px;
        border-radius: 16px;
    }

    .stDataFrame {
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        overflow: hidden;
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

    .hero-logo-wrap {
        margin-bottom: 14px;
        animation: fadeInLogo 0.8s ease forwards;
    }

    .hero-logo-wrap img {
        height: 88px;
        width: auto;
        max-width: 100%;
        display: inline-block;
        transition: transform 0.25s ease, filter 0.25s ease;
    }

    .hero-logo-wrap img:hover {
        transform: scale(1.04);
        filter: drop-shadow(0 6px 18px rgba(59,130,246,0.35));
    }

    @keyframes fadeInLogo {
        from {
            opacity: 0;
            transform: translateY(6px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @media (max-width: 768px) {
        .hero-logo-wrap img {
            height: 58px;
        }
    }

    .row-nav-wrap {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
        margin: 10px 0 4px 0;
        flex-wrap: nowrap;
    }

    .row-nav-btn {
        width: 40px;
        height: 40px;
        min-width: 40px;
        border-radius: 10px;
        border: 1px solid rgba(148,163,184,0.35);
        background: #ffffff;
        color: #111827;
        font-size: 18px;
        font-weight: 700;
        line-height: 1;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        cursor: pointer;
        transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    }

    .row-nav-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 14px rgba(59,130,246,0.16);
    }

    .row-nav-btn:disabled {
        opacity: 0.38;
        cursor: default;
        box-shadow: none;
    }

    @media (max-width: 768px) {
        .row-nav-wrap {
            justify-content: center;
            gap: 10px;
            margin: 8px 0 0 0;
        }

        .row-nav-btn {
            width: 42px;
            height: 42px;
            min-width: 42px;
            border-radius: 12px;
            font-size: 18px;
        }
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


def render_logo_if_available(path, width=None):
    try:
        if Path(path).exists():
            st.image(str(path), width=width)
            return True
    except Exception:
        pass
    return False


def show_login_screen():
    top_left, top_mid, top_right = st.columns([1.0, 2.5, 1.0])

    with top_mid:
        login_header_logo_html = ""
        if FULL_LOGO_PATH.exists():
            login_logo_b64 = base64.b64encode(FULL_LOGO_PATH.read_bytes()).decode("utf-8")
            login_header_logo_html = (
                '<div class="login-header-logo">'
                f'<img src="data:image/svg+xml;base64,{login_logo_b64}" alt="Pricing Tool logo" />'
                '</div>'
            )

        st.markdown(
            f"""
            <div class="login-shell login-shell-premium">
                <div class="login-badge">Secure workspace access</div>
                {login_header_logo_html}
                <p>Upload supplier sources, compare products and export polished Excel reports.</p>
                <div class="login-feature-row">
                    <div class="login-feature-card">
                        <div class="login-feature-title">Fast comparison</div>
                        <div class="login-feature-text">Build, save and reload pricing scenarios in seconds.</div>
                    </div>
                    <div class="login-feature-card">
                        <div class="login-feature-title">Protected access</div>
                        <div class="login-feature-text">Sign in securely with your Google or Microsoft account.</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    btn_left, btn_mid, btn_right = st.columns([1.1, 2.2, 1.1])

    with btn_mid:
        st.markdown(
            """
            <div class="provider-chip">Choose a sign-in provider</div>
            <div class="login-provider-preview">
                <div class="login-provider-card">
                    <span class="provider-logo-box">
                        <span class="provider-logo-google">G</span>
                    </span>
                    <span class="provider-meta">
                        <span class="provider-title">Continue with Google</span>
                        <span class="provider-subtitle">Use your Google account</span>
                    </span>
                </div>
                <div class="login-provider-card login-provider-card-ms">
                    <span class="provider-logo-box ms-box">
                        <span class="provider-logo-microsoft">
                            <span></span><span></span><span></span><span></span>
                        </span>
                    </span>
                    <span class="provider-meta">
                        <span class="provider-title">Sign in with Microsoft</span>
                        <span class="provider-subtitle">Use your Microsoft account</span>
                    </span>
                </div>
            </div>
            <div class="login-actions-label">Use the buttons below to continue</div>
            """,
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
            "Sign in with Microsoft",
            use_container_width=True,
            key="login_microsoft_button",
        ):
            st.login("microsoft")

        st.markdown(
            '<div class="login-note">Secure login • No passwords stored • Existing app flow unchanged</div>',
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


def get_comparison_state_signature():
    relevant = {}
    prefixes = ("row_", "select_", "carry_forward_", "widget_row_")
    direct_keys = {
        "row_ids",
        "next_row_id",
        "comparison_company_selection",
        "comparison_name_input",
        "current_comparison_id",
        "selected_export_fields",
    }
    for key in list(st.session_state.keys()):
        if key in direct_keys or key.startswith(prefixes):
            try:
                relevant[key] = st.session_state.get(key)
            except Exception:
                pass
    return json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)


def mark_comparison_clean():
    st.session_state["comparison_saved_signature"] = get_comparison_state_signature()
    st.session_state["comparison_dirty"] = False


def comparison_has_meaningful_content():
    if st.session_state.get("current_comparison_id"):
        return True

    if len(st.session_state.get("row_ids", [])) > 1:
        return True

    if st.session_state.get("comparison_company_selection", []):
        return True

    if st.session_state.get("comparison_name_input", "").strip():
        return True

    for key, value in st.session_state.items():
        if key.startswith("row_") and key.endswith("_product") and str(value).strip():
            return True

        if key.startswith("row_") and "_disc_" in key:
            try:
                if float(value or 0) != 0:
                    return True
            except Exception:
                pass

    return False


def has_unsaved_comparison_changes():
    if not comparison_has_meaningful_content():
        return False

    if st.session_state.get("comparison_dirty"):
        return True

    saved = st.session_state.get("comparison_saved_signature", "")
    current = get_comparison_state_signature()

    if not saved:
        return False

    return current != saved


def mark_comparison_dirty():
    st.session_state["comparison_dirty"] = comparison_has_meaningful_content()


@st.cache_data(show_spinner=False)
def load_prepared_catalog_from_file(file_path_str: str, modified_ts: float):
    file_path = Path(file_path_str)
    df = pd.read_excel(file_path, sheet_name="PRICELIST")
    df.columns = [str(c).strip() for c in df.columns]

    def _find_col(local_df, names):
        cols = {str(c).strip().lower(): c for c in local_df.columns}
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    sap = _find_col(df, ["SAP", "Κωδικός SAP"])
    prod = _find_col(df, ["Product", "Προϊόν"])
    price = _find_col(df, ["Price", "Τιμή €/ΜΜ", "Τιμή", "Price €/MM"])
    mm = _find_col(df, ["ΜΜ πώλησης", "MM", "Unit", "ΜΜ"])
    pack = _find_col(df, ["Συσκευασία", "Package", "pack"])
    category = _find_col(df, ["Κατηγορία", "Category", "category"])

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


def reset_user_to_trial(email, sub):
    users = load_users_registry()
    idx = find_user_index(users, email, sub)
    if idx is not None:
        users[idx]["is_premium"] = False
        users[idx]["billing_status"] = "trialing"
        users[idx]["trial_start"] = now_iso()
        users[idx]["trial_end"] = (now_utc() + timedelta(days=TRIAL_DAYS)).isoformat()
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
                "status": "approved",
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
COMPARISONS_DIR = WORKSPACE_DIR / "_saved_comparisons"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)


def get_current_user_comparisons_file():
    raw_user = get_current_user_id() or get_current_user_email() or "anonymous"
    safe_user = normalize_company_key(raw_user)
    return COMPARISONS_DIR / f"{safe_user}.json"


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


@st.cache_data(show_spinner=False)
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
    title_fill = PatternFill(fill_type="solid", fgColor="0F172A")
    title_font = Font(color="FFFFFF", bold=True, size=14)
    header_fill = PatternFill(fill_type="solid", fgColor="1E3A8A")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    subheader_fill = PatternFill(fill_type="solid", fgColor="DBEAFE")
    zebra_fill = PatternFill(fill_type="solid", fgColor="F8FAFC")
    siniat_fill = PatternFill(fill_type="solid", fgColor="E0F2FE")
    knauf_fill = PatternFill(fill_type="solid", fgColor="ECFCCB")
    sg_fill = PatternFill(fill_type="solid", fgColor="FCE7F3")
    result_fill = PatternFill(fill_type="solid", fgColor="FEF3C7")
    best_fill = PatternFill(fill_type="solid", fgColor="DCFCE7")

    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right_align = Alignment(horizontal="right", vertical="center", wrap_text=True)

    thin = Side(style="thin", color="CBD5E1")
    medium = Side(style="medium", color="94A3B8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_border = Border(left=medium, right=medium, top=medium, bottom=medium)

    max_col = ws.max_column

    ws.insert_rows(1, amount=2)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    ws["A1"] = "Pricing Comparison Report"
    ws["A1"].fill = title_fill
    ws["A1"].font = title_font
    ws["A1"].alignment = left_align
    ws["A1"].border = header_border

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
    ws["A2"] = f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    ws["A2"].fill = subheader_fill
    ws["A2"].font = Font(color="0F172A", italic=True, size=10)
    ws["A2"].alignment = left_align
    ws["A2"].border = border

    header_row = 3
    data_start_row = 4
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{ws.max_row}"

    for cell in ws[header_row]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = header_border

    headers = [cell.value for cell in ws[header_row]]

    for row_idx in range(data_start_row, ws.max_row + 1):
        is_zebra = (row_idx - data_start_row) % 2 == 1
        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            header = headers[col_idx - 1]
            cell.border = border

            if isinstance(cell.value, (int, float)) and header != "Row":
                cell.number_format = '#,##0.00'
                cell.alignment = right_align
            else:
                cell.alignment = left_align

            if is_zebra and cell.fill.fill_type is None:
                cell.fill = zebra_fill

            if isinstance(header, str):
                if header.startswith("Siniat "):
                    cell.fill = siniat_fill
                elif header.startswith("Knauf "):
                    cell.fill = knauf_fill
                elif header.startswith("Saint-Gobain "):
                    cell.fill = sg_fill
                elif header in ["Best Price", "Comparisons"]:
                    cell.fill = result_fill

        best_price_col = None
        for idx, header in enumerate(headers, start=1):
            if header == "Best Price":
                best_price_col = idx
                break
        if best_price_col:
            ws.cell(row=row_idx, column=best_price_col).fill = best_fill
            ws.cell(row=row_idx, column=best_price_col).font = Font(bold=True, color="166534")

    for col_idx, header in enumerate(headers, start=1):
        max_len = len(str(header)) if header is not None else 0
        for row_idx in range(1, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            val_len = len(str(val)) if val is not None else 0
            if val_len > max_len:
                max_len = val_len

        if header == "Comparisons":
            adjusted_width = 70
        elif header == "Row":
            adjusted_width = 10
        elif isinstance(header, str) and ("Price" in header or "Disc" in header):
            adjusted_width = 14
        else:
            adjusted_width = min(max(max_len + 3, 14), 38)

        ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 20
    ws.row_dimensions[3].height = 28

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Comparison Report")
        ws = writer.book["Comparison Report"]
        style_excel_worksheet(ws)

    output.seek(0)
    return output.getvalue()



# -------------------------------------------------
# COMPARISON STORAGE HELPERS
# -------------------------------------------------
def auto_comparison_name(selected_codes):
    if not selected_codes:
        return f"Comparison {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    labels = [get_company_label(code) for code in selected_codes]
    return " vs ".join(labels)


def build_source_files_map(selected_codes):
    source_files = {}
    for code in selected_codes:
        label = get_company_label(code)
        source_files[label] = st.session_state.get(f"select_{code}", "")
    return source_files


def collect_comparison_state_payload(selected_codes):
    payload = {}

    static_keys = [
        "row_ids",
        "next_row_id",
        "comparison_company_selection",
        "selected_export_fields",
    ]

    for key in static_keys:
        if key in st.session_state:
            payload[key] = st.session_state[key]

    for code in selected_codes:
        select_key = f"select_{code}"
        if select_key in st.session_state:
            payload[select_key] = st.session_state[select_key]

        carry_key = f"carry_forward_{code}"
        if carry_key in st.session_state:
            payload[carry_key] = st.session_state[carry_key]

    for row_id in st.session_state.get("row_ids", []):
        for code in selected_codes:
            product_key = f"row_{row_id}_{code}_product"
            if product_key in st.session_state:
                payload[product_key] = st.session_state[product_key]

            for j in range(1, 6):
                disc_key = f"row_{row_id}_{code}_disc_{j}"
                if disc_key in st.session_state:
                    payload[disc_key] = st.session_state[disc_key]

    return payload


def restore_comparison_state_payload(payload: dict):
    keys_to_clear = [
        key for key in list(st.session_state.keys())
        if key.startswith("row_") or key.startswith("select_") or key.startswith("carry_forward_")
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    protected_keys = {
        "current_comparison_id",
        "comparison_name_input",
        "show_saved_comparisons",
        "show_new_comparison_confirm",
        "pending_load_payload",
        "pending_loaded_comparison_id",
        "pending_loaded_comparison_name",
        "pending_clear_comparison",
    }

    for key, value in payload.items():
        if key not in protected_keys:
            st.session_state[key] = value


def clear_current_comparison_state():
    keys_to_clear = [
        key for key in list(st.session_state.keys())
        if key.startswith("row_") or key.startswith("select_") or key.startswith("carry_forward_")
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state["row_ids"] = [1]
    st.session_state["next_row_id"] = 2
    st.session_state["comparison_company_selection"] = []
    st.session_state["comparison_name_input"] = ""
    st.session_state["current_comparison_id"] = None
    st.session_state["show_saved_comparisons"] = False
    st.session_state["show_new_comparison_confirm"] = False
    st.session_state["selected_export_fields"] = [
        "Product",
        "Total Discounts",
        "Final Price",
        "Comparison %",
        "Best Price",
    ]


def load_selected_comparison_record(selected_record):
    if not selected_record:
        return False, "Could not load comparison."

    state_payload = selected_record.get("state", {}) or {}
    st.session_state["pending_load_payload"] = state_payload
    st.session_state["pending_loaded_comparison_id"] = selected_record.get("id")
    st.session_state["pending_loaded_comparison_name"] = selected_record.get("name", "")
    st.session_state["show_saved_comparisons"] = False
    return True, ""


def save_or_update_current_comparison(selected_codes):
    if not selected_codes:
        return False, "Please select companies first."

    comparison_name = st.session_state.get("comparison_name_input", "").strip()
    if not comparison_name:
        comparison_name = auto_comparison_name(selected_codes)
        st.session_state["comparison_name_input"] = comparison_name

    comparison_file = get_current_user_comparisons_file()
    current_id = st.session_state.get("current_comparison_id")

    if current_id:
        ok = update_comparison(
            comparison_file,
            comparison_id=current_id,
            owner_sub=get_current_user_id(),
            owner_email=get_current_user_email(),
            name=comparison_name,
            companies=[get_company_label(code) for code in selected_codes],
            source_files=build_source_files_map(selected_codes),
            state=collect_comparison_state_payload(selected_codes),
        )
        if ok:
            return True, "Comparison updated successfully."
        return False, "This comparison no longer exists. Save it again as new."

    comparison_id = save_new_comparison(
        comparison_file,
        owner_sub=get_current_user_id(),
        owner_email=get_current_user_email(),
        name=comparison_name,
        companies=[get_company_label(code) for code in selected_codes],
        source_files=build_source_files_map(selected_codes),
        state=collect_comparison_state_payload(selected_codes),
    )
    st.session_state["current_comparison_id"] = comparison_id
    return True, "Comparison saved successfully."


def get_previous_row_discounts(current_row_id, code):
    row_ids = st.session_state.get("row_ids", [])
    try:
        idx = row_ids.index(current_row_id)
    except ValueError:
        return [0.0] * 5

    if idx <= 0:
        return [0.0] * 5

    prev_row_id = row_ids[idx - 1]
    values = []
    for j in range(1, 6):
        try:
            values.append(float(st.session_state.get(f"row_{prev_row_id}_{code}_disc_{j}", 0.0) or 0.0))
        except Exception:
            values.append(0.0)
    return values


def row_discounts_are_blank(row_id, code):
    values = []
    for j in range(1, 6):
        disc_key = f"row_{row_id}_{code}_disc_{j}"
        raw = st.session_state.get(disc_key, None)
        if raw is None:
            values.append(None)
            continue
        try:
            values.append(float(raw))
        except Exception:
            values.append(None)
    present_values = [v for v in values if v is not None]
    if not present_values:
        return True
    return all(abs(v) < 1e-9 for v in present_values)


def ensure_discount_defaults_for_row(row_id, selected_codes):
    for code in selected_codes:
        carry_enabled = bool(st.session_state.get(f"carry_forward_{code}", False))

        # ALWAYS ensure keys exist first (critical fix)
        for j in range(1, 6):
            disc_key = f"row_{row_id}_{code}_disc_{j}"
            if disc_key not in st.session_state or st.session_state[disc_key] is None:
                st.session_state[disc_key] = 0.0

        # THEN apply carry forward only if needed
        if carry_enabled and row_id != st.session_state.row_ids[0] and row_discounts_are_blank(row_id, code):
            base_values = get_previous_row_discounts(row_id, code)
            for j, value in enumerate(base_values, start=1):
                st.session_state[f"row_{row_id}_{code}_disc_{j}"] = float(value)


def add_comparison_row(selected_codes, insert_after_row_id=None):
    new_row_id = st.session_state.next_row_id
    st.session_state.next_row_id += 1

    current_rows = list(st.session_state.get("row_ids", []))
    if insert_after_row_id is not None and insert_after_row_id in current_rows:
        insert_index = current_rows.index(insert_after_row_id) + 1
        current_rows.insert(insert_index, new_row_id)
    else:
        current_rows.append(new_row_id)

    st.session_state.row_ids = current_rows
    st.session_state["pending_focus_row_id"] = new_row_id

    for code in selected_codes:
        product_key = f"row_{new_row_id}_{code}_product"
        if product_key not in st.session_state:
            st.session_state[product_key] = ""

        carry_enabled = bool(st.session_state.get(f"carry_forward_{code}", False))
        base_values = get_previous_row_discounts(new_row_id, code) if carry_enabled else [0.0] * 5

        for j, value in enumerate(base_values, start=1):
            disc_key = f"row_{new_row_id}_{code}_disc_{j}"
            st.session_state[disc_key] = float(value)


def focus_existing_row(target_row_id):
    if target_row_id in st.session_state.get("row_ids", []):
        st.session_state["pending_focus_row_id"] = target_row_id


def execute_pending_leave_action():
    action_type = st.session_state.get("pending_action_type")
    target_view = st.session_state.get("pending_target_view")
    payload = st.session_state.get("pending_action_payload")

    st.session_state["show_leave_prompt"] = False
    st.session_state["leave_prompt_step"] = ""
    st.session_state["pending_action_type"] = None
    st.session_state["pending_target_view"] = None
    st.session_state["pending_action_payload"] = None
    st.session_state["save_as_exit_name"] = ""

    if action_type == "switch_view" and target_view:
        st.session_state["committed_view"] = target_view
    elif action_type == "logout":
        logout_current_user()
    elif action_type == "clear_comparison":
        st.session_state["show_new_comparison_confirm"] = False
        st.session_state["pending_clear_comparison"] = True
    elif action_type == "load_comparison" and payload:
        st.session_state["pending_load_payload"] = payload.get("state_payload")
        st.session_state["pending_loaded_comparison_id"] = payload.get("comparison_id")
        st.session_state["pending_loaded_comparison_name"] = payload.get("comparison_name", "")
        st.session_state["show_saved_comparisons"] = False


def render_row_navigation_buttons(current_row_id, visible_index):
    row_ids = st.session_state.get("row_ids", [])
    if not row_ids:
        return

    first_row_id = row_ids[0]
    last_row_id = row_ids[-1]
    prev_row_id = row_ids[visible_index - 1] if visible_index > 0 else None
    next_row_id = row_ids[visible_index + 1] if visible_index < len(row_ids) - 1 else None

    def make_button_html(symbol, target_row_id, disabled=False):
        disabled_attr = "disabled" if disabled or not target_row_id else ""
        onclick = ""
        if target_row_id and not disabled:
            onclick = (
                "onclick=\"(function(){"
                f"const el = window.parent.document.getElementById('row-anchor-{target_row_id}');"
                "if (el) { el.scrollIntoView({behavior: 'auto', block: 'start'}); }"
                "})()\""
            )
        return f'<button type="button" class="row-nav-btn" {disabled_attr} {onclick}>{symbol}</button>'

    nav_html = f'''
        <div class="row-nav-wrap">
            {make_button_html("⏮", first_row_id, visible_index == 0)}
            {make_button_html("◀", prev_row_id, prev_row_id is None)}
            {make_button_html("▶", next_row_id, next_row_id is None)}
            {make_button_html("⏭", last_row_id, visible_index == len(row_ids) - 1)}
        </div>
    '''
    components.html(nav_html, height=58)


def apply_specific_discount_to_all_rows(selected_codes, target_code, disc_index, disc_value):
    if target_code not in selected_codes:
        return
    try:
        disc_number = int(disc_index)
    except Exception:
        return
    if disc_number < 1 or disc_number > 5:
        return

    for row_id in st.session_state.get("row_ids", []):
        current_values = {}
        for j in range(1, 6):
            disc_key = f"row_{row_id}_{target_code}_disc_{j}"
            if disc_key in st.session_state:
                try:
                    current_values[j] = float(st.session_state.get(disc_key, 0.0) or 0.0)
                except Exception:
                    current_values[j] = 0.0
            else:
                current_values[j] = 0.0

        current_values[disc_number] = float(disc_value)

        for j in range(1, 6):
            st.session_state[f"row_{row_id}_{target_code}_disc_{j}"] = float(current_values[j])


def get_discount_widget_key(row_id, code, disc_number):
    return f"widget_row_{row_id}_{code}_disc_{disc_number}"


def sync_discount_widget_to_data(row_id, code, disc_number):
    data_key = f"row_{row_id}_{code}_disc_{disc_number}"
    widget_key = get_discount_widget_key(row_id, code, disc_number)
    try:
        st.session_state[data_key] = float(st.session_state.get(widget_key, 0.0) or 0.0)
    except Exception:
        st.session_state[data_key] = 0.0


def mirror_discount_data_to_widget(row_id, code, disc_number):
    data_key = f"row_{row_id}_{code}_disc_{disc_number}"
    widget_key = get_discount_widget_key(row_id, code, disc_number)
    try:
        value = float(st.session_state.get(data_key, 0.0) or 0.0)
    except Exception:
        value = 0.0
    st.session_state[widget_key] = value



# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "row_ids" not in st.session_state:
    st.session_state.row_ids = [1]

if "next_row_id" not in st.session_state:
    st.session_state.next_row_id = 2

if "current_comparison_id" not in st.session_state:
    st.session_state.current_comparison_id = None

if "comparison_name_input" not in st.session_state:
    st.session_state.comparison_name_input = ""

if "show_saved_comparisons" not in st.session_state:
    st.session_state.show_saved_comparisons = False

if "show_new_comparison_confirm" not in st.session_state:
    st.session_state.show_new_comparison_confirm = False

if "pending_load_payload" not in st.session_state:
    st.session_state.pending_load_payload = None

if "pending_clear_comparison" not in st.session_state:
    st.session_state.pending_clear_comparison = False

if "pending_loaded_comparison_id" not in st.session_state:
    st.session_state.pending_loaded_comparison_id = None

if "pending_loaded_comparison_name" not in st.session_state:
    st.session_state.pending_loaded_comparison_name = ""

if "selected_export_fields" not in st.session_state:
    st.session_state["selected_export_fields"] = [
        "Product",
        "Total Discounts",
        "Final Price",
        "Comparison %",
        "Best Price",
    ]

if "pending_company_delete_code" not in st.session_state:
    st.session_state["pending_company_delete_code"] = None

if "pending_company_delete_display" not in st.session_state:
    st.session_state["pending_company_delete_display"] = ""

if "pending_focus_row_id" not in st.session_state:
    st.session_state["pending_focus_row_id"] = None

if "bulk_discount_success_message" not in st.session_state:
    st.session_state["bulk_discount_success_message"] = ""

if "comparison_loaded_success_message" not in st.session_state:
    st.session_state["comparison_loaded_success_message"] = ""

if "comparison_saved_signature" not in st.session_state:
    st.session_state["comparison_saved_signature"] = ""

if "comparison_dirty" not in st.session_state:
    st.session_state["comparison_dirty"] = False

if "committed_view" not in st.session_state:
    st.session_state["committed_view"] = "Comparisons"

if "show_leave_prompt" not in st.session_state:
    st.session_state["show_leave_prompt"] = False

if "leave_prompt_step" not in st.session_state:
    st.session_state["leave_prompt_step"] = ""

if "pending_target_view" not in st.session_state:
    st.session_state["pending_target_view"] = None

if "pending_action_type" not in st.session_state:
    st.session_state["pending_action_type"] = None

if "pending_action_payload" not in st.session_state:
    st.session_state["pending_action_payload"] = None

if "save_as_exit_name" not in st.session_state:
    st.session_state["save_as_exit_name"] = ""


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
# APPLY PENDING COMPARISON LOAD BEFORE WIDGETS
# -------------------------------------------------
if st.session_state.get("pending_load_payload") is not None:
    restore_comparison_state_payload(st.session_state["pending_load_payload"])
    st.session_state["current_comparison_id"] = st.session_state.get("pending_loaded_comparison_id")
    st.session_state["comparison_name_input"] = st.session_state.get("pending_loaded_comparison_name", "")
    st.session_state["pending_load_payload"] = None
    st.session_state["pending_loaded_comparison_id"] = None
    st.session_state["pending_loaded_comparison_name"] = ""
    st.session_state["comparison_loaded_success_message"] = "Comparison loaded successfully."
    mark_comparison_clean()

if st.session_state.get("pending_clear_comparison"):
    clear_current_comparison_state()
    st.session_state["pending_clear_comparison"] = False
    mark_comparison_clean()


if not st.session_state.get("comparison_saved_signature"):
    mark_comparison_clean()

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    render_logo_if_available(FULL_LOGO_PATH, width=180)
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
    st.subheader("🧭 Navigation")

    nav_options = [
        "Company Manager",
        "Sources",
        "Comparisons",
    ]
    if is_admin_user():
        nav_options.append("Admin Panel")

    current_view_ui = st.radio(
        "Go to",
        nav_options,
        key="sidebar_navigation",
        label_visibility="collapsed",
    )

    current_view = st.session_state.get("committed_view", current_view_ui)

    if (
        current_view_ui != current_view
        and current_view == "Comparisons"
        and has_unsaved_comparison_changes()
        and not st.session_state.get("show_leave_prompt")
    ):
        st.session_state["show_leave_prompt"] = True
        st.session_state["leave_prompt_step"] = ""
        st.session_state["pending_target_view"] = current_view_ui
        st.session_state["pending_action_type"] = "switch_view"
        st.rerun()
    elif not st.session_state.get("show_leave_prompt"):
        st.session_state["committed_view"] = current_view_ui
        current_view = current_view_ui

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

    if st.button(
        "Logout",
        use_container_width=True,
        key="logout_button",
    ):
        if current_view == "Comparisons" and has_unsaved_comparison_changes():
            st.session_state["show_leave_prompt"] = True
            st.session_state["leave_prompt_step"] = ""
            st.session_state["pending_action_type"] = "logout"
            st.session_state["pending_target_view"] = None
            st.rerun()
        else:
            logout_current_user()

    if not is_admin_user():
        active_sessions_count = len(user_row.get("active_sessions", [])) if user_row else 0
        remaining_sessions = max(0, MAX_ACTIVE_SESSIONS - active_sessions_count)
        st.warning("⚠️ Please logout before closing the app to free your session.")
        st.caption(
            f"Active sessions: {active_sessions_count}/{MAX_ACTIVE_SESSIONS} • Remaining available: {remaining_sessions}"
        )


# -------------------------------------------------
# MAIN UI
# -------------------------------------------------
hero_logo_html = ""
if FULL_LOGO_PATH.exists():
    hero_logo_b64 = base64.b64encode(FULL_LOGO_PATH.read_bytes()).decode("utf-8")
    hero_logo_html = f'<div class="hero-logo-wrap"><img src="data:image/svg+xml;base64,{hero_logo_b64}" /></div>'

st.markdown(
    f"""
    <div class="app-hero">
        {hero_logo_html}
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

if st.session_state.get("show_leave_prompt"):
    comparison_label = st.session_state.get("comparison_name_input", "").strip() or "Untitled Comparison"
    action_type = st.session_state.get("pending_action_type")
    target_view = st.session_state.get("pending_target_view")
    prompt_text = f'Do you want to save the changes you made to Comparison "{comparison_label}"?'
    note_map = {
        "switch_view": f"You are leaving Comparisons and moving to {target_view}." if target_view else "",
        "logout": "You are about to logout.",
        "clear_comparison": "You are about to start a new comparison.",
        "load_comparison": "You are about to load another saved comparison.",
    }

    components.html(
        """
        <script>
        const scrollTopNow = () => {
            try {
                window.parent.scrollTo({top: 0, behavior: 'auto'});
            } catch (e) {}
        };
        requestAnimationFrame(scrollTopNow);
        setTimeout(scrollTopNow, 20);
        </script>
        """,
        height=0,
    )

    st.warning(prompt_text)
    if note_map.get(action_type):
        st.caption(note_map[action_type])

    ask_c1, ask_c2 = st.columns(2)
    with ask_c1:
        if st.button("Yes", key="leave_prompt_yes", use_container_width=True):
            st.session_state["leave_prompt_step"] = "save"
            st.rerun()
    with ask_c2:
        if st.button("No", key="leave_prompt_no", use_container_width=True):
            st.session_state["leave_prompt_step"] = ""
            mark_comparison_clean()
            execute_pending_leave_action()
            st.rerun()

    if st.session_state.get("leave_prompt_step") == "save":
        company_options_for_save = {
            f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
        }
        selected_codes_for_save = [
            company_options_for_save[x]
            for x in st.session_state.get("comparison_company_selection", [])
            if x in company_options_for_save
        ]

        if not selected_codes_for_save:
            if st.session_state.get("current_comparison_id"):
                st.info("No active comparison fields are selected right now, so there is nothing new to save. Choose No to continue leaving this section.")
            else:
                st.info("This empty untitled comparison has nothing to save yet. Choose No to continue leaving this section.")
        else:
            save_c1, save_c2 = st.columns(2)
            with save_c1:
                if st.button("Save", key="leave_prompt_save", use_container_width=True):
                    ok, msg = save_or_update_current_comparison(selected_codes_for_save)
                    if ok:
                        mark_comparison_clean()
                        execute_pending_leave_action()
                        st.rerun()
                    else:
                        st.warning(msg)
            with save_c2:
                st.text_input("New name for Save As", key="save_as_exit_name")
                if st.button("Save As", key="leave_prompt_save_as", use_container_width=True):
                    new_name = st.session_state.get("save_as_exit_name", "").strip()
                    if not new_name:
                        st.warning("Please enter a new name for Save As.")
                    else:
                        st.session_state["comparison_name_input"] = new_name
                        st.session_state["current_comparison_id"] = None
                        ok, msg = save_or_update_current_comparison(selected_codes_for_save)
                        if ok:
                            mark_comparison_clean()
                            execute_pending_leave_action()
                            st.rerun()
                        else:
                            st.warning(msg)

    st.stop()

# -------------------------------------------------
# SECTION RENDERERS
# -------------------------------------------------


def comparison_has_missing_companies(state_payload, company_options):
    selected_displays = state_payload.get("comparison_company_selection", []) if isinstance(state_payload, dict) else []
    missing = [item for item in selected_displays if item not in company_options]
    return missing


def comparisons_reference_company(comparison_file, company_code, company_name):
    records = list_comparisons(comparison_file)
    for record in records:
        companies = record.get("companies", []) or []
        source_files = record.get("source_files", {}) or {}
        state = record.get("state", {}) or {}

        if company_name in companies:
            return True

        if company_name in source_files:
            return True

        selected_displays = state.get("comparison_company_selection", []) if isinstance(state, dict) else []
        for display in selected_displays:
            if f"({company_code})" in str(display):
                return True

    return False


def render_company_manager():
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
                    st.session_state["pending_company_delete_code"] = delete_code
                    st.session_state["pending_company_delete_display"] = delete_company_display
                    st.rerun()

    pending_company_delete_code = st.session_state.get("pending_company_delete_code")
    pending_company_delete_display = st.session_state.get("pending_company_delete_display", "")

    if pending_company_delete_code:
        pending_company_name = get_company_label(pending_company_delete_code)
        comparison_file = get_current_user_comparisons_file()
        has_linked_comparisons = comparisons_reference_company(
            comparison_file,
            pending_company_delete_code,
            pending_company_name,
        )

        warning_text = (
            f"Deleting {pending_company_name} ({pending_company_delete_code}) may make saved comparisons that include this company unloadable."
        )
        if has_linked_comparisons:
            warning_text += " Some of your saved comparisons reference this company."

        st.warning(warning_text)

        confirm_c1, confirm_c2 = st.columns(2)

        with confirm_c1:
            if st.button(
                "Confirm Delete Company",
                key="confirm_delete_company_button",
                use_container_width=True,
            ):
                updated_df = companies_df[companies_df["code"] != pending_company_delete_code].copy()
                save_companies(updated_df)
                folder = get_company_folder(pending_company_delete_code)
                try:
                    folder.rmdir()
                except Exception:
                    pass

                st.session_state["pending_company_delete_code"] = None
                st.session_state["pending_company_delete_display"] = ""
                st.success(f"Company {pending_company_delete_code} was deleted.")
                st.rerun()

        with confirm_c2:
            if st.button(
                "Cancel Delete",
                key="cancel_delete_company_button",
                use_container_width=True,
            ):
                st.session_state["pending_company_delete_code"] = None
                st.session_state["pending_company_delete_display"] = ""
                st.info("Company deletion cancelled.")
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_source_library(show_title=True):
    if show_title:
        st.markdown("### 3. Source Library")

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


def render_sources():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("## Sources")

    st.markdown("### 2. Save Source")

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

    st.markdown("---")
    render_source_library(show_title=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_comparisons():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("## Comparisons")

    current_name = st.session_state.get("comparison_name_input", "").strip()
    if current_name:
        st.info(f"📊 Working on: {current_name}")

    loaded_msg = st.session_state.get("comparison_loaded_success_message", "")
    if loaded_msg:
        st.success(loaded_msg)
        st.session_state["comparison_loaded_success_message"] = ""

    company_options = {
        f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
    }

    current_selection = st.session_state.get("comparison_company_selection", [])
    missing_current_companies = [item for item in current_selection if item not in company_options]
    if missing_current_companies:
        st.warning(
            "Some previously selected companies were deleted and have been removed from the current comparison: "
            + ", ".join(missing_current_companies)
        )
        st.session_state["comparison_company_selection"] = [
            item for item in current_selection if item in company_options
        ]

    st.markdown("### 4B. Saved Comparisons")

    default_name = st.session_state.get("comparison_name_input", "").strip()
    current_selected_displays = st.session_state.get("comparison_company_selection", [])
    current_selected_codes = [company_options[x] for x in current_selected_displays if x in company_options]
    if not default_name and current_selected_codes:
        st.session_state["comparison_name_input"] = auto_comparison_name(current_selected_codes)

    st.text_input(
        "Comparison Name",
        key="comparison_name_input",
        placeholder="e.g. Siniat vs Knauf - April",
    )

    save_c1, save_c2, save_c3, save_c4, save_c5 = st.columns(5)

    with save_c1:
        if st.button("💾 Save Comparison", use_container_width=True, key="save_comparison_btn"):
            if not current_selected_codes:
                st.warning("Please select companies first.")
            else:
                comparison_name = st.session_state.get("comparison_name_input", "").strip()
                if not comparison_name:
                    comparison_name = auto_comparison_name(current_selected_codes)
                    st.session_state["comparison_name_input"] = comparison_name

                comparison_file = get_current_user_comparisons_file()
                comparison_id = save_new_comparison(
                    comparison_file,
                    owner_sub=get_current_user_id(),
                    owner_email=get_current_user_email(),
                    name=comparison_name,
                    companies=[get_company_label(code) for code in current_selected_codes],
                    source_files=build_source_files_map(current_selected_codes),
                    state=collect_comparison_state_payload(current_selected_codes),
                )

                st.session_state["current_comparison_id"] = comparison_id
                st.success("Comparison saved successfully.")
                mark_comparison_clean()

    with save_c2:
        if st.button("🔄 Save Changes", use_container_width=True, key="save_changes_btn"):
            comparison_id = st.session_state.get("current_comparison_id")

            if not comparison_id:
                st.warning("Save a comparison first.")
            elif not current_selected_codes:
                st.warning("Please select companies first.")
            else:
                comparison_name = st.session_state.get("comparison_name_input", "").strip()
                if not comparison_name:
                    comparison_name = auto_comparison_name(current_selected_codes)
                    st.session_state["comparison_name_input"] = comparison_name

                comparison_file = get_current_user_comparisons_file()
                ok = update_comparison(
                    comparison_file,
                    comparison_id=comparison_id,
                    owner_sub=get_current_user_id(),
                    owner_email=get_current_user_email(),
                    name=comparison_name,
                    companies=[get_company_label(code) for code in current_selected_codes],
                    source_files=build_source_files_map(current_selected_codes),
                    state=collect_comparison_state_payload(current_selected_codes),
                )

                if ok:
                    st.success("Comparison updated successfully.")
                    mark_comparison_clean()
                else:
                    st.warning("This comparison no longer exists. Save it again as new.")

    with save_c3:
        if st.button("🆕 Save As New", use_container_width=True, key="save_as_new_btn"):
            if not current_selected_codes:
                st.warning("Please select companies first.")
            else:
                comparison_name = st.session_state.get("comparison_name_input", "").strip()
                if not comparison_name:
                    comparison_name = auto_comparison_name(current_selected_codes)
                    st.session_state["comparison_name_input"] = comparison_name

                comparison_file = get_current_user_comparisons_file()
                comparison_id = save_new_comparison(
                    comparison_file,
                    owner_sub=get_current_user_id(),
                    owner_email=get_current_user_email(),
                    name=comparison_name,
                    companies=[get_company_label(code) for code in current_selected_codes],
                    source_files=build_source_files_map(current_selected_codes),
                    state=collect_comparison_state_payload(current_selected_codes),
                )

                st.session_state["current_comparison_id"] = comparison_id
                st.success("Saved as new comparison.")
                mark_comparison_clean()

    with save_c4:
        if st.button("📂 Load Comparison", use_container_width=True, key="toggle_load_comparison_btn"):
            st.session_state["show_saved_comparisons"] = True
            st.rerun()

    with save_c5:
        if st.button("🧹 New Comparison", use_container_width=True, key="new_comparison_btn"):
            if has_unsaved_comparison_changes():
                st.session_state["show_leave_prompt"] = True
                st.session_state["leave_prompt_step"] = ""
                st.session_state["pending_action_type"] = "clear_comparison"
                st.rerun()
            else:
                st.session_state["show_new_comparison_confirm"] = True
                st.rerun()

    if st.session_state.get("show_new_comparison_confirm"):
        st.warning("Do you want to save the current comparison before clearing it?")

        nc1, nc2, nc3 = st.columns(3)

        with nc1:
            if st.button("Save & Clear", use_container_width=True, key="save_and_clear_btn"):
                if current_selected_codes:
                    ok, msg = save_or_update_current_comparison(current_selected_codes)
                    if ok:
                        st.session_state["show_new_comparison_confirm"] = False
                        st.session_state["pending_clear_comparison"] = True
                        st.rerun()
                    else:
                        st.warning(msg)
                else:
                    st.session_state["show_new_comparison_confirm"] = False
                    st.session_state["pending_clear_comparison"] = True
                    st.rerun()

        with nc2:
            if st.button("Clear Without Saving", use_container_width=True, key="clear_without_saving_btn"):
                st.session_state["show_new_comparison_confirm"] = False
                st.session_state["pending_clear_comparison"] = True
                st.rerun()

        with nc3:
            if st.button("Cancel", use_container_width=True, key="cancel_new_comparison_btn"):
                st.session_state["show_new_comparison_confirm"] = False
                st.rerun()

    if st.session_state.get("show_saved_comparisons"):
        comparison_file = get_current_user_comparisons_file()
        saved_records = list_comparisons(comparison_file)

        if not saved_records:
            st.info("You have no saved comparisons yet.")
        else:
            saved_options = {
                build_display_label(record): record["id"]
                for record in saved_records
            }

            selected_saved_label = st.selectbox(
                "Your saved comparisons",
                [""] + list(saved_options.keys()),
                key="selected_saved_comparison_label",
            )

            if selected_saved_label:
                selected_saved_id = saved_options[selected_saved_label]
                selected_record = get_comparison(comparison_file, selected_saved_id)

                if selected_record:
                    source_line = ", ".join(
                        [
                            f"{k}: {v}"
                            for k, v in selected_record.get("source_files", {}).items()
                            if v
                        ]
                    )
                    if source_line:
                        st.caption("Source files: " + source_line)

                    load_c1, load_c2, load_c3 = st.columns([1, 2, 1])

                    with load_c1:
                        if st.button("Load Selected", use_container_width=True, key="load_selected_comparison_btn"):
                            state_payload = selected_record.get("state", {}) or {}
                            missing_companies = comparison_has_missing_companies(state_payload, company_options)

                            if missing_companies:
                                st.warning(
                                    "This comparison cannot be loaded because some companies were deleted: "
                                    + ", ".join(missing_companies)
                                )
                            else:
                                if has_unsaved_comparison_changes():
                                    st.session_state["show_leave_prompt"] = True
                                    st.session_state["leave_prompt_step"] = ""
                                    st.session_state["pending_action_type"] = "load_comparison"
                                    st.session_state["pending_action_payload"] = {
                                        "state_payload": selected_record.get("state", {}) or {},
                                        "comparison_id": selected_record.get("id"),
                                        "comparison_name": selected_record.get("name", ""),
                                    }
                                    st.rerun()
                                else:
                                    ok, msg = load_selected_comparison_record(selected_record)
                                    if ok:
                                        mark_comparison_clean()
                                        st.rerun()
                                    else:
                                        st.warning(msg)

                    with load_c2:
                        st.info("Select a saved comparison and use Load or Delete.")

                    with load_c3:
                        if st.button("🗑️ Delete", use_container_width=True, key="delete_selected_comparison_btn"):
                            ok = delete_comparison(comparison_file, selected_record.get("id"))
                            if ok:
                                if st.session_state.get("current_comparison_id") == selected_record.get("id"):
                                    st.session_state["current_comparison_id"] = None
                                st.success("Comparison deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("Could not delete comparison.")

    st.markdown("---")
    st.markdown("### 4. Select Saved Sources for Comparison")

    selected_company_displays = st.multiselect(
        "Select up to 5 companies to compare",
        options=list(company_options.keys()),
        max_selections=5,
        key="comparison_company_selection",
    )

    selected_codes = [company_options[x] for x in selected_company_displays if x in company_options]

    if not selected_codes:
        st.info("Please select at least 1 company for comparison.")

    selected = {}
    catalogs = {}

    if selected_codes:
        source_cols_per_row = 2 if len(selected_codes) >= 4 else len(selected_codes)

        for start_idx in range(0, len(selected_codes), source_cols_per_row):
            chunk = selected_codes[start_idx:start_idx + source_cols_per_row]
            cols = st.columns(len(chunk))

            for i, code in enumerate(chunk):
                with cols[i]:
                    files = get_company_files(code)
                    selected[code] = st.selectbox(
                        f"{code} source file",
                        [""] + files,
                        key=f"select_{code}",
                        on_change=mark_comparison_dirty,
                    )

        for code in selected_codes:
            if selected.get(code):
                source_path = get_company_folder(code) / selected[code]
                try:
                    catalogs[code] = load_prepared_catalog_from_file(str(source_path), source_path.stat().st_mtime)
                except Exception as e:
                    st.error(f"Error loading file: {e}")
                    catalogs[code] = None
            else:
                catalogs[code] = None


    if selected_codes:
        st.markdown("---")
        st.markdown("### Apply Specific Discount to All Products")
        st.caption(
            "Choose one discount slot and one value for each company. It will be applied to all current rows of that company only."
        )

        bulk_cols_per_row = 2 if len(selected_codes) >= 4 else len(selected_codes)
        for start_idx in range(0, len(selected_codes), bulk_cols_per_row):
            chunk = selected_codes[start_idx:start_idx + bulk_cols_per_row]
            bulk_cols = st.columns(len(chunk))

            for i, code in enumerate(chunk):
                with bulk_cols[i]:
                    label = get_company_label(code)

                    selector_key = f"bulk_discount_slot_{code}"
                    value_key = f"bulk_discount_value_{code}"

                    if selector_key not in st.session_state:
                        st.session_state[selector_key] = "Disc1"
                    if value_key not in st.session_state:
                        st.session_state[value_key] = 0.0

                    st.markdown(f"**{label}**")
                    st.selectbox(
                        f"{label} discount slot",
                        ["Disc1", "Disc2", "Disc3", "Disc4", "Disc5"],
                        key=selector_key,
                    )
                    st.number_input(
                        f"{label} discount value %",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        key=value_key,
                    )

                    if st.button(
                        f"Apply to all {label} rows",
                        key=f"apply_bulk_discount_{code}",
                        use_container_width=True,
                    ):
                        disc_index = int(str(st.session_state[selector_key]).replace("Disc", ""))
                        disc_value = float(st.session_state[value_key])
                        apply_specific_discount_to_all_rows(selected_codes, code, disc_index, disc_value)
                        mark_comparison_dirty()
                        st.session_state["bulk_discount_success_message"] = (
                            f"{label}: {st.session_state[selector_key]} set to {disc_value:.2f}% for all current rows."
                        )
                        st.rerun()

        success_message = st.session_state.get("bulk_discount_success_message", "")
        if success_message:
            st.success(success_message)
            st.session_state["bulk_discount_success_message"] = ""

    if selected_codes:
        st.markdown("---")
        st.markdown("### Carry Discounts Forward")
        st.caption(
            "When enabled, each new row starts with the previous row's discounts for that company. If a row is still blank, turning this on will also prefill it. You can still edit any discount normally."
        )
        carry_cols_per_row = 2 if len(selected_codes) >= 4 else len(selected_codes)
        for start_idx in range(0, len(selected_codes), carry_cols_per_row):
            chunk = selected_codes[start_idx:start_idx + carry_cols_per_row]
            carry_cols = st.columns(len(chunk))
            for i, code in enumerate(chunk):
                with carry_cols[i]:
                    label = get_company_label(code)
                    st.checkbox(
                        f"{label}: use previous row discounts",
                        key=f"carry_forward_{code}",
                        on_change=mark_comparison_dirty,
                    )

    st.markdown("---")
    st.markdown("### 6. Multi-Line Comparison")

    if not selected_codes:
        st.info("Select companies first to start comparison.")
    else:
        st.info(f"Current rows: {len(st.session_state.row_ids)}")

        for visible_index, row_id in enumerate(st.session_state.row_ids):
            ensure_discount_defaults_for_row(row_id, selected_codes)
            st.markdown(f'<div id="row-anchor-{row_id}"></div>', unsafe_allow_html=True)
            st.markdown(f"#### Row {visible_index + 1}")

            row_final_prices = {}
            comparison_cols_per_row = 2 if len(selected_codes) >= 4 else len(selected_codes)

            for start_idx in range(0, len(selected_codes), comparison_cols_per_row):
                chunk = selected_codes[start_idx:start_idx + comparison_cols_per_row]
                row_cols = st.columns(len(chunk))

                for col_idx, code in enumerate(chunk):
                    with row_cols[col_idx]:
                        label = get_company_label(code)

                        st.write(f"**{label}**")

                        df = catalogs.get(code)
                        if df is not None and not df.empty:
                            options = [""] + df["DISPLAY"].tolist()
                            selected_product = st.selectbox(
                                f"{label} product",
                                options,
                                key=f"row_{row_id}_{code}_product",
                                on_change=mark_comparison_dirty,
                            )
                            row = get_catalog_row(df, selected_product)

                            if row is not None:
                                st.write("SAP:", row["SAP"])
                                st.write("MM:", row["MM"])
                                st.write("Package:", row["Package"])
                                st.write("Base Price:", round(float(row["Price"]), 2))

                                discs = []
                                for j in range(1, 6):
                                    data_key = f"row_{row_id}_{code}_disc_{j}"
                                    widget_key = get_discount_widget_key(row_id, code, j)
                                    mirror_discount_data_to_widget(row_id, code, j)
                                    disc_val = st.number_input(
                                        f"{label} Disc {j}",
                                        min_value=0.0,
                                        max_value=100.0,
                                        step=0.1,
                                        key=widget_key,
                                        on_change=lambda r=row_id, c=code, d=j: (sync_discount_widget_to_data(r, c, d), mark_comparison_dirty()),
                                    )
                                    st.session_state[data_key] = float(disc_val)
                                    discs.append(disc_val)

                                final = apply_discounts(row["Price"], discs)
                                row_final_prices[code] = final
                                st.success(f"Final Price: {final}")
                            else:
                                for j in range(1, 6):
                                    widget_key = get_discount_widget_key(row_id, code, j)
                                    mirror_discount_data_to_widget(row_id, code, j)
                                    disc_val = st.number_input(
                                        f"{label} Disc {j}",
                                        min_value=0.0,
                                        max_value=100.0,
                                        step=0.1,
                                        key=widget_key,
                                        on_change=lambda r=row_id, c=code, d=j: (sync_discount_widget_to_data(r, c, d), mark_comparison_dirty()),
                                    )
                                    st.session_state[f"row_{row_id}_{code}_disc_{j}"] = float(disc_val)
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

                action_cols = st.columns([3.2, 1.2, 1.2])

                with action_cols[0]:
                    st.metric(f"Row {visible_index + 1} Best Price", best_label)

                with action_cols[1]:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Add Row Below",
                        key=f"add_row_after_{row_id}",
                        use_container_width=True,
                    ):
                        add_comparison_row(selected_codes, insert_after_row_id=row_id)
                        mark_comparison_dirty()
                        st.rerun()

                    render_row_navigation_buttons(row_id, visible_index)

                with action_cols[2]:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Delete This Row",
                        key=f"delete_row_{row_id}",
                        use_container_width=True,
                    ):
                        st.session_state.row_ids = [
                            r for r in st.session_state.row_ids if r != row_id
                        ]
                        mark_comparison_dirty()
                        st.rerun()

                save_complete_left, save_complete_mid, save_complete_right = st.columns([3.2, 1.2, 1.2])

                with save_complete_right:
                    if st.button(
                        "Save and Complete",
                        key=f"save_complete_{row_id}",
                        use_container_width=True,
                    ):
                        ok, msg = save_or_update_current_comparison(selected_codes)
                        if ok:
                            st.success("Comparison saved successfully.")
                            mark_comparison_clean()
                        else:
                            st.warning(msg)

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

    target_row_id = st.session_state.get("pending_focus_row_id")
    if target_row_id is not None:
        components.html(
            f"""
            <script>
            const scrollToNewRow = () => {{
                const el = window.parent.document.getElementById("row-anchor-{target_row_id}");
                if (el) {{
                    el.scrollIntoView({{behavior: "smooth", block: "start"}});
                }}
            }};
            requestAnimationFrame(scrollToNewRow);
            setTimeout(scrollToNewRow, 60);
            </script>
            """,
            height=0,
        )
        st.session_state["pending_focus_row_id"] = None

    render_export_inside_comparisons(catalogs, selected_codes)
    st.markdown("</div>", unsafe_allow_html=True)

def render_export_inside_comparisons(catalogs, selected_codes):
    st.markdown("---")
    st.markdown("### 7. Export Excel Report")

    full_export_df = build_export_dataframe(
        st.session_state.row_ids, catalogs, selected_codes
    )

    selected_export_fields = st.multiselect(
        "Choose columns for Excel export",
        options=EXPORT_FIELD_OPTIONS,
        key="selected_export_fields",
    )

    if not selected_export_fields:
        st.warning("Please select at least one export field.")
        return

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


def render_admin_panel():
    if not is_admin_user():
        return

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

        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

        with c1:
            if st.button(
                "Unblock User", key="unblock_user_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    set_user_status(
                        row.get("email", ""),
                        row.get("sub", ""),
                        "approved",
                    )
                    st.success(f"User restored: {row.get('email', '')}")
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
                "Reset to Trial", key="reset_to_trial_button", use_container_width=True
            ):
                if selected_user_label:
                    row = user_options[selected_user_label]
                    reset_user_to_trial(
                        row.get("email", ""),
                        row.get("sub", ""),
                    )
                    st.success(f"Trial reset for: {row.get('email', '')}")
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

        with c8:
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


# -------------------------------------------------
# RENDER CURRENT VIEW
# -------------------------------------------------
if current_view == "Company Manager":
    render_company_manager()
elif current_view == "Sources":
    render_sources()
elif current_view == "Comparisons":
    render_comparisons()
elif current_view == "Admin Panel":
    render_admin_panel()