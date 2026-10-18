from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Ensure 'backend' directory is in sys.path regardless of launch cwd
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.api import api_router
from app.core.config import settings, PROJECT_ROOT
from app.core.errors import register_exception_handlers
from app.core.logging import logger
from app.core.network import get_lan_ips
from app.db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown routines."""
    logger.info("Starting %s v%s in %s mode", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    await init_db()

    lan_ips = get_lan_ips()
    ip_hints = ", ".join([f"http://{ip}:{settings.PORT}" for ip in lan_ips]) if lan_ips else "No external adapter found"
    logger.info("================================================================================")
    logger.info("%s is READY for LAN access!", settings.APP_NAME)
    logger.info("  Host Local Address:  http://localhost:%d", settings.PORT)
    logger.info("  Reachable LAN URL:   %s", ip_hints)
    logger.info("  Ensure port %d is permitted through your OS firewall for Private Networks.", settings.PORT)
    logger.info("================================================================================")

    yield
    logger.info("Shutting down %s", settings.APP_NAME)
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Exception handlers
register_exception_handlers(app)

# CORS Middleware (configured for local network and LAN cross-device development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount WebSocket route at root /ws and API routes under /api
from app.api.websocket import router as websocket_router
app.include_router(websocket_router)
app.include_router(api_router, prefix=settings.API_PREFIX)

# Static Frontend Serving (for LAN single-host demo deployment)
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "index.html").exists():
    logger.info("Serving compiled frontend from: %s", FRONTEND_DIST_DIR)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Do not intercept API or WS routes
        if full_path.startswith("api") or full_path.startswith("ws"):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "Not found"}})

        file_path = FRONTEND_DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root_info():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "online",
            "health_check": f"{settings.API_PREFIX}/health",
            "frontend_status": "Run 'npm run build' in frontend/ to bundle single-origin UI, or visit Vite dev server at http://localhost:5173",
        }
