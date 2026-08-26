"""GET /api/v1/analytics/monthly"""

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Task, User
from ..task_support import iso, is_text_type, is_video_type, loads, parse_month

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/monthly")
def monthly(
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    target = month or datetime.now().strftime("%Y-%m")
    tasks = (
        db.query(Task)
        .filter(Task.status == "completed")
        .order_by(Task.updated_at.asc())
        .all()
    )
    batches = []
    media_fees: dict[str, float] = defaultdict(float)
    quote_count = 0
    total_fee = 0.0

    for task in tasks:
        # “当月汇总”按系统处理批次归月，而不是按作品发布日期归月。
        # 作品可能发布于更早月份，但只要本月上传并完成处理，就应计入本月记录。
        if parse_month(task.updated_at) != target:
            continue
        summary = loads(task.quote_summary_json, None) or {}
        details = summary.get("details") or []
        month_details = details

        text_fee = 0.0
        video_fee = 0.0
        unclassified_fee = 0.0
        batch_fee = 0.0
        for row in month_details:
            amount = float(row.get("amount") or 0)
            batch_fee += amount
            media_fees[str(row.get("media_name") or "")] += amount
            if is_text_type(str(row.get("content_type") or "")):
                text_fee += amount
            elif is_video_type(str(row.get("content_type") or "")):
                video_fee += amount
            else:
                unclassified_fee += amount
        if not details:
            batch_fee = float(summary.get("total_fee") or 0)
            text_fee = float(summary.get("text_fee") or 0)
            video_fee = float(summary.get("video_fee") or 0)
            unclassified_fee = float(summary.get("unclassified_fee") or 0)

        count = len(details) if details else int(summary.get("quote_count") or 0)
        quote_count += count
        total_fee += batch_fee
        batches.append(
            {
                "task_id": task.id,
                "processed_at": iso(task.updated_at),
                "quote_count": count,
                "total_fee": round(batch_fee, 2),
                "text_fee": round(text_fee, 2),
                "video_fee": round(video_fee, 2),
                "unclassified_fee": round(unclassified_fee, 2),
            }
        )

    top_media = [
        {"media": name, "total_fee": round(fee, 2)}
        for name, fee in sorted(media_fees.items(), key=lambda item: item[1], reverse=True)
        if name
    ][:10]
    batch_count = len(batches)
    return {
        "month": target,
        "batch_count": batch_count,
        "quote_count": quote_count,
        "total_fee": round(total_fee, 2),
        "average_batch_fee": round(total_fee / batch_count, 2) if batch_count else 0,
        "batches": batches,
        "top_media": top_media,
    }
