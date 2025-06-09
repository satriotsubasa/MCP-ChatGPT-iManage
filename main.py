from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import os, httpx, time, base64

load_dotenv()
app = FastAPI()

# Token cache
token_cache = {"token": None, "expires": 0}

async def get_token():
    if token_cache["token"] and token_cache["expires"] > time.time():
        return token_cache["token"]

    async with httpx.AsyncClient() as client:
        data = {
            "username": os.getenv("_USERNAME"),
            "password": os.getenv("PASSWORD"),
            "grant_type": "password",
            "client_id": os.getenv("CLIENT_ID"),
            "client_secret": os.getenv("CLIENT_SECRET")
        }
        url = f"{os.getenv('AUTH_URL_PREFIX')}/oauth2/token?scope=admin"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        res = await client.post(url, data=data, headers=headers)
        res.raise_for_status()
        token_data = res.json()
        token_cache["token"] = token_data["access_token"]
        token_cache["expires"] = time.time() + token_data.get("expires_in", 1800) - 60
        return token_data["access_token"]

class SearchRequest(BaseModel):
    query: str
    search_type: str = "keywords"
    search_in: str = "anywhere"
    filters: Optional[dict] = None
    limit: int = 50

class FetchRequest(BaseModel):
    id: str
    include_content: bool = True

@app.post("/search")
async def search_documents(req: SearchRequest):
    token = await get_token()
    headers = {"X-Auth-Token": token}
    base_url = os.getenv("URL_PREFIX")
    customer_id = os.getenv("CUSTOMER_ID")
    library_id = os.getenv("LIBRARY_ID")
    
    if req.search_type == "title":
        params = {"title": req.query, "latest": True, "limit": req.limit}
        url = f"{base_url}/api/v2/customers/{customer_id}/libraries/{library_id}/documents"
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json().get("data", [])
            return {"results": data, "search_type": "title"}

    elif req.search_type == "keywords":
        params = {req.search_in: req.query, "latest": True, "limit": req.limit}
        url = f"{base_url}/api/v2/customers/{customer_id}/libraries/{library_id}/documents"
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json().get("data", [])
            return {"results": data, "search_type": "keywords"}

    elif req.search_type == "advanced":
        url = f"{base_url}/api/v2/customers/{customer_id}/libraries/{library_id}/documents/search"
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json={
                "filters": req.filters or {"anywhere": req.query},
                "limit": req.limit
            })
            res.raise_for_status()
            data = res.json().get("data", [])
            return {"results": data, "search_type": "advanced"}

    else:
        raise HTTPException(status_code=400, detail="Unsupported search_type")

@app.post("/fetch")
async def fetch_document(req: FetchRequest):
    token = await get_token()
    base_url = os.getenv("URL_PREFIX")
    customer_id = os.getenv("CUSTOMER_ID")
    library_id = os.getenv("LIBRARY_ID")
    headers = {"X-Auth-Token": token}

    doc_url = f"{base_url}/api/v2/customers/{customer_id}/libraries/{library_id}/documents/{req.id}"
    async with httpx.AsyncClient() as client:
        res = await client.get(doc_url, headers=headers)
        res.raise_for_status()
        doc = res.json()["data"]

    if not req.include_content:
        return {"id": req.id, "title": doc.get("name", ""), "text": "", "metadata": doc}

    download_url = f"{doc_url}/download"
    async with httpx.AsyncClient() as client:
        res = await client.get(download_url, headers=headers)
        res.raise_for_status()
        content = base64.b64encode(res.content).decode()

    return {
        "id": req.id,
        "title": doc.get("name", ""),
        "text": content,
        "metadata": doc
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

