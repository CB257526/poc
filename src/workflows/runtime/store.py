"""工作流运行持久化。SQLite 是查询层 / MCP / CLI 的共同真相源。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from workflows.models import Issue, NodeMetrics, NodeRun, WorkflowContext
from workflows.paths import runtime_db_path
from workflows.runtime.redact import RECORD_SAMPLE_FIELDS, project_record

RECORD_INDEX_FIELDS = [
    "id",
    "主题",
    "媒体",
    "platform",
    "primary_platform",
    "标题",
    "url",
    "primary_link",
    "media_match_status",
    "account_match_status",
    "processable",
    "费用",
]

QUOTE_SAMPLE_FIELDS = [
    "id",
    "媒体",
    "平台",
    "标题",
    "媒体等级",
    "文章类型",
    "费用",
    "eligible_for_monthly_summary",
]


def _default_db_path() -> Path:
    return runtime_db_path()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class RunStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    input_file TEXT,
                    table_dir TEXT,
                    current_node TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT,
                    termination_reason TEXT,
                    records_count INTEGER DEFAULT 0,
                    output_files_json TEXT DEFAULT '{}',
                    quote_summary_json TEXT,
                    monthly_summary_json TEXT,
                    paths_json TEXT
                );
                CREATE TABLE IF NOT EXISTS node_runs (
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    metrics_json TEXT,
                    issue_count INTEGER DEFAULT 0,
                    output_keys_json TEXT,
                    error TEXT,
                    snapshot_ref TEXT,
                    PRIMARY KEY (run_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    node_id TEXT,
                    record_id TEXT,
                    level TEXT NOT NULL,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    path TEXT NOT NULL,
                    kind TEXT,
                    PRIMARY KEY (run_id, key)
                );
                CREATE TABLE IF NOT EXISTS node_snapshots (
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    records_json TEXT NOT NULL,
                    extras_json TEXT DEFAULT '{}',
                    PRIMARY KEY (run_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS record_index (
                    run_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    media TEXT,
                    platform TEXT,
                    title TEXT,
                    url TEXT,
                    processable INTEGER,
                    media_match_status TEXT,
                    account_match_status TEXT,
                    fee REAL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_issues_run ON issues(run_id, node_id, level, code);
                CREATE INDEX IF NOT EXISTS idx_record_index_run ON record_index(run_id, processable);
                """
            )
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        run_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "updated_at" not in run_columns:
            connection.execute("ALTER TABLE runs ADD COLUMN updated_at TEXT")
            connection.execute(
                "UPDATE runs SET updated_at = COALESCE(finished_at, started_at) "
                "WHERE updated_at IS NULL"
            )
        snapshot_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(node_snapshots)").fetchall()
        }
        if "extras_json" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE node_snapshots ADD COLUMN extras_json TEXT DEFAULT '{}'"
            )
        if "paths_json" not in run_columns:
            connection.execute("ALTER TABLE runs ADD COLUMN paths_json TEXT")

    def save_run(self, context: WorkflowContext) -> None:
        quote_summary = None
        if context.quote_details:
            details = context.quote_details.get("details") or []
            quote_summary = {
                "total_count": context.quote_details.get("total_count", len(details)),
                "total_fee": context.quote_details.get("total_fee"),
                "excluded_count": context.quote_details.get("excluded_count"),
                "eligible_count": sum(
                    1 for item in details if item.get("eligible_for_monthly_summary") is True
                ),
            }
        updated_at = _iso(datetime.now())
        paths = context.config.get("paths") if isinstance(context.config, dict) else None
        paths_json = json.dumps(paths, ensure_ascii=False) if paths else None
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, status, input_file, table_dir, current_node,
                    started_at, finished_at, updated_at, termination_reason, records_count,
                    output_files_json, quote_summary_json, monthly_summary_json, paths_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    current_node=excluded.current_node,
                    finished_at=excluded.finished_at,
                    updated_at=excluded.updated_at,
                    termination_reason=excluded.termination_reason,
                    records_count=excluded.records_count,
                    output_files_json=excluded.output_files_json,
                    quote_summary_json=excluded.quote_summary_json,
                    monthly_summary_json=excluded.monthly_summary_json,
                    paths_json=COALESCE(excluded.paths_json, runs.paths_json)
                """,
                (
                    context.run_id,
                    context.run_status,
                    context.input_file,
                    context.table_dir,
                    context.current_node,
                    _iso(context.run_started_at),
                    _iso(context.run_finished_at),
                    updated_at,
                    context.termination_reason,
                    len(context.records),
                    json.dumps(context.output_files, ensure_ascii=False),
                    json.dumps(quote_summary, ensure_ascii=False) if quote_summary else None,
                    json.dumps(context.monthly_summary, ensure_ascii=False) if context.monthly_summary else None,
                    paths_json,
                ),
            )
            for node_run in context.node_runs:
                connection.execute(
                    """
                    INSERT INTO node_runs (
                        run_id, node_id, node_name, status, started_at, finished_at,
                        metrics_json, issue_count, output_keys_json, error, snapshot_ref
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        node_name=excluded.node_name,
                        status=excluded.status,
                        started_at=excluded.started_at,
                        finished_at=excluded.finished_at,
                        metrics_json=excluded.metrics_json,
                        issue_count=excluded.issue_count,
                        output_keys_json=excluded.output_keys_json,
                        error=excluded.error,
                        snapshot_ref=excluded.snapshot_ref
                    """,
                    (
                        context.run_id,
                        node_run.node_id,
                        node_run.node_name,
                        node_run.status,
                        _iso(node_run.started_at),
                        _iso(node_run.finished_at),
                        node_run.metrics.model_dump_json(),
                        node_run.issue_count,
                        json.dumps(node_run.output_keys, ensure_ascii=False),
                        node_run.error,
                        node_run.snapshot_ref,
                    ),
                )
            connection.execute("DELETE FROM issues WHERE run_id = ?", (context.run_id,))
            for issue in context.issues:
                connection.execute(
                    """
                    INSERT INTO issues (run_id, node_id, record_id, level, code, message, details_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.run_id,
                        issue.node_id,
                        issue.record_id,
                        issue.level,
                        issue.code,
                        issue.message,
                        json.dumps(issue.details, ensure_ascii=False),
                    ),
                )
            for key, path in context.output_files.items():
                connection.execute(
                    """
                    INSERT INTO artifacts (run_id, key, path, kind) VALUES (?, ?, ?, ?)
                    ON CONFLICT(run_id, key) DO UPDATE SET
                        path=excluded.path,
                        kind=excluded.kind
                    """,
                    (context.run_id, key, path, Path(path).suffix.lstrip(".") or "file"),
                )
            self._upsert_record_index(connection, context)

    def save_node_snapshot(self, context: WorkflowContext, node_id: str) -> str:
        payload = [project_record(record, RECORD_SAMPLE_FIELDS) for record in context.records]
        extras = self._snapshot_extras(context, node_id)
        ref = f"snapshot://{context.run_id}/{node_id}"
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO node_snapshots (run_id, node_id, records_json, extras_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, node_id) DO UPDATE SET
                    records_json=excluded.records_json,
                    extras_json=excluded.extras_json
                """,
                (
                    context.run_id,
                    node_id,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(extras, ensure_ascii=False),
                ),
            )
            self._upsert_record_index(connection, context)
        return ref

    def get_snapshot(self, run_id: str, node_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT records_json FROM node_snapshots WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
        if not row:
            return []
        return json.loads(row["records_json"])

    def get_snapshot_extras(self, run_id: str, node_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT extras_json FROM node_snapshots WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
        if not row or not row["extras_json"]:
            return {}
        return json.loads(row["extras_json"])

    def list_runs(
        self,
        status: str | None = None,
        limit: int = 20,
        input_file: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if input_file:
            clauses.append("input_file LIKE ?")
            params.append(f"%{input_file}%")
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        if until:
            clauses.append("started_at <= ?")
            params.append(until)
        query = "SELECT * FROM runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["issue_counts"] = self._issue_counts(connection, row["run_id"])
                item["completed_nodes"] = self._completed_nodes(connection, row["run_id"])
                result.append(item)
            return result

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["issue_counts"] = self._issue_counts(connection, run_id)
            data["completed_nodes"] = self._completed_nodes(connection, run_id)
            data["node_runs"] = [dict(item) for item in connection.execute(
                "SELECT * FROM node_runs WHERE run_id = ? ORDER BY started_at", (run_id,)
            ).fetchall()]
            data["artifacts"] = [dict(item) for item in connection.execute(
                "SELECT key, path, kind FROM artifacts WHERE run_id = ?", (run_id,)
            ).fetchall()]
            return data

    def get_node_run(self, run_id: str, node_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM node_runs WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
            return dict(row) if row else None

    def list_issues(
        self,
        run_id: str,
        node_id: str | None = None,
        level: str | None = None,
        code: str | None = None,
        record_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["run_id = ?"]
        params: list[Any] = [run_id]
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if code:
            clauses.append("code = ?")
            params.append(code)
        if record_id:
            clauses.append("record_id = ?")
            params.append(record_id)
        sql = "SELECT node_id, record_id, level, code, message, details_json FROM issues WHERE " + " AND ".join(clauses)
        with self._lock, self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        issues = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            issues.append(item)
        return issues

    def summarize_issues(
        self,
        run_id: str,
        node_id: str | None = None,
        level: str | None = None,
        sample_size: int = 5,
    ) -> list[dict[str, Any]]:
        clauses = ["run_id = ?"]
        params: list[Any] = [run_id]
        if node_id:
            clauses.append("node_id = ?")
            params.append(node_id)
        if level:
            clauses.append("level = ?")
            params.append(level)
        where = " AND ".join(clauses)
        with self._lock, self._connect() as connection:
            groups = connection.execute(
                f"""
                SELECT code, level, node_id, COUNT(*) AS count
                FROM issues
                WHERE {where}
                GROUP BY code, level, node_id
                ORDER BY count DESC, code
                """,
                params,
            ).fetchall()
            result = []
            for group in groups:
                samples = connection.execute(
                    f"""
                    SELECT record_id, message
                    FROM issues
                    WHERE {where} AND code = ? AND level = ? AND IFNULL(node_id, '') = IFNULL(?, '')
                    ORDER BY id
                    LIMIT ?
                    """,
                    [*params, group["code"], group["level"], group["node_id"], sample_size],
                ).fetchall()
                result.append({
                    "code": group["code"],
                    "level": group["level"],
                    "node_id": group["node_id"],
                    "count": group["count"],
                    "sample_record_ids": [
                        row["record_id"] for row in samples if row["record_id"]
                    ],
                    "sample_message": samples[0]["message"] if samples else None,
                })
            return result

    def list_records(
        self,
        run_id: str,
        processable: bool | None = None,
        media: str | None = None,
        platform: str | None = None,
        media_match_status: str | None = None,
        account_match_status: str | None = None,
        has_issue: bool | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["run_id = ?"]
        params: list[Any] = [run_id]
        if processable is not None:
            clauses.append("processable = ?")
            params.append(1 if processable else 0)
        if media:
            clauses.append("IFNULL(media, '') LIKE ?")
            params.append(f"%{media}%")
        if platform:
            clauses.append("IFNULL(platform, '') LIKE ?")
            params.append(f"%{platform}%")
        if media_match_status:
            clauses.append("media_match_status = ?")
            params.append(media_match_status)
        if account_match_status:
            clauses.append("account_match_status = ?")
            params.append(account_match_status)
        if q:
            like = f"%{q}%"
            clauses.append(
                "(record_id LIKE ? OR IFNULL(media, '') LIKE ? OR IFNULL(title, '') LIKE ? "
                "OR IFNULL(url, '') LIKE ?)"
            )
            params.extend([like, like, like, like])
        if has_issue is True:
            clauses.append(
                "record_id IN (SELECT DISTINCT record_id FROM issues "
                "WHERE run_id = ? AND record_id IS NOT NULL)"
            )
            params.append(run_id)
        elif has_issue is False:
            clauses.append(
                "(record_id IS NULL OR record_id NOT IN ("
                "SELECT DISTINCT record_id FROM issues "
                "WHERE run_id = ? AND record_id IS NOT NULL))"
            )
            params.append(run_id)
        where = " AND ".join(clauses)
        with self._lock, self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS n FROM record_index WHERE {where}",
                params,
            ).fetchone()["n"]
            rows = connection.execute(
                f"""
                SELECT payload_json FROM record_index
                WHERE {where}
                ORDER BY record_id
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
            issue_counts = {
                row["record_id"]: row["n"]
                for row in connection.execute(
                    """
                    SELECT record_id, COUNT(*) AS n FROM issues
                    WHERE run_id = ? AND record_id IS NOT NULL
                    GROUP BY record_id
                    """,
                    (run_id,),
                ).fetchall()
            }
        records = []
        for row in rows:
            item = json.loads(row["payload_json"])
            item["issue_count"] = issue_counts.get(item.get("id"), 0)
            records.append(item)
        return records, total

    def get_indexed_records(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM record_index WHERE run_id = ? ORDER BY record_id",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT key, path, kind FROM artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def load_context_shell(self, run_id: str) -> WorkflowContext | None:
        """把库里的运行还原成轻量 context（不含全量 records）。"""
        data = self.get_run(run_id)
        if not data:
            return None
        node_runs = []
        for item in data.get("node_runs") or []:
            metrics = json.loads(item["metrics_json"] or "{}")
            node_runs.append(NodeRun(
                node_id=item["node_id"],
                node_name=item["node_name"],
                status=item["status"],
                started_at=_parse_dt(item["started_at"]),
                finished_at=_parse_dt(item["finished_at"]),
                metrics=NodeMetrics(**metrics),
                issue_count=item["issue_count"] or 0,
                output_keys=json.loads(item["output_keys_json"] or "[]"),
                error=item["error"],
                snapshot_ref=item["snapshot_ref"],
            ))
        issues = [
            Issue(
                level=issue["level"],
                code=issue["code"],
                message=issue["message"],
                node_id=issue["node_id"] or "unknown",
                record_id=issue.get("record_id"),
                details=issue.get("details") or {},
            )
            for issue in self.list_issues(run_id)
        ]
        return WorkflowContext(
            run_id=run_id,
            run_started_at=_parse_dt(data["started_at"]) or datetime.now(),
            run_finished_at=_parse_dt(data["finished_at"]),
            input_file=data["input_file"] or "",
            table_dir=data["table_dir"] or "./table",
            current_node=data["current_node"],
            completed_nodes=data["completed_nodes"],
            node_runs=node_runs,
            run_status=data["status"],
            termination_reason=data["termination_reason"],
            issues=issues,
            output_files=json.loads(data["output_files_json"] or "{}"),
            quote_details=json.loads(data["quote_summary_json"]) if data.get("quote_summary_json") else None,
            monthly_summary=json.loads(data["monthly_summary_json"]) if data.get("monthly_summary_json") else None,
        )

    def _issue_counts(self, connection: sqlite3.Connection, run_id: str) -> dict[str, int]:
        rows = connection.execute(
            "SELECT level, COUNT(*) AS n FROM issues WHERE run_id = ? GROUP BY level",
            (run_id,),
        ).fetchall()
        counts = {"critical": 0, "error": 0, "warning": 0, "total": 0}
        for row in rows:
            counts[row["level"]] = row["n"]
            counts["total"] += row["n"]
        return counts

    def _completed_nodes(self, connection: sqlite3.Connection, run_id: str) -> list[str]:
        rows = connection.execute(
            "SELECT node_id FROM node_runs WHERE run_id = ? AND status = 'completed' ORDER BY started_at",
            (run_id,),
        ).fetchall()
        return [row["node_id"] for row in rows]

    def _upsert_record_index(self, connection: sqlite3.Connection, context: WorkflowContext) -> None:
        if not context.records:
            return
        connection.execute("DELETE FROM record_index WHERE run_id = ?", (context.run_id,))
        for record in context.records:
            projected = project_record(record, RECORD_INDEX_FIELDS)
            record_id = projected.get("id") or record.get("id")
            if not record_id:
                continue
            processable = record.get("processable")
            fee = record.get("费用")
            try:
                fee_value = float(fee) if fee not in (None, "") else None
            except (TypeError, ValueError):
                fee_value = None
            connection.execute(
                """
                INSERT INTO record_index (
                    run_id, record_id, media, platform, title, url, processable,
                    media_match_status, account_match_status, fee, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.run_id,
                    str(record_id),
                    projected.get("媒体"),
                    projected.get("platform") or projected.get("primary_platform"),
                    projected.get("标题"),
                    _as_text(projected.get("url") or projected.get("primary_link")),
                    None if processable is None else (1 if processable else 0),
                    projected.get("media_match_status"),
                    projected.get("account_match_status"),
                    fee_value,
                    json.dumps(projected, ensure_ascii=False),
                ),
            )

    def _snapshot_extras(self, context: WorkflowContext, node_id: str) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        if context.quote_details:
            details = context.quote_details.get("details") or []
            extras["quote"] = {
                "total_count": context.quote_details.get("total_count", len(details)),
                "total_fee": context.quote_details.get("total_fee"),
                "excluded_count": context.quote_details.get("excluded_count"),
                "eligible_count": sum(
                    1 for item in details if item.get("eligible_for_monthly_summary") is True
                ),
                "sample": [
                    project_record(item, QUOTE_SAMPLE_FIELDS) for item in details[:5]
                ],
            }
        if node_id == "node_06":
            extras["payment"] = {
                "output_files": context.output_files,
                "payment_row_count": len(context.payment_rows or []),
                "monthly_months": len(context.monthly_summary or {}),
            }
        return extras


def _as_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


_store: Optional[RunStore] = None
_store_lock = threading.Lock()


def get_run_store() -> RunStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = RunStore()
        return _store


def reset_run_store(db_path: str | Path | None = None) -> RunStore:
    global _store
    with _store_lock:
        _store = RunStore(db_path)
        return _store
