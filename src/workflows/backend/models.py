"""业务库表。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _now() -> datetime:
    return datetime.now()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    input_file_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    records_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_media_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrections_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_file_path: Mapped[str | None] = mapped_column(String, nullable=True)


class ConfigFile(Base):
    __tablename__ = "config_files"

    kind: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)


class FeeException(Base):
    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target: Mapped[str] = mapped_column(String, default="费用核算结果")
    issue: Mapped[str] = mapped_column(String, default="两个子表费用不一致")
    suggestion: Mapped[str] = mapped_column(
        String, default="核对「约稿」与「约稿费用合计」的媒体费用及总费用"
    )
    status: Mapped[str] = mapped_column(String, default="待确认")
    correction: Mapped[str] = mapped_column(Text, default="")
    calculation_json: Mapped[str] = mapped_column(Text, default="[]")
    compare_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
