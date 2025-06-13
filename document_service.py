"""
Document service module for iManage Deep Research MCP Server
"""

import httpx
from typing import Dict, Any
from auth import get_token
from config import URL_PREFIX, CUSTOMER_ID, LIBRARY_ID
from document_processor import process_document_content, DOCUMENT_PROCESSING_AVAILABLE

async def fetch_document_content(doc_id: str) -> Dict[str, Any]:
    """Fetch full document content and metadata with enhanced text extraction"""
    print(f"📥 Fetching document content: {doc_id}")
    
    token = await get_token()
    
    # First get document metadata - FIXED URL FORMAT
    doc_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
    headers = {"X-Auth-Token": token}
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get document metadata
            print(f"📋 Getting document metadata from: {doc_url}")
            response = await client.get(doc_url, headers=headers)
            response.raise_for_status()
            doc_data = response.json().get("data", {})
            
            title = doc_data.get("name", "Untitled Document")
            doc_type = doc_data.get("type", "Unknown")
            doc_size = doc_data.get("size", 0)
            
            print(f"📄 Document metadata: title='{title}', type='{doc_type}', size={doc_size}")
            
            # Try to download document content - FIXED URL FORMAT
            download_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}/download"
            
            document_text = ""
            download_success = False
            
            try:
                print(f"⬇️ Downloading document from: {download_url}")
                download_response = await client.get(download_url, headers=headers)
                download_response.raise_for_status()
                
                content_type = download_response.headers.get("content-type", "").lower()
                content_disposition = download_response.headers.get("content-disposition", "")
                filename = title  # Use document title as filename fallback
                
                # Try to extract filename from content-disposition header
                if "filename=" in content_disposition:
                    try:
                        filename = content_disposition.split("filename=")[1].strip('"')
                    except:
                        pass
                
                print(f"📄 Downloaded: content_type='{content_type}', filename='{filename}', size={len(download_response.content)}")
                
                if DOCUMENT_PROCESSING_AVAILABLE:
                    # Use enhanced document processing
                    document_text = await process_document_content(
                        download_response.content, 
                        content_type, 
                        filename
                    )
                    download_success = True
                    print(f"✅ Successfully processed document: {len(document_text)} characters extracted")
                else:
                    # Fallback to simple text extraction
                    if "text" in content_type or "json" in content_type or "xml" in content_type:
                        document_text = download_response.text
                        download_success = True
                        print(f"✅ Text content extracted: {len(document_text)} characters")
                    else:
                        document_text = f"Binary document ({content_type}). Size: {len(download_response.content)} bytes. Document processing libraries not available for text extraction."
                        print(f"⚠️ Binary document, no processing available")
                
            except Exception as download_error:
                print(f"❌ Document download failed: {str(download_error)}")
                document_text = f"Document download failed: {str(download_error)}. Document metadata available below."
            
            # Build comprehensive document information
            text_parts = []
            
            # Add document content
            if document_text and document_text.strip():
                text_parts.append("=== DOCUMENT CONTENT ===")
                text_parts.append(document_text)
            else:
                text_parts.append("=== DOCUMENT CONTENT UNAVAILABLE ===")
                text_parts.append("Document content could not be extracted or is empty.")
            
            # Add document metadata
            text_parts.append("\n=== DOCUMENT METADATA ===")
            if doc_data.get("comments"):
                text_parts.append(f"Comments: {doc_data['comments']}")
            if doc_data.get("author"):
                text_parts.append(f"Author: {doc_data['author']}")
            if doc_data.get("type"):
                text_parts.append(f"Document Type: {doc_data['type']}")
            if doc_data.get("size"):
                text_parts.append(f"Size: {doc_data['size']} bytes")
            if doc_data.get("edit_date"):
                text_parts.append(f"Last Modified: {doc_data['edit_date']}")
            if doc_data.get("create_date"):
                text_parts.append(f"Created: {doc_data['create_date']}")
            if doc_data.get("document_number"):
                text_parts.append(f"Document Number: {doc_data['document_number']}")
            if doc_data.get("version"):
                text_parts.append(f"Version: {doc_data['version']}")
            
            # Add processing status
            text_parts.append(f"\n=== PROCESSING STATUS ===")
            text_parts.append(f"Download Successful: {download_success}")
            text_parts.append(f"Text Extraction: {'Successful' if document_text and len(document_text) > 100 else 'Limited or Failed'}")
            text_parts.append(f"Document Processing Libraries: {'Available' if DOCUMENT_PROCESSING_AVAILABLE else 'Not Available'}")
            
            full_text = "\n".join(text_parts)
            
            # Generate document URL for citations - FIXED URL FORMAT
            doc_citation_url = f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}"
            
            metadata = {
                "document_number": str(doc_data.get("document_number", "")),
                "version": str(doc_data.get("version", "")),
                "author": doc_data.get("author", ""),
                "type": doc_data.get("type", ""),
                "size": str(doc_data.get("size", "")),
                "download_url": download_url,
                "download_success": str(download_success),
                "text_extracted": str(len(document_text) > 100),
                "processing_available": str(DOCUMENT_PROCESSING_AVAILABLE)
            }
            
            print(f"📊 Document processing complete: {len(full_text)} total characters")
            
            return {
                "id": doc_id,
                "title": title,
                "text": full_text,
                "url": doc_citation_url,
                "metadata": metadata
            }
            
    except Exception as e:
        print(f"❌ Failed to fetch document {doc_id}: {str(e)}")
        error_msg = f"Failed to fetch document {doc_id}: {str(e)}"
        return {
            "id": doc_id,
            "title": f"Error accessing document {doc_id}",
            "text": error_msg,
            "url": f"{URL_PREFIX}/work/web/api/v2/customers/{CUSTOMER_ID}/libraries/{LIBRARY_ID}/documents/{doc_id}",
            "metadata": {"error": str(e)}
        }