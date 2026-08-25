"""给 MCP / HTTP 用的查询视图。永远返回摘要，不 dump 整份 context。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from workflows.runtime.catalog import WORKFLOW_NODES, get_node_catalog, remaining_nodes
from workflows.runtime.store import RunStore, get_run_store

STALE_AFTER_SECONDS = 15 * 60
TERMINAL_STATUSES = {"completed", "failed", "terminated"}


class WorkflowQueryError(LookupError):
    pass


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _bool_param(value: bool | str | None) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


class WorkflowQueryService:
    def __init__(self, store: RunStore | None = None):
        self.store = store or get_run_store()

    def list_runs(
        self,
        status: str | None = None,
        limit: int = 20,
        input_file: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        rows = self.store.list_runs(
            status=status,
            limit=limit,
            input_file=input_file,
            since=since,
            until=until,
        )
        return {
            "runs": [
                {
                    "run_id": row["run_id"],
                    "status": row["status"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "updated_at": row.get("updated_at"),
                    "current_node": row["current_node"],
                    "input_file": row.get("input_file"),
                    "records": row["records_count"],
                    "completed_nodes": row["completed_nodes"],
                    "issue_counts": row["issue_counts"],
                    "termination_reason": row["termination_reason"],
                    "stale": self._is_stale(row),
                }
                for row in rows
            ]
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id)
        if not row:
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        completed = row["completed_nodes"]
        quote_summary = json.loads(row["quote_summary_json"]) if row.get("quote_summary_json") else None
        paths = {}
        if row.get("paths_json"):
            try:
                paths = json.loads(row["paths_json"]) or {}
            except json.JSONDecodeError:
                paths = {}
        artifacts = row.get("artifacts") or []
        output_dir = paths.get("output_dir")
        if not output_dir and artifacts and artifacts[0].get("path"):
            output_dir = str(Path(artifacts[0]["path"]).parent)
        return {
            "run_id": run_id,
            "status": row["status"],
            "current_node": row["current_node"],
            "stale": self._is_stale(row),
            "progress": {
                "completed": completed,
                "remaining": remaining_nodes(completed),
            },
            "counts": {
                "records": row["records_count"],
                "issues": row["issue_counts"],
            },
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row.get("updated_at"),
            "input_file": row.get("input_file"),
            "table_dir": paths.get("table_dir") or row.get("table_dir"),
            "output_dir": output_dir,
            "runtime_db": paths.get("runtime_db"),
            "paths": paths or None,
            "termination_reason": row["termination_reason"],
            "quote_summary": quote_summary,
            "output_files": [item["key"] for item in artifacts],
            "nodes": [
                {
                    "node_id": item["node_id"],
                    "name": item["node_name"],
                    "status": item["status"],
                    "duration_ms": json.loads(item["metrics_json"] or "{}").get("duration_ms", 0),
                    "issue_count": item["issue_count"],
                    "error": item["error"],
                }
                for item in row.get("node_runs") or []
            ],
        }

    def get_node(self, run_id: str, node_id: str, sample_size: int = 5, include_records: bool = False) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        node_run = self.store.get_node_run(run_id, node_id)
        catalog = get_node_catalog(node_id) if node_id in {item["node_id"] for item in WORKFLOW_NODES} else {
            "node_id": node_id,
            "name": node_id,
            "writes": [],
        }
        issues = self.store.list_issues(run_id, node_id=node_id)
        snapshot = self.store.get_snapshot(run_id, node_id)
        extras = self.store.get_snapshot_extras(run_id, node_id)
        sample_size = max(0, min(sample_size, 50))
        sample = snapshot[:sample_size]
        payload: dict[str, Any] = {
            "run_id": run_id,
            "node_id": node_id,
            "name": (node_run or {}).get("node_name") or catalog.get("name"),
            "status": (node_run or {}).get("status") or "pending",
            "started_at": (node_run or {}).get("started_at"),
            "finished_at": (node_run or {}).get("finished_at"),
            "metrics": json.loads((node_run or {}).get("metrics_json") or "{}"),
            "error": (node_run or {}).get("error"),
            "issues": issues,
            "output_summary": {
                "records_updated": len(snapshot),
                "fields_written": json.loads((node_run or {}).get("output_keys_json") or "[]") or catalog.get("writes", []),
                "sample": sample,
            },
        }
        if extras.get("quote"):
            payload["output_summary"]["quote"] = extras["quote"]
        if extras.get("payment"):
            payload["output_summary"]["payment"] = extras["payment"]
        if include_records:
            payload["output_summary"]["records"] = snapshot
        return payload

    def list_issues(
        self,
        run_id: str,
        node_id: str | None = None,
        level: str | None = None,
        code: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        issues = self.store.list_issues(
            run_id, node_id=node_id, level=level, code=code, record_id=record_id
        )
        return {"run_id": run_id, "count": len(issues), "issues": issues}

    def summarize_issues(
        self,
        run_id: str,
        node_id: str | None = None,
        level: str | None = None,
    ) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        groups = self.store.summarize_issues(run_id, node_id=node_id, level=level)
        return {
            "run_id": run_id,
            "group_count": len(groups),
            "total": sum(item["count"] for item in groups),
            "groups": groups,
        }

    def list_records(
        self,
        run_id: str,
        processable: bool | str | None = None,
        media: str | None = None,
        platform: str | None = None,
        media_match_status: str | None = None,
        account_match_status: str | None = None,
        has_issue: bool | str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        records, total = self.store.list_records(
            run_id,
            processable=_bool_param(processable),
            media=media,
            platform=platform,
            media_match_status=media_match_status,
            account_match_status=account_match_status,
            has_issue=_bool_param(has_issue),
            q=q,
            limit=limit,
            offset=offset,
        )
        return {
            "run_id": run_id,
            "total": total,
            "count": len(records),
            "offset": offset,
            "records": records,
        }

    def get_funnel(self, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id)
        if not row:
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        records = self.store.get_indexed_records(run_id)
        if not records:
            latest = None
            for node in reversed(row.get("node_runs") or []):
                snapshot = self.store.get_snapshot(run_id, node["node_id"])
                if snapshot:
                    latest = snapshot
                    break
            records = latest or []

        def _count(predicate) -> int:
            return sum(1 for item in records if predicate(item))

        input_count = len(records)
        media_matched = _count(lambda item: item.get("media_match_status") == "matched")
        media_failed = _count(
            lambda item: item.get("media_match_status") in {
                "not_found", "pending_confirmation", "incomplete", "duplicate",
            }
        )
        media_pending = _count(lambda item: item.get("media_match_status") == "pending_confirmation")
        account_matched = _count(lambda item: item.get("account_match_status") == "matched")
        account_failed = _count(
            lambda item: item.get("account_match_status") in {
                "not_found", "incomplete", "duplicate",
            }
        )
        account_skipped = _count(lambda item: item.get("account_match_status") == "skipped")
        processable = _count(lambda item: item.get("processable") is True)
        quote_summary = json.loads(row["quote_summary_json"]) if row.get("quote_summary_json") else {}
        extras = self.store.get_snapshot_extras(run_id, "node_05") or self.store.get_snapshot_extras(run_id, "node_06")
        quote = extras.get("quote") or quote_summary or {}
        quoted = int(quote.get("total_count") or 0)
        excluded_from_fee = int(quote.get("excluded_count") or max(input_count - quoted, 0))
        in_payment = int(quote.get("eligible_count") or quoted)
        issues = self.store.list_issues(run_id)
        drop_reasons: dict[tuple[str, str], dict[str, Any]] = {}
        for issue in issues:
            if issue["level"] not in {"error", "critical"}:
                continue
            key = (issue["code"], issue.get("node_id") or "")
            bucket = drop_reasons.setdefault(key, {
                "code": issue["code"],
                "node_id": issue.get("node_id"),
                "count": 0,
            })
            bucket["count"] += 1
        return {
            "run_id": run_id,
            "input": input_count,
            "media_matched": media_matched,
            "media_failed": media_failed,
            "media_pending": media_pending,
            "account_matched": account_matched,
            "account_failed": account_failed,
            "account_skipped": account_skipped,
            "processable": processable,
            "quoted": quoted,
            "excluded_from_fee": excluded_from_fee,
            "in_payment": in_payment,
            "total_fee": quote.get("total_fee"),
            "drop_reasons": sorted(drop_reasons.values(), key=lambda item: item["count"], reverse=True),
        }

    def wait_run(
        self,
        run_id: str,
        timeout_seconds: float = 60,
        interval_seconds: float = 2,
    ) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        timeout_seconds = max(1.0, min(float(timeout_seconds), 120.0))
        interval_seconds = max(0.2, min(float(interval_seconds), 10.0))
        deadline = time.monotonic() + timeout_seconds
        overview = self.get_run(run_id)
        while overview["status"] not in TERMINAL_STATUSES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                overview["timed_out"] = True
                overview["message"] = (
                    f"等待超时（{timeout_seconds:.0f}s），当前仍为 {overview['status']}。"
                    "可再次调用 wait_run 或 get_run。"
                )
                return overview
            time.sleep(min(interval_seconds, remaining))
            overview = self.get_run(run_id)
        overview["timed_out"] = False
        return overview

    def get_record(self, run_id: str, record_id: str) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        lineage: list[dict[str, Any]] = []
        latest: dict[str, Any] | None = None
        run = self.store.get_run(run_id) or {}
        for node in run.get("node_runs") or []:
            snapshot = self.store.get_snapshot(run_id, node["node_id"])
            match = next((item for item in snapshot if item.get("id") == record_id), None)
            if match:
                latest = match
                lineage.append({
                    "node_id": node["node_id"],
                    "node_name": node["node_name"],
                    "status": node["status"],
                    "record": match,
                })
        if latest is None and not lineage:
            raise WorkflowQueryError(f"记录不存在: {record_id}")
        return {
            "run_id": run_id,
            "record_id": record_id,
            "record": latest,
            "issues": self.store.list_issues(run_id, record_id=record_id),
            "lineage": lineage,
        }

    def list_artifacts(self, run_id: str) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise WorkflowQueryError(f"运行不存在: {run_id}")
        artifacts = []
        for item in self.store.list_artifacts(run_id):
            path = Path(item["path"])
            artifacts.append({
                "key": item["key"],
                "kind": item["kind"],
                "filename": path.name,
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
            })
        return {"run_id": run_id, "artifacts": artifacts}

    def describe_artifact(self, run_id: str, file_key: str) -> dict[str, Any]:
        artifacts = {item["key"]: item for item in self.store.list_artifacts(run_id)}
        if file_key not in artifacts:
            raise WorkflowQueryError(f"产物不存在: {file_key}")
        item = artifacts[file_key]
        path = Path(item["path"])
        descriptions = {
            "payment": "云账户银行卡付款上传模板",
            "quote_detail": "约稿资料明细与费用合计",
        }
        run = self.store.get_run(run_id) or {}
        quote_summary = json.loads(run["quote_summary_json"]) if run.get("quote_summary_json") else None
        return {
            "run_id": run_id,
            "key": file_key,
            "description": descriptions.get(file_key, file_key),
            "filename": path.name,
            "kind": item["kind"],
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "summary": quote_summary,
            "note": "文件本体请走工作流 HTTP 下载接口，MCP 只返回描述。",
        }

    def get_workflow_schema(self) -> dict[str, Any]:
        return {
            "name": "quotation-fee-workflow",
            "node_count": len(WORKFLOW_NODES),
            "nodes": WORKFLOW_NODES,
        }

    def _is_stale(self, row: dict[str, Any]) -> bool:
        if row.get("status") != "running":
            return False
        stamp = _parse_iso(row.get("updated_at") or row.get("started_at"))
        if stamp is None:
            return False
        return (datetime.now() - stamp).total_seconds() > STALE_AFTER_SECONDS
