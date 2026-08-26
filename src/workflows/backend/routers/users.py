"""用户管理：/api/v1/users"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..errors import ApiError
from ..models import User
from .auth import user_payload

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class PatchUserBody(BaseModel):
    role: str | None = None
    status: str | None = None


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    status_order = case(
        (User.status == "pending", 0),
        (User.status == "active", 1),
        else_=2,
    )
    users = db.query(User).order_by(status_order, User.created_at.desc()).all()
    return [user_payload(u) for u in users]


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: PatchUserBody,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ApiError("用户不存在", code="NOT_FOUND", status_code=404)
    if user.id == admin.id and body.status == "disabled":
        raise ApiError("不能停用自己", code="VALIDATION_ERROR", status_code=400)
    if body.role is not None:
        if body.role not in {"admin", "operator", "finance", "viewer"}:
            raise ApiError("非法角色", code="VALIDATION_ERROR", status_code=400)
        user.role = body.role
    if body.status is not None:
        if body.status not in {"pending", "active", "disabled"}:
            raise ApiError("非法状态", code="VALIDATION_ERROR", status_code=400)
        user.status = body.status
    db.commit()
    db.refresh(user)
    return user_payload(user)
