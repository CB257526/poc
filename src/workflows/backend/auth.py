"""JWT 与角色校验。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .errors import ApiError
from .models import User

SECRET_KEY = "byd-workflow-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 7200
REFRESH_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401) from exc
    if payload.get("type") != expected_type:
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401)
    return payload


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401)
    payload = decode_token(credentials.credentials, "access")
    user_id = payload.get("sub")
    if not user_id:
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401)
    user = db.query(User).filter(User.id == str(user_id)).first()
    if user is None:
        raise ApiError("未登录或登录已过期", code="UNAUTHENTICATED", status_code=401)
    if user.status != "active":
        raise ApiError("账号尚未启用或已停用", code="ACCOUNT_INACTIVE", status_code=403)
    return user


def require_role(*allowed_roles: str):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ApiError("当前角色无权执行该操作", code="FORBIDDEN", status_code=403)
        return current_user

    return checker
