"""
Search service module for iManage Deep Research MCP Server
"""

import json
import httpx
from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import HTTPException
from auth import get_token
from config import URL_PREFIX, CUSTOMER_ID, LIBRARY_ID

class SearchResult(BaseModel):
    id: str
    title: str
    text: str
    url: str = None
    metadata: Dict[str, str] = None

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
            "name": query
        },
        "profile_fields": {
            "document": [
                "id", "name", "document_number", "version", "author", 
                "edit_date", "create_date", "size", "type"
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print(f"🔍 Sending title search request: {json.dumps(search_body, indent=2)}")
            response = await client.post(search_url, headers=headers, json=search_body)
            
            # Log the response for debugging
            print(f"📊 Response status: {response.status_code}")
            print(f"📊 Response headers: {dict(response.headers)}")
            
            if response.status_code == 400:
                error_text = response.text
                print(f"❌ 400 Error details: {error_text}")
                # Try a simpler search format
                return await search_documents_simple(query, limit, "title")
            
            response.raise_for_status()
            data = response.json()
            
            results = []
            for doc in data.get("data", []):
                doc_id = doc.get("id", "")
                title = doc.get("name", "Untitled Document")
                
                # Create text snippet from document metadata
                text_parts = []
                if doc.get("author"):
                    text_parts.append(f"Author: {doc['author']}")
                if doc.get("type"):
                    text_parts.append(f"Type: {doc['type']}")
                if doc.get("edit_date"):
                    text_parts.append(f"Last Modified: {doc['edit_date']}")
                
                text = "; ".join(text_parts) if text_parts else "Document metadata"
                
                # Generate document URL for citations - FIXED URL FORMAT
                doc_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
                
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
        # Try fallback search methods
        try:
            return await search_documents_simple(query, limit, "title")
        except Exception as fallback_error:
            print(f"❌ Fallback search also failed: {str(fallback_error)}")
            return []

async def search_documents_keyword(query: str, limit: int = 20) -> List[SearchResult]:
    """Search documents by keywords (full-text search)"""
    print(f"🔍 Searching documents by keywords: '{query}'")
    
    token = await get_token()
    search_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/search"
    
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    # Try different search body formats
    search_body_options = [
        # Option 1: Basic fields only (removing comments)
        {
            "limit": limit,
            "filters": {
                "anywhere": query
            },
            "profile_fields": {
                "document": [
                    "id", "name", "document_number", "version", "author", 
                    "edit_date", "create_date", "size", "type"
                ]
            }
        },
        # Option 2: Even more basic fields
        {
            "limit": limit,
            "filters": {
                "anywhere": query
            },
            "profile_fields": {
                "document": [
                    "id", "name", "author", "edit_date", "type"
                ]
            }
        },
        # Option 3: No profile_fields specified
        {
            "limit": limit,
            "filters": {
                "anywhere": query
            }
        },
        # Option 4: Body search only
        {
            "limit": limit,
            "filters": {
                "body": query
            }
        }
    ]
    
    for i, search_body in enumerate(search_body_options):
        try:
            print(f"🔍 Trying keyword search format {i+1}: {json.dumps(search_body, indent=2)}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(search_url, headers=headers, json=search_body)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    results = []
                    for doc in data.get("data", []):
                        doc_id = doc.get("id", "")
                        title = doc.get("name", "Untitled Document")
                        
                        # Create text snippet from document metadata
                        text_parts = []
                        if doc.get("author"):
                            text_parts.append(f"Author: {doc['author']}")
                        if doc.get("type"):
                            text_parts.append(f"Type: {doc['type']}")
                        if doc.get("edit_date"):
                            text_parts.append(f"Last Modified: {doc['edit_date']}")
                        
                        text = "; ".join(text_parts) if text_parts else f"Document contains keyword: {query}"
                        
                        # Generate document URL for citations - FIXED URL FORMAT
                        doc_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
                        
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
                else:
                    print(f"⚠️ Search format {i+1} returned {response.status_code}: {response.text}")
                    
        except Exception as e:
            print(f"⚠️ Search format {i+1} failed: {str(e)}")
            continue
    
    # If all POST methods fail, try GET fallback
    print("🔄 POST search failed, trying GET fallback")
    try:
        return await search_documents_simple(query, limit, "keyword")
    except Exception as fallback_error:
        print(f"❌ Keyword search and fallback failed: {str(fallback_error)}")
        return []

async def search_documents_simple(query: str, limit: int = 20, search_type: str = "simple") -> List[SearchResult]:
    """Simple search using GET parameters - fallback method"""
    print(f"🔍 Trying simple search ({search_type}): '{query}'")
    
    token = await get_token()
    
    # Use GET endpoint with query parameters
    search_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents"
    
    headers = {"X-Auth-Token": token}
    
    # Try different parameter combinations
    params_options = [
        {"name": query, "limit": limit},
        {"anywhere": query, "limit": limit},
        {"title": query, "limit": limit},
        {"body": query, "limit": limit},
        {"q": query, "limit": limit}  # Sometimes 'q' is used as generic search
    ]
    
    for params in params_options:
        try:
            print(f"🔍 Trying search with params: {params}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(search_url, headers=headers, params=params)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        print(f"⚠️ Response is not JSON: {response.text[:200]}")
                        continue
                    
                    # Handle different response formats
                    documents = []
                    if isinstance(data, dict):
                        documents = data.get("data", [])
                    elif isinstance(data, list):
                        documents = data
                    
                    results = []
                    for doc in documents:
                        if not isinstance(doc, dict):
                            continue
                            
                        doc_id = doc.get("id", "")
                        title = doc.get("name", "Untitled Document")
                        
                        # Create text snippet from document metadata
                        text_parts = []
                        if doc.get("author"):
                            text_parts.append(f"Author: {doc['author']}")
                        if doc.get("type"):
                            text_parts.append(f"Type: {doc['type']}")
                        if doc.get("edit_date"):
                            text_parts.append(f"Last Modified: {doc['edit_date']}")
                        
                        text = "; ".join(text_parts) if text_parts else f"Document found with {search_type} search"
                        
                        # Generate document URL for citations - FIXED URL FORMAT
                        doc_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
                        
                        metadata = {
                            "document_number": str(doc.get("document_number", "")),
                            "version": str(doc.get("version", "")),
                            "size": str(doc.get("size", "")),
                            "search_type": search_type
                        }
                        
                        results.append(SearchResult(
                            id=doc_id,
                            title=title,
                            text=text,
                            url=doc_url,
                            metadata=metadata
                        ))
                    
                    print(f"📄 Simple search found {len(results)} documents")
                    return results[:limit]  # Limit results
                else:
                    print(f"⚠️ Search params {params} returned {response.status_code}: {response.text[:200]}")
                    
        except Exception as e:
            print(f"⚠️ Search params {params} failed: {str(e)}")
            continue
    
    print("❌ All simple search methods failed")
    return []

async def perform_combined_search(query: str, limit_per_type: int = 10) -> List[SearchResult]:
    """Perform both title and keyword searches and combine results"""
    print(f"🔍 Performing combined search for: '{query}'")
    
    all_results = {}
    
    # Try title search first
    try:
        title_results = await search_documents_title(query, limit=limit_per_type)
        for result in title_results:
            all_results[result.id] = result
        print(f"✅ Title search returned {len(title_results)} results")
    except Exception as title_error:
        print(f"⚠️ Title search failed: {str(title_error)}")
    
    # Try keyword search
    try:
        keyword_results = await search_documents_keyword(query, limit=limit_per_type)
        for result in keyword_results:
            if result.id not in all_results:
                all_results[result.id] = result
        print(f"✅ Keyword search returned {len(keyword_results)} results")
    except Exception as keyword_error:
        print(f"⚠️ Keyword search failed: {str(keyword_error)}")
    
    # If no results from either search, try simple fallback
    if not all_results:
        print("🔄 No results from main searches, trying simple fallback")
        try:
            fallback_results = await search_documents_simple(query, 20, "fallback")
            for result in fallback_results:
                all_results[result.id] = result
            print(f"✅ Fallback search returned {len(fallback_results)} results")
        except Exception as fallback_error:
            print(f"❌ Fallback search also failed: {str(fallback_error)}")
    
    # Convert to list and limit to 20 total results
    final_results = list(all_results.values())[:20]
    
    print(f"✅ Combined search returned {len(final_results)} total results")
    return final_results