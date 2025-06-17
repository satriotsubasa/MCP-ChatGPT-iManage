#!/usr/bin/env python3
"""
iManage Deep Research MCP Server for ChatGPT Integration - Fixed Version
"""

import time
import os
import logging
import asyncio
from urllib.parse import urlencode
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

# Import our modules
from config import validate_config, CUSTOMER_ID, LIBRARY_ID, is_user_auth_enabled, AUTH_MODE, BASE_URL, CLIENT_ID, AUTH_URL_PREFIX
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
        "registration_endpoint": f"{BASE_URL}/oauth/register",  # Dynamic client registration
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "scopes_supported": ["read"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256"]
    }

# ---- Dynamic OAuth Client Registration Endpoint ----
@app.post("/oauth/register")
async def oauth_register():
    """Dynamic OAuth Client Registration endpoint"""
    print("🔐 OAuth client registration requested")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # For ChatGPT MCP integration, return a simplified client registration
    return {
        "client_id": "chatgpt_mcp_client",
        "client_secret": "chatgpt_mcp_secret",
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,  # Never expires
        "redirect_uris": [
            "https://chatgpt.com/oauth/callback",
            "https://chat.openai.com/oauth/callback"
        ],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "scope": "read",
        "token_endpoint_auth_method": "client_secret_post"
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
    """OAuth authorization endpoint - redirect to iManage"""
    print("🔐 OAuth authorization requested")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Get parameters from ChatGPT
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    state = params.get("state")
    code_challenge = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method")
    
    print(f"🔍 OAuth params: client_id={client_id}, redirect_uri={redirect_uri}, state={state}")
    
    # Store the original ChatGPT request for later use
    if state:
        user_auth_manager.oauth_states[state] = {
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "created_at": time.time(),
            "expires_at": time.time() + 600  # 10 minutes
        }
    
    # Build iManage OAuth authorization URL
    imanage_auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,  # Your iManage client ID
        "redirect_uri": f"{BASE_URL}/oauth/callback",  # Your server's callback
        "scope": "admin",
        "state": state  # Pass through the state from ChatGPT
    }
    
    # Build the query string
    from urllib.parse import urlencode
    query_string = urlencode(imanage_auth_params)
    imanage_auth_url = f"{AUTH_URL_PREFIX}/oauth2/authorize?{query_string}"
    
    print(f"🔀 Redirecting to iManage: {imanage_auth_url}")
    
    # Redirect user to official iManage login page
    return RedirectResponse(url=imanage_auth_url)

@app.get("/oauth/callback")
async def oauth_callback_endpoint(request: Request):
    """OAuth callback from iManage - exchange code and redirect back to ChatGPT"""
    print("🔄 OAuth callback from iManage received")
    
    params = dict(request.query_params)
    code = params.get("code")  # Authorization code from iManage
    state = params.get("state")  # State from original ChatGPT request
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
        print("❌ Missing code or state from iManage callback")
        return HTMLResponse("""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Missing authorization code or state from iManage.</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    # Get the original ChatGPT request details
    if state not in user_auth_manager.oauth_states:
        print(f"❌ Invalid or expired state: {state}")
        return HTMLResponse("""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Invalid or expired authentication session.</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    chatgpt_request = user_auth_manager.oauth_states[state]
    
    try:
        # Exchange iManage authorization code for access token
        from config import AUTH_URL_PREFIX, CLIENT_ID, CLIENT_SECRET
        import httpx
        
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
            token_info = token_response.json()
        
        # Store user session (optional - for your internal use)
        user_token = token_info["access_token"]
        print(f"✅ Successfully obtained iManage access token")
        
        # Generate authorization code for ChatGPT
        chatgpt_auth_code = f"chatgpt_{state[:16]}"
        
        # Clean up state
        del user_auth_manager.oauth_states[state]
        
        # Redirect back to ChatGPT with authorization code
        chatgpt_redirect_uri = chatgpt_request["redirect_uri"]
        if chatgpt_redirect_uri:
            separator = "&" if "?" in chatgpt_redirect_uri else "?"
            redirect_url = f"{chatgpt_redirect_uri}{separator}code={chatgpt_auth_code}&state={state}"
            
            print(f"🔀 Redirecting back to ChatGPT: {redirect_url}")
            return RedirectResponse(url=redirect_url)
        else:
            # Fallback success page
            return HTMLResponse(f"""
            <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                        .success {{ color: green; }}
                    </style>
                </head>
                <body>
                    <h2 class="success">✅ Authentication Successful!</h2>
                    <p>You have successfully logged in to iManage.</p>
                    <p>Authorization Code: {chatgpt_auth_code}</p>
                    <p>You can now close this window and return to ChatGPT.</p>
                    <script>
                        // Auto-close after 3 seconds
                        setTimeout(function() {{
                            window.close();
                        }}, 3000);
                    </script>
                </body>
            </html>
            """)
        
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
    code_verifier: str = Form(None)  # PKCE support
):
    """OAuth token endpoint - simplified with PKCE support and dynamic client registration"""
    print(f"🔐 OAuth token request: grant_type={grant_type}, code={code}, client_id={client_id}, pkce={code_verifier is not None}")
    
    # Accept both static and dynamic client credentials
    valid_clients = [
        ("chatgpt_mcp_client", "chatgpt_mcp_secret"),  # Dynamic registration
        ("mcp_client", "mcp_secret"),  # Static fallback
    ]
    
    client_valid = any(client_id == cid and client_secret == csec for cid, csec in valid_clients)
    
    if not client_valid:
        print(f"❌ Invalid client credentials: {client_id}")
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    
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