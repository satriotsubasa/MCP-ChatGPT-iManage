#!/usr/bin/env python3
"""
iManage Deep Research MCP Server - Proper OAuth with SAML SSO Support
This version implements correct OAuth flow that works with iManage OAuth + SAML SSO
"""

import time
import os
import logging
import asyncio
import secrets
import httpx
from urllib.parse import urlencode, urlparse, parse_qs
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

# Import our modules
from config import validate_config, CUSTOMER_ID, LIBRARY_ID, is_user_auth_enabled, AUTH_MODE, BASE_URL
from config import AUTH_URL_PREFIX, CLIENT_ID, CLIENT_SECRET
from auth import get_token, user_auth_manager
from mcp_handlers import handle_mcp_request
from test_endpoints import router as test_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate configuration on startup
try:
    validate_config()
except ValueError as e:
    print(f"Configuration error: {e}")
    exit(1)

app = FastAPI(
    title="iManage Deep Research MCP Server",
    description="MCP server with OAuth + SAML SSO for ChatGPT integration with iManage Work API",
    version="2.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include test router
app.include_router(test_router)

# In-memory storage for OAuth states (use Redis in production)
oauth_sessions = {}

# ---- CORS Preflight Handler ----
@app.options("/")
async def options_handler():
    """Handle CORS preflight requests for MCP endpoint"""
    print("🔄 CORS preflight request for MCP endpoint")
    return {
        "Allow": "GET, POST, OPTIONS",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }

# ---- Main MCP Protocol Handler ----
@app.post("/")
async def mcp_handler(request: Request):
    """Main MCP protocol handler with user context support"""
    return await handle_mcp_request(request)

@app.get("/")
async def root():
    """Health check and basic info endpoint for GET requests"""
    print("🏥 Health check requested (GET)")
    return {
        "name": "iManage Deep Research MCP Server",
        "version": "2.1.0",
        "description": "MCP server with OAuth + SAML SSO for ChatGPT integration with iManage Work API",
        "protocol": "MCP/1.0",
        "capabilities": ["tools"],
        "status": "healthy",
        "authentication": "oauth_saml_sso",
        "auth_mode": AUTH_MODE,
        "endpoints": {
            "mcp": "POST /",
            "oauth_authorize": "GET /oauth/authorize",
            "oauth_callback": "GET /oauth/callback",
            "oauth_token": "POST /oauth/token",
            "health": "GET /health",
            "test": "GET /test"
        }
    }

# ---- OAuth Authorization Server Metadata Endpoint ----
@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    """OAuth 2.0 Authorization Server Metadata"""
    print("🔍 OAuth authorization server metadata requested")
    
    if not is_user_auth_enabled():
        return {"error": "User authentication not enabled"}
    
    return {
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "userinfo_endpoint": f"{BASE_URL}/oauth/userinfo",
        "registration_endpoint": f"{BASE_URL}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "scopes_supported": ["read"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"]
    }

# ---- Dynamic OAuth Client Registration Endpoint ----
@app.post("/oauth/register")
async def oauth_register():
    """Dynamic OAuth Client Registration endpoint"""
    print("🔐 OAuth client registration requested")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Generate a unique client for ChatGPT
    client_id = f"chatgpt_mcp_{secrets.token_hex(8)}"
    client_secret = secrets.token_urlsafe(32)
    
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,
        "redirect_uris": [
            "https://chatgpt.com/connector_platform_oauth_redirect",
            "https://chat.openai.com/connector_platform_oauth_redirect"
        ],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "scope": "read",
        "token_endpoint_auth_method": "client_secret_post"
    }

