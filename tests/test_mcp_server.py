"""MCP 协议面：tools / resources / prompts 分开注册，并逐个调用每个 tool。"""

import inspect
import json
from datetime import datetime
from pathlib import Path

from workflows import mcp_server
from workflows.models import NodeRun, WorkflowContext
from workflows.runtime.store import reset_run_store
from workflows.runtime.views import WorkflowQueryService


def _names(items, attr="name"):
    return {getattr(item, attr) for item in items}


def _load(payload: str) -> dict:
    data = json.loads(payload)
    assert isinstance(data, dict)
    return data


def _write_xlsx(path: Path) -> None:
    from openpyxl import Workbook

    book = Workbook()
    book.active["A1"] = "ok"
    book.save(path)


def _seed_run(store, tmp_path: Path) -> str:
    artifact = tmp_path / "payment.xlsx"
    artifact.write_text("xlsx", encoding="utf-8")
    context = WorkflowContext(
        run_id="run_mcp",
        input_file="./table/1-链接.xlsx",
        records=[
            {
                "id": "rec_0001",
                "媒体": "媒体A",
                "platform": "zhihu",
                "标题": "已入账",
                "media_match_status": "matched",
                "account_match_status": "matched",
                "processable": True,
                "费用": 100,
                "身份证": "110101199001011234",
                "账号": "6222021234567890",
            },
            {
                "id": "rec_0002",
                "媒体": "媒体B",
                "platform": "weibo",
                "标题": "未匹配",
                "media_match_status": "pending_confirmation",
                "account_match_status": "skipped",
                "processable": False,
            },
        ],
        quote_details={
            "details": [
                {"id": "rec_0001", "媒体": "媒体A", "费用": 100, "eligible_for_monthly_summary": True},
            ],
            "total_count": 1,
            "total_fee": 100,
            "excluded_count": 1,
        },
        output_files={"payment": str(artifact)},
        run_status="completed",
        current_node="node_06",
        completed_nodes=["node_00", "node_05", "node_06"],
        node_runs=[
            NodeRun(node_id="node_05", node_name="计算费用", status="completed", output_keys=["quote_details"]),
            NodeRun(node_id="node_06", node_name="生成付款表", status="completed", output_keys=["output_files"]),
        ],
    )
    context.add_issue(
        level="error",
        code="MEDIA_NOT_FOUND",
        message="媒体B不在库",
        node_id="node_03",
        record_id="rec_0002",
    )
    store.save_run(context)
    store.save_node_snapshot(context, "node_05")
    store.save_node_snapshot(context, "node_06")
    return context.run_id



def test_tools_resources_prompts_are_distinct():
    tools = _names(mcp_server.mcp._tool_manager.list_tools())
    assert tools == {
        "start_run",
        "list_runs",
        "get_run",
        "wait_run",
        "get_node",
        "list_issues",
        "summarize_issues",
        "list_records",
        "get_funnel",
        "get_record",
        "list_artifacts",
        "describe_artifact",
        "get_workflow_schema",
    }

    resources = mcp_server.mcp._resource_manager.list_resources()
    templates = mcp_server.mcp._resource_manager.list_templates()
    resource_uris = {str(item.uri) for item in resources}
    template_uris = {
        getattr(item, "uri_template", None) or getattr(item, "uriTemplate", None)
        for item in templates
    }
    assert "workflow://schema" in resource_uris
    assert "workflow://runs" in resource_uris
    assert "workflow://runs/{run_id}" in template_uris
    assert "workflow://runs/{run_id}/nodes/{node_id}" in template_uris
    assert "workflow://runs/{run_id}/issues" in template_uris

    prompts = _names(mcp_server.mcp._prompt_manager.list_prompts())
    assert prompts == {"run_workflow", "inspect_run", "inspect_node", "explain_record"}

    # 协议面三个能力互不混用：查询带参数走 tool，固定 URI 走 resource，模板走 prompt。
    assert inspect.iscoroutinefunction(mcp_server.mcp.list_tools)
    assert inspect.iscoroutinefunction(mcp_server.mcp.list_resources)
    assert inspect.iscoroutinefunction(mcp_server.mcp.list_prompts)


