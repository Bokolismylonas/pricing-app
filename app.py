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

st.markdown(
    """
    <meta name="description" content="Upload supplier data, compare products and export polished Excel reports instantly with Pricing Tool.">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="https://www.pricingtool.gr/">
    """,
    unsafe_allow_html=True,

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

    .save-panel-card {
        padding: 16px 18px;
        border-radius: 16px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        margin-top: 10px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,


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


# -------------------------------------------------
# SUPABASE
# -------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],


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
    prefixes = ("row_", "select_", "carry_forward_")
    direct_keys = {
        "row_ids",
        "next_row_id",
        "comparison_company_selection",
        "comparison_name_input",
        "current_comparison_id",
        "selected_export_fields",
    }
    excluded_keys = {
        "sidebar_navigation",
        "comparison_dirty",
        "comparison_saved_signature",
        "comparison_last_active_view",
        "show_leave_comparison_prompt",
        "pending_leave_target_view",
        "save_as_exit_name",
        "active_comparison_label",
        "leave_prompt_step",
        "pending_focus_row_id",
        "bulk_discount_success_message",
        "comparison_loaded_success_message",
        "pending_load_payload",
        "pending_loaded_comparison_id",
        "pending_loaded_comparison_name",
        "pending_clear_comparison",
        "checkout_email",
        "checkout_url",
        "checkout_created_at",
        "app_session_id",
    }

    for key in list(st.session_state.keys()):
        if key in excluded_keys:
            continue
        if key in direct_keys or key.startswith(prefixes):
            try:
                value = st.session_state.get(key)
                if isinstance(value, Path):
                    value = str(value)
                relevant[key] = value
            except Exception:
                pass

    return json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)



def get_current_selected_codes_from_state():
    company_options_for_state = {
        f"{row['name']} ({row['code']})": row["code"] for _, row in companies_df.iterrows()
    }

    selected_codes = [
        company_options_for_state[x]
        for x in st.session_state.get("comparison_company_selection", [])
        if x in company_options_for_state
    ]

    if selected_codes:
        return selected_codes

    known_codes = set(companies_df["code"].astype(str).tolist())
    inferred_codes = []

    for code in known_codes:
        has_select_key = f"select_{code}" in st.session_state
        has_carry_key = f"carry_forward_{code}" in st.session_state
        has_row_key = any(
            key.startswith("row_") and f"_{code}_" in key
            for key in st.session_state.keys()

        if has_select_key or has_carry_key or has_row_key:
            inferred_codes.append(code)

    return inferred_codes


def get_comparison_payload_signature_from_state():
    selected_displays = list(st.session_state.get("comparison_company_selection", []))
    selected_codes = get_current_selected_codes_from_state()
    row_ids = list(st.session_state.get("row_ids", []))

    stable_payload = {
        "row_ids": row_ids,
        "comparison_company_selection": selected_displays,
        "comparison_name_input": st.session_state.get("comparison_name_input", ""),
        "current_comparison_id": st.session_state.get("current_comparison_id"),
        "selected_export_fields": list(st.session_state.get("selected_export_fields", [])),
    }

    for code in selected_codes:
        stable_payload[f"select_{code}"] = st.session_state.get(f"select_{code}", "")
        stable_payload[f"carry_forward_{code}"] = bool(st.session_state.get(f"carry_forward_{code}", False))

    for row_id in row_ids:
        for code in selected_codes:
            stable_payload[f"row_{row_id}_{code}_product"] = st.session_state.get(
                f"row_{row_id}_{code}_product", ""
            for j in range(1, 6):
                disc_key = f"row_{row_id}_{code}_disc_{j}"
                try:
                    stable_payload[disc_key] = float(st.session_state.get(disc_key, 0.0) or 0.0)
                except Exception:
                    stable_payload[disc_key] = 0.0

    return json.dumps(stable_payload, sort_keys=True, ensure_ascii=False, default=str)


def mark_comparison_clean():
    st.session_state["comparison_saved_signature"] = get_comparison_state_signature()
    st.session_state["comparison_baseline_state_json"] = get_comparison_payload_signature_from_state()
    st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
    st.session_state["comparison_dirty"] = False
    st.session_state["comparison_user_modified"] = False


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


def refresh_comparison_dirty_state():
    if not comparison_has_meaningful_content():
        st.session_state["comparison_dirty"] = False
        return

    baseline = st.session_state.get("comparison_baseline_state_json", "")
    if not baseline:
        st.session_state["comparison_dirty"] = False
        return

    current = get_comparison_payload_signature_from_state()
    st.session_state["comparison_dirty"] = (current != baseline)


def has_real_changes_against_loaded_baseline():
    return bool(
        st.session_state.get("comparison_user_modified", False)
        and comparison_has_meaningful_content()


def has_unsaved_comparison_changes():
    return bool(
        st.session_state.get("comparison_user_modified", False)
        and comparison_has_meaningful_content()


def mark_comparison_dirty():
    if not comparison_has_meaningful_content():
        st.session_state["comparison_dirty"] = False
        st.session_state["comparison_user_modified"] = False
        return
    st.session_state["comparison_edit_generation"] = st.session_state.get("comparison_edit_generation", 0) + 1
    st.session_state["comparison_dirty"] = True
    st.session_state["comparison_user_modified"] = True


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

    if rows:
        return (
            pd.DataFrame(rows)
            .sort_values("Modified", ascending=False)
            .reset_index(drop=True)

    return pd.DataFrame(
        columns=[
            "Company Code",
            "Company Name",
            "Filename",
            "Folder",
            "Full Path",
            "Modified",
        ]


def company_has_files(code):
    folder = get_company_folder(code)
    for f in folder.glob("*.*"):
        if f.suffix.lower() in [".xlsx", ".xlsm"]:
            return True
    return False


def load_data(file):
    try:
        df = pd.read_excel(file, sheet_name="PRICELIST", engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None



def load_excel_file_any(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    attempts = [
        ("openpyxl", io.BytesIO(file_bytes)),
    ]

    last_error = None
    for engine, buffer in attempts:
        try:
            return pd.ExcelFile(buffer, engine=engine), file_bytes
        except Exception as e:
            last_error = e

    try:
        import xlrd  # noqa: F401
        try:
            return pd.ExcelFile(io.BytesIO(file_bytes), engine="xlrd"), file_bytes
        except Exception as e:
            last_error = e
    except Exception:
        pass

    raise ValueError(
        "The uploaded file could not be read as a valid Excel workbook. "
        "If it was saved as .xls or exported with the wrong extension, please re-save it as a real .xlsx file and upload it again."
    ) from last_error


def read_excel_any(file_bytes, sheet_name, header=None):
    try:
        return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header, engine="openpyxl")
    except Exception as first_error:
        try:
            import xlrd  # noqa: F401
            return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header, engine="xlrd")
        except Exception:
            raise ValueError(
                "This workbook is not a standard .xlsx file that can be opened safely. "
                "Please open it in Excel and use Save As -> Excel Workbook (.xlsx), then upload it again."
            ) from first_error


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



def get_row_summary_text(row_id, selected_codes, catalogs):
    parts = []
    for code in selected_codes:
        selected_product = str(st.session_state.get(f"row_{row_id}_{code}_product", "") or "").strip()
        if selected_product:
            row = get_catalog_row(catalogs.get(code), selected_product)
            if row is not None:
                parts.append(f"{get_company_label(code)}: {row['Product']}")
            else:
                parts.append(f"{get_company_label(code)}: selected")
    if parts:
        summary = " | ".join(parts[:2])
        if len(parts) > 2:
            summary += f" +{len(parts)-2} more"
        return summary
    return "Empty row"

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


def collect_merged_comparison_state_payload(selected_codes):
    payload = dict(st.session_state.get("active_loaded_state_payload", {}) or {})
    current_payload = collect_comparison_state_payload(selected_codes)
    payload.update(current_payload)

    # remove stale row keys for rows that no longer exist in current state
    current_row_ids = set(current_payload.get("row_ids", st.session_state.get("row_ids", [])))
    keys_to_remove = []
    for key in payload.keys():
        if key.startswith("row_"):
            parts = key.split("_")
            if len(parts) >= 2:
                try:
                    row_id = int(parts[1])
                    if row_id not in current_row_ids:
                        keys_to_remove.append(key)
                except Exception:
                    pass
    for key in keys_to_remove:
        payload.pop(key, None)

    return payload


def restore_comparison_state_payload(payload: dict):
    keys_to_clear = [
        key for key in list(st.session_state.keys())
        if key.startswith("row_") or key.startswith("select_") or key.startswith("carry_forward_") or key.startswith("widget_row_")
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
        if key.startswith("row_") or key.startswith("select_") or key.startswith("carry_forward_") or key.startswith("widget_row_")
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state["row_ids"] = [1]
    st.session_state["active_row_id"] = None
    st.session_state["next_row_id"] = 2
    st.session_state["comparison_company_selection"] = []
    st.session_state["comparison_name_input"] = ""
    st.session_state["pending_comparison_name_input"] = None
    st.session_state["active_comparison_label"] = ""
    st.session_state["active_loaded_state_payload"] = {}
    st.session_state["comparison_loaded_from_record"] = False
    st.session_state["comparison_baseline_state_json"] = ""
    st.session_state["comparison_dirty"] = False
    st.session_state["comparison_user_modified"] = False
    st.session_state["comparison_edit_generation"] = 0
    st.session_state["comparison_clean_generation"] = 0
    st.session_state["current_comparison_id"] = None
    st.session_state["show_saved_comparisons"] = False
    st.session_state["show_new_comparison_confirm"] = False
    st.session_state["comparison_mode"] = "menu"
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
    st.session_state["active_loaded_state_payload"] = dict(state_payload)
    st.session_state["pending_load_payload"] = state_payload
    st.session_state["pending_loaded_comparison_id"] = selected_record.get("id")
    st.session_state["pending_loaded_comparison_name"] = selected_record.get("name", "")
    st.session_state["active_comparison_label"] = selected_record.get("name", "")
    st.session_state["comparison_loaded_from_record"] = True
    st.session_state["comparison_mode"] = "edit"
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
    st.session_state["current_comparison_id"] = comparison_id
    return True, "Comparison saved successfully."


def save_current_comparison_from_state(force_new: bool = False, override_name: str | None = None):
    selected_codes = get_current_selected_codes_from_state()

    for row_id in st.session_state.get("row_ids", []):
        for code in selected_codes:
            sync_product_widget_to_data(row_id, code)
            for disc_number in range(1, 6):
                sync_discount_widget_to_data(row_id, code, disc_number)
    if not selected_codes:
        return False, "Please select companies first."

    comparison_name = (override_name or st.session_state.get("comparison_name_input", "")).strip()
    if not comparison_name:
        comparison_name = auto_comparison_name(selected_codes)

    comparison_file = get_current_user_comparisons_file()
    current_id = None if force_new else st.session_state.get("current_comparison_id")
    payload_state = (
        collect_merged_comparison_state_payload(selected_codes)
        if st.session_state.get("comparison_loaded_from_record") or st.session_state.get("active_loaded_state_payload")
        else collect_comparison_state_payload(selected_codes)
    payload_companies = [get_company_label(code) for code in selected_codes]
    payload_sources = build_source_files_map(selected_codes)

    if current_id:
        ok = update_comparison(
            comparison_file,
            comparison_id=current_id,
            owner_sub=get_current_user_id(),
            owner_email=get_current_user_email(),
            name=comparison_name,
            companies=payload_companies,
            source_files=payload_sources,
            state=payload_state,
        if ok:
            st.session_state["pending_comparison_name_input"] = comparison_name
            st.session_state["active_comparison_label"] = comparison_name
            st.session_state["active_loaded_state_payload"] = dict(payload_state)
            st.session_state["comparison_loaded_from_record"] = True
            st.session_state["comparison_dirty"] = False
            st.session_state["comparison_user_modified"] = False
            st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
            return True, "Comparison updated successfully."
        return False, "This comparison no longer exists. Save it again as new."

    comparison_id = save_new_comparison(
        comparison_file,
        owner_sub=get_current_user_id(),
        owner_email=get_current_user_email(),
        name=comparison_name,
        companies=payload_companies,
        source_files=payload_sources,
        state=payload_state,
    st.session_state["current_comparison_id"] = comparison_id
    st.session_state["pending_comparison_name_input"] = comparison_name
    st.session_state["active_comparison_label"] = comparison_name
    st.session_state["active_loaded_state_payload"] = dict(payload_state)
    st.session_state["comparison_loaded_from_record"] = True
    st.session_state["comparison_dirty"] = False
    st.session_state["comparison_user_modified"] = False
    st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
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
    st.session_state["active_row_id"] = new_row_id

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
        st.session_state["active_row_id"] = target_row_id


def execute_pending_leave_action():
    action_type = st.session_state.get("pending_action_type")
    target_view = st.session_state.get("pending_target_view")
    payload = st.session_state.get("pending_action_payload")

    st.session_state["show_leave_prompt"] = False
    st.session_state["leave_prompt_step"] = ""
    st.session_state["pending_action_type"] = None
    st.session_state["pending_target_view"] = None
    st.session_state["pending_action_payload"] = None
    st.session_state["pending_save_as_exit_name"] = ""

    if action_type == "switch_view" and target_view:
        st.session_state["committed_view"] = target_view
        if target_view == "Comparisons":
            st.session_state["comparison_mode"] = "menu"
            st.session_state["show_saved_comparisons"] = False
            st.session_state["show_inline_save_options"] = False
            st.session_state["inline_save_mode"] = "menu"
            st.session_state["active_save_row_id"] = None
            st.session_state["pending_inline_save_as_name"] = ""
            st.session_state["pending_save_as_exit_name"] = ""
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

    def make_btn(symbol, target, disabled=False):
        if disabled or not target:
            return f'<span style="font-size:30px;opacity:0.3;margin:6px;">{symbol}</span>'
        return f'<a href="#row-anchor-{target}" style="font-size:30px;margin:6px;text-decoration:none;">{symbol}</a>'

    nav_html = f"""
    <div style="display:flex;gap:12px;align-items:center;">
        {make_btn("⏮", first_row_id, visible_index==0)}
        {make_btn("◀", prev_row_id, prev_row_id is None)}
        {make_btn("▶", next_row_id, next_row_id is None)}
        {make_btn("⏭", last_row_id, visible_index==len(row_ids)-1)}
    </div>
    """
    st.markdown(nav_html, unsafe_allow_html=True)


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
    if widget_key not in st.session_state:
        return
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


def get_product_widget_key(row_id, code):
    return f"widget_row_{row_id}_{code}_product"


def sync_product_widget_to_data(row_id, code):
    data_key = f"row_{row_id}_{code}_product"
    widget_key = get_product_widget_key(row_id, code)
    if widget_key not in st.session_state:
        return
    st.session_state[data_key] = st.session_state.get(widget_key, "")


def mirror_product_data_to_widget(row_id, code):
    data_key = f"row_{row_id}_{code}_product"
    widget_key = get_product_widget_key(row_id, code)
    data_value = st.session_state.get(data_key, "")
    if st.session_state.get(widget_key) != data_value:
        st.session_state[widget_key] = data_value



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

if "pending_comparison_name_input" not in st.session_state:
    st.session_state["pending_comparison_name_input"] = None

if "post_save_success_message" not in st.session_state:
    st.session_state["post_save_success_message"] = ""

if "show_saved_comparisons" not in st.session_state:
    st.session_state.show_saved_comparisons = False

if "show_new_comparison_confirm" not in st.session_state:
    st.session_state.show_new_comparison_confirm = False

if "pending_load_payload" not in st.session_state:
    st.session_state.pending_load_payload = None

if "pending_clear_comparison" not in st.session_state:
    st.session_state.pending_clear_comparison = False

if "show_export_preview" not in st.session_state:
    st.session_state["show_export_preview"] = False

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

if "active_row_id" not in st.session_state:
    st.session_state["active_row_id"] = None

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

if "pending_save_as_exit_name" not in st.session_state:
    st.session_state["pending_save_as_exit_name"] = None

if "active_comparison_label" not in st.session_state:
    st.session_state["active_comparison_label"] = ""

if "active_loaded_state_payload" not in st.session_state:
    st.session_state["active_loaded_state_payload"] = {}

if "comparison_edit_generation" not in st.session_state:
    st.session_state["comparison_edit_generation"] = 0

if "comparison_clean_generation" not in st.session_state:
    st.session_state["comparison_clean_generation"] = 0

if "comparison_user_modified" not in st.session_state:
    st.session_state["comparison_user_modified"] = False

if "comparison_mode" not in st.session_state:
    st.session_state["comparison_mode"] = "menu"

if "show_inline_save_options" not in st.session_state:
    st.session_state["show_inline_save_options"] = False

if "inline_save_mode" not in st.session_state:
    st.session_state["inline_save_mode"] = "menu"

if "inline_save_as_name" not in st.session_state:
    st.session_state["inline_save_as_name"] = ""

if "pending_inline_save_as_name" not in st.session_state:
    st.session_state["pending_inline_save_as_name"] = None

if "comparison_baseline_state_json" not in st.session_state:
    st.session_state["comparison_baseline_state_json"] = ""

if "comparison_loaded_from_record" not in st.session_state:
    st.session_state["comparison_loaded_from_record"] = False

if "skip_export_preview_once" not in st.session_state:
    st.session_state["skip_export_preview_once"] = False


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

    c1, c2, c3 = st.columns([1, 1.6, 1])
    with c2:
        st.warning(
            f"{company.get('name', 'This company')} is using all seats ({format_company_seats(company)})."
        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="company_full_logout",
    st.stop()

if current_user_is_blocked():
    st.error("Access denied. Your account has been blocked.")
    st.button(
        "Logout",
        on_click=logout_current_user,
        use_container_width=True,
        key="blocked_logout",
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
        st.button(
            "Logout",
            on_click=logout_current_user,
            use_container_width=True,
            key="device_limit_logout",
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
    st.stop()


# -------------------------------------------------
# APPLY PENDING COMPARISON LOAD BEFORE WIDGETS
# -------------------------------------------------
if st.session_state.get("pending_load_payload") is not None:
    restore_comparison_state_payload(st.session_state["pending_load_payload"])
    if "selected_export_fields" not in st.session_state or not st.session_state.get("selected_export_fields"):
        st.session_state["selected_export_fields"] = [
            "Product",
            "Total Discounts",
            "Final Price",
            "Comparison %",
            "Best Price",
        ]
    st.session_state["current_comparison_id"] = st.session_state.get("pending_loaded_comparison_id")
    st.session_state["comparison_name_input"] = st.session_state.get("pending_loaded_comparison_name", "")
    st.session_state["active_comparison_label"] = st.session_state.get("pending_loaded_comparison_name", "")
    st.session_state["comparison_loaded_from_record"] = True
    st.session_state["pending_load_payload"] = None
    st.session_state["pending_loaded_comparison_id"] = None
    st.session_state["pending_loaded_comparison_name"] = ""
    st.session_state["comparison_loaded_success_message"] = "Comparison loaded successfully."
    st.session_state["active_row_id"] = None
    st.session_state["comparison_mode"] = "edit"
    st.session_state["comparison_dirty"] = False
    st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
    st.session_state["active_loaded_state_payload"] = collect_comparison_state_payload(get_current_selected_codes_from_state())
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

    nav_buttons = ["Company Manager", "Sources", "Comparisons"]
    if is_admin_user():
        nav_buttons.append("Admin Panel")

    current_view = st.session_state.get("committed_view", "Comparisons")

    for nav_label in nav_buttons:
        button_label = f"• {nav_label}" if current_view == nav_label else nav_label
        if st.button(button_label, use_container_width=True, key=f"sidebar_nav_btn_{nav_label}"):
            current_view_ui = nav_label

            if current_view_ui == "Comparisons" and current_view == "Comparisons":
                if has_unsaved_comparison_changes() and not st.session_state.get("show_leave_prompt"):
                    st.session_state["show_leave_prompt"] = True
                    st.session_state["leave_prompt_step"] = ""
                    st.session_state["pending_target_view"] = "Comparisons"
                    st.session_state["pending_action_type"] = "switch_view"
                    st.rerun()
                else:
                    st.session_state["committed_view"] = "Comparisons"
                    st.session_state["comparison_mode"] = "menu"
                    st.session_state["show_saved_comparisons"] = False
                    st.session_state["show_inline_save_options"] = False
                    st.session_state["inline_save_mode"] = "menu"
                    st.session_state["active_save_row_id"] = None
                    st.session_state["pending_inline_save_as_name"] = ""
                    st.session_state["pending_save_as_exit_name"] = ""
                    st.rerun()

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
            else:
                previous_committed_view = st.session_state.get("committed_view", current_view_ui)
                st.session_state["committed_view"] = current_view_ui
                if current_view_ui == "Comparisons" and previous_committed_view != "Comparisons":
                    st.session_state["comparison_mode"] = "menu"
                    st.session_state["show_saved_comparisons"] = False
                    st.session_state["show_inline_save_options"] = False
                    st.session_state["inline_save_mode"] = "menu"
                    st.session_state["active_save_row_id"] = None
                    st.session_state["pending_inline_save_as_name"] = ""
                    st.session_state["pending_save_as_exit_name"] = ""
                st.rerun()

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

if st.query_params.get("payment") == "success":
    st.success("Payment completed successfully. Refreshing access may take a few seconds.")
elif st.query_params.get("payment") == "cancel":
    st.info("Checkout was cancelled.")

if st.session_state.get("show_leave_prompt"):
    comparison_label = st.session_state.get("active_comparison_label", "").strip() or st.session_state.get("comparison_name_input", "").strip() or "Untitled Comparison"
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
            st.session_state["comparison_dirty"] = False
            st.session_state["comparison_user_modified"] = False
            st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
            execute_pending_leave_action()
            st.rerun()

    if st.session_state.get("leave_prompt_step") == "save":
        selected_codes_for_save = get_current_selected_codes_from_state()

        if not selected_codes_for_save:
            if st.session_state.get("current_comparison_id"):
                st.info("This saved comparison has no new unsaved changes right now. Use No to continue to the next section.")
            else:
                st.info("This empty untitled comparison has nothing to save yet. Use No to continue to the next section.")
        else:
            save_c1, save_c2 = st.columns(2)
            with save_c1:
                if st.button("Save", key="leave_prompt_save", use_container_width=True):
                    ok, msg = save_current_comparison_from_state(force_new=False)
                    if ok:
                        st.session_state["comparison_dirty"] = False
                        st.session_state["comparison_user_modified"] = False
                        st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
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
                        ok, msg = save_current_comparison_from_state(force_new=True, override_name=new_name)
                        if ok:
                            st.session_state["comparison_dirty"] = False
                            st.session_state["comparison_user_modified"] = False
                            st.session_state["comparison_clean_generation"] = st.session_state.get("comparison_edit_generation", 0)
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
    with add_c2:
        new_name = st.text_input(
            "Name", key="new_company_name", placeholder="Technogips"
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

        warning_text = (
            f"Deleting {pending_company_name} ({pending_company_delete_code}) may make saved comparisons that include this company unloadable."
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




def _source_generator_output_columns():
    return ["SAP", "Product", "Base Price", "Increase %", "Price", "MM", "Package", "Category"]


def _detect_supplier_header_row(raw_df: pd.DataFrame) -> int:
    max_scan = min(len(raw_df), 25)
    best_row = 0
    best_score = -1

    code_tokens = ["sap", "code", "item code", "item no", "article", "article no", "sku", "reference", "ref", "material", "κωδικ", "κωδ"]
    product_tokens = ["description", "product", "name", "item", "material description", "περιγραφ", "προϊ", "προιο", "όνομα", "ονομα"]
    price_tokens = ["price", "list", "net price", "catalog", "unit price", "τιμή", "τιμο", "value", "αξία", "€/"]
    unit_tokens = ["unit", "uom", "mm", "μον", "μ.μ", "μ/μ"]
    package_tokens = ["pack", "package", "packing", "minimum", "pallet", "box", "συσκ"]

    for idx in range(max_scan):
        values = [str(v).strip().lower() for v in raw_df.iloc[idx].tolist() if str(v).strip() not in ["", "nan", "none"]]
        score = 0
        if any(any(token in v for token in code_tokens) for v in values):
            score += 2
        if any(any(token in v for token in product_tokens) for v in values):
            score += 3
        if any(any(token in v for token in price_tokens) for v in values):
            score += 4
        if any(any(token in v for token in unit_tokens) for v in values):
            score += 1
        if any(any(token in v for token in package_tokens) for v in values):
            score += 1
        if len(values) >= 3:
            score += 0.5
        if score > best_score:
            best_score = score
            best_row = idx

    return best_row


def _normalize_supplier_column_name(col_name: str) -> str:
    c = str(col_name).strip().lower()

    if any(token in c for token in [
        "sap", "item code", "item no", "product code", "article", "article no", "sku",
        "reference", "ref", "material code", "material no", "κωδικ", "κωδ.", "κωδ", "code"
    ]):
        return "SAP"
    if any(token in c for token in [
        "description", "product", "item description", "product description", "name",
        "material description", "material", "περιγραφ", "προϊ", "προιο", "όνομα", "ονομα"
    ]):
        return "Product"
    if any(token in c for token in ["increase %", "increase", "diff%", "markup", "adjustment %", "delta %", "ανατ", "αύξη", "αυξη"]):
        return "Increase %"
    if any(token in c for token in [
        "base price", "list price", "net price", "catalog price", "price", "τιμή", "τιμο",
        "pricelist", "unit price", "value", "αξία", "€/", "eur"
    ]):
        return "Base Price"
    if any(token in c for token in ["unit of measure", "uom", "unit", " mm", "mm ", "μον", "μ.μ", "μ/μ"]) or c == "mm":
        return "MM"
    if any(token in c for token in ["package", "pack", "packing", "minimum order", "min order", "pallet", "box", "συσκ"]):
        return "Package"
    if any(token in c for token in ["category", "group", "family", "range", "line", "segment", "κατηγο"]):
        return "Category"

    return str(col_name).strip()


def _guess_supplier_columns_by_values(df: pd.DataFrame) -> dict:
    guessed = {}
    used_columns = set()

    def _sample(series):
        vals = []
        if isinstance(series, pd.DataFrame):
            if series.shape[1] == 0:
                return vals
            series = series.iloc[:, 0]
        for val in series.astype(object).tolist():
            if val is None:
                continue
            sval = str(val).strip()
            if sval.lower() in {"", "nan", "none"}:
                continue
            vals.append(sval)
            if len(vals) >= 30:
                break
        return vals

    def _numeric_ratio(values):
        if not values:
            return 0.0
        ok = 0
        for v in values:
            if _to_float_or_none(v) is not None:
                ok += 1
        return ok / len(values)

    def _long_text_ratio(values):
        if not values:
            return 0.0
        ok = 0
        for v in values:
            if len(v) >= 8 and _to_float_or_none(v) is None:
                ok += 1
        return ok / len(values)

    def _code_like_ratio(values):
        if not values:
            return 0.0
        ok = 0
        for v in values:
            compact = v.replace(" ", "")
            if len(compact) <= 20 and any(ch.isdigit() for ch in compact):
                ok += 1
        return ok / len(values)

    profiles = {}
    for col in df.columns:
        vals = _sample(df[col])
        profiles[col] = {
            "numeric_ratio": _numeric_ratio(vals),
            "long_text_ratio": _long_text_ratio(vals),
            "code_like_ratio": _code_like_ratio(vals),
        }

    price_candidates = sorted(df.columns, key=lambda c: (profiles[c]["numeric_ratio"], "price" in str(c).lower()), reverse=True)
    for col in price_candidates:
        if profiles[col]["numeric_ratio"] >= 0.55:
            guessed["Base Price"] = col
            used_columns.add(col)
            break

    product_candidates = sorted(df.columns, key=lambda c: (profiles[c]["long_text_ratio"], len(str(c))), reverse=True)
    for col in product_candidates:
        if col in used_columns:
            continue
        if profiles[col]["long_text_ratio"] >= 0.35:
            guessed["Product"] = col
            used_columns.add(col)
            break

    code_candidates = sorted(df.columns, key=lambda c: (profiles[c]["code_like_ratio"], -profiles[c]["numeric_ratio"]), reverse=True)
    for col in code_candidates:
        if col in used_columns:
            continue
        if profiles[col]["code_like_ratio"] >= 0.35:
            guessed["SAP"] = col
            used_columns.add(col)
            break

    return guessed


def _to_float_or_none(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-", "--", "upon request", "contact us"}:
        return None

    text = text.replace("€", "").replace("EUR", "").replace("eur", "")
    text = text.replace(" ", "")

    if text.count(",") > 0 and text.count(".") > 0:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except Exception:
        return None


def _to_increase_fraction(value):
    num = _to_float_or_none(value)
    if num is None:
        return 0.0
    return num / 100.0 if abs(num) > 1 else num



def _clean_header_part(value):
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in {"", "nan", "none", "unnamed"}:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _build_supplier_header_names(raw_df: pd.DataFrame, header_row: int, depth: int = 3):
    if raw_df.empty:
        return []

    end_row = min(len(raw_df), header_row + depth)
    header_block = raw_df.iloc[header_row:end_row].copy()

    # forward-fill horizontally and vertically to better simulate merged header cells
    header_block = header_block.ffill(axis=1).ffill(axis=0)

    names = []
    for col_idx in range(header_block.shape[1]):
        parts = []
        for row_idx in range(header_block.shape[0]):
            part = _clean_header_part(header_block.iat[row_idx, col_idx])
            if part and part.lower() not in {p.lower() for p in parts}:
                parts.append(part)
        joined = " | ".join(parts).strip(" |")
        if not joined:
            joined = f"Column {col_idx + 1}"
        names.append(joined)
    return names


def _is_section_title_row(values):
    cleaned = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s.lower() in {"", "nan", "none"}:
            continue
        cleaned.append(s)

    if not cleaned:
        return False

    if len(cleaned) == 1:
        s = cleaned[0]
        if _to_float_or_none(s) is not None:
            return False
        upper_ratio = sum(1 for ch in s if ch.isupper()) / max(1, sum(1 for ch in s if ch.isalpha()))
        if len(s) <= 80 and (upper_ratio >= 0.6 or len(s.split()) <= 6):
            return True

    numeric_count = sum(1 for s in cleaned if _to_float_or_none(s) is not None)
    if numeric_count == 0 and len(cleaned) <= 2:
        merged = " ".join(cleaned)
        alpha_count = sum(1 for ch in merged if ch.isalpha())
        if alpha_count >= 3:
            return True

    return False


def _extract_section_title(values):
    cleaned = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s.lower() in {"", "nan", "none"}:
            continue
        cleaned.append(s)
    return " | ".join(cleaned[:2]).strip()


def _normalize_supplier_dataframe_from_raw(raw_df: pd.DataFrame, header_row: int) -> pd.DataFrame:
    header_names = _build_supplier_header_names(raw_df, header_row=header_row, depth=3)
    data_start = min(len(raw_df), header_row + 3)
    body = raw_df.iloc[data_start:].copy().reset_index(drop=True)
    if body.empty:
        body = raw_df.iloc[header_row + 1:].copy().reset_index(drop=True)
    body.columns = header_names[:body.shape[1]]
    body = body.dropna(how="all")
    body = body.reset_index(drop=True)
    return body


def convert_supplier_pricelist_to_source(uploaded_file):
    xls, file_bytes = load_excel_file_any(uploaded_file)

    all_rows = []
    used_sheets = []
    skipped_sheets = []
    rows_missing_price = 0
    rows_missing_sap = 0
    rows_missing_product = 0
    detected_section_titles = []

    for sheet_name in xls.sheet_names:
        lowered_sheet = str(sheet_name).strip().lower()
        if any(token in lowered_sheet for token in ["cover", "legend", "notes", "summary", "readme", "categorie", "lookup", "contents", "index"]):
            skipped_sheets.append(f"{sheet_name} (helper)")
            continue

        raw = read_excel_any(file_bytes, sheet_name=sheet_name, header=None)
        if raw.empty:
            skipped_sheets.append(f"{sheet_name} (empty)")
            continue

        raw = raw.ffill(axis=1)
        header_row = _detect_supplier_header_row(raw)
        df = _normalize_supplier_dataframe_from_raw(raw, header_row=header_row)
        if df.empty:
            skipped_sheets.append(f"{sheet_name} (no rows)")
            continue

        original_columns = [str(c).strip() for c in df.columns]
        renamed_columns = {_col: _normalize_supplier_column_name(_col) for _col in original_columns}
        df = df.rename(columns=renamed_columns)
        df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

        guessed_columns = _guess_supplier_columns_by_values(df)
        for canonical_name, original_col in guessed_columns.items():
            if canonical_name not in df.columns and original_col in df.columns:
                df = df.rename(columns={original_col: canonical_name})
        df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

        if "Product" not in df.columns:
            skipped_sheets.append(f"{sheet_name} (missing Product)")
            continue

        if "Base Price" not in df.columns:
            skipped_sheets.append(f"{sheet_name} (missing Base Price)")
            continue

        if "SAP" not in df.columns:
            df["SAP"] = ""

        if "Category" not in df.columns:
            df["Category"] = ""

        current_category = str(sheet_name).strip()

        normalized_rows = []
        for _, source_row in df.iterrows():
            row_values = source_row.tolist()

            if _is_section_title_row(row_values):
                section_title = _extract_section_title(row_values)
                if section_title:
                    current_category = section_title
                    detected_section_titles.append(f"{sheet_name}: {section_title}")
                continue

            product_value = source_row["Product"] if "Product" in source_row.index else None
            price_value = source_row["Base Price"] if "Base Price" in source_row.index else None
            sap_value = source_row["SAP"] if "SAP" in source_row.index else ""

            product_text = "" if product_value is None else str(product_value).strip()
            base_price = _to_float_or_none(price_value)
            sap_text = "" if sap_value is None else str(sap_value).strip()

            if product_text.lower() in {"", "nan", "none"} and base_price is None:
                continue

            if _to_float_or_none(product_text) is not None and base_price is None:
                continue

            if not product_text or product_text.lower() in {"nan", "none"}:
                rows_missing_product += 1
                continue

            increase_fraction = _to_increase_fraction(source_row["Increase %"]) if "Increase %" in source_row.index else 0.0
            mm_text = str(source_row["MM"]).strip() if "MM" in source_row.index and pd.notna(source_row["MM"]) else ""
            package_text = str(source_row["Package"]).strip() if "Package" in source_row.index and pd.notna(source_row["Package"]) else ""
            category_text = str(source_row["Category"]).strip() if "Category" in source_row.index and pd.notna(source_row["Category"]) else ""
            final_category = category_text if category_text and category_text.lower() not in {"nan", "none"} else current_category

            if base_price is None:
                rows_missing_price += 1
            if not sap_text:
                rows_missing_sap += 1

            normalized_rows.append({
                "SAP": sap_text,
                "Product": product_text,
                "Base Price": base_price,
                "Increase %": increase_fraction,
                "Price": round(base_price * (1 + increase_fraction), 4) if base_price is not None else None,
                "MM": mm_text,
                "Package": package_text,
                "Category": final_category,
            })

        if not normalized_rows:
            skipped_sheets.append(f"{sheet_name} (no valid product rows)")
            continue

        out = pd.DataFrame(normalized_rows)
        out = out.dropna(subset=["Base Price"], how="all")
        out = out[
            ~(
                out["Product"].astype(str).str.strip().str.lower().isin(["", "nan", "none"])
                & out["Base Price"].isna()
        ].copy()

        if out.empty:
            skipped_sheets.append(f"{sheet_name} (all rows invalid)")
            continue

        used_sheets.append(sheet_name)
        all_rows.append(out)

    if not all_rows:
        return None, {
            "used_sheets": used_sheets,
            "skipped_sheets": skipped_sheets,
            "missing_price_rows": rows_missing_price,
            "missing_sap_rows": rows_missing_sap,
            "missing_product_rows": rows_missing_product,
            "detected_section_titles": detected_section_titles,
            "total_rows": 0,
        }

    source_df = pd.concat(all_rows, ignore_index=True)
    source_df["Base Price"] = pd.to_numeric(source_df["Base Price"], errors="coerce")
    source_df["Increase %"] = pd.to_numeric(source_df["Increase %"], errors="coerce").fillna(0)
    source_df["Price"] = source_df.apply(
        lambda r: round(r["Base Price"] * (1 + r["Increase %"]), 4) if pd.notna(r["Base Price"]) else None,
        axis=1,
    source_df = source_df.reset_index(drop=True)

    stats = {
        "used_sheets": used_sheets,
        "skipped_sheets": skipped_sheets,
        "missing_price_rows": rows_missing_price,
        "missing_sap_rows": rows_missing_sap,
        "missing_product_rows": rows_missing_product,
        "detected_section_titles": detected_section_titles,
        "total_rows": len(source_df),
    }
    return source_df, stats