import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from app.core.config import settings
from app.api.routes import session, diagnosis

app = FastAPI(title="AI Math Tutor API", version="1.0.0")
logger = logging.getLogger("uvicorn.error")
allowed_origins = settings.allowed_frontend_origins
allowed_methods = "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"

logger.info("CORS allowed origins: %s", ", ".join(allowed_origins))

app.include_router(session.router, prefix="/api/session", tags=["session"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["diagnosis"])


@app.middleware("http")
async def local_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    is_allowed_origin = origin in allowed_origins
    requested_headers = request.headers.get("access-control-request-headers", "content-type")

    if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
        if not is_allowed_origin:
            return Response(status_code=400, content="Disallowed CORS origin")

        response = Response(status_code=204)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = allowed_methods
        response.headers["Access-Control-Allow-Headers"] = requested_headers
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Vary"] = "Origin"
        return response

    response = await call_next(request)
    if is_allowed_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.exception_handler(RedisConnectionError)
@app.exception_handler(RedisTimeoutError)
async def redis_connection_handler(request: Request, exc: Exception):
    logger.error("Redis connection failure: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"error": "connection_error", "detail": "Cannot reach the session store. Please check your internet connection and try again."},
    )


@app.exception_handler(OSError)
async def os_error_handler(request: Request, exc: OSError):
    # OSError covers getaddrinfo failures (DNS resolution) and other socket errors
    if exc.errno in (11001, -2, -3, -5):  # getaddrinfo failed (Win/Linux/macOS)
        logger.error("DNS/network error: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "connection_error", "detail": "Cannot reach the session store. Please check your internet connection and try again."},
        )
    raise exc


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "server_error", "detail": "An unexpected server error occurred. Please try again."},
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-math-tutor"}
