"""HTTP layer only: request ids, error contract, routes. Logic lives in other modules."""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dotenv import load_dotenv

from app.ask import answer_question
from app.data import load_dataset
from app.llm import DEFAULT_MODEL, LLMUnavailable, llm_configured
from app.policy import load_policy
from app.schemas import AskRequest, AskResponse, ErrorCode, ErrorDetail, ErrorResponse, SummaryResponse
from app.summary import build_summary

load_dotenv()  # backend/.env (git-ignored) holds ANTHROPIC_API_KEY
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finance_assistant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast: if the data or the policy doesn't validate, the app doesn't start.
    app.state.dataset = load_dataset()
    app.state.policy = load_policy()
    logger.info("Answering mode: %s", "llm" if llm_configured() else "STUB (no ANTHROPIC_API_KEY)")
    yield


app = FastAPI(title="Finance spend assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info("%s %s -> %s [%s]", request.method, request.url.path,
                response.status_code, request.state.request_id)
    return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(request: Request, status: int, code: ErrorCode,
                   message: str, retryable: bool) -> JSONResponse:
    body = ErrorResponse(
        request_id=_request_id(request),
        error=ErrorDetail(code=code, message=message, retryable=retryable),
    )
    return JSONResponse(status_code=status, content=body.model_dump(),
                        headers={"X-Request-ID": _request_id(request)})


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return error_response(request, 422, "invalid_request", msg, retryable=False)


@app.exception_handler(StarletteHTTPException)
async def on_http_error(request: Request, exc: StarletteHTTPException):
    code: ErrorCode = "not_found" if exc.status_code == 404 else "invalid_request"
    return error_response(request, exc.status_code, code, str(exc.detail), retryable=False)


@app.exception_handler(LLMUnavailable)
async def on_llm_unavailable(request: Request, exc: LLMUnavailable):
    # A system failure: 503, and no silent fallback to the stub.
    return error_response(request, 503, "llm_unavailable", str(exc), retryable=exc.retryable)


@app.exception_handler(Exception)
async def on_unexpected_error(request: Request, exc: Exception):
    logger.exception("Unhandled error [%s]", _request_id(request))
    return error_response(request, 500, "internal_error",
                          "Unexpected server error. Quote the request id when reporting it.",
                          retryable=True)


@app.get("/health")
def health(request: Request) -> dict:
    """Liveness + which answering mode is active (the UI shows a STUB banner)."""
    configured = llm_configured()
    return {"request_id": _request_id(request), "status": "ok",
            "mode": "llm" if configured else "stub",
            "model": os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL) if configured else None}


@app.get("/summary", response_model=SummaryResponse)
def get_summary(request: Request) -> SummaryResponse:
    return build_summary(request.app.state.dataset, _request_id(request))


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    # Sync def: FastAPI runs it in a thread pool, so the blocking LLM call doesn't stall the server.
    return answer_question(body.question, request.app.state.dataset, request.app.state.policy,
                           _request_id(request))
