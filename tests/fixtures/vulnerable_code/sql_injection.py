# EXPECTED: CWE-89, SQL Injection, line 15, severity: critical
"""User search endpoint with SQL injection vulnerability."""

import sqlite3


def get_db():
    conn = sqlite3.connect("app.db")
    conn.row_factory = sqlite3.Row
    return conn


def search_users(query: str) -> list[dict]:
    """Search users by name. WARNING: SQL injection vulnerable."""
    db = get_db()
    cursor = db.execute(
        f"SELECT id, name, email FROM users WHERE name LIKE '%{query}%'"
    )
    results = [dict(row) for row in cursor.fetchall()]
    db.close()
    return results


def get_user_by_id(user_id: str) -> dict | None:
    """Get user by ID."""
    db = get_db()
    cursor = db.execute(
        "SELECT id, name, email FROM users WHERE id = " + user_id
    )
    row = cursor.fetchone()
    db.close()
    return dict(row) if row else None


def delete_user(user_id: str) -> bool:
    """Delete a user account."""
    db = get_db()
    db.execute(f"DELETE FROM users WHERE id = {user_id}")
    db.commit()
    db.close()
    return True
