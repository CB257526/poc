"""约稿工作流 HTTP API，供 Streamlit 或其他前端调用。"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from workflows.models import WorkflowContext
from workflows.nodes.node_00_input import Node00Input
from workflows.workflow_run import run_workflow


BASE_DIR = Path(os.getenv("WORKFLOW_RUNTIME_DIR", "./runtime")).resolve()
TABLE_DIR = Path(os.getenv("WORKFLOW_TABLE_DIR", "./table")).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="约稿平台 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_tasks: dict[str, dict[str, Any]] = {}
_task_lock = threading.Lock()


def _database_path() -> Path:
    return BASE_DIR / "workflow.db"


def _init_database() -> None:
    with sqlite3.connect(_database_path()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS completed_batches (
                task_id TEXT PRIMARY KEY,
                month TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                quote_count INTEGER NOT NULL,
                total_fee REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS completed_details (
                task_id TEXT NOT NULL,
                detail_id TEXT NOT NULL,
                month TEXT NOT NULL,
                media TEXT NOT NULL,
                article_type TEXT,
                fee REAL NOT NULL,
                PRIMARY KEY (task_id, detail_id)
            );
            """
        )


def _detail_month(detail: dict[str, Any]) -> str:
    value = str(detail.get("发布日期") or "").strip().replace("/", "-")
    return value[:7] if len(value) >= 7 and value[:4].isdigit() else ""


def _save_completed_statistics(task_id: str, context: WorkflowContext) -> None:
    details = [
        detail for detail in (context.quote_details or {}).get("details", [])
        if detail.get("eligible_for_monthly_summary") is True and _detail_month(detail)
    ]
    if not details:
        return
    _init_database()
    processed_at = datetime.now().isoformat()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for detail in details:
        grouped.setdefault(_detail_month(detail), []).append(detail)
    with sqlite3.connect(_database_path()) as connection:
        for month, month_details in grouped.items():
            batch_key = f"{task_id}:{month}"
            connection.execute(
                "INSERT OR REPLACE INTO completed_batches VALUES (?, ?, ?, ?, ?)",
                (batch_key, month, processed_at, len(month_details), sum(float(d.get("费用") or 0) for d in month_details)),
            )
            for index, detail in enumerate(month_details):
                detail_id = str(detail.get("id") or index)
                connection.execute(
                    "INSERT OR REPLACE INTO completed_details VALUES (?, ?, ?, ?, ?, ?)",
                    (task_id, detail_id, month, str(detail.get("媒体") or ""), str(detail.get("文章类型") or ""), float(detail.get("费用") or 0)),
                )


class CorrectionRequest(BaseModel):
    media_name_corrections: dict[str, str] = Field(default_factory=dict)


def _issue_dict(issue) -> dict[str, Any]:
    return issue.model_dump()


def _record_dict(record: dict[str, Any]) -> dict[str, Any]:
    links = record.get("链接") or []
    if not isinstance(links, list):
        links = [links]
    return {
        "record_id": record.get("id"),
        "row_number": record.get("row_number"),
        "topic": record.get("主题"),
        "media_name": record.get("媒体"),
        "link_count": len(links),
        "link_preview": "\n".join(str(item) for item in links[:2]),
    }


def _validate_task(task_id: str, corrections: dict[str, str] | None = None) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    context = WorkflowContext(
        run_id=f"precheck_{task_id}",
        input_file=task["input_file"],
        table_dir=str(TABLE_DIR),
        config={"media_name_corrections": corrections or {}},
    )
    output = Node00Input().process(context)
    issues = output.issues
    blocking_issues = [issue for issue in issues if issue.level in {"critical", "error"}]
    records = output.data.get("records", [])
    allowed_names = sorted({
        name
        for issue in issues if issue.code == "MEDIA_NOT_IN_LIBRARY"
        for name in issue.details.get("allowed_media_names", [])
    })
    task.update({
        "status": "needs_correction" if blocking_issues else "ready",
        "corrections": corrections or {},
        "records": records,
        "issues": issues,
        "updated_at": datetime.now().isoformat(),
    })
    return {
        "task_id": task_id,
        "status": task["status"],
        "records": [_record_dict(record) for record in records],
        "issues": [_issue_dict(issue) for issue in issues],
        "allowed_media_names": allowed_names,
    }


