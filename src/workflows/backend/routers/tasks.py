"""任务：validate / corrections / run / get / latest / files。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workflows.paths import runtime_dir

from ..auth import get_current_user, require_role
from ..database import get_db
from ..errors import ApiError
from ..jobs import execute_workflow
from ..models import Task, User
from ..seed import new_id
from ..task_support import (
    apply_preview,
    dumps,
    loads,
    preview_validate,
    task_payload,
    touch,
    validate_payload,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class CorrectionsBody(BaseModel):
    media_name_corrections: dict[str, str]


def _uploads_dir() -> Path:
    path = runtime_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_task(db: Session, task_id: str) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise ApiError("任务不存在", code="NOT_FOUND", status_code=404)
    return task


@router.post("/validate")
async def validate_task(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    content_type = (request.headers.get("content-type") or "").lower()
    filename = "1-链接.xlsx"
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise ApiError("请先上传 1-链接.xlsx", code="VALIDATION_ERROR", status_code=400)
        content = await upload.read()
        filename = getattr(upload, "filename", None) or filename
    else:
        content = await request.body()
    if not content:
        raise ApiError("请先上传 1-链接.xlsx", code="VALIDATION_ERROR", status_code=400)
    if not str(filename).lower().endswith(".xlsx"):
        raise ApiError("请上传 .xlsx 文件", code="VALIDATION_ERROR", status_code=400)

    task_id = new_id("task")
    run_id = new_id("run")
    dest = _uploads_dir() / f"{task_id}.xlsx"
    dest.write_bytes(content)

    try:
        preview = preview_validate(str(dest))
    except ApiError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ApiError(f"没有读取到有效的媒体与链接: {exc}", code="VALIDATION_ERROR", status_code=400) from exc

    task = Task(
        id=task_id,
        run_id=run_id,
        filename=str(filename),
        input_file_path=str(dest),
        status=preview["status"],
        created_by=user.id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    apply_preview(task, preview)
    db.add(task)
    db.commit()
    db.refresh(task)
    return validate_payload(task)


@router.post("/{task_id}/corrections")
def submit_corrections(
    task_id: str,
    body: CorrectionsBody,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    task = _get_task(db, task_id)
    if task.status != "needs_correction":
        raise ApiError("当前任务状态不允许修正", code="TASK_CONFLICT", status_code=409)

    allowed = set(loads(task.allowed_media_json, []))
    cleaned: dict[str, str] = {}
    for key, value in body.media_name_corrections.items():
        name = str(value).strip()
        if not name:
            continue
        if allowed and name not in allowed:
            raise ApiError(
                f"媒体名不在允许列表: {name}",
                code="UNPROCESSABLE",
                status_code=422,
            )
        cleaned[str(key)] = name

    existing = loads(task.corrections_json, {})
    existing.update(cleaned)
    task.corrections_json = dumps(existing)
    try:
        preview = preview_validate(task.input_file_path, existing)
    except Exception as exc:
        raise ApiError(str(exc), code="UNPROCESSABLE", status_code=422) from exc
    apply_preview(task, preview)
    db.commit()
    db.refresh(task)
    return validate_payload(task)


@router.post("/{task_id}/run", status_code=202)
def run_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    task = _get_task(db, task_id)
    if task.status != "ready":
        raise ApiError("当前任务状态不允许启动", code="TASK_CONFLICT", status_code=409)
    task.status = "running"
    touch(task)
    db.commit()
    background_tasks.add_task(execute_workflow, task_id)
    return {"task_id": task.id, "status": "running"}


@router.get("/latest")
def latest_task(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    task = db.query(Task).order_by(Task.created_at.desc()).first()
    if not task:
        return None
    return task_payload(task)


@router.get("/{task_id}")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return task_payload(_get_task(db, task_id))


@router.get("/{task_id}/files/archive")
def download_archive(
    task_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator", "finance")),
):
    import io
    import zipfile

    task = _get_task(db, task_id)
    if task.status != "completed":
        raise ApiError("任务尚未完成，无法下载", code="TASK_CONFLICT", status_code=409)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in (
            (task.quote_file_path, Path(task.quote_file_path).name if task.quote_file_path else None),
            (task.payment_file_path, Path(task.payment_file_path).name if task.payment_file_path else None),
        ):
            if path and Path(path).is_file() and arcname:
                zf.write(path, arcname)
    filename = "约稿费用验收_处理结果.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="quote_results.zip"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/{task_id}/files/{file_key}")
def download_file(
    task_id: str,
    file_key: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator", "finance")),
):
    task = _get_task(db, task_id)
    if task.status != "completed":
        raise ApiError("任务尚未完成，无法下载", code="TASK_CONFLICT", status_code=409)
    mapping = {
        "quote_detail": task.quote_file_path,
        "payment": task.payment_file_path,
    }
    if file_key not in mapping:
        raise ApiError("文件类型不存在", code="NOT_FOUND", status_code=404)
    path = mapping[file_key]
    if not path or not Path(path).is_file():
        raise ApiError("文件尚未生成", code="NOT_FOUND", status_code=404)
    return FileResponse(
        path=path,
        filename=Path(path).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
