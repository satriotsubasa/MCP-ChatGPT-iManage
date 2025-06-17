#!/usr/bin/env python3
"""
iManage Deep Research MCP Server - Hybrid Authentication
Uses service account for API calls but captures user context for access control
"""

import time
import os
import logging
import asyncio
from urllib.parse import urlencode, urlparse, parse_qs
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
    description="MCP server with hybrid authentication for ChatGPT integration with iManage Work API",
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
        "description": "MCP server with hybrid authentication for ChatGPT integration with iManage Work API",
        "protocol": "MCP/1.0",
        "capabilities": ["tools"],
        "status": "healthy",
        "authentication": "hybrid" if is_user_auth_enabled() else "service",
        "auth_mode": AUTH_MODE,
        "sso_info": "SAML SSO enabled - using hybrid authentication approach",
        "endpoints": {
            "mcp": "POST /",
            "oauth_authorize": "GET /oauth/authorize" if is_user_auth_enabled() else None,
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
    
    return {
        "client_id": "chatgpt_mcp_client",
        "client_secret": "chatgpt_mcp_secret",
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,
        "redirect_uris": [
            "https://chatgpt.com/oauth/callback",
            "https://chat.openai.com/oauth/callback"
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
        "description": "Deep research connector for iManage Work API with hybrid authentication",
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

# ---- Simple OAuth Endpoints (for ChatGPT compatibility) ----
@app.get("/oauth/authorize")
async def oauth_authorize_endpoint(request: Request):
    """OAuth authorization - simplified for SAML SSO environment"""
    print("🔐 OAuth authorization requested (SAML SSO environment)")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Get parameters from ChatGPT
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    state = params.get("state")
    
    print(f"🔍 OAuth params: client_id={client_id}, redirect_uri={redirect_uri}")
    
    # For SAML SSO environment, show a user identification form
    # This allows us to capture user identity without dealing with SAML complexity
    return HTMLResponse(f"""
    <html>
        <head>
            <title>iManage User Identification</title>
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0; padding: 0; min-height: 100vh;
                    display: flex; align-items: center; justify-content: center;
                }}
                .container {{ 
                    background: white; border-radius: 15px; 
                    padding: 40px; box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    max-width: 400px; width: 90%;
                }}
                .logo {{ text-align: center; margin-bottom: 30px; }}
                .logo h1 {{ color: #333; margin: 0; font-size: 24px; }}
                .logo p {{ color: #666; margin: 5px 0; font-size: 14px; }}
                .form-group {{ margin-bottom: 20px; }}
                label {{ display: block; margin-bottom: 8px; color: #333; font-weight: 500; }}
                input[type="email"] {{ 
                    width: 100%; padding: 12px; border: 2px solid #e1e5e9;
                    border-radius: 8px; font-size: 16px; transition: border-color 0.3s;
                }}
                input[type="email"]:focus {{ 
                    outline: none; border-color: #667eea; 
                }}
                .btn {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; padding: 14px 30px; border: none; 
                    border-radius: 8px; font-size: 16px; cursor: pointer;
                    width: 100%; transition: transform 0.2s;
                }}
                .btn:hover {{ transform: translateY(-2px); }}
                .info {{ 
                    background: #f8f9fa; border-radius: 8px; padding: 15px; 
                    margin-bottom: 20px; border-left: 4px solid #667eea;
                }}
                .info p {{ margin: 0; color: #555; font-size: 14px; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">
                    <h1>🔐 iManage Deep Research</h1>
                    <p>User Identification</p>
                </div>
                
                <div class="info">
                    <p><strong>SAML SSO Detected:</strong> Since your organization uses SAML SSO, please enter your email address to identify yourself for document access control.</p>
                </div>
                
                <form method="get" action="/oauth/identify">
                    <input type="hidden" name="redirect_uri" value="{redirect_uri or ''}" />
                    <input type="hidden" name="state" value="{state or ''}" />
                    <input type="hidden" name="client_id" value="{client_id or ''}" />
                    
                    <div class="form-group">
                        <label for="email">Your Email Address:</label>
                        <input type="email" id="email" name="email" placeholder="your.email@riotinto.com" required />
                    </div>
                    
                    <button type="submit" class="btn">🔍 Continue to Deep Research</button>
                </form>
                
                <div style="margin-top: 20px; text-align: center; color: #666; font-size: 12px;">
                    <p>Your email will be used to ensure you only access documents you have permission to view.</p>
                </div>
            </div>
        </body>
    </html>
    """)

@app.get("/oauth/identify")
async def oauth_identify(
    email: str,
    redirect_uri: str = "",
    state: str = "",
    client_id: str = ""
):
    """Handle user identification for SAML SSO environment"""
    print(f"🔐 User identification: {email}")
    
    try:
        # Validate email format and domain
        if not email or "@" not in email:
            raise ValueError("Please enter a valid email address")
        
        # You could add domain validation here
        # if not email.endswith("@riotinto.com"):
        #     raise ValueError("Please use your Rio Tinto email address")
        
        # Generate authorization code with user context (simplified format for ChatGPT)
        auth_code = f"auth{int(time.time())}{email.split('@')[0][:8]}"
        
        # Store user context for later use (simple in-memory storage)
        # In production, use a proper database
        user_auth_manager.oauth_states[auth_code] = {
            "email": email,
            "created_at": time.time(),
            "expires_at": time.time() + 3600  # 1 hour
        }
        
        print(f"✅ User identified: {email}, auth_code: {auth_code}")
        
        # Redirect back to ChatGPT with authorization code
        if redirect_uri:
            # Ensure proper URL encoding
            from urllib.parse import urlencode, urlparse, parse_qs
            
            # Parse the redirect URI to add parameters correctly
            parsed_uri = urlparse(redirect_uri)
            query_params = parse_qs(parsed_uri.query) if parsed_uri.query else {}
            
            # Add our parameters
            query_params['code'] = [auth_code]
            query_params['state'] = [state]
            
            # Rebuild the URL
            new_query = urlencode(query_params, doseq=True)
            redirect_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}?{new_query}"
            
            print(f"✅ Redirecting to ChatGPT: {redirect_url}")
            return RedirectResponse(url=redirect_url)
        else:
            return HTMLResponse(f"""
            <html>
                <head>
                    <title>Identification Successful</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                        .success {{ color: green; font-size: 18px; }}
                    </style>
                </head>
                <body>
                    <h2 class="success">✅ Identification Successful!</h2>
                    <p>Welcome, {email}</p>
                    <p>You can now close this window and return to ChatGPT.</p>
                    <p>Your document access will be filtered based on your permissions.</p>
                    <script>
                        setTimeout(function() {{ window.close(); }}, 3000);
                    </script>
                </body>
            </html>
            """)
        
    except Exception as e:
        print(f"❌ User identification failed: {str(e)}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>❌ Identification Failed</h2>
                <p>Error: {str(e)}</p>
                <p><a href="javascript:history.back()">Try Again</a></p>
            </body>
        </html>
        """, status_code=400)

@app.post("/oauth/token")
async def oauth_token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None)
):
    """OAuth token endpoint - returns token with user context"""
    print(f"🔐 OAuth token request: grant_type={grant_type}, code={code}")
    
    # Accept dynamic client credentials
    valid_clients = [
        ("chatgpt_mcp_client", "chatgpt_mcp_secret"),
        ("mcp_client", "mcp_secret"),
    ]
    
    client_valid = any(client_id == cid and client_secret == csec for cid, csec in valid_clients)
    
    if not client_valid:
        print(f"❌ Invalid client credentials: {client_id}")
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # Get user context from authorization code
        user_context = user_auth_manager.oauth_states.get(code, {})
        user_email = user_context.get("email", "unknown")
        
        print(f"✅ Token issued for user: {user_email}")
        
        return {
            "access_token": f"mcp_token_{code}",
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": "read",
            "user_email": user_email  # Include user context
        }
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant type")

@app.get("/oauth/userinfo")
async def oauth_userinfo_endpoint(request: Request):
    """OAuth user info endpoint"""
    print("👤 OAuth userinfo requested")
    
    # Extract user info from access token if available
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer mcp_token_"):
        token_code = auth_header.replace("Bearer mcp_token_", "")
        user_context = user_auth_manager.oauth_states.get(token_code, {})
        user_email = user_context.get("email", "user@riotinto.com")
    else:
        user_email = "user@riotinto.com"
    
    return {
        "sub": user_email,
        "name": user_email.split("@")[0].title(),
        "email": user_email,
        "preferred_username": user_email
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
        "auth_mode": f"{AUTH_MODE}_hybrid",
        "sso_compatible": True,
        "user_auth_enabled": is_user_auth_enabled()
    }

# ---- Startup Event ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up (Hybrid Authentication)")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    print(f"🔐 Authentication Mode: {AUTH_MODE} (Hybrid)")
    print("🔒 SAML SSO Compatible: User identification + Service account API access")
    
    if is_user_auth_enabled():
        print(f"🌐 Base URL: {BASE_URL}")
        print("✅ Hybrid authentication configured for SAML SSO environment")
    else:
        print("⚙️ Running in service account mode")
        try:
            await get_token()
            print("✅ Service account authentication test successful")
        except Exception as e:
            print(f"⚠️ Warning: Service account authentication test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting iManage Deep Research MCP Server (Hybrid Auth)...")
    
    port = int(os.getenv("PORT", 10000))
    print(f"🌐 Server will bind to port: {port}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )