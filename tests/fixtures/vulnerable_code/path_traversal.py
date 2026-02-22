# EXPECTED: CWE-22, Path Traversal, line 15, severity: critical
"""File download endpoint with path traversal vulnerability."""

import os
from pathlib import Path

UPLOAD_DIR = "/var/app/uploads"


def get_file(filename: str) -> bytes:
    """Download a file from the uploads directory."""
    # Vulnerable: no sanitization of filename
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "rb") as f:
        return f.read()


def read_user_document(user_id: str, doc_name: str) -> str:
    """Read a user's document."""
    # Vulnerable: path components not validated
    path = Path(UPLOAD_DIR) / user_id / doc_name
    return path.read_text()


def list_files(directory: str) -> list[str]:
    """List files in a subdirectory of uploads."""
    # Vulnerable: allows traversal out of UPLOAD_DIR
    target = os.path.join(UPLOAD_DIR, directory)
    return os.listdir(target)


def save_file(filename: str, content: bytes) -> str:
    """Save uploaded file."""
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return filepath
