# EXPECTED: CWE-798, Hardcoded Credentials, line 10, severity: critical
"""Payment processing module with hardcoded API credentials."""

import requests

API_BASE = "https://api.stripe.com/v1"

# Hardcoded API keys — should be in environment variables
STRIPE_SECRET_KEY = "sk_live_FAKE_KEY_FOR_TESTING_00000000"
STRIPE_PUBLISHABLE_KEY = "pk_live_FAKE_KEY_FOR_TESTING_00000000"

DATABASE_PASSWORD = "FAKE_PASSWORD_FOR_TESTING"
ADMIN_TOKEN = "FAKE_TOKEN_FOR_TESTING.not.real"


def charge_customer(amount: int, currency: str, token: str) -> dict:
    """Charge a customer's card."""
    response = requests.post(
        f"{API_BASE}/charges",
        auth=(STRIPE_SECRET_KEY, ""),
        data={
            "amount": amount,
            "currency": currency,
            "source": token,
        },
    )
    return response.json()


def get_balance() -> dict:
    """Check account balance."""
    response = requests.get(
        f"{API_BASE}/balance",
        auth=(STRIPE_SECRET_KEY, ""),
    )
    return response.json()


def connect_db():
    """Connect to database with hardcoded password."""
    import psycopg2

    return psycopg2.connect(
        host="db.production.internal",
        database="app_prod",
        user="admin",
        password=DATABASE_PASSWORD,
    )
