"""VYRO — FastAPI application factory.

Production-ready wiring: CORS, gzip, global rate-limit, unified error envelope,
media static serving, /api/v1 REST + WebSocket chat, health & meta probes.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import check_rate, client_ip
from app.ws.chat import router as ws_router

logger = logging.getLogger("vyro")
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

MEDIA_DIRS = ["avatars", "banners", "posts"]


def _ensure_media_dirs() -> None:
    for sub in MEDIA_DIRS:
        (Path(settings.MEDIA_ROOT) / "uploads" / sub).mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=settings.VERSION,
        description=(
            "VYRO — گیمینگ سوشال پلتفرم بک‌اند (Omlet-Arcade-style)\n\n"
            "* احراز هویت امن (JWT + Refresh Rotation)\n"
            "* پست/کامنت/لایک/سیو/ریپست + هشتگ\n"
            "* چت realtime با ریپلای (WebSocket)\n"
            "* اقتصاد کوین ZYRA: Buff، دونیت، فروشگاه فریم انیمیشنی\n"
            "* فالوور/فالوینگ + فید شخصی و اکسپلور\n"
            "* لایو استریم (placeholder برای توسعه آینده)\n"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---------- middleware ----------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def global_rate_limit_and_logging(request: Request, call_next):
        path = request.url.path
        if path.startswith(("/docs", "/redoc", "/openapi.json", "/media", "/health", "/playground")):
            return await call_next(request)
        times, seconds = settings.RATE_LIMIT_GLOBAL.split("/")
        allowed = await check_rate(
            f"global:{client_ip(request)}", int(times), int(seconds)
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "تعداد درخواست‌ها زیاد است", "details": None}},
            )
        started = time.perf_counter()
        response = await call_next(request)
        if settings.DEBUG:
            ms = (time.perf_counter() - started) * 1000
            logger.debug("%s %s -> %s (%.1fms)", request.method, path, response.status_code, ms)
        return response

    # ---------- error handlers ----------
    @app.exception_handler(AppError)
    async def app_error_handler(_req: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_req: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            field = ".".join(str(x) for x in err.get("loc", [])[1:]) or "body"
            details.append({"field": field, "message": err.get("msg", "invalid")})
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_failed", "message": "اطلاعات ارسالی نامعتبر است", "details": details[:10]}},
        )

    @app.exception_handler(Exception)
    async def generic_handler(_req: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "خطای داخلی سرور", "details": None}},
        )

    # ---------- media ----------
    _ensure_media_dirs()
    app.mount("/media", StaticFiles(directory=settings.MEDIA_ROOT), name="media")

    # ---------- routers ----------
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_router)  # /ws/chat

    # ---------- probes ----------
    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}

    @app.get("/api/v1/meta", tags=["meta"])
    async def meta():
        from app.core.cache import cache

        return {
            "app": settings.APP_NAME,
            "version": settings.VERSION,
            "coin": "ZYRA",
            "economy": {
                "signup_bonus": settings.SIGNUP_BONUS_ZYRA,
                "daily_bonus": settings.DAILY_BONUS_ZYRA,
                "buff_min": settings.BUFF_MIN,
                "buff_max": settings.BUFF_MAX,
            },
            "cache_backend": cache.backend_name,
            "limits": {"post_max_images": settings.MAX_IMAGES_PER_POST},
        }

    # ---------- dev playground ----------
    playground_path = Path(__file__).parent / "static" / "playground.html"
    if playground_path.exists():

        @app.get("/playground", include_in_schema=False)
        async def playground():
            return FileResponse(playground_path)

    return app


app = create_app()