def test_every_mcp_tool(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)
    monkeypatch.setattr("workflows.mcp_server._query", lambda: WorkflowQueryService(store))
    monkeypatch.setattr("workflows.runtime.jobs.get_run_store", lambda: store)
    run_id = _seed_run(store, tmp_path)

    schema = _load(mcp_server.get_workflow_schema())
    assert schema["node_count"] == 7
    assert schema["nodes"][0]["node_id"] == "node_00"

    listed = _load(mcp_server.list_runs(status="completed", limit=5, input_file="1-链接.xlsx"))
    assert listed["runs"][0]["run_id"] == run_id
    assert listed["runs"][0]["stale"] is False

    since = datetime(2000, 1, 1).isoformat()
    until = datetime(2100, 1, 1).isoformat()
    ranged = _load(mcp_server.list_runs(since=since, until=until))
    assert ranged["runs"][0]["run_id"] == run_id

    overview = _load(mcp_server.get_run(run_id))
    assert overview["status"] == "completed"
    assert overview["stale"] is False
    assert "payment" in overview["output_files"]

    waited = _load(mcp_server.wait_run(run_id, timeout_seconds=1, interval_seconds=0.2))
    assert waited["timed_out"] is False
    assert waited["status"] == "completed"

    node = _load(mcp_server.get_node(run_id, "node_05", sample_size=3, include_records=True))
    assert node["status"] == "completed"
    assert node["output_summary"]["sample"][0]["id"] == "rec_0001"
    assert "*" in node["output_summary"]["records"][0]["身份证"]
    assert node["output_summary"]["quote"]["total_count"] == 1

    issues = _load(mcp_server.list_issues(run_id, node_id="node_03", level="error", code="MEDIA_NOT_FOUND"))
    assert issues["count"] == 1
    assert issues["issues"][0]["record_id"] == "rec_0002"

    summarized = _load(mcp_server.summarize_issues(run_id, level="error"))
    assert summarized["total"] == 1
    assert summarized["groups"][0]["code"] == "MEDIA_NOT_FOUND"

    records = _load(mcp_server.list_records(run_id, processable=False, media="媒体B", has_issue=True, q="未匹配"))
    assert records["total"] == 1
    assert records["records"][0]["id"] == "rec_0002"

    funnel = _load(mcp_server.get_funnel(run_id))
    assert funnel["input"] == 2
    assert funnel["processable"] == 1
    assert funnel["quoted"] == 1
    assert funnel["drop_reasons"][0]["code"] == "MEDIA_NOT_FOUND"

    record = _load(mcp_server.get_record(run_id, "rec_0001"))
    assert record["record"]["id"] == "rec_0001"
    assert "*" in record["record"]["账号"]
    assert record["lineage"]

    artifacts = _load(mcp_server.list_artifacts(run_id))
    assert artifacts["artifacts"][0]["key"] == "payment"
    assert artifacts["artifacts"][0]["exists"] is True

    described = _load(mcp_server.describe_artifact(run_id, "payment"))
    assert described["key"] == "payment"
    assert described["summary"]["total_fee"] == 100

    missing_run = _load(mcp_server.get_run("does_not_exist"))
    assert missing_run["error"]["code"] == "NOT_FOUND"

    missing_record = _load(mcp_server.get_record(run_id, "rec_missing"))
    assert missing_record["error"]["code"] == "NOT_FOUND"

    missing_artifact = _load(mcp_server.describe_artifact(run_id, "nope"))
    assert missing_artifact["error"]["code"] == "NOT_FOUND"

    started = _load(mcp_server.start_run(str(tmp_path / "missing.xlsx"), table_dir=str(tmp_path)))
    assert started["error"]["code"] == "INVALID_INPUT"

    input_file = tmp_path / "1-链接.xlsx"
    _write_xlsx(input_file)
    started_ok = _load(mcp_server.start_run(
        str(input_file),
        table_dir=str(tmp_path),
        output_dir=str(tmp_path / "out"),
    ))
    assert started_ok["status"] == "running"
    assert "run_id" in started_ok
    created = store.get_run(started_ok["run_id"])
    assert created is not None
    assert created["status"] == "running"

    store.save_run(WorkflowContext(run_id="run_hanging", input_file="in.xlsx", run_status="running"))
    hanging = _load(mcp_server.wait_run("run_hanging", timeout_seconds=1, interval_seconds=0.2))
    assert hanging["status"] == "running"
    assert hanging["timed_out"] is True
