# EXPECTED: CWE-367, TOCTOU Race Condition, line 17, severity: high
"""File operations with time-of-check to time-of-use vulnerability."""

import os
import shutil

UPLOAD_DIR = "/var/app/uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def safe_delete(filepath: str) -> bool:
    """Delete a file after checking it exists. WARNING: TOCTOU race condition."""
    # Time-of-check
    if os.path.exists(filepath):
        if os.path.isfile(filepath):
            # Time-of-use — file could have changed between check and delete
            os.remove(filepath)
            return True
    return False


def process_upload(filepath: str, dest_dir: str) -> str:
    """Process an uploaded file. WARNING: TOCTOU between size check and read."""
    # Check file size
    size = os.path.getsize(filepath)
    if size > MAX_FILE_SIZE:
        raise ValueError("File too large")

    # Race: file could be replaced with larger file between check and read
    with open(filepath, "rb") as f:
        content = f.read()

    dest = os.path.join(dest_dir, os.path.basename(filepath))
    with open(dest, "wb") as f:
        f.write(content)
    return dest


def update_config(config_path: str, new_config: dict) -> None:
    """Update config file. WARNING: no file locking."""
    import json

    # Read current config
    with open(config_path) as f:
        current = json.load(f)

    # Modify — another process could write between read and write
    current.update(new_config)

    # Write back
    with open(config_path, "w") as f:
        json.dump(current, f)
