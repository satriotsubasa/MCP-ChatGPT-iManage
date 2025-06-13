"""
Authentication module for iManage Deep Research MCP Server
"""

import time
import httpx
from fastapi import HTTPException
from config import (
    AUTH_URL_PREFIX, USERNAME, PASSWORD, CLIENT_ID, CLIENT_SECRET,
    get_token_cache, update_token_cache
)

async def get_token() -> str:
    """Get authentication token with caching"""
    cache = get_token_cache()
    
    if cache["token"] and cache["expires"] > time.time():
        print("🔓 Using cached access token")
        return cache["token"]
    
    print("🔐 Authenticating to iManage...")
    auth_url = f"{AUTH_URL_PREFIX}/oauth2/token?scope=admin"
    data = {
        "username": USERNAME,
        "password": PASSWORD,
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(auth_url, data=data, headers=headers)
            res.raise_for_status()
            token_data = res.json()
            
            # Update cache
            update_token_cache(token_data["access_token"], token_data.get("expires_in", 1800))
            
            print("✅ Authentication successful")
            return token_data["access_token"]
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")