"""Single-service v9 workbench: generation, bounded improvement and honest review."""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from fallback import fallback_code
from file_import import MAX_BYTES, extract_document
from llm_client import LLMClient, ModelUnavailable, generation_messages, extract_code
from scenarios import public_scenarios
from validation import local_report, merge_review, structural_issues, repair_needed, improved_report

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env", override=False)
llm = LLMClient.from_environment()
logger = logging.getLogger("demo")
cache = OrderedDict()
gate = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "4")))
rate_log = defaultdict(deque)
MAX_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "360"))


@asynccontextmanager
async def lifespan(app):
    yield
    await llm.close()


app = FastAPI(title="工业代码工作台 Demo", version="9.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class BodyLimit:
    """Enforce a size limit before multipart parsing, including chunked uploads."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        size = 0
        messages = []
        # A bounded buffer prevents oversized uploads being spooled to disk.
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > MAX_BYTES + 65536:
                response = JSONResponse({"detail": "请求内容过大，请将文件控制在 2 MB 内。"}, status_code=413)
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, replay, send)


app.add_middleware(BodyLimit)
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip() and x.strip() != "*"]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response


class GenerateRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=20000)
    language: Literal["st", "cpp"] = "st"

    @field_validator("requirement")
    @classmethod
    def not_empty(cls, value):
        if not value.strip():
            raise ValueError("需求不能为空")
        return value.strip()


class ValidateRequest(GenerateRequest):
    code: str = Field(min_length=1, max_length=80000)


def cache_key(requirement, language):
    return hashlib.sha256((language + "\0" + requirement.replace("\r\n", "\n").strip()).encode()).hexdigest()


def content_id(code):
    return hashlib.sha256(code.encode()).hexdigest()[:16]


def limit(request):
    now = time.monotonic()
    # Bounded memory; do not trust caller-supplied forwarding headers.
    if len(rate_log) > 4096:
        rate_log.clear()
    key = request.client.host if request.client else "unknown"
    values = rate_log[key]
    while values and now - values[0] > 60:
        values.popleft()
    if len(values) >= int(os.getenv("REQUESTS_PER_MINUTE", "30")):
        raise HTTPException(429, "请求较密集，请稍后再试。")
    values.append(now)


def event(kind, **values):
    return {"type": kind, **values}


def is_greeting(text):
    return bool(re.fullmatch(r"\s*(你好|您好|嗨|hello|hi|你是谁|你能做什么|谢谢)[!！?？。\s]*", text, re.I))


async def review_events(requirement, code, language, allow_improve=False):
    local = local_report(code, language)
    yield event("checks", report=local, code_id=content_id(code))
    yield event("stage", stage="structure", status="done", message="完整代码结构检查完成")
    yield event("stage", stage="review", status="active", message="逐项比对需求、阈值、时序和保护条件")
    try:
        async with asyncio.timeout(100):
            reviewed = await llm.review(requirement, code, language)
        report = merge_review(local, reviewed)
    except Exception as exc:
        logger.warning("review unavailable: %s", type(exc).__name__)
        local["suggestions"].append("详细需求审查暂未完成，可点击“重新验证”；现有结果仅来自基础规则检查。")
        report = local
    quality = {"attempted": False, "accepted": False, "attempts": 0}
    for attempt in range(2):
        if not allow_improve or not repair_needed(report):
            break
        quality["attempted"] = True
        quality["attempts"] = attempt + 1
        yield event("stage", stage="review", status="active", message=f"发现可修正项，正在进行第 {attempt + 1} 轮改进与复核")
        try:
            async with asyncio.timeout(150):
                candidate = await llm.improve(requirement, code, language, report)
                if len(candidate) > 80000 or structural_issues(candidate, language):
                    raise ModelUnavailable("invalid_improvement")
                candidate_report = merge_review(local_report(candidate, language), await llm.review(requirement, candidate, language))
            if improved_report(report, candidate_report):
                code, report = candidate, candidate_report
                quality["accepted"] = True
                yield event("code", code=code, language=language, source="model", code_id=content_id(code))
                yield event("stage", stage="generation", status="done", message="已修正发现的问题并完成复核")
            # Otherwise keep the previous complete version and its real findings.
        except Exception as exc:
            logger.warning("improvement unavailable: %s", type(exc).__name__)
    report["quality_improvement"] = quality
    yield event("checks", report=report, code_id=content_id(code))
    yield event("stage", stage="review", status="done" if report["source"] == "review" else "warn", message="需求对应审查完成" if report["source"] == "review" else "已保留基础检查结果，详细审查待补充")
    yield event("done", report=report, code_id=content_id(code))


async def generation_events(body):
    if is_greeting(body.requirement):
        yield event("chat", content="你好！请选择一个轨道交通示例，或输入、导入控制需求。我可以生成 ST / C++ 代码，并展示结构检查和需求对应审查过程。")
        return
    key = cache_key(body.requirement, body.language)
    yield event("stage", stage="input", status="done", message="需求已接收，目标语言 " + body.language.upper())
    yield event("stage", stage="generation", status="active", message="正在生成与当前需求对应的代码")
    cached = cache.get(key)
    code, source = "", "model"
    if cached and time.monotonic() - cached[0] < 3600:
        code, source = cached[1], "cache"
        cache.move_to_end(key)
        yield event("delta", text=code)
    else:
        cache.pop(key, None)
        try:
            messages = generation_messages(body.requirement, body.language)
            last_check = 0
            async for chunk in llm.stream(messages):
                code += chunk
                if len(code) > 80000:
                    raise ModelUnavailable("too_long")
                yield event("delta", text=chunk)
                if len(code) - last_check >= 450:
                    last_check = len(code)
                    yield event("checks", report=local_report(code, body.language, partial=True))
                    yield event("stage", stage="structure", status="active", message=f"已接收 {len(code.splitlines())} 行，增量检查中")
            code = extract_code(code, body.language)
            issues = structural_issues(code, body.language)
            if issues:
                yield event("stage", stage="generation", status="active", message="正在补全与复核代码结构")
                messages += [{"role": "assistant", "content": code}, {"role": "user", "content": "请保留原需求全部功能，修复以下结构问题并重新输出完整代码：" + "；".join(issues)}]
                code = extract_code(await llm.complete(messages), body.language)
                if structural_issues(code, body.language):
                    raise ModelUnavailable("invalid_structure")
            cache[key] = (time.monotonic(), code)
            while len(cache) > 32:
                cache.popitem(last=False)
        except Exception as exc:
            logger.warning("generation unavailable: %s", type(exc).__name__)
            reference = fallback_code(body.requirement, body.language) if os.getenv("ALLOW_FALLBACK", "true").lower() == "true" else None
            if not reference:
                yield event("error", message="本次未得到完整可用的代码，请稍后重试或按功能拆分需求。未完成内容不可导出，也不会用无关示例替代。", clear_code=True)
                return
            code, source = reference, "reference"
            yield event("notice", message="当前展示与所选示例严格对应的离线参考代码，可稍后重新生成。")
    yield event("code", code=code, language=body.language, source=source, code_id=content_id(code))
    yield event("stage", stage="generation", status="done", message=f"完整代码已返回，共 {len(code.splitlines())} 行")
    async for value in review_events(body.requirement, code, body.language, allow_improve=source != "reference"):
        if value["type"] == "code":
            cache[key] = (time.monotonic(), value["code"])
        yield value


async def bounded_events(iterator, request):
    acquired = False
    try:
        await asyncio.wait_for(gate.acquire(), timeout=15)
        acquired = True
        async with asyncio.timeout(MAX_SECONDS):
            async for value in iterator:
                if await request.is_disconnected():
                    return
                yield value
    except (TimeoutError, asyncio.TimeoutError):
        yield event("error", message="本次处理时间较长，请稍后重试。已完成代码会保留，未完成代码不会作为最终结果。")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("job unavailable: %s", type(exc).__name__)
        yield event("error", message="本次处理暂未完成，请稍后重试。")
    finally:
        await iterator.aclose()
        if acquired:
            gate.release()


def stream_response(iterator, request):
    async def serialize():
        async for value in bounded_events(iterator, request):
            yield "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"
    return StreamingResponse(serialize(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "9.0.0", "service": "industrial-code-demo-v9", "generation_ready": llm.configured, "languages": ["st", "cpp"]}


@app.get("/api/scenarios")
async def scenarios():
    return {"scenarios": public_scenarios()}


@app.post("/api/import-file")
async def import_file(request: Request, file: UploadFile = File(...)):
    limit(request)
    try:
        data = await file.read(MAX_BYTES + 1)
        return await run_in_threadpool(extract_document, file.filename, data)
    finally:
        await file.close()


@app.post("/api/generate-stream")
async def generate_stream(body: GenerateRequest, request: Request):
    limit(request)
    return stream_response(generation_events(body), request)


@app.post("/api/validate-stream")
async def validate_stream(body: ValidateRequest, request: Request):
    limit(request)
    return stream_response(review_events(body.requirement, body.code, body.language), request)


@app.post("/api/generate-code")
async def generate_compat(body: GenerateRequest, request: Request):
    limit(request)
    result = {}
    async for value in bounded_events(generation_events(body), request):
        if value["type"] == "chat":
            return {"mode": "chat", "content": value["content"], "can_validate": False}
        if value["type"] == "code":
            result.update(mode="code", content=value["code"], code=value["code"], language=body.language, source=value["source"], can_validate=True)
        elif value["type"] == "done":
            result["report"] = value["report"]
        elif value["type"] == "error":
            raise HTTPException(503, value["message"])
    return result


@app.post("/api/validate-code")
async def validate_compat(body: ValidateRequest, request: Request):
    limit(request)
    async for value in bounded_events(review_events(body.requirement, body.code, body.language), request):
        if value["type"] == "done":
            return value["report"]
        if value["type"] == "error":
            raise HTTPException(503, value["message"])


@app.get("/")
async def index():
    return FileResponse(BASE / "static" / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
