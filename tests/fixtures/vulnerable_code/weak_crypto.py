# EXPECTED: CWE-327, Use of a Broken Cryptographic Algorithm, line 16, severity: high
"""User authentication with weak cryptographic practices."""

import hashlib
import os

SALT = "fixed_salt_value"


def hash_password(password: str) -> str:
    """Hash a password for storage. WARNING: uses MD5."""
    # MD5 is cryptographically broken for password hashing
    return hashlib.md5((SALT + password).encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash."""
    return hash_password(password) == stored_hash


def generate_token() -> str:
    """Generate a session token. WARNING: uses SHA1."""
    random_bytes = os.urandom(16)
    return hashlib.sha1(random_bytes).hexdigest()


def encrypt_data(data: str, key: str) -> str:
    """'Encrypt' data. WARNING: this is just XOR, not real encryption."""
    key_bytes = key.encode()
    data_bytes = data.encode()
    result = bytearray()
    for i, b in enumerate(data_bytes):
        result.append(b ^ key_bytes[i % len(key_bytes)])
    return result.hex()
