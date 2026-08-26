"""后台跑完整工作流，并把进度写回 tasks 表。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from workflows.paths import default_table_dir

from .database import SessionLocal, ensure_db
from .models import FeeException, Task
from .task_support import (
    dumps,
    files_payload,
    loads,
    media_fee_from_quote_sheet,
    media_fee_from_summary_sheet,
    quote_summary_from_context,
    workflow_issues,
)


def _session() -> Session:
    return SessionLocal()


def execute_workflow(task_id: str) -> None:
    ensure_db()
    db = _session()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
        task.status = "running"
        task.updated_at = datetime.now()
        task.error = None
        task.progress_json = dumps(
            {"completed_nodes": ["node_00"], "total_nodes": 7, "current_node": "node_00"}
        )
        db.commit()

        corrections = {}
        if task.corrections_json:
            import json

            corrections = json.loads(task.corrections_json)

        def on_progress(context) -> None:
            inner = _session()
            try:
                row = inner.query(Task).filter(Task.id == task_id).first()
                if not row:
                    return
                row.status = "running"
                row.updated_at = datetime.now()
                row.progress_json = dumps(
                    {
                        "completed_nodes": list(context.completed_nodes),
                        "total_nodes": 7,
                        "current_node": context.current_node,
                    }
                )
                row.issues_json = dumps(workflow_issues(context))
                inner.commit()
            finally:
                inner.close()

        from workflows.workflow_run import run_workflow

        context = run_workflow(
            input_file=task.input_file_path,
            table_dir=str(default_table_dir()),
            config={"media_name_corrections": corrections},
            run_id=task.run_id,
            on_progress=on_progress,
        )

        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
        failed = context.run_status in {"failed", "terminated"} or context.has_critical_errors()
        task.status = "failed" if failed else "completed"
        task.updated_at = datetime.now()
        task.progress_json = dumps(
            {
                "completed_nodes": list(context.completed_nodes),
                "total_nodes": 7,
                "current_node": None if not failed else context.current_node,
            }
        )
        task.issues_json = dumps(workflow_issues(context))
        if failed:
            task.error = context.termination_reason or "工作流执行失败"
            task.quote_summary_json = None
        else:
            task.error = None
            task.quote_summary_json = dumps(quote_summary_from_context(context))
            quote_path = context.output_files.get("quote_detail")
            payment_path = context.output_files.get("payment")
            task.quote_file_path = quote_path
            task.payment_file_path = payment_path
            task.files_json = dumps(files_payload(task))
            if quote_path:
                _sync_exceptions(db, task, quote_path)
        db.commit()
    except Exception as exc:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = "failed"
            task.error = str(exc)
            task.updated_at = datetime.now()
            issues = loads(task.issues_json, [])
            issues.append(
                {
                    "record_id": None,
                    "node_id": None,
                    "code": "WORKFLOW_CRASH",
                    "message": str(exc),
                    "severity": "critical",
                }
            )
            task.issues_json = dumps(issues)
            db.commit()
    finally:
        db.close()


def _sync_exceptions(db: Session, task: Task, quote_path: str) -> None:
    from .seed import new_id

    if not Path(quote_path).is_file():
        return
    try:
        detail = media_fee_from_quote_sheet(quote_path)
        summary = media_fee_from_summary_sheet(quote_path)
    except Exception:
        return
    compare = []
    mismatched = False
    for media in sorted(set(detail) | set(summary)):
        d = round(detail.get(media, 0.0), 2)
        s = round(summary.get(media, 0.0), 2)
        ok = abs(d - s) < 0.01
        if not ok:
            mismatched = True
        compare.append(
            {
                "media_name": media,
                "detail_fee": d,
                "summary_fee": s,
                "status": "一致" if ok else "不一致",
            }
        )
    existing = db.query(FeeException).filter(FeeException.task_id == task.id).first()
    if not mismatched:
        if existing and existing.status != "已解决":
            existing.status = "已解决"
            existing.correction = existing.correction or "两个子表费用已一致"
            existing.compare_json = dumps(compare)
            existing.updated_at = datetime.now()
        return
    calculation = []
    summary_obj = None
    if task.quote_summary_json:
        import json

        summary_obj = json.loads(task.quote_summary_json)
    for row in (summary_obj or {}).get("details") or []:
        calculation.append(
            {
                "media_name": row.get("media_name"),
                "platform": row.get("platform"),
                "content_type": row.get("content_type"),
                "work_count": row.get("quote_count") or 1,
                "fee_rule": f"{row.get('media_level') or ''}级{row.get('content_type') or ''}核定价",
                "unit_price": row.get("unit_price") or 0,
                "expected_fee": row.get("amount") or 0,
            }
        )
    if existing is None:
        db.add(
            FeeException(
                id=new_id("ex"),
                task_id=task.id,
                status="待确认",
                calculation_json=dumps(calculation),
                compare_json=dumps(compare),
            )
        )
    else:
        existing.status = "待确认"
        existing.correction = ""
        existing.calculation_json = dumps(calculation)
        existing.compare_json = dumps(compare)
        existing.updated_at = datetime.now()
