"""
Test endpoints for iManage Deep Research MCP Server
"""

import time
import httpx
from fastapi import APIRouter
from auth import get_token
from config import URL_PREFIX, CUSTOMER_ID, LIBRARY_ID
from document_processor import get_processing_capabilities

router = APIRouter()

@router.get("/test")
async def test_connection():
    """Test iManage connection"""
    print("🧪 Testing iManage connection...")
    
    try:
        token = await get_token()
        
        # Test a simple API call
        test_url = f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/features"
        headers = {"X-Auth-Token": token}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(test_url, headers=headers)
            response.raise_for_status()
            
        print("✅ iManage connection test successful")
        return {
            "status": "success",
            "message": "iManage connection working",
            "customer_id": CUSTOMER_ID,
            "library_id": LIBRARY_ID,
            "timestamp": time.time()
        }
        
    except Exception as e:
        print(f"❌ iManage connection test failed: {str(e)}")
        return {
            "status": "error",
            "message": f"iManage connection failed: {str(e)}",
            "timestamp": time.time()
        }

@router.get("/test/search")
async def test_search():
    """Test a basic search to verify API format"""
    print("🧪 Testing basic search...")
    
    try:
        token = await get_token()
        
        # Test both URL formats
        search_urls = [
            f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents",
            f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents"
        ]
        
        results = {}
        headers = {"X-Auth-Token": token}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for url in search_urls:
                try:
                    response = await client.get(url, headers=headers, params={"limit": 5})
                    results[url] = {
                        "status_code": response.status_code,
                        "response_sample": response.text[:500],
                        "success": response.status_code == 200
                    }
                except Exception as e:
                    results[url] = {
                        "error": str(e),
                        "success": False
                    }
            
            return {
                "status": "completed",
                "test_results": results,
                "recommendation": "Use the URL format that returned 200 status"
            }
            
    except Exception as e:
        print(f"❌ Search test failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Search test failed: {str(e)}",
            "timestamp": time.time()
        }

@router.get("/test/document/{doc_id}")
async def test_document_access(doc_id: str):
    """Test document access with both URL formats"""
    print(f"🧪 Testing document access for: {doc_id}")
    
    try:
        token = await get_token()
        
        # Test both URL formats for document access
        doc_urls = [
            f"{URL_PREFIX}/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}",
            f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
        ]
        
        results = {}
        headers = {"X-Auth-Token": token}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for url in doc_urls:
                try:
                    response = await client.get(url, headers=headers)
                    results[url] = {
                        "status_code": response.status_code,
                        "response_sample": response.text[:300],
                        "success": response.status_code == 200,
                        "accessible": "data" in response.text.lower()
                    }
                except Exception as e:
                    results[url] = {
                        "error": str(e),
                        "success": False,
                        "accessible": False
                    }
            
            return {
                "status": "completed",
                "document_id": doc_id,
                "test_results": results,
                "recommendation": "Use the URL format that returned 200 status and contains 'data'"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Document test failed: {str(e)}"
        }

@router.get("/test/processing")
async def test_document_processing():
    """Test document processing capabilities"""
    print("🧪 Testing document processing capabilities...")
    
    capabilities = get_processing_capabilities()
    
    return {
        "status": "completed",
        "document_processing": capabilities,
        "recommendation": "Install missing libraries with: pip install PyPDF2 pdfplumber python-docx openpyxl python-pptx beautifulsoup4" if not capabilities["overall_status"] else "All document processing libraries are available"
    }