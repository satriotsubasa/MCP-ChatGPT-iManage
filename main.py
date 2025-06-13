#!/usr/bin/env python3
"""
iManage Deep Research MCP Server for ChatGPT Integration - Main Server File

This is the main server file that coordinates all modules.
The server has been modularized for better maintainability.

Modules:
- config.py: Configuration and environment variables
- auth.py: Authentication and token management
- document_processor.py: Document text extraction (PDF, Word, Excel, etc.)
- search_service.py: Search functionality (title and keyword searches)
- document_service.py: Document fetching and content retrieval
- mcp_handlers.py: MCP protocol handlers
- test_endpoints.py: Test and diagnostic endpoints

Environment Variables Required:
- AUTH_URL_PREFIX: iManage authentication URL prefix
- URL_PREFIX: iManage API URL prefix 
- USERNAME: iManage username
- PASSWORD: iManage password
- CLIENT_ID: OAuth client ID
- CLIENT_SECRET: OAuth client secret
- CUSTOMER_ID: iManage customer ID
- LIBRARY_ID: iManage library ID (default library to search)
"""

import time
import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Import our modules
from config import validate_config, CUSTOMER_ID, LIBRARY_ID
from auth import get_token
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

app = FastAPI(title="iManage Deep Research MCP Server")

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
    """Main MCP protocol handler"""
    return await handle_mcp_request(request)

@app.get("/")
async def root():
    """Health check and basic info endpoint for GET requests"""
    print("🏥 Health check requested (GET)")
    return {
        "name": "iManage Deep Research MCP Server",
        "version": "1.0.0",
        "description": "MCP server for ChatGPT integration with iManage Work API",
        "protocol": "MCP/1.0",
        "capabilities": ["tools"],
        "status": "healthy",
        "authentication": "none",
        "modules": [
            "config", "auth", "document_processor", "search_service", 
            "document_service", "mcp_handlers", "test_endpoints"
        ],
        "endpoints": {
            "mcp": "POST /",
            "health": "GET /health",
            "test": "GET /test",
            "test_search": "GET /test/search",
            "test_document": "GET /test/document/{doc_id}",
            "test_processing": "GET /test/processing"
        }
    }

# ---- MCP Discovery Endpoints ----
@app.get("/.well-known/mcp")
async def mcp_discovery():
    """MCP discovery endpoint"""
    print("🔍 MCP discovery requested")
    return {
        "version": "1.0.0",
        "name": "iManage Deep Research MCP Server",
        "description": "Deep research connector for iManage Work API",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False
        },
        "authentication": {
            "type": "none"
        },
        "endpoint": {
            "url": "/",
            "method": "POST"
        }
    }

@app.options("/")
async def options_handler():
    """Handle CORS preflight requests"""
    print("🔄 CORS preflight request")
    return {
        "Allow": "GET, POST, OPTIONS",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }

# ---- Manifest and Discovery Endpoints ----
@app.get("/manifest.json")
async def manifest():
    """Application manifest for ChatGPT"""
    print("📋 Manifest requested")
    return {
        "schema_version": "v1",
        "name_for_model": "imanage_deep_research",
        "name_for_human": "iManage Deep Research",
        "description_for_model": "Search and retrieve documents from iManage Work for deep research analysis",
        "description_for_human": "Access your iManage documents for comprehensive research",
        "auth": {
            "type": "none"
        },
        "api": {
            "type": "mcp",
            "url": "/",
            "has_user_authentication": False
        },
        "logo_url": "",
        "contact_email": "",
        "legal_info_url": ""
    }

@app.get("/.well-known/ai-plugin.json")
async def ai_plugin():
    """AI Plugin manifest"""
    print("🤖 AI Plugin manifest requested")
    return {
        "schema_version": "v1",
        "name_for_model": "imanage_deep_research",
        "name_for_human": "iManage Deep Research",
        "description_for_model": "Search and retrieve documents from iManage Work for deep research analysis. No authentication required.",
        "description_for_human": "Access your iManage documents for comprehensive research",
        "auth": {
            "type": "none"
        },
        "api": {
            "type": "mcp",
            "url": "/",
            "has_user_authentication": False
        }
    }

# ---- OAuth/Connector Endpoints ----
@app.get("/oauth/authorize")
async def oauth_authorize():
    """Handle OAuth authorization - auto-approve since no real auth needed"""
    print("🔓 OAuth authorize request - auto-approving")
    return {
        "code": "auto_approved",
        "state": "no_auth_required"
    }

