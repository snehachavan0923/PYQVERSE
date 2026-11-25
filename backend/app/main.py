import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import ProgrammingError

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.api.admin_academic_routes import router as admin_academic_router
from app.api.content_routes import router as content_router
from app.core.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-powered academic preparation platform for RVCE students.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(auth_router)
app.include_router(admin_academic_router)
app.include_router(content_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a sanitized error and log only non-sensitive diagnostic metadata."""
    logger.error(
        "Unhandled server error path=%s method=%s exception_class=%s",
        request.url.path,
        request.method,
        type(exc).__name__,
    )
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if isinstance(exc, ProgrammingError) and sqlstate in {"42703", "42P01"}:
        return JSONResponse(
            status_code=500,
            content={
                "code": "DATABASE_SCHEMA_ERROR",
                "detail": "The server's data schema is out of date. Please contact an administrator.",
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected server error occurred",
        },
    )
