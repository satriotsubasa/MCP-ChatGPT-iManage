"""
Authentication module for iManage Deep Research MCP Server
Supports both service account and user authentication modes
"""

import time
import httpx
import secrets
import hashlib
from typing import Dict, Optional, Any
from dataclasses import dataclass
from fastapi import HTTPException, Request

from config import (
    AUTH_URL_PREFIX, SERVICE_USERNAME, SERVICE_PASSWORD, CLIENT_ID, CLIENT_SECRET,
    get_token_cache, update_token_cache, is_user_auth_enabled, get_oauth_redirect_uri
)

# ---- Service Account Authentication (Legacy) ----
async def get_token() -> str:
    """Get authentication token with caching (service account mode)"""
    cache = get_token_cache()
    
    if cache["token"] and cache["expires"] > time.time():
        print("🔓 Using cached service account token")
        return cache["token"]
    
    print("🔐 Authenticating service account to iManage...")
    auth_url = f"{AUTH_URL_PREFIX}/oauth2/token?scope=admin"
    data = {
        "username": SERVICE_USERNAME,
        "password": SERVICE_PASSWORD,
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
            
            update_token_cache(token_data["access_token"], token_data.get("expires_in", 1800))
            print("✅ Service account authentication successful")
            return token_data["access_token"]
    except Exception as e:
        print(f"❌ Service account authentication failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# ---- User Authentication Classes ----
@dataclass
class UserSession:
    """User session data"""
    user_id: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    user_info: Dict[str, Any]
    created_at: float

class UserAuthManager:
    """Manages authentication for individual users"""
    
    def __init__(self):
        # In-memory session storage (in production, use Redis or database)
        self.user_sessions: Dict[str, UserSession] = {}
        self.oauth_states: Dict[str, Dict[str, Any]] = {}  # Track OAuth states
    
    def generate_oauth_state(self, session_id: str) -> str:
        """Generate OAuth state parameter for security"""
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = {
            "session_id": session_id,
            "created_at": time.time(),
            "expires_at": time.time() + 600  # 10 minutes
        }
        return state
    
    def validate_oauth_state(self, state: str) -> Optional[str]:
        """Validate OAuth state and return session_id"""
        if state not in self.oauth_states:
            return None
        
        state_data = self.oauth_states[state]
        if time.time() > state_data["expires_at"]:
            del self.oauth_states[state]
            return None
        
        session_id = state_data["session_id"]
        del self.oauth_states[state]  # Single use
        return session_id
    
    async def authenticate_user(self, username: str, password: str) -> UserSession:
        """Authenticate user with iManage and create session"""
        print(f"🔐 Authenticating user: {username}")
        
        auth_url = f"{AUTH_URL_PREFIX}/oauth2/token?scope=admin"
        data = {
            "username": username,
            "password": password,
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
                
                # Get user information
                user_info = await self._get_user_info(token_data["access_token"])
                
                # Create user session
                user_session = UserSession(
                    user_id=username,
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    expires_at=time.time() + token_data.get("expires_in", 1800) - 60,
                    user_info=user_info,
                    created_at=time.time()
                )
                
                # Generate session ID
                session_id = self._generate_session_id(username)
                self.user_sessions[session_id] = user_session
                
                print(f"✅ User authentication successful: {username}")
                return user_session
                
        except Exception as e:
            print(f"❌ User authentication failed for {username}: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    
    async def authenticate_with_oauth_code(self, code: str, state: str) -> UserSession:
        """Authenticate user using OAuth authorization code"""
        print(f"🔐 Processing OAuth code authentication")
        
        # Validate state
        session_id = self.validate_oauth_state(state)
        if not session_id:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
        
        # Exchange authorization code for tokens
        token_url = f"{AUTH_URL_PREFIX}/oauth2/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": get_oauth_redirect_uri()
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(token_url, data=data, headers=headers)
                res.raise_for_status()
                token_data = res.json()
                
                # Get user information
                user_info = await self._get_user_info(token_data["access_token"])
                username = user_info.get("username", "unknown")
                
                # Create user session
                user_session = UserSession(
                    user_id=username,
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    expires_at=time.time() + token_data.get("expires_in", 1800) - 60,
                    user_info=user_info,
                    created_at=time.time()
                )
                
                self.user_sessions[session_id] = user_session
                
                print(f"✅ OAuth authentication successful: {username}")
                return user_session
                
        except Exception as e:
            print(f"❌ OAuth authentication failed: {str(e)}")
            raise HTTPException(status_code=401, detail=f"OAuth authentication failed: {str(e)}")
    
    async def get_user_token(self, session_id: str) -> str:
        """Get valid user token, refreshing if necessary"""
        if session_id not in self.user_sessions:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        session = self.user_sessions[session_id]
        
        # Check if token is still valid
        if time.time() < session.expires_at:
            print(f"🔓 Using cached token for user: {session.user_id}")
            return session.access_token
        
        # Try to refresh token
        if session.refresh_token:
            try:
                refreshed_session = await self._refresh_user_token(session)
                self.user_sessions[session_id] = refreshed_session
                print(f"🔄 Token refreshed for user: {session.user_id}")
                return refreshed_session.access_token
            except Exception as e:
                print(f"❌ Token refresh failed for {session.user_id}: {str(e)}")
        
        # Token expired and refresh failed
        del self.user_sessions[session_id]
        raise HTTPException(status_code=401, detail="User session expired, please re-authenticate")
    
    async def _refresh_user_token(self, session: UserSession) -> UserSession:
        """Refresh user's access token"""
        print(f"🔄 Refreshing token for user: {session.user_id}")
        
        token_url = f"{AUTH_URL_PREFIX}/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": session.refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(token_url, data=data, headers=headers)
            res.raise_for_status()
            token_data = res.json()
            
            # Update session with new tokens
            session.access_token = token_data["access_token"]
            session.refresh_token = token_data.get("refresh_token", session.refresh_token)
            session.expires_at = time.time() + token_data.get("expires_in", 1800) - 60
            
            return session
    
    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from iManage"""
        try:
            user_url = f"{AUTH_URL_PREFIX.replace('/oauth2', '')}/api/v2/user"  # Adjust URL as needed
            headers = {"X-Auth-Token": access_token}
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(user_url, headers=headers)
                if res.status_code == 200:
                    return res.json().get("data", {})
                else:
                    # Fallback user info
                    return {"username": "authenticated_user"}
        except Exception as e:
            print(f"⚠️ Could not get user info: {str(e)}")
            return {"username": "authenticated_user", "error": str(e)}
    
    def _generate_session_id(self, username: str) -> str:
        """Generate unique session ID for user"""
        data = f"{username}:{time.time()}:{secrets.token_hex(16)}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def get_authorization_url(self, session_id: str) -> str:
        """Generate authorization URL for OAuth flow"""
        state = self.generate_oauth_state(session_id)
        
        auth_url = f"{AUTH_URL_PREFIX}/oauth2/authorize"
        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": get_oauth_redirect_uri(),
            "scope": "admin",
            "state": state
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{auth_url}?{query_string}"
    
    def logout_user(self, session_id: str) -> bool:
        """Logout user and cleanup session"""
        if session_id in self.user_sessions:
            user_id = self.user_sessions[session_id].user_id
            del self.user_sessions[session_id]
            print(f"👋 User logged out: {user_id}")
            return True
        return False
    
    def get_user_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get user information for a session"""
        if session_id not in self.user_sessions:
            return None
        return self.user_sessions[session_id].user_info
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions (call periodically)"""
        current_time = time.time()
        expired_sessions = [
            sid for sid, session in self.user_sessions.items()
            if current_time > session.expires_at
        ]
        
        for sid in expired_sessions:
            user_id = self.user_sessions[sid].user_id
            del self.user_sessions[sid]
            print(f"🗑️ Cleaned up expired session for user: {user_id}")
        
        # Also cleanup expired OAuth states
        expired_states = [
            state for state, data in self.oauth_states.items()
            if current_time > data["expires_at"]
        ]
        
        for state in expired_states:
            del self.oauth_states[state]

# ---- Context Management ----
def get_user_token_from_request(request: Request) -> Optional[str]:
    """Extract user token from request context"""
    if hasattr(request.state, 'user_token') and request.state.user_token:
        return request.state.user_token
    return None

def get_session_id_from_request(request: Request) -> Optional[str]:
    """Extract session ID from request headers"""
    # Try to get session from headers
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return session_id
    
    # Try to get from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer "
        # If it looks like a session ID (64 char hash), use it
        if len(token) == 64 and all(c in '0123456789abcdef' for c in token):
            return token
    
    return None

# ---- Global instances ----
user_auth_manager = UserAuthManager()

# ---- Token Resolution ----
async def get_authenticated_token(request: Request = None) -> str:
    """Get token based on authentication mode and request context"""
    if is_user_auth_enabled() and request:
        # Try to get user token from request
        user_token = get_user_token_from_request(request)
        if user_token:
            return user_token
        
        # Try to get session and resolve token
        session_id = get_session_id_from_request(request)
        if session_id:
            try:
                return await user_auth_manager.get_user_token(session_id)
            except HTTPException:
                pass  # Fall back to service account
    
    # Fall back to service account token
    return await get_token()