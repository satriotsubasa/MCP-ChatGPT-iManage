"""
Configuration module for iManage Deep Research MCP Server
Updated to support both user authentication and service account modes
"""

import os
import time
from typing import Dict, List

# ---- Configuration ----
AUTH_URL_PREFIX = os.getenv("AUTH_URL_PREFIX", "")
URL_PREFIX = os.getenv("URL_PREFIX", "")

# Service Account Configuration (legacy/fallback)
SERVICE_USERNAME = os.getenv("SERVICE_USERNAME", "") or os.getenv("USERNAME", "")
SERVICE_PASSWORD = os.getenv("SERVICE_PASSWORD", "") or os.getenv("PASSWORD", "")

# OAuth Configuration
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

# iManage Configuration
CUSTOMER_ID = os.getenv("CUSTOMER_ID", "")
LIBRARY_ID = os.getenv("LIBRARY_ID", "")

# Server Configuration
BASE_URL = os.getenv("BASE_URL", "")  # Required for OAuth callbacks
PORT = int(os.getenv("PORT", 8000))

# Authentication Mode Configuration
AUTH_MODE = os.getenv("AUTH_MODE", "service").lower()  # "user" or "service"

# Required environment variables based on auth mode
def get_required_vars() -> List[str]:
    """Get required variables based on authentication mode"""
    base_vars = ["AUTH_URL_PREFIX", "URL_PREFIX", "CLIENT_ID", "CLIENT_SECRET", "CUSTOMER_ID", "LIBRARY_ID"]
    
    if AUTH_MODE == "user":
        return base_vars + ["BASE_URL"]
    else:
        return base_vars + ["SERVICE_USERNAME", "SERVICE_PASSWORD"]

def validate_config():
    """Validate that all required environment variables are set"""
    required_vars = get_required_vars()
    missing_vars = []
    
    for var in required_vars:
        value = globals().get(var, "") or os.getenv(var, "")
        if not value:
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"❌ Required environment variables not set: {', '.join(missing_vars)}")
    
    print("✅ All required environment variables are configured")
    print(f"🔐 Authentication Mode: {AUTH_MODE}")
    if AUTH_MODE == "user":
        print(f"🌐 Base URL: {BASE_URL}")
    return True

def is_user_auth_enabled() -> bool:
    """Check if user authentication is enabled"""
    return AUTH_MODE == "user"

def get_oauth_redirect_uri() -> str:
    """Get OAuth redirect URI"""
    return f"{BASE_URL.rstrip('/')}/oauth/callback"

# ---- Token cache (for service account mode) ----
token_cache: Dict[str, float] = {"token": None, "expires": 0}

def get_token_cache():
    """Get current token cache"""
    return token_cache

def update_token_cache(token: str, expires_in: int = 1800):
    """Update token cache with new token"""
    token_cache["token"] = token
    token_cache["expires"] = time.time() + expires_in - 60  # 1 minute buffer
    return token_cache