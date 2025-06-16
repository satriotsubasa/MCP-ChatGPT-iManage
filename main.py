#!/usr/bin/env python3
"""
iManage Deep Research MCP Server for ChatGPT Integration - Main Server File
Updated with User Authentication Support

This is the main server file that coordinates all modules.
The server supports both user authentication and service account modes.

Modules:
- config.py: Configuration and environment variables (updated for user auth)
- auth.py: Authentication and token management (updated with user auth)
- oauth_endpoints.py: OAuth 2.0 authentication endpoints (new)
- document_processor.py: Document text extraction (PDF, Word, Excel, etc.)
- search_service.py: Search functionality (title and keyword searches)
- document_service.py: Document fetching and content retrieval
- mcp_handlers.py: MCP protocol handlers (updated for user context)
- test_endpoints.py: Test and diagnostic endpoints

Environment Variables Required:
- AUTH_MODE: "user" or "service" (authentication mode)
- AUTH_URL_PREFIX: iManage authentication URL prefix
- URL_PREFIX: iManage API URL prefix 
- CLIENT_ID: OAuth client ID
- CLIENT_SECRET: OAuth client secret
- CUSTOMER_ID: iManage customer ID
- LIBRARY_ID: iManage library ID
- BASE_URL: Server base URL (required for user auth)
- SERVICE_USERNAME: Service account username (for service mode)
- SERVICE_PASSWORD: Service account password (for service mode)
"""

import time
import os
import logging
import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Import our modules
from config import validate_config, CUSTOMER_ID, LIBRARY_ID, is_user_auth_enabled, AUTH_MODE, BASE_URL
from auth import get_token, user_auth_manager
from mcp_handlers import handle_mcp_request
from test_endpoints import router as test_router
from oauth_endpoints import oauth_authorize, oauth_callback, oauth_token, oauth_userinfo, get_oauth_metadata

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
        "modules": [
            "config", "auth", "oauth_endpoints", "document_processor", 
            "search_service", "document_service", "mcp_handlers", "test_endpoints"
        ],
        "endpoints": {
            "mcp": "POST /",
            "oauth_authorize": "GET /oauth/authorize" if is_user_auth_enabled() else None,
            "oauth_callback": "GET /oauth/callback" if is_user_auth_enabled() else None,
            "oauth_token": "POST /oauth/token",
            "health": "GET /health",
            "test": "GET /test",
            "test_auth": "GET /test/auth"
        }
    }

# ---- OAuth Endpoints (User Authentication) ----
@app.get("/oauth/authorize")
async def oauth_authorize_endpoint(request: Request):
    """OAuth authorization endpoint"""
    return await oauth_authorize(request)

@app.get("/oauth/callback")
async def oauth_callback_endpoint(request: Request):
    """OAuth callback endpoint"""
    return await oauth_callback(request)

@app.post("/oauth/token")
async def oauth_token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(None),
    refresh_token: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...)
):
    """OAuth token endpoint"""
    return await oauth_token(grant_type, code, refresh_token, client_id, client_secret)

@app.get("/oauth/userinfo")
async def oauth_userinfo_endpoint(request: Request):
    """OAuth user info endpoint"""
    return await oauth_userinfo(request)

@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata():
    """OAuth server metadata"""
    if not is_user_auth_enabled():
        return {"error": "User authentication not enabled"}
    return await get_oauth_metadata()

