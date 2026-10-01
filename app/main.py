"""FastAPI application factory and entry point for Recruiter Bot."""

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import close_pool, get_conn, init_pool
from app.errors import AppError, NotFoundError, ValidationError
from app.logging_config import setup_logging
from app.migrate import run_migrations
from app.routers import candidates, health, ingest, jobs, matches

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown lifecycle."""
    cfg = get_settings()
    setup_logging(log_level=cfg.log_level)
    logger.info("Starting Recruiter Bot backend service...")

    # 1. Initialize DB pool
    init_pool(cfg)

    # 2. Run migrations
    for conn in get_conn():
        applied = run_migrations(conn)
        if applied:
            logger.info("Applied database migrations: %s", ", ".join(applied))
        else:
            logger.info("Database schema is up to date.")
        break

    yield

    # Shutdown
    logger.info("Shutting down Recruiter Bot service...")
    close_pool()


app = FastAPI(
    title="Recruiter Bot Matching API",
    description="Explainable candidate-job matching service powered by raw SQL and MySQL 8.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Any) -> Any:
    """Inject a unique request ID into request state and response headers."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ==========================================
# Uniform Error Handlers
# ==========================================


@app.exception_handler(NotFoundError)
def handle_not_found_error(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ValidationError)
def handle_validation_error(_request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
def handle_request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    clean_errors = []
    for err in exc.errors():
        clean_errors.append(
            {
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request parameters or payload",
                "details": clean_errors,
            }
        },
    )


@app.exception_handler(AppError)
def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
def handle_unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later.",
            }
        },
    )


# ==========================================
# Routers Registration
# ==========================================

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(matches.router)
app.include_router(candidates.router)
app.include_router(jobs.router)