# ---- Core MCP Discovery ----
@app.get("/.well-known/mcp")
async def mcp_discovery():
    """MCP discovery endpoint"""
    print("🔍 MCP discovery requested")
    
    if is_user_auth_enabled():
        auth_config = {
            "type": "oauth2",
            "authorization_url": f"{BASE_URL}/oauth/authorize",
            "token_url": f"{BASE_URL}/oauth/token",
            "userinfo_url": f"{BASE_URL}/oauth/userinfo",
            "scopes": ["read"]
        }
    else:
        auth_config = {"type": "none"}
    
    return {
        "version": "2.1.0",
        "name": "iManage Deep Research MCP Server", 
        "description": "Deep research connector for iManage Work API with OAuth + SAML SSO",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False
        },
        "authentication": auth_config,
        "endpoint": {
            "url": "/",
            "method": "POST"
        }
    }

# ---- OAuth Endpoints ----
@app.get("/oauth/authorize")
async def oauth_authorize_endpoint(request: Request):
    """OAuth authorization endpoint - redirect to iManage OAuth (which then goes to SAML SSO)"""
    print("🔐 OAuth authorization requested - will redirect to iManage OAuth + SAML SSO")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Get parameters from ChatGPT
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    state = params.get("state")
    code_challenge = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method")
    scope = params.get("scope", "read")
    
    print(f"🔍 ChatGPT OAuth params: client_id={client_id}, redirect_uri={redirect_uri}, state={state}")
    print(f"🔍 PKCE: challenge={code_challenge[:20] if code_challenge else None}..., method={code_challenge_method}")
    
    # Store the ChatGPT request for later use
    session_id = secrets.token_urlsafe(32)
    oauth_sessions[session_id] = {
        "chatgpt_client_id": client_id,
        "chatgpt_redirect_uri": redirect_uri,
        "chatgpt_state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "created_at": time.time(),
        "expires_at": time.time() + 600  # 10 minutes
    }
    
    # Build iManage OAuth authorization URL (which will redirect to SAML SSO)
    imanage_oauth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,  # Your iManage OAuth client ID
        "redirect_uri": f"{BASE_URL}/oauth/callback",  # Your server's callback
        "scope": "admin",  # iManage scope
        "state": session_id  # Use our session ID as state for iManage
    }
    
    imanage_oauth_url = f"{AUTH_URL_PREFIX}/oauth2/authorize?" + urlencode(imanage_oauth_params)
    
    print(f"🔀 Redirecting to iManage OAuth (which will redirect to SAML SSO): {imanage_oauth_url}")
    
    # Redirect user to iManage OAuth (which will then redirect to SAML SSO)
    return RedirectResponse(url=imanage_oauth_url)

