#!/usr/bin/env python3
"""
iManage Deep Research MCP Server for ChatGPT Integration - Fixed Version
"""

import time
import os
import logging
import asyncio
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

# Import our modules
from config import validate_config, CUSTOMER_ID, LIBRARY_ID, is_user_auth_enabled, AUTH_MODE, BASE_URL
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
    description="MCP server with user authentication for ChatGPT integration with iManage Work API",
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
        "description": "MCP server with user authentication for ChatGPT integration with iManage Work API",
        "protocol": "MCP/1.0",
        "capabilities": ["tools"],
        "status": "healthy",
        "authentication": "user" if is_user_auth_enabled() else "service",
        "auth_mode": AUTH_MODE,
        "endpoints": {
            "mcp": "POST /",
            "oauth_authorize": "GET /oauth/authorize" if is_user_auth_enabled() else None,
            "oauth_callback": "GET /oauth/callback" if is_user_auth_enabled() else None,
            "oauth_token": "POST /oauth/token" if is_user_auth_enabled() else None,
            "health": "GET /health",
            "test": "GET /test"
        }
    }

# ---- OAuth Authorization Server Metadata Endpoint ----
@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    """OAuth 2.0 Authorization Server Metadata - Required by ChatGPT"""
    print("🔍 OAuth authorization server metadata requested")
    
    if not is_user_auth_enabled():
        return {"error": "User authentication not enabled"}
    
    return {
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/oauth/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "userinfo_endpoint": f"{BASE_URL}/oauth/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "scopes_supported": ["read"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"]
    }

# ---- Core MCP Discovery - This is what ChatGPT reads ----
@app.get("/.well-known/mcp")
async def mcp_discovery():
    """MCP discovery endpoint with embedded OAuth configuration"""
    print("🔍 MCP discovery requested")
    
    if is_user_auth_enabled():
        # Embed OAuth configuration directly in MCP discovery
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
        "description": "Deep research connector for iManage Work API with user authentication",
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

# ---- Simple OAuth Endpoints ----
@app.get("/oauth/authorize")
async def oauth_authorize_endpoint(request: Request):
    """OAuth authorization endpoint - simplified"""
    print("🔐 OAuth authorization requested")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Get parameters
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    state = params.get("state")
    
    print(f"🔍 OAuth params: client_id={client_id}, redirect_uri={redirect_uri}, state={state}")
    
    # For simplified implementation, return a simple login form
    return HTMLResponse(f"""
    <html>
        <head>
            <title>iManage Authentication</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .form {{ background: #f5f5f5; padding: 20px; border-radius: 10px; max-width: 400px; margin: 0 auto; }}
                input {{ margin: 10px; padding: 10px; width: 200px; }}
                button {{ background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <h2>🔐 iManage Authentication</h2>
            <div class="form">
                <p>Please log in with your iManage credentials:</p>
                <form method="post" action="/oauth/authenticate">
                    <input type="hidden" name="redirect_uri" value="{redirect_uri or ''}" />
                    <input type="hidden" name="state" value="{state or ''}" />
                    <input type="text" name="username" placeholder="Username" required /><br>
                    <input type="password" name="password" placeholder="Password" required /><br>
                    <button type="submit">🔓 Login</button>
                </form>
            </div>
        </body>
    </html>
    """)

@app.post("/oauth/authenticate")
async def oauth_authenticate(
    username: str = Form(...),
    password: str = Form(...),
    redirect_uri: str = Form(""),
    state: str = Form("")
):
    """Handle OAuth authentication form submission"""
    print(f"🔐 OAuth authentication attempt for user: {username}")
    
    try:
        # Authenticate user with iManage
        session = await user_auth_manager.authenticate_user(username, password)
        session_id = list(user_auth_manager.user_sessions.keys())[-1]
        
        # Generate authorization code (simplified)
        auth_code = f"auth_{session_id[:16]}"
        
        print(f"✅ Authentication successful, redirecting with code: {auth_code}")
        
        # Redirect back to ChatGPT with authorization code
        if redirect_uri:
            separator = "&" if "?" in redirect_uri else "?"
            redirect_url = f"{redirect_uri}{separator}code={auth_code}&state={state}"
            return RedirectResponse(url=redirect_url)
        else:
            # If no redirect URI, show success page
            return HTMLResponse(f"""
            <html>
                <body>
                    <h2>✅ Authentication Successful!</h2>
                    <p>Authorization Code: {auth_code}</p>
                    <p>You can now close this window.</p>
                </body>
            </html>
            """)
        
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>❌ Authentication Failed</h2>
                <p>Error: {str(e)}</p>
                <p><a href="javascript:history.back()">Try Again</a></p>
            </body>
        </html>
        """, status_code=401)

@app.post("/oauth/token")
async def oauth_token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None)  # PKCE support
):
    """OAuth token endpoint - simplified with PKCE support"""
    print(f"🔐 OAuth token request: grant_type={grant_type}, code={code}, pkce={code_verifier is not None}")
    
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # For simplified implementation, just return a basic token
        # In real implementation, you'd validate the code and PKCE verifier
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
    
    # For simplified implementation, return basic user info
    return {
        "sub": "imanage_user",
        "name": "iManage User",
        "email": "user@imanage.com",
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
        "auth_mode": AUTH_MODE,
        "user_auth_enabled": is_user_auth_enabled()
    }

# ---- Startup Event ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up (Fixed Version)")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    print(f"🔐 Authentication Mode: {AUTH_MODE}")
    
    if is_user_auth_enabled():
        print(f"🌐 Base URL: {BASE_URL}")
        print(f"🔗 Authorization URL: {BASE_URL}/oauth/authorize")
        print(f"🎫 Token URL: {BASE_URL}/oauth/token")
        print("✅ Simplified OAuth endpoints configured")
    else:
        print("⚙️ Running in service account mode")
        # Test service authentication on startup
        try:
            await get_token()
            print("✅ Service account authentication test successful")
        except Exception as e:
            print(f"⚠️ Warning: Service account authentication test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting iManage Deep Research MCP Server (Fixed Version)...")
    
    # Use PORT environment variable (Render.com sets this automatically)
    port = int(os.getenv("PORT", 10000))
    print(f"🌐 Server will bind to port: {port}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )