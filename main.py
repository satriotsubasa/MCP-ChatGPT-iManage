from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import httpx, os, time, json
from datetime import datetime
import base64

load_dotenv()
app = FastAPI()

# ---- Logging Middleware (mirrors Node.js style) ----
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        timestamp = datetime.utcnow().isoformat()
        method = request.method
        path = request.url.path
        user_agent = request.headers.get("user-agent", "Unknown")
        origin = request.headers.get("origin", "No Origin")
        print(f"\n📡 [{timestamp}] {method} {path}")
        print(f"   🌐 Origin: {origin}")
        print(f"   🤖 User-Agent: {user_agent}")

        if method == "POST":
            body = await request.body()
            try:
                parsed = json.loads(body.decode())
                print("   📤 Body:", json.dumps(parsed, indent=2))
            except Exception:
                pass

        if request.query_params:
            print(f"   🔍 Query: {dict(request.query_params)}")

        start = time.time()
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        content_length = response.headers.get("content-length", "unknown")
        print(f"   ✅ Response: {response.status_code} ({content_length} bytes) in {duration:.1f}ms")
        return response

app.add_middleware(LoggingMiddleware)

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Token cache ----
token_cache = {"token": None, "expires": 0}

async def get_token():
    if token_cache["token"] and token_cache["expires"] > time.time():
        print("✅ Using cached access token")
        return token_cache["token"]

    print("🔐 Authenticating to iManage...")
    auth_url = f"{os.getenv('AUTH_URL_PREFIX')}/oauth2/token?scope=admin"
    data = {
        "username": os.getenv("_USERNAME"),
        "password": os.getenv("PASSWORD"),
        "grant_type": "password",
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET")
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        res = await client.post(auth_url, data=data, headers=headers)
        res.raise_for_status()
        token_data = res.json()
        token_cache["token"] = token_data["access_token"]
        token_cache["expires"] = time.time() + token_data.get("expires_in", 1800) - 60
        print("✅ Authentication successful")
        return token_data["access_token"]

# ---- Models ----
class SearchRequest(BaseModel):
    query: str
    search_type: str = "keywords"
    search_in: str = "anywhere"
    filters: Optional[dict] = None
    limit: int = 50

class FetchRequest(BaseModel):
    id: str
    include_content: bool = True

# ---- Routes ----
@app.get("/")
def root():
    return {
        "message": "iManage MCP Server for Deep Research",
        "version": "Python-FastAPI",
        "endpoints": {
            "health": "/health",
            "search": "/search",
            "fetch": "/fetch"
        }
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "environment": {
            "auth": os.getenv("AUTH_URL_PREFIX"),
            "url": os.getenv("URL_PREFIX"),
            "library": os.getenv("LIBRARY_ID")
        }
    }

@app.post("/search")
async def search_documents(req: SearchRequest):
    token = await get_token()
    headers = {"X-Auth-Token": token}
    base_url = os.getenv("URL_PREFIX")
    cid = os.getenv("CUSTOMER_ID")
    lid = os.getenv("LIBRARY_ID")

    if req.search_type == "title":
        params = {"title": req.query, "limit": req.limit, "latest": True}
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{base_url}/api/v2/customers/{cid}/libraries/{lid}/documents", headers=headers, params=params)
            return {"results": res.json().get("data", []), "search_type": "title"}

    elif req.search_type == "keywords":
        params = {"limit": req.limit, "latest": True, req.search_in: req.query}
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{base_url}/api/v2/customers/{cid}/libraries/{lid}/documents", headers=headers, params=params)
            return {"results": res.json().get("data", []), "search_type": "keywords"}

    elif req.search_type == "advanced":
        body = {"filters": req.filters or {"anywhere": req.query}, "limit": req.limit}
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{base_url}/api/v2/customers/{cid}/libraries/{lid}/documents/search", headers=headers, json=body)
            return {"results": res.json().get("data", []), "search_type": "advanced"}

    else:
        raise HTTPException(status_code=400, detail="Invalid search_type")

@app.post("/fetch")
async def fetch_document(req: FetchRequest):
    token = await get_token()
    headers = {"X-Auth-Token": token}
    base_url = os.getenv("URL_PREFIX")
    cid = os.getenv("CUSTOMER_ID")
    lid = os.getenv("LIBRARY_ID")

    doc_url = f"{base_url}/api/v2/customers/{cid}/libraries/{lid}/documents/{req.id}"
    async with httpx.AsyncClient() as client:
        meta = await client.get(doc_url, headers=headers)
        doc = meta.json()["data"]

        if not req.include_content:
            return {"id": doc["id"], "title": doc["name"], "text": "", "metadata": doc}

        try:
            download = await client.get(f"{doc_url}/download", headers=headers)
            content_b64 = base64.b64encode(download.content).decode()
        except Exception as e:
            content_b64 = "[DOWNLOAD FAILED] " + str(e)

    return {
        "id": doc["id"],
        "title": doc["name"],
        "text": content_b64,
        "metadata": doc
    }