@app.get("/oauth/callback")
async def oauth_callback_endpoint(request: Request):
    """OAuth callback from iManage (after SAML SSO authentication)"""
    print("🔄 OAuth callback from iManage received (user authenticated via SAML SSO)")
    
    params = dict(request.query_params)
    code = params.get("code")  # Authorization code from iManage
    state = params.get("state")  # Our session ID
    error = params.get("error")
    
    if error:
        print(f"❌ OAuth error from iManage: {error}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>iManage authentication failed: {error}</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    if not code or not state:
        print("❌ Missing code or state from iManage")
        return HTMLResponse("""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Missing authorization code or state from iManage.</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    # Get the original ChatGPT request
    if state not in oauth_sessions:
        print(f"❌ Invalid or expired session: {state}")
        return HTMLResponse("""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Invalid or expired authentication session.</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    session_data = oauth_sessions[state]
    
    try:
        # Exchange iManage authorization code for access token
        print("🔄 Exchanging iManage authorization code for access token...")
        
        token_url = f"{AUTH_URL_PREFIX}/oauth2/token"
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": f"{BASE_URL}/oauth/callback"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                token_url, 
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            token_response.raise_for_status()
            imanage_token_info = token_response.json()
        
        print("✅ Successfully obtained iManage access token (user authenticated via SAML SSO)")
        
        # Generate authorization code for ChatGPT (simple format)
        chatgpt_auth_code = f"auth_{secrets.token_hex(16)}"
        
        # Store the iManage token with the ChatGPT auth code
        oauth_sessions[chatgpt_auth_code] = {
            "imanage_access_token": imanage_token_info["access_token"],
            "imanage_refresh_token": imanage_token_info.get("refresh_token"),
            "user_authenticated": True,
            "created_at": time.time(),
            "expires_at": time.time() + imanage_token_info.get("expires_in", 3600)
        }
        
        # Clean up the original session
        del oauth_sessions[state]
        
        # Redirect back to ChatGPT
        chatgpt_redirect_uri = session_data["chatgpt_redirect_uri"]
        chatgpt_state = session_data["chatgpt_state"]
        
        redirect_params = {
            "code": chatgpt_auth_code,
            "state": chatgpt_state
        }
        
        redirect_url = f"{chatgpt_redirect_uri}?" + urlencode(redirect_params)
        
        print(f"🔀 Redirecting back to ChatGPT: {redirect_url}")
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        print(f"❌ Failed to exchange iManage authorization code: {str(e)}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Authentication Failed</h2>
                <p>Failed to complete authentication with iManage: {str(e)}</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=500)

@app.post("/oauth/token")
async def oauth_token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None)
):
    """OAuth token endpoint"""
    print(f"🔐 OAuth token request: grant_type={grant_type}, code={code}")
    
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # Validate that we have session data for this code
        if code not in oauth_sessions:
            print(f"❌ Invalid authorization code: {code}")
            raise HTTPException(status_code=400, detail="Invalid authorization code")
        
        session_data = oauth_sessions[code]
        
        if not session_data.get("user_authenticated"):
            raise HTTPException(status_code=400, detail="User not authenticated")
        
        print(f"✅ Token issued for authenticated user")
        
        return {
            "access_token": f"mcp_token_{code}",
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": "read"
        }
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant type")

@app.get("/oauth/userinfo")
async def oauth_userinfo_endpoint(request: Request):
    """OAuth user info endpoint"""
    print("👤 OAuth userinfo requested")
    
    # Try to extract user info from the access token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer mcp_token_"):
        token_code = auth_header.replace("Bearer mcp_token_", "")
        session_data = oauth_sessions.get(token_code, {})
        
        if session_data.get("user_authenticated"):
            # In a real implementation, you'd get user info from iManage using the stored access token
            return {
                "sub": "authenticated_user",
                "name": "Authenticated User",
                "email": "user@riotinto.com",
                "preferred_username": "authenticated_user"
            }
    
    # Fallback
    return {
        "sub": "imanage_user",
        "name": "iManage User",
        "email": "user@riotinto.com",
        "preferred_username": "imanage_user"
    }

# ---- Health Check ----
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    print("🩺 Health check via /health")
    return {
        "status": "healthy", 
        "timestamp": time.time(),
        "version": "2.1.0",
        "auth_mode": f"{AUTH_MODE}_oauth_saml",
        "oauth_saml_enabled": True,
        "user_auth_enabled": is_user_auth_enabled()
    }

# ---- Startup Event ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up (OAuth + SAML SSO)")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    print(f"🔐 Authentication Mode: {AUTH_MODE} (OAuth + SAML SSO)")
    print("🔒 Flow: ChatGPT → Your Server → iManage OAuth → SAML SSO → Back to ChatGPT")
    
    if is_user_auth_enabled():
        print(f"🌐 Base URL: {BASE_URL}")
        print(f"🔗 Authorization URL: {BASE_URL}/oauth/authorize")
        print(f"🎫 Token URL: {BASE_URL}/oauth/token")
        print("✅ OAuth + SAML SSO flow configured")
        print(f"📋 Make sure your iManage OAuth client includes this redirect URI: {BASE_URL}/oauth/callback")
    else:
        print("⚙️ Running in service account mode")
        try:
            await get_token()
            print("✅ Service account authentication test successful")
        except Exception as e:
            print(f"⚠️ Warning: Service account authentication test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting iManage Deep Research MCP Server (OAuth + SAML SSO)...")
    
    port = int(os.getenv("PORT", 10000))
    print(f"🌐 Server will bind to port: {port}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )