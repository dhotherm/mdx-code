# EXPECTED: CWE-502, Insecure Deserialization, line 18, severity: critical
"""Session management with insecure deserialization."""

import base64
import pickle
from dataclasses import dataclass


@dataclass
class UserSession:
    user_id: str
    role: str
    preferences: dict


def load_session(session_data: str) -> UserSession:
    """Load user session from cookie. WARNING: uses pickle on untrusted input."""
    raw = base64.b64decode(session_data)
    return pickle.loads(raw)


def save_session(session: UserSession) -> str:
    """Serialize session to cookie value."""
    raw = pickle.dumps(session)
    return base64.b64encode(raw).decode()


def process_webhook(payload: bytes) -> dict:
    """Process incoming webhook data."""
    # Also dangerous: deserializing untrusted external data
    data = pickle.loads(payload)
    return {"status": "processed", "type": data.get("event_type")}


def import_config(config_str: str) -> dict:
    """Import configuration from string."""
    # Using eval on user input
    return eval(config_str)
