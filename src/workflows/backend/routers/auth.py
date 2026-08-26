"""认证路由：/api/v1/auth/*"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..database import get_db
from ..errors import ApiError
from ..models import User
from ..seed import new_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    email: str
    name: str = Field(min_length=1)
    password: str = Field(min_length=8)


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ApiError("邮箱格式不正确", code="VALIDATION_ERROR", status_code=400, field_errors={"email": "邮箱格式不正确"})
    return value


class RefreshBody(BaseModel):
    refresh_token: str


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def tokens_payload(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
    }


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise ApiError("邮箱或密码不正确", code="INVALID_CREDENTIALS", status_code=401)
    if user.status == "pending":
        raise ApiError("账号待管理员审核，暂不能登录", code="ACCOUNT_PENDING", status_code=403)
    if user.status == "disabled":
        raise ApiError("账号已停用", code="ACCOUNT_DISABLED", status_code=403)
    if user.status != "active":
        raise ApiError("账号尚未启用或已停用", code="ACCOUNT_INACTIVE", status_code=403)
    user.last_login_at = datetime.now()
    db.commit()
    db.refresh(user)
    return {"user": user_payload(user), "tokens": tokens_payload(user)}


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ApiError("该邮箱已注册", code="EMAIL_TAKEN", status_code=409, field_errors={"email": "该邮箱已注册"})
    user = User(
        id=new_id("u"),
        email=email,
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        role="operator",
        status="pending",
    )
    db.add(user)
    db.commit()
    return {"message": "注册成功，请等待管理员审核后再登录"}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return user_payload(current_user)


@router.post("/logout")
def logout(_current_user: User = Depends(get_current_user)):
    return {"ok": True}


@router.post("/refresh")
def refresh(body: RefreshBody, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, "refresh")
    user = db.query(User).filter(User.id == str(payload.get("sub"))).first()
    if not user or user.status != "active":
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401)
    return tokens_payload(user)