def _execute_task(task_id: str) -> None:
    task = _tasks[task_id]
    try:
        context = run_workflow(
            input_file=task["input_file"],
            table_dir=str(TABLE_DIR),
            config={
                "media_name_corrections": task.get("corrections", {}),
                "output_dir": task["output_dir"],
            },
        )
        task.update({
            "status": "failed" if context.has_critical_errors() else "completed",
            "context": context,
            "issues": context.issues,
            "updated_at": datetime.now().isoformat(),
        })
        if task["status"] == "completed":
            _save_completed_statistics(task_id, context)
    except Exception as exc:
        task.update({"status": "failed", "error": str(exc), "updated_at": datetime.now().isoformat()})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/tasks/validate")
async def validate_upload(request: Request) -> dict[str, Any]:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    task_id = uuid.uuid4().hex
    task_dir = BASE_DIR / task_id
    upload_dir = task_dir / "uploads"
    output_dir = task_dir / "outputs"
    upload_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    input_path = upload_dir / "1-链接.xlsx"
    input_path.write_bytes(content)
    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "validating",
            "input_file": str(input_path),
            "output_dir": str(output_dir),
            "created_at": datetime.now().isoformat(),
        }
    return _validate_task(task_id)


@app.post("/api/v1/tasks/{task_id}/corrections")
def submit_corrections(task_id: str, request: CorrectionRequest) -> dict[str, Any]:
    return _validate_task(task_id, request.media_name_corrections)


@app.post("/api/v1/tasks/{task_id}/run", status_code=202)
def start_task(task_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "ready":
        raise HTTPException(status_code=409, detail="输入预检尚未通过")
    task["status"] = "running"
    background_tasks.add_task(_execute_task, task_id)
    return {"task_id": task_id, "status": "running"}


@app.get("/api/v1/tasks/{task_id}")
def task_status(task_id: str) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    context = task.get("context")
    return {
        "task_id": task_id,
        "status": task["status"],
        "error": task.get("error"),
        "completed_nodes": context.completed_nodes if context else [],
        "issues": [_issue_dict(issue) for issue in task.get("issues", [])],
        "quote_summary": context.quote_details if context else None,
        "monthly_summary": context.monthly_summary if context else None,
        "files": list(context.output_files) if context else [],
    }


@app.get("/api/v1/tasks/{task_id}/files/{file_key}")
def download_file(task_id: str, file_key: str):
    task = _tasks.get(task_id)
    context = task.get("context") if task else None
    if not context or file_key not in context.output_files:
        raise HTTPException(status_code=404, detail="结果文件不存在")
    path = Path(context.output_files[file_key]).resolve()
    output_dir = Path(task["output_dir"]).resolve()
    if output_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    return FileResponse(path, filename=path.name)


@app.get("/api/v1/analytics/monthly")
def monthly_analytics(month: str | None = None) -> dict[str, Any]:
    target_month = month or datetime.now().strftime("%Y-%m")
    _init_database()
    with sqlite3.connect(_database_path()) as connection:
        connection.row_factory = sqlite3.Row
        summary = connection.execute(
            """
            SELECT COUNT(*) AS batch_count,
                   COALESCE(SUM(quote_count), 0) AS quote_count,
                   COALESCE(SUM(total_fee), 0) AS total_fee
            FROM completed_batches WHERE month = ?
            """,
            (target_month,),
        ).fetchone()
        batches = connection.execute(
            """
            SELECT task_id, processed_at, quote_count, total_fee
            FROM completed_batches WHERE month = ? ORDER BY processed_at
            """,
            (target_month,),
        ).fetchall()
        top_media = connection.execute(
            """
            SELECT media, COUNT(*) AS quote_count, SUM(fee) AS total_fee
            FROM completed_details WHERE month = ?
            GROUP BY media ORDER BY total_fee DESC LIMIT 10
            """,
            (target_month,),
        ).fetchall()
    batch_count = int(summary["batch_count"])
    total_fee = float(summary["total_fee"])
    return {
        "month": target_month,
        "batch_count": batch_count,
        "quote_count": int(summary["quote_count"]),
        "total_fee": total_fee,
        "average_batch_fee": total_fee / batch_count if batch_count else 0,
        "batches": [dict(row) for row in batches],
        "top_media": [dict(row) for row in top_media],
    }


def main() -> None:
    import uvicorn
    uvicorn.run("workflows.api:app", host="0.0.0.0", port=8000, reload=False)
