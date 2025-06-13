"""
Configuration module for iManage Deep Research MCP Server
"""

import os
import time
from typing import Dict

# ---- Configuration ----
AUTH_URL_PREFIX = os.getenv("AUTH_URL_PREFIX", "")
URL_PREFIX = os.getenv("URL_PREFIX", "")
USERNAME = os.getenv("USERNAME", "")
PASSWORD = os.getenv("PASSWORD", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
CUSTOMER_ID = os.getenv("CUSTOMER_ID", "")
LIBRARY_ID = os.getenv("LIBRARY_ID", "")

# Validate required environment variables
required_vars = [
    "AUTH_URL_PREFIX", "URL_PREFIX", "USERNAME", "PASSWORD", 
    "CLIENT_ID", "CLIENT_SECRET", "CUSTOMER_ID", "LIBRARY_ID"
]

def validate_config():
    """Validate that all required environment variables are set"""
    missing_vars = []
    for var in required_vars:
        if not globals()[var]:
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"❌ Required environment variables not set: {', '.join(missing_vars)}")
    
    print("✅ All required environment variables are configured")
    return True

# ---- Token cache ----
token_cache: Dict[str, float] = {"token": None, "expires": 0}

def get_token_cache():
    """Get current token cache"""
    return token_cache

def update_token_cache(token: str, expires_in: int = 1800):
    """Update token cache with new token"""
    token_cache["token"] = token
    token_cache["expires"] = time.time() + expires_in - 60  # 1 minute buffer
    return token_cache