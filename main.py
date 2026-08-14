from __future__ import annotations

from collections import OrderedDict
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import time
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm_client import LLMClient, LLMServiceError
from validator_fallback import fallback_code, fallback_validation, looks_like_plc_request


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("plc-demo")

llm = LLMClient.from_environment()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await llm.close()


app = FastAPI(
    title="工业PLC代码生成与验证平台",
    version="7.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# The production UI and API are same-origin, so CORS is normally unnecessary.
# Optional origins are supported for local integration or a separated frontend.
configured_origins = [
    item.strip()
    for item in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if item.strip()
]
if configured_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

_generation_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_cache_ttl_seconds = max(60, int(os.getenv("GENERATION_CACHE_TTL_SECONDS", "3600")))
_cache_max_entries = max(8, int(os.getenv("GENERATION_CACHE_MAX_ENTRIES", "64")))


def _cache_key(requirement: str) -> str:
    return " ".join(requirement.lower().split())


def _get_cached_code(requirement: str) -> str | None:
    key = _cache_key(requirement)
    cached = _generation_cache.get(key)
    if cached is None:
        return None
    created_at, code = cached
    if time.monotonic() - created_at > _cache_ttl_seconds:
        _generation_cache.pop(key, None)
        return None
    _generation_cache.move_to_end(key)
    return code


def _set_cached_code(requirement: str, code: str) -> None:
    key = _cache_key(requirement)
    _generation_cache[key] = (time.monotonic(), code)
    _generation_cache.move_to_end(key)
    while len(_generation_cache) > _cache_max_entries:
        _generation_cache.popitem(last=False)


class GenerateRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=8000)


class GenerateResponse(BaseModel):
    mode: Literal["code", "chat"]
    content: str
    can_validate: bool


class ValidateRequest(BaseModel):
    requirement: str = Field(default="", max_length=8000)
    code: str = Field(min_length=1, max_length=30000)


@app.get("/health")
async def health() -> dict[str, object]:
    """Lightweight health check for Render, Railway and Docker."""
    return {
        "status": "ok",
        "service": "plc-code-generation-demo",
        "version": "7.0.0",
        "llm_configured": llm.is_configured,
    }


@app.get("/api/health", include_in_schema=False)
async def api_health() -> dict[str, object]:
    """Compatibility route retained for the v5 frontend."""
    return await health()


@app.post("/api/generate-code", response_model=GenerateResponse)
async def generate_code(payload: GenerateRequest) -> GenerateResponse:
    requirement = payload.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=400, detail="请输入需求内容")

    if not looks_like_plc_request(requirement):
        try:
            message = await llm.chat(requirement)
        except LLMServiceError as exc:
            logger.warning("Chat completion unavailable: %s", exc)
            message = (
                "您好！我是工业PLC代码生成与验证助手。您可以描述电动机、"
                "泵阀、传送带、报警保护或定时控制等需求，我会协助生成ST代码。"
            )
        return GenerateResponse(mode="chat", content=message, can_validate=False)

    cached_code = _get_cached_code(requirement)
    if cached_code is not None:
        return GenerateResponse(mode="code", content=cached_code, can_validate=True)

    try:
        code = await llm.generate_st_code(requirement)
        if not code.strip():
            raise LLMServiceError("Empty model response")
        _set_cached_code(requirement, code)
    except LLMServiceError as exc:
        logger.warning("Code generation unavailable; using safe fallback: %s", exc)
        code = fallback_code(requirement)

    return GenerateResponse(mode="code", content=code, can_validate=True)


@app.post("/api/validate-code")
async def validate_code(payload: ValidateRequest) -> JSONResponse:
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="没有可验证的代码")

    local_result = fallback_validation(payload.requirement, code)
    try:
        result = await llm.validate_st_code(payload.requirement, code, local_result)
    except LLMServiceError as exc:
        logger.warning("Model validation unavailable; using local review: %s", exc)
        result = local_result

    return JSONResponse(result)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务暂时不可用，请稍后重试"},
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
