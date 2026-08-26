"""配置表落盘到 table/。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from workflows.paths import default_table_dir

from .models import ConfigFile, User

# 工作流只读 3/4/5。表 2、表 6 由 node_06 按固定模板生成，不要求管理员上传。
CONFIG_KINDS: dict[str, dict[str, str]] = {
    "media_library": {
        "filename": "3-媒体库.xlsx",
        "label": "媒体库",
    },
    "accounts": {
        "filename": "4-账户信息.xlsx",
        "label": "账户信息",
    },
    "fee_rules": {
        "filename": "5-费用.xlsx",
        "label": "费用规则",
    },
}


def table_dir() -> Path:
    path = default_table_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def existing_table_file(kind: str) -> Path | None:
    meta = CONFIG_KINDS.get(kind)
    if meta is None:
        return None
    path = table_dir() / meta["filename"]
    return path if path.is_file() else None


def ensure_config_rows(db: Session) -> None:
    for kind, meta in CONFIG_KINDS.items():
        row = db.query(ConfigFile).filter(ConfigFile.kind == kind).first()
        disk = existing_table_file(kind)
        if row is None:
            row = ConfigFile(kind=kind)
            db.add(row)
        if disk is not None:
            row.configured = True
            row.filename = disk.name
            row.file_path = str(disk)
            if row.updated_at is None:
                row.updated_at = datetime.fromtimestamp(disk.stat().st_mtime)
        else:
            if not row.configured:
                row.filename = meta["filename"]
    db.commit()


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def config_status_payload(db: Session) -> dict:
    ensure_config_rows(db)
    files = []
    for kind, meta in CONFIG_KINDS.items():
        row = db.query(ConfigFile).filter(ConfigFile.kind == kind).first()
        configured = bool(row and row.configured and row.file_path and Path(row.file_path).is_file())
        files.append(
            {
                "kind": kind,
                "label": meta["label"],
                "configured": configured,
                "filename": (row.filename if row else meta["filename"]) if configured or (row and row.filename) else meta["filename"],
                "updated_at": iso(row.updated_at) if row else None,
                "updated_by": row.updated_by if row else None,
            }
        )
    return {"all_ready": all(item["configured"] for item in files), "files": files}


def save_config_upload(db: Session, kind: str, content: bytes, original_name: str, user: User) -> dict:
    if kind not in CONFIG_KINDS:
        from .errors import ApiError

        raise ApiError("非法配置类型", code="VALIDATION_ERROR", status_code=400)
    target_name = CONFIG_KINDS[kind]["filename"]
    dest = table_dir() / target_name
    dest.write_bytes(content)
    row = db.query(ConfigFile).filter(ConfigFile.kind == kind).first()
    if row is None:
        row = ConfigFile(kind=kind)
        db.add(row)
    row.filename = original_name or target_name
    row.file_path = str(dest)
    row.configured = True
    row.updated_at = datetime.now()
    row.updated_by = user.id
    db.commit()
    return config_status_payload(db)