@app.post("/oauth/token") 
async def oauth_token():
    """Handle OAuth token request - return dummy token"""
    print("🔓 OAuth token request - returning dummy token")
    return {
        "access_token": "no_auth_required",
        "token_type": "bearer",
        "expires_in": 3600,
        "scope": "read"
    }

@app.get("/oauth/userinfo")
async def oauth_userinfo():
    """Handle OAuth user info request"""
    print("🔓 OAuth userinfo request")
    return {
        "sub": "imanage_user",
        "name": "iManage User",
        "email": "user@imanage.com"
    }

# ---- ChatGPT Connector Specific Endpoints ----
@app.get("/connectors/oauth")
async def connectors_oauth(request: Request):
    """Handle ChatGPT connector OAuth flow"""
    print("🔗 ChatGPT connector OAuth request")
    base_url = str(request.base_url).rstrip('/')
    return {
        "authorization_url": f"{base_url}/oauth/authorize",
        "token_url": f"{base_url}/oauth/token",
        "userinfo_url": f"{base_url}/oauth/userinfo",
        "scopes": [],
        "auto_approved": True
    }

@app.post("/connectors/oauth")
async def connectors_oauth_post():
    """Handle ChatGPT connector OAuth POST"""
    print("🔗 ChatGPT connector OAuth POST request")
    return {
        "access_token": "no_auth_required",
        "token_type": "bearer",
        "expires_in": 3600
    }

# ---- Authentication Endpoints ----
@app.get("/auth/status")
async def auth_status():
    """Return authentication status - no auth required"""
    print("🔓 Authentication status requested")
    return {
        "authenticated": True,
        "type": "none",
        "message": "No authentication required - server handles iManage auth internally"
    }

@app.post("/auth/callback")
async def auth_callback():
    """Handle auth callback - always successful since no auth needed"""
    print("✅ Auth callback - auto-success (no auth required)")
    return {
        "success": True,
        "authenticated": True,
        "message": "Authentication successful"
    }

# ---- Handle Any Auth-Related Requests ----
@app.get("/auth/{path:path}")
async def auth_catch_all(path: str):
    """Catch all auth requests and return success"""
    print(f"🔓 Auth catch-all request: {path}")
    return {
        "authenticated": True,
        "status": "success",
        "message": "No authentication required"
    }

@app.post("/auth/{path:path}")
async def auth_catch_all_post(path: str):
    """Catch all auth POST requests and return success"""
    print(f"🔓 Auth catch-all POST request: {path}")
    return {
        "authenticated": True,
        "status": "success",
        "message": "No authentication required"
    }

# ---- Legacy Endpoints for Testing ----
@app.get("/mcp/tools")
async def get_tools_legacy():
    """Legacy endpoint for testing - redirects to proper MCP format"""
    print("🔄 Legacy tools endpoint accessed - redirecting to MCP format")
    return {
        "message": "This is a legacy endpoint. Use POST / with proper MCP protocol.",
        "mcp_format": "POST / with method='tools/list'",
        "tools": [
            {
                "name": "search",
                "description": "Search iManage documents"
            },
            {
                "name": "fetch", 
                "description": "Fetch document content"
            }
        ]
    }

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    print("🩺 Health check via /health")
    return {"status": "healthy", "timestamp": time.time()}

# ---- Startup Event ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    print("📦 Modules loaded:")
    print("   - config.py: Configuration management")
    print("   - auth.py: Authentication and token caching")
    print("   - document_processor.py: Document text extraction")
    print("   - search_service.py: Search functionality")
    print("   - document_service.py: Document fetching")
    print("   - mcp_handlers.py: MCP protocol handling")
    print("   - test_endpoints.py: Test and diagnostic endpoints")
    
    # Test authentication on startup
    try:
        await get_token()
        print("✅ Initial authentication test successful")
    except Exception as e:
        print(f"⚠️ Warning: Initial authentication test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting iManage Deep Research MCP Server...")
    print("📋 Server Structure:")
    print("├── server.py (main)")
    print("├── config.py")
    print("├── auth.py")
    print("├── document_processor.py")
    print("├── search_service.py")
    print("├── document_service.py")
    print("├── mcp_handlers.py")
    print("└── test_endpoints.py")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )