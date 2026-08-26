"""用户 id 生成与种子账号。"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from .auth import hash_password
from .models import User

SEED_USERS = [
    ("u_admin", "admin@byd.local", "管理员", "admin"),
    ("u_op", "operator@byd.local", "业务经办", "operator"),
    ("u_fin", "finance@byd.local", "财务", "finance"),
    ("u_view", "viewer@byd.local", "只读访客", "viewer"),
]

DEMO_PASSWORD = "Passw0rd!"


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def seed_users(db: Session) -> None:
    for user_id, email, name, role in SEED_USERS:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            continue
        db.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                name=name,
                role=role,
                status="active",
            )
        )
    db.commit()
