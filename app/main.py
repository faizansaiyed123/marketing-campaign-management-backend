from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import get_settings
from .routers import analytics, auth, audiences, campaigns, dashboard, tracking
settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"], allow_headers=["Content-Type"])
app.include_router(auth.router)
app.include_router(audiences.router)
app.include_router(campaigns.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(tracking.router)
@app.get("/health", tags=["system"])
def health():
    return {"status":"ok"}
