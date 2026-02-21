"""
Authentication Module

This module has intentional security vulnerabilities for demo purposes.
MDx Code's security agent should catch these!
"""

import hashlib
import random


# Security Issue: Hardcoded credentials
DEFAULT_PASSWORD = "password123"
ADMIN_TOKEN = "super_secret_admin_token_12345"


def hash_password(password):
    """Hash a password.
    
    Security Issue: Using MD5 which is cryptographically weak!
    """
    return hashlib.md5(password.encode()).hexdigest()


def generate_token():
    """Generate an authentication token.
    
    Security Issue: Using random module instead of secrets!
    """
    return str(random.randint(100000, 999999))


def verify_user(username, password):
    """Verify user credentials.
    
    Security Issue: SQL injection vulnerability!
    """
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    # This would execute the query... 
    print(f"Executing: {query}")
    return True


def get_user_data(user_id):
    """Get user data by ID.
    
    Security Issue: Another SQL injection via string formatting!
    """
    query = "SELECT * FROM users WHERE id = {}".format(user_id)
    print(f"Executing: {query}")
    return {"id": user_id, "name": "Test User"}


def execute_command(cmd):
    """Execute a system command.
    
    Security Issue: Using eval!
    """
    result = eval(cmd)
    return result


def load_config(config_string):
    """Load configuration from YAML string.
    
    Security Issue: Using yaml.load without safe loader!
    """
    import yaml
    return yaml.load(config_string)


# Debug mode left on
DEBUG = True
