"""GET /api/v1/dashboard/overview"""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config_store import config_status_payload
from ..database import get_db
from ..models import FeeException, Task, User
from ..task_support import STATUS_LABELS, loads, task_payload

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    latest = db.query(Task).order_by(Task.created_at.desc()).first()
    pending = (
        db.query(FeeException)
        .filter(FeeException.status != "已解决")
        .count()
    )
    config = config_status_payload(db)
    if latest is None:
        return {
            "latest_task": None,
            "task_status_label": "待处理",
            "media_count": 0,
            "quote_count": 0,
            "total_fee": 0,
            "type_distribution": [],
            "pending_exceptions": pending,
            "config_ready": config["all_ready"],
        }

    summary = loads(latest.quote_summary_json, None) if latest.status == "completed" else None
    details = (summary or {}).get("details") or []
    type_counts = Counter(d.get("content_type") or "其他" for d in details)
    return {
        "latest_task": task_payload(latest),
        "task_status_label": STATUS_LABELS.get(latest.status, latest.status),
        "media_count": (summary or {}).get("media_count") or 0,
        "quote_count": (summary or {}).get("quote_count") or 0,
        "total_fee": (summary or {}).get("total_fee") or 0,
        "type_distribution": [
            {"content_type": name, "quote_count": count}
            for name, count in type_counts.items()
            if count
        ],
        "pending_exceptions": pending,
        "config_ready": config["all_ready"],
    }
