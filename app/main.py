from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .db import settings
from .routers import ingest, summary

def custom_generate_unique_id(route):
    # method + path is always unique
    return f"{list(route.methods)[0].lower()}_{route.path.replace('/', '_').strip('_')}"

app = FastAPI(
    title="Gaia Backend",
    version="0.1.0",
    generate_unique_id_function=custom_generate_unique_id
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# No auth dependency for now
app.include_router(ingest.router, prefix="/v1")
app.include_router(summary.router, prefix="/v1")

@app.get("/health")
async def health():
    return {"ok": True}

# ---- Simple bearer auth for /v1/*
async def require_auth(authorization: str = Header(..., alias="Authorization")):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if not settings.DEV_BEARER or token != settings.DEV_BEARER:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid bearer token")

# Mount routers WITH /v1 prefix and the auth dependency
app.include_router(ingest.router, prefix="/v1", dependencies=[Depends(require_auth)])
app.include_router(summary.router, prefix="/v1", dependencies=[Depends(require_auth)])
