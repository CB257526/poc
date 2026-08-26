"""异常核验：/api/v1/exceptions"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..errors import ApiError
from ..models import FeeException, Task, User
from ..task_support import dumps, loads, write_summary_fees

router = APIRouter(prefix="/api/v1/exceptions", tags=["exceptions"])


class PatchExceptionBody(BaseModel):
    summary_fees: dict[str, float]


def item_payload(row: FeeException) -> dict:
    return {
        "exception_id": row.id,
        "task_id": row.task_id,
        "target": row.target,
        "issue": row.issue,
        "suggestion": row.suggestion,
        "status": row.status,
        "correction": row.correction or "",
        "calculation": loads(row.calculation_json, []),
        "compare": loads(row.compare_json, []),
    }


@router.get("")
def list_exceptions(
    task_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    query = db.query(FeeException)
    if task_id:
        query = query.filter(FeeException.task_id == task_id)
    rows = query.order_by(FeeException.created_at.desc()).all()
    return [item_payload(row) for row in rows]


@router.patch("/{exception_id}")
def save_exception(
    exception_id: str,
    body: PatchExceptionBody,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    row = db.query(FeeException).filter(FeeException.id == exception_id).first()
    if not row:
        raise ApiError("异常不存在", code="NOT_FOUND", status_code=404)
    compare = loads(row.compare_json, [])
    updated = []
    mismatch = False
    total = 0.0
    for item in compare:
        media = item.get("media_name")
        detail = float(item.get("detail_fee") or 0)
        summary = float(body.summary_fees.get(media, item.get("summary_fee") or 0))
        ok = abs(summary - detail) < 0.01
        if not ok:
            mismatch = True
        total += detail
        updated.append(
            {
                "media_name": media,
                "detail_fee": detail,
                "summary_fee": summary,
                "status": "一致" if ok else "不一致",
            }
        )
    if mismatch:
        raise ApiError(
            "请先修改红色金额，确保两个子表中各媒体费用及总费用全部一致。",
            code="AMOUNTS_MISMATCH",
            status_code=400,
        )
    task = db.query(Task).filter(Task.id == row.task_id).first()
    if task and task.quote_file_path:
        write_summary_fees(task.quote_file_path, {k: float(v) for k, v in body.summary_fees.items()})
    row.compare_json = dumps(updated)
    row.status = "待校对"
    row.correction = f"两个子表费用已一致，总费用 ¥{total:,.0f}"
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return item_payload(row)


@router.post("/reaudit")
def reaudit(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    rows = db.query(FeeException).all()
    for row in rows:
        if row.status == "待校对" and row.correction:
            row.status = "已解决"
            row.updated_at = datetime.now()
    db.commit()
    remaining = db.query(FeeException).filter(FeeException.status != "已解决").count()
    resolved = db.query(FeeException).filter(FeeException.status == "已解决").count()
    return {"resolved": resolved, "remaining": remaining}
