"""
MCP protocol handlers for iManage Deep Research MCP Server
Updated to support user authentication context
"""

import json
from fastapi import Request
from search_service import perform_combined_search
from document_service import fetch_document_content

async def handle_mcp_request(request: Request):
    """Main MCP protocol handler - handles raw JSON with user context"""
    print("📨 MCP request received")
    
    try:
        # Parse the raw JSON request
        body = await request.json()
        print(f"🔍 Request body: {json.dumps(body, indent=2)}")
        
        method = body.get("method", "")
        request_id = body.get("id")
        params = body.get("params", {})
        
        if method == "initialize":
            return await handle_initialize(request_id)
        
        elif method == "auth/list":
            return await handle_auth_list(request_id)
        
        elif method == "auth/status":
            return await handle_auth_status(request_id)
        
        elif method == "tools/list":
            return await handle_tools_list(request_id)
        
        elif method == "tools/call":
            return await handle_tools_call(request_id, params, request)
        
        elif method == "notifications/initialized":
            return await handle_initialized_notification(request_id)
        
        else:
            print(f"❌ Unknown method: {method}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}"
                }
            }
    
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32700,
                "message": "Parse error: Invalid JSON"
            }
        }
    
    except Exception as e:
        print(f"❌ Handler error: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }

async def handle_initialize(request_id):
    """Handle MCP initialize request"""
    print("🚀 Initialize request")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "iManage Deep Research MCP Server",
                "version": "2.1.0"
            },
            "instructions": "This server provides access to iManage document search and retrieval with user authentication. Users will be authenticated to ensure they only access documents they have permission to view."
        }
    }

async def handle_auth_list(request_id):
    """Handle auth methods list request"""
    print("🔓 Auth methods requested")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "authMethods": []  # Empty array means auth handled externally via OAuth
        }
    }

async def handle_auth_status(request_id):
    """Handle auth status request"""
    print("🔓 Auth status requested")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "authenticated": True,
            "method": "oauth"
        }
    }

async def handle_tools_list(request_id):
    """Handle tools list request"""
    print("🛠️ Tools list requested")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "search",
                    "description": "Search for documents in iManage using title search or keyword search. "
                                  "For title search, use specific document names or titles. "
                                  "For keyword search, use terms that might appear in document content. "
                                  "The system will automatically determine the best search strategy. "
                                  "You can search for legal documents, contracts, memos, emails, and other business documents. "
                                  "Use specific terms like client names, matter names, document types, or legal concepts. "
                                  "Results will only include documents that the authenticated user has permission to access.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string", 
                                "description": "Search query. Can be document titles, keywords, or phrases to search for in documents."
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "fetch",
                    "description": "Retrieve the complete content and metadata of a specific document by its ID. "
                                  "Use this after finding documents with search to get the full document content for analysis. "
                                  "Only documents that the authenticated user has permission to access will be returned.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Document ID obtained from search results"}
                        },
                        "required": ["id"]
                    }
                }
            ]
        }
    }

async def handle_initialized_notification(request_id):
    """Handle MCP initialized notification"""
    print("📢 Initialized notification received")
    # Notifications don't require a response, but we'll return a simple acknowledgment
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {}
    } if request_id else None

async def handle_tools_call(request_id, params, request: Request):
    """Handle tools call request with user context"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    print(f"🔧 Tool call: {tool_name} with args: {arguments}")
    
    if tool_name == "search":
        return await handle_search_tool(request_id, arguments, request)
    
    elif tool_name == "fetch":
        return await handle_fetch_tool(request_id, arguments, request)
    
    else:
        print(f"❌ Unknown tool: {tool_name}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}"
            }
        }

async def handle_search_tool(request_id, arguments, request: Request):
    """Handle search tool call with user context"""
    try:
        query = arguments.get("query", "")
        if not query:
            raise ValueError("Query parameter is required")
        
        print(f"🔍 Searching for: '{query}' (with user context)")
        
        # Perform combined search using the search service with user context
        final_results = await perform_combined_search(query, limit_per_type=10, request=request)
        
        if not final_results:
            # Return a helpful message if no results found
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "results": [],
                                "message": f"No documents found for query: '{query}'. This could be because no documents match your search terms, or you don't have permission to access documents containing these terms."
                            }, indent=2)
                        }
                    ]
                }
            }
        
        # Convert to the expected format
        results_data = []
        for result in final_results:
            results_data.append({
                "id": result.id,
                "title": result.title,
                "text": result.text,
                "url": result.url
            })
        
        print(f"✅ Returning {len(results_data)} search results (user-filtered)")
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"results": results_data}, indent=2)
                    }
                ]
            }
        }
        
    except Exception as e:
        print(f"❌ Search failed: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": f"Search failed: {str(e)}"
            }
        }

async def handle_fetch_tool(request_id, arguments, request: Request):
    """Handle fetch tool call with user context"""
    try:
        doc_id = arguments.get("id", "")
        if not doc_id:
            raise ValueError("Document ID parameter is required")
        
        print(f"📥 Fetching document: {doc_id} (with user context)")
        
        # Fetch document using the document service with user context
        document = await fetch_document_content(doc_id, request)
        
        print(f"✅ Document fetched successfully (user-authorized)")
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(document, indent=2)
                    }
                ]
            }
        }
        
    except Exception as e:
        print(f"❌ Fetch failed: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": f"Fetch failed: {str(e)}"
            }
        }