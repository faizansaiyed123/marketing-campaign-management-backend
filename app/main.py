from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.rate_limit import check_rate_limit_store
from .db import get_db
from .routers import analytics, auth, audiences, campaigns, dashboard, templates, tracking

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    api_mutation = request.url.path.startswith("/api/v1/") and request.method in unsafe_methods
    origin_mismatch = origin is not None and origin.rstrip("/") != settings.frontend_origin.rstrip("/")
    cross_site_without_origin = origin is None and fetch_site == "cross-site"
    if api_mutation and (origin_mismatch or cross_site_without_origin):
        response = JSONResponse(
            status_code=403,
            content={"detail": "Request origin is not allowed"},
        )
    else:
        response = await call_next(request)

    if request.url.path.startswith("/api/") or request.url.path == "/health" or request.url.path.startswith("/track/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if settings.environment.lower() not in {"development", "test"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(auth.router)
app.include_router(audiences.router)
app.include_router(campaigns.router)
app.include_router(dashboard.router)
app.include_router(templates.router)
app.include_router(analytics.router)
app.include_router(tracking.router)

@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable")
    try:
        check_rate_limit_store()
    except RuntimeError:
        raise HTTPException(503, "Authentication protection service unavailable")
    return {"status": "ok"}
