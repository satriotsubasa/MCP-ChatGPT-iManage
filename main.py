#!/usr/bin/env python3
"""
iManage Deep Research MCP Server for ChatGPT Integration

This MCP server enables ChatGPT to perform deep research using iManage Work API.
It provides search and fetch capabilities for documents stored in iManage.

Features:
- Title-based search
- Keyword search (full-text)
- Document retrieval and download
- Token-based authentication with caching
- Comprehensive logging with emojis
- Support for multiple search strategies

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

import asyncio
import httpx
import json
import os
import time
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="iManage Deep Research MCP Server")

# ---- Configuration ----
AUTH_URL_PREFIX = os.getenv("AUTH_URL_PREFIX", "")
URL_PREFIX = os.getenv("URL_PREFIX", "")
USERNAME = os.getenv("USERNAME", "")
PASSWORD = os.getenv("PASSWORD", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
CUSTOMER_ID = os.getenv("CUSTOMER_ID", "")
LIBRARY_ID = os.getenv("LIBRARY_ID", "")

# Validate required environment variables
required_vars = [
    "AUTH_URL_PREFIX", "URL_PREFIX", "USERNAME", "PASSWORD", 
    "CLIENT_ID", "CLIENT_SECRET", "CUSTOMER_ID", "LIBRARY_ID"
]

for var in required_vars:
    if not globals()[var]:
        raise ValueError(f"❌ Required environment variable {var} is not set")

print("✅ All required environment variables are configured")

# ---- Token cache ----
token_cache = {"token": None, "expires": 0}

async def get_token() -> str:
    """Get authentication token with caching"""
    if token_cache["token"] and token_cache["expires"] > time.time():
        print("🔓 Using cached access token")
        return token_cache["token"]
    
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
            token_cache["token"] = token_data["access_token"]
            token_cache["expires"] = time.time() + token_data.get("expires_in", 1800) - 60
            print("✅ Authentication successful")
            return token_data["access_token"]
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# ---- MCP Models ----
class SearchRequest(BaseModel):
    query: str

class FetchRequest(BaseModel):
    id: str

class MCPResponse(BaseModel):
    content: List[Dict[str, Any]]
    isError: bool = False

class SearchResult(BaseModel):
    id: str
    title: str
    text: str
    url: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

# ---- Core Search Functions ----
async def search_documents_title(query: str, limit: int = 20) -> List[SearchResult]:
    """Search documents by title/name"""
    print(f"🔍 Searching documents by title: '{query}'")
    
    token = await get_token()
    search_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/search"
    
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    # Search using POST with filters for title search
    search_body = {
        "limit": limit,
        "filters": {
            "name": query  # Search in document name/title
        },
        "profile_fields": {
            "document": [
                "id", "name", "document_number", "version", "author", 
                "edit_date", "create_date", "size", "type", "comments"
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(search_url, headers=headers, json=search_body)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for doc in data.get("data", []):
                doc_id = doc.get("id", "")
                title = doc.get("name", "Untitled Document")
                
                # Create text snippet from document metadata
                text_parts = []
                if doc.get("comments"):
                    text_parts.append(f"Comments: {doc['comments']}")
                if doc.get("author"):
                    text_parts.append(f"Author: {doc['author']}")
                if doc.get("type"):
                    text_parts.append(f"Type: {doc['type']}")
                if doc.get("edit_date"):
                    text_parts.append(f"Last Modified: {doc['edit_date']}")
                
                text = "; ".join(text_parts) if text_parts else "Document metadata"
                
                # Generate document URL for citations
                doc_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
                
                metadata = {
                    "document_number": str(doc.get("document_number", "")),
                    "version": str(doc.get("version", "")),
                    "size": str(doc.get("size", "")),
                    "search_type": "title"
                }
                
                results.append(SearchResult(
                    id=doc_id,
                    title=title,
                    text=text,
                    url=doc_url,
                    metadata=metadata
                ))
            
            print(f"📄 Found {len(results)} documents by title")
            return results
            
    except Exception as e:
        print(f"❌ Title search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Title search failed: {str(e)}")

async def search_documents_keyword(query: str, limit: int = 20) -> List[SearchResult]:
    """Search documents by keywords (full-text search)"""
    print(f"🔍 Searching documents by keywords: '{query}'")
    
    token = await get_token()
    search_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/search"
    
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    # Search using POST with filters for keyword/full-text search
    search_body = {
        "limit": limit,
        "filters": {
            "anywhere": query,  # Search anywhere in document content and metadata
            "body": query       # Also search in document body/content
        },
        "profile_fields": {
            "document": [
                "id", "name", "document_number", "version", "author", 
                "edit_date", "create_date", "size", "type", "comments"
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(search_url, headers=headers, json=search_body)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for doc in data.get("data", []):
                doc_id = doc.get("id", "")
                title = doc.get("name", "Untitled Document")
                
                # Create text snippet from document metadata
                text_parts = []
                if doc.get("comments"):
                    text_parts.append(f"Comments: {doc['comments']}")
                if doc.get("author"):
                    text_parts.append(f"Author: {doc['author']}")
                if doc.get("type"):
                    text_parts.append(f"Type: {doc['type']}")
                if doc.get("edit_date"):
                    text_parts.append(f"Last Modified: {doc['edit_date']}")
                
                text = "; ".join(text_parts) if text_parts else f"Document contains keyword: {query}"
                
                # Generate document URL for citations
                doc_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
                
                metadata = {
                    "document_number": str(doc.get("document_number", "")),
                    "version": str(doc.get("version", "")),
                    "size": str(doc.get("size", "")),
                    "search_type": "keyword",
                    "search_query": query
                }
                
                results.append(SearchResult(
                    id=doc_id,
                    title=title,
                    text=text,
                    url=doc_url,
                    metadata=metadata
                ))
            
            print(f"📄 Found {len(results)} documents by keywords")
            return results
            
    except Exception as e:
        print(f"❌ Keyword search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Keyword search failed: {str(e)}")

async def fetch_document_content(doc_id: str) -> Dict[str, Any]:
    """Fetch full document content and metadata"""
    print(f"📥 Fetching document content: {doc_id}")
    
    token = await get_token()
    
    # First get document metadata
    doc_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
    headers = {"X-Auth-Token": token}
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get document metadata
            response = await client.get(doc_url, headers=headers)
            response.raise_for_status()
            doc_data = response.json().get("data", {})
            
            title = doc_data.get("name", "Untitled Document")
            
            # Try to download document content
            download_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}/download"
            
            try:
                download_response = await client.get(download_url, headers=headers)
                download_response.raise_for_status()
                
                # Try to decode content as text if possible
                content_type = download_response.headers.get("content-type", "").lower()
                if "text" in content_type or "json" in content_type or "xml" in content_type:
                    document_text = download_response.text
                else:
                    # For binary files, provide metadata instead
                    document_text = f"Binary document ({content_type}). " + \
                                  f"Size: {download_response.headers.get('content-length', 'unknown')} bytes. " + \
                                  f"Use the download URL to access the full content."
                
                print(f"✅ Successfully fetched document: {title}")
                
            except Exception as download_error:
                print(f"⚠️ Could not download document content: {str(download_error)}")
                document_text = "Document content could not be retrieved. Document metadata available."
            
            # Build comprehensive document information
            text_parts = [document_text]
            
            if doc_data.get("comments"):
                text_parts.append(f"\n\nDocument Comments: {doc_data['comments']}")
            
            # Add metadata section
            metadata_section = "\n\nDocument Metadata:"
            if doc_data.get("author"):
                metadata_section += f"\nAuthor: {doc_data['author']}"
            if doc_data.get("type"):
                metadata_section += f"\nDocument Type: {doc_data['type']}"
            if doc_data.get("size"):
                metadata_section += f"\nSize: {doc_data['size']} bytes"
            if doc_data.get("edit_date"):
                metadata_section += f"\nLast Modified: {doc_data['edit_date']}"
            if doc_data.get("create_date"):
                metadata_section += f"\nCreated: {doc_data['create_date']}"
            
            text_parts.append(metadata_section)
            
            full_text = "\n".join(text_parts)
            
            # Generate document URL for citations
            doc_citation_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
            
            metadata = {
                "document_number": str(doc_data.get("document_number", "")),
                "version": str(doc_data.get("version", "")),
                "author": doc_data.get("author", ""),
                "type": doc_data.get("type", ""),
                "size": str(doc_data.get("size", "")),
                "download_url": download_url
            }
            
            return {
                "id": doc_id,
                "title": title,
                "text": full_text,
                "url": doc_citation_url,
                "metadata": metadata
            }
            
    except Exception as e:
        print(f"❌ Failed to fetch document {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch document: {str(e)}")

# ---- MCP Endpoints ----
@app.get("/")
async def root():
    """Health check endpoint"""
    print("🏥 Health check requested")
    return {"status": "healthy", "message": "iManage Deep Research MCP Server is running"}

@app.get("/mcp/tools")
async def get_tools():
    """Return MCP tool definitions for ChatGPT"""
    print("🛠️ Tools requested by ChatGPT")
    
    tools = {
        "tools": [
            {
                "name": "search",
                "description": "Search for documents in iManage using title search or keyword search. "
                              "For title search, use specific document names or titles. "
                              "For keyword search, use terms that might appear in document content. "
                              "The system will automatically determine the best search strategy. "
                              "You can search for legal documents, contracts, memos, emails, and other business documents. "
                              "Use specific terms like client names, matter names, document types, or legal concepts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string", 
                            "description": "Search query. Can be document titles, keywords, or phrases to search for in documents."
                        }
                    },
                    "required": ["query"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string", "description": "Document ID for fetching full content"},
                                    "title": {"type": "string", "description": "Document title or name"},
                                    "text": {"type": "string", "description": "Document summary or excerpt"},
                                    "url": {"type": "string", "description": "Document URL for citations"}
                                },
                                "required": ["id", "title", "text"]
                            }
                        }
                    },
                    "required": ["results"]
                }
            },
            {
                "name": "fetch",
                "description": "Retrieve the complete content and metadata of a specific document by its ID. "
                              "Use this after finding documents with search to get the full document content for analysis.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Document ID obtained from search results"}
                    },
                    "required": ["id"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Document ID"},
                        "title": {"type": "string", "description": "Document title"},
                        "text": {"type": "string", "description": "Complete document content and metadata"},
                        "url": {"type": "string", "description": "Document URL for citations"},
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "Document metadata including author, type, dates, etc."
                        }
                    },
                    "required": ["id", "title", "text"]
                }
            }
        ]
    }
    
    return tools

@app.post("/mcp/tools/search")
async def search_tool(request: SearchRequest):
    """MCP search tool endpoint"""
    print(f"🔍 Search request from ChatGPT: '{request.query}'")
    
    try:
        # Perform both title and keyword searches to maximize results
        title_results = await search_documents_title(request.query, limit=10)
        keyword_results = await search_documents_keyword(request.query, limit=10)
        
        # Combine and deduplicate results
        all_results = {}
        
        # Add title results first (higher priority)
        for result in title_results:
            all_results[result.id] = result
        
        # Add keyword results, avoiding duplicates
        for result in keyword_results:
            if result.id not in all_results:
                all_results[result.id] = result
        
        # Convert to list and limit to 20 total results
        final_results = list(all_results.values())[:20]
        
        # Convert to the expected format
        results_data = []
        for result in final_results:
            results_data.append({
                "id": result.id,
                "title": result.title,
                "text": result.text,
                "url": result.url,
                "metadata": result.metadata
            })
        
        response = MCPResponse(
            content=[{
                "type": "text",
                "text": json.dumps({"results": results_data}, indent=2)
            }]
        )
        
        print(f"✅ Returning {len(results_data)} search results to ChatGPT")
        return response
        
    except Exception as e:
        print(f"❌ Search tool failed: {str(e)}")
        return MCPResponse(
            content=[{
                "type": "text", 
                "text": f"Search failed: {str(e)}"
            }],
            isError=True
        )

@app.post("/mcp/tools/fetch")
async def fetch_tool(request: FetchRequest):
    """MCP fetch tool endpoint"""
    print(f"📥 Fetch request from ChatGPT: {request.id}")
    
    try:
        document = await fetch_document_content(request.id)
        
        response = MCPResponse(
            content=[{
                "type": "text",
                "text": json.dumps(document, indent=2)
            }]
        )
        
        print(f"✅ Returning document content to ChatGPT")
        return response
        
    except Exception as e:
        print(f"❌ Fetch tool failed: {str(e)}")
        return MCPResponse(
            content=[{
                "type": "text",
                "text": f"Fetch failed: {str(e)}"
            }],
            isError=True
        )

# ---- Additional Helper Endpoints ----
@app.get("/mcp/capabilities")
async def get_capabilities():
    """Return MCP server capabilities"""
    print("🎯 Capabilities requested")
    return {
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False
        },
        "serverInfo": {
            "name": "iManage Deep Research MCP Server",
            "version": "1.0.0"
        }
    }

@app.post("/mcp/initialize")
async def initialize():
    """Initialize MCP connection"""
    print("🚀 MCP connection initialized")
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": True
        },
        "serverInfo": {
            "name": "iManage Deep Research MCP Server",
            "version": "1.0.0"
        }
    }

# ---- Startup ----
@app.on_event("startup")
async def startup_event():
    """Server startup logging"""
    print("🎉 iManage Deep Research MCP Server starting up")
    print(f"📁 Connected to Customer: {CUSTOMER_ID}, Library: {LIBRARY_ID}")
    
    # Test authentication on startup
    try:
        await get_token()
        print("✅ Initial authentication test successful")
    except Exception as e:
        print(f"⚠️ Warning: Initial authentication test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting iManage Deep Research MCP Server...")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )