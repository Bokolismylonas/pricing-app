import os
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify
import stripe

app = Flask(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

PERSIST_ROOT = Path(os.getenv("PERSIST_ROOT", "/tmp/pricing_app_webhook"))
PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

ADMIN_DIR = PERSIST_ROOT / "_admin"
ADMIN_DIR.mkdir(parents=True, exist_ok=True)

USERS_REGISTRY_FILE = ADMIN_DIR / "users_registry.json"


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
        encoding="utf-8"
    )


def now_iso():
    return datetime.utcnow().isoformat()


def find_user_by_email(users, email):
    for i, row in enumerate(users):
        if row.get("email", "").strip().lower() == email.strip().lower():
            return i
    return None


def set_user_premium(email, is_premium=True, billing_status="active"):
    users = load_users_registry()
    idx = find_user_by_email(users, email)

    if idx is None:
        return False

    users[idx]["is_premium"] = is_premium
    users[idx]["billing_status"] = billing_status
    users[idx]["last_seen"] = now_iso()

    save_users_registry(users)
    return True


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        customer_email = data_object.get("customer_details", {}).get("email") or data_object.get("customer_email")
        if customer_email:
            set_user_premium(customer_email, True, "active")

    elif event_type == "customer.subscription.created":
        customer_email = None
        customer_id = data_object.get("customer")
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            customer_email = customer.get("email")

        status = data_object.get("status", "active")
        if customer_email and status in ["trialing", "active"]:
            set_user_premium(customer_email, True, status)

    elif event_type == "customer.subscription.updated":
        customer_email = None
        customer_id = data_object.get("customer")
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            customer_email = customer.get("email")

        status = data_object.get("status", "")
        if customer_email:
            if status in ["trialing", "active"]:
                set_user_premium(customer_email, True, status)
            else:
                set_user_premium(customer_email, False, status or "inactive")

    elif event_type == "customer.subscription.deleted":
        customer_email = None
        customer_id = data_object.get("customer")
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            customer_email = customer.get("email")

        if customer_email:
            set_user_premium(customer_email, False, "canceled")

    return jsonify({"received": True}), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)