"""FastAPI application for the Forge support investigation engine."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge import __version__
from forge.api.dependencies import ForgeRuntime
from forge.api.routes import router
from forge.bootstrap import ensure_runtime_assets
from forge.config import CHROMA_PATH, DB_PATH
from forge.config import OpenAIConfigurationError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("forge.api")


def create_app(runtime: ForgeRuntime | None = None) -> FastAPI:
    """Create the API application with an injectable runtime for tests."""
    bootstrap_required = runtime is None
    active_runtime = runtime or ForgeRuntime(DB_PATH, CHROMA_PATH)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.runtime = active_runtime
        started = time.perf_counter()
        if bootstrap_required:
            ensure_runtime_assets(DB_PATH, CHROMA_PATH)
        active_runtime.startup()
        logger.info("Forge API startup_ms=%.2f semantic_ready=%s", (time.perf_counter() - started) * 1000, active_runtime.semantic_ready)
        yield
        active_runtime.shutdown()

    application = FastAPI(
        title="Forge API",
        description="Production API for grounded Forge support-ticket investigation.",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.middleware("http")
    async def request_logging(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed method=%s path=%s", request.method, request.url.path)
            raise
        logger.info("request method=%s path=%s status=%s latency_ms=%.2f", request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
        return response

    @application.exception_handler(OpenAIConfigurationError)
    async def openai_configuration_error(_: Request, exc: OpenAIConfigurationError):
        return JSONResponse(status_code=503, content={"error": {"code": "openai_configuration", "message": str(exc)}})

    @application.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception):
        logger.exception("unhandled API error: %s", exc)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Forge could not complete the request."}})

    return application


app = create_app()
