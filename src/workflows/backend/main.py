"""FastAPI 入口。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config_store import ensure_config_rows
from .database import SessionLocal, init_db
from .errors import ApiError, api_error_handler
from .routers import analytics, auth, config, dashboard, exceptions, tasks, users
from .seed import seed_users

app = FastAPI(
    title="约稿费用验收系统",
    description="约稿费用验收工作流 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(detail) if detail else "请求失败", "code": "HTTP_ERROR"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    field_errors = {}
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part != "body"]
        key = ".".join(loc) if loc else "body"
        field_errors[key] = err.get("msg") or "参数不合法"
    return JSONResponse(
        status_code=400,
        content={
            "detail": next(iter(field_errors.values()), "参数不合法"),
            "code": "VALIDATION_ERROR",
            "field_errors": field_errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception):
    if isinstance(exc, ApiError):
        return await api_error_handler(_request, exc)
    if isinstance(exc, StarletteHTTPException):
        return await http_error_handler(_request, exc)
    if isinstance(exc, RequestValidationError):
        return await validation_error_handler(_request, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后重试或查看后端日志",
            "code": "INTERNAL",
        },
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(config.router)
app.include_router(tasks.router)
app.include_router(analytics.router)
app.include_router(exceptions.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    try:
        seed_users(db)
        ensure_config_rows(db)
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "约稿费用验收系统 API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
