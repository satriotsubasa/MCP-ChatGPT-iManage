"""
OAuth authentication endpoints for user authentication
"""

import time
import secrets
from typing import Dict, Any
from fastapi import Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse

from config import CLIENT_ID, CLIENT_SECRET, is_user_auth_enabled, BASE_URL
from auth import user_auth_manager

async def oauth_authorize(request: Request) -> RedirectResponse:
    """Handle OAuth authorization request"""
    print("🔐 OAuth authorization requested")
    
    if not is_user_auth_enabled():
        raise HTTPException(status_code=404, detail="User authentication not enabled")
    
    # Extract parameters
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    state = params.get("state")
    response_type = params.get("response_type")
    
    print(f"🔍 OAuth params: client_id={client_id}, redirect_uri={redirect_uri}, state={state}")
    
    # Validate parameters
    if not client_id or client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="Invalid client_id")
    
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type")
    
    # Generate session ID for this authorization attempt
    session_id = secrets.token_urlsafe(32)
    
    # Store the original request for later
    user_auth_manager.oauth_states[session_id] = {
        "redirect_uri": redirect_uri,
        "state": state,
        "created_at": time.time(),
        "expires_at": time.time() + 600  # 10 minutes
    }
    
    # Redirect to iManage authorization
    imanage_auth_url = user_auth_manager.get_authorization_url(session_id)
    print(f"🔀 Redirecting to iManage: {imanage_auth_url}")
    
    return RedirectResponse(url=imanage_auth_url)

async def oauth_callback(request: Request) -> HTMLResponse:
    """Handle OAuth callback from iManage"""
    print("🔄 OAuth callback received")
    
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    
    if error:
        print(f"❌ OAuth error: {error}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Error: {error}</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    if not code or not state:
        print("❌ Missing code or state in callback")
        return HTMLResponse("""
        <html>
            <body>
                <h2>Authentication Error</h2>
                <p>Missing authorization code or state parameter.</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=400)
    
    try:
        # Authenticate user with OAuth code
        user_session = await user_auth_manager.authenticate_with_oauth_code(code, state)
        
        print(f"✅ User authenticated successfully: {user_session.user_id}")
        
        # Return success page
        return HTMLResponse(f"""
        <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .success {{ color: green; }}
                    .user-info {{ background: #f0f0f0; padding: 20px; margin: 20px; border-radius: 10px; }}
                </style>
            </head>
            <body>
                <h2 class="success">✅ Authentication Successful!</h2>
                <div class="user-info">
                    <p><strong>User:</strong> {user_session.user_id}</p>
                    <p><strong>Connected to:</strong> iManage Deep Research</p>
                    <p><strong>Status:</strong> Ready for deep research</p>
                </div>
                <p>You can now close this window and return to ChatGPT.</p>
                <p>Your iManage documents are now accessible for deep research with proper access controls.</p>
                <script>
                    // Auto-close after 5 seconds
                    setTimeout(function() {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
        </html>
        """)
        
    except Exception as e:
        print(f"❌ OAuth callback failed: {str(e)}")
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Authentication Failed</h2>
                <p>Error: {str(e)}</p>
                <p>Please close this window and try again.</p>
            </body>
        </html>
        """, status_code=401)

async def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(None),
    refresh_token: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...)
) -> Dict[str, Any]:
    """Handle OAuth token request"""
    print(f"🔐 OAuth token request: grant_type={grant_type}")
    
    # Validate client credentials
    if client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # For MCP integration, return a dummy token since we handle auth differently
        return {
            "access_token": "mcp_authenticated",
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": "read"
        }
    
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Missing refresh token")
        
        return {
            "access_token": "mcp_refreshed",
            "token_type": "bearer", 
            "expires_in": 3600,
            "scope": "read"
        }
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant type")

async def oauth_userinfo(request: Request) -> Dict[str, Any]:
    """Handle OAuth user info request"""
    print("👤 OAuth userinfo requested")
    
    # In a real implementation, you'd validate the token from the Authorization header
    return {
        "sub": "imanage_user",
        "name": "iManage User",
        "email": "user@imanage.com",
        "preferred_username": "imanage_user"
    }

async def get_oauth_metadata() -> Dict[str, Any]:
    """Return OAuth server metadata"""
    base_url = BASE_URL.rstrip('/')
    
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "userinfo_endpoint": f"{base_url}/oauth/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "scopes_supported": ["read", "admin"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"]
    }