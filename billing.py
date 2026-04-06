import os
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

PRICE_ID = os.getenv("STRIPE_PRICE_PREMIUM_MONTHLY")
APP_URL = os.getenv("APP_BASE_URL")


def create_checkout_session(user_email):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        customer_email=user_email,
        line_items=[{
            "price": PRICE_ID,
            "quantity": 1,
        }],
        success_url=f"{APP_URL}/?payment=success",
        cancel_url=f"{APP_URL}/?payment=cancel",
    )
    return session.url