# ---- User Management Endpoints ----
@app.post("/auth/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    """Direct user login (alternative to OAuth)"""
    if not is_user_auth_enabled():
        return {"success": False, "error": "User authentication not enabled"}
    
    try:
        session = await user_auth_manager.authenticate_user(username, password)
        session_id = list(user_auth_manager.user_sessions.keys())[-1]  # Get latest session
        
        return {
            "success": True,
            "session_id": session_id,
            "user_id": session.user_id,
            "expires_at": session.expires_at
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/auth/status")
async def auth_status_endpoint(request: Request):
    """Check authentication status"""
    if not is_user_auth_enabled():
        return {
            "authenticated": True,
            "auth_mode": "service",
            "message": "Service account authentication"
        }
    
    # Extract session info from request
    session_id = request.headers.get("X-Session-ID")
    user_info = None
    is_authenticated = False
    
    if session_id and session_id in user_auth_manager.user_sessions:
        user_info = user_auth_manager.get_user_info(session_id)
        is_authenticated = True
    
    return {
        "authenticated": is_authenticated,
        "auth_mode": "user",
        "user_info": user_info,
        "active_sessions": len(user_auth_manager.user_sessions),
        "message": "User authentication required" if not is_authenticated else "User authenticated"
    }

# ---- MCP Discovery Endpoints ----
@app.get("/.well-known/mcp")
async def mcp_discovery():
    """MCP discovery endpoint"""
    print("🔍 MCP discovery requested")
    
    auth_config = {
        "type": "oauth2" if is_user_auth_enabled() else "none"
    }
    
    if is_user_auth_enabled():
        auth_config.update({
            "authorization_url": f"{BASE_URL}/oauth/authorize",
            "token_url": f"{BASE_URL}/oauth/token"
        })
    
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

@app.get("/manifest.json")
async def manifest():
    """Application manifest for ChatGPT"""
    print("📋 Manifest requested")
    
    auth_config = {
        "type": "oauth" if is_user_auth_enabled() else "none"
    }
    
    if is_user_auth_enabled():
        auth_config.update({
            "authorization_url": f"{BASE_URL}/oauth/authorize",
            "token_url": f"{BASE_URL}/oauth/token",
            "scope": "read"
        })
    
    return {
        "schema_version": "v1",
        "name_for_model": "imanage_deep_research",
        "name_for_human": "iManage Deep Research",
        "description_for_model": "Search and retrieve documents from iManage Work for deep research analysis with user authentication",
        "description_for_human": "Access your iManage documents for comprehensive research with proper access controls",
        "auth": auth_config,
        "api": {
            "type": "mcp",
            "url": "/",
            "has_user_authentication": is_user_auth_enabled()
        },
        "logo_url": "",
        "contact_email": "",
        "legal_info_url": ""
    }

@app.get("/.well-known/ai-plugin.json")
async def ai_plugin():
    """AI Plugin manifest"""
    print("🤖 AI Plugin manifest requested")
    return await manifest()

# ---- ChatGPT MCP OAuth Configuration Endpoint ----
@app.get("/oauth_config")
async def oauth_config():
    """OAuth configuration endpoint for ChatGPT MCP connector"""
    print("🔗 ChatGPT MCP OAuth config requested")
    
    if not is_user_auth_enabled():
        return {
            "error": "User authentication not enabled",
            "auth_mode": "service"
        }
    
    return {
        "authorization_url": f"{BASE_URL}/oauth/authorize",
        "token_url": f"{BASE_URL}/oauth/token", 
        "userinfo_url": f"{BASE_URL}/oauth/userinfo",
        "scopes": ["read"],
        "client_id_required": True,
        "client_secret_required": True
    }

# ---- Legacy OAuth Endpoints for Backward Compatibility ----
@app.get("/connectors/oauth")
async def connectors_oauth_legacy(request: Request):
    """Legacy ChatGPT connector OAuth endpoint"""
    print("🔗 Legacy ChatGPT connector OAuth request")
    
    if not is_user_auth_enabled():
        base_url = str(request.base_url).rstrip('/')
        return {
            "authorization_url": f"{base_url}/oauth/authorize",
            "token_url": f"{base_url}/oauth/token",
            "userinfo_url": f"{base_url}/oauth/userinfo",
            "scopes": [],
            "auto_approved": True
        }
    
    return {
        "authorization_url": f"{BASE_URL}/oauth/authorize",
        "token_url": f"{BASE_URL}/oauth/token",
        "userinfo_url": f"{BASE_URL}/oauth/userinfo",
        "scopes": ["read"],
        "requires_auth": True
    }

@app.post("/connectors/oauth")
async def connectors_oauth_post_legacy():
    """Legacy ChatGPT connector OAuth POST"""
    return await oauth_token_endpoint("authorization_code", None, None, "dummy", "dummy")

# ---- Legacy Endpoints ----
@app.get("/mcp/tools")
async def get_tools_legacy():
    """Legacy endpoint for testing"""
    print("🔄 Legacy tools endpoint accessed")
    return {
        "message": "This is a legacy endpoint. Use POST / with proper MCP protocol.",
        "mcp_format": "POST / with method='tools/list'",
        "version": "2.1.0",
        "auth_mode": AUTH_MODE,
        "tools": [
            {"name": "search", "description": "Search iManage documents"},
            {"name": "fetch", "description": "Fetch document content"}
        ]
    }

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

# ---- Background Tasks ----
async def session_cleanup_task():
    """Background task to cleanup expired sessions"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            if is_user_auth_enabled():
                user_auth_manager.cleanup_expired_sessions()
        except Exception as e:
            print(f"⚠️ Session cleanup error: {str(e)}")

# ---- Startup Event ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up (User Auth Version)")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    print(f"🔐 Authentication Mode: {AUTH_MODE}")
    print("📦 Modules loaded:")
    print("   - config.py: Configuration management (updated)")
    print("   - auth.py: Authentication and token caching (updated)")
    print("   - oauth_endpoints.py: OAuth 2.0 endpoints (new)")
    print("   - document_processor.py: Document text extraction")
    print("   - search_service.py: Search functionality")
    print("   - document_service.py: Document fetching")
    print("   - mcp_handlers.py: MCP protocol handling")
    print("   - test_endpoints.py: Test and diagnostic endpoints")
    
    if is_user_auth_enabled():
        print(f"🌐 OAuth Base URL: {BASE_URL}")
        print(f"🔗 Authorization URL: {BASE_URL}/oauth/authorize")
        print(f"🎫 Token URL: {BASE_URL}/oauth/token")
        
        # Start session cleanup task
        asyncio.create_task(session_cleanup_task())
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
    
    print("🚀 Starting iManage Deep Research MCP Server (User Auth)...")
    print("📋 Server Structure:")
    print("├── main.py (main - updated)")
    print("├── config.py (updated)")
    print("├── auth.py (updated)")
    print("├── oauth_endpoints.py (new)")
    print("├── document_processor.py")
    print("├── search_service.py")
    print("├── document_service.py")
    print("├── mcp_handlers.py")
    print("└── test_endpoints.py")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 10000)),
        log_level="info"
    )