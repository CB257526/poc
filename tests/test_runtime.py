"""运行时观测：NodeRun 时间线、RunStore、查询视图、脱敏。"""

import json
from pathlib import Path

from workflows.models import Issue, NodeMetrics, NodeOutput, WorkflowContext
from workflows.nodes.base import BaseNode, WorkflowTerminated
from workflows.runtime.redact import project_record
from workflows.runtime.store import reset_run_store
from workflows.runtime.jobs import WorkflowStartError, start_workflow_job
from workflows.runtime.views import WorkflowQueryError, WorkflowQueryService
from workflows.workflow_run import create_workflow


class _OkNode(BaseNode):
    def process(self, context: WorkflowContext) -> NodeOutput:
        records = [{"id": "rec_0001", "媒体": "媒体A", "身份证": "110101199001011234", "账号": "6222021234567890"}]
        return NodeOutput.create_success(
            metrics=NodeMetrics(processed_count=1, success_count=1),
            data={"records": records},
        )


class _FailNode(BaseNode):
    def process(self, context: WorkflowContext) -> NodeOutput:
        return NodeOutput.create_failure(
            metrics=NodeMetrics(processed_count=1, success_count=0, error_count=1),
            issues=[
                Issue(
                    level="critical",
                    code="TEST_FAIL",
                    message="故意失败",
                    node_id=self.node_id,
                    record_id="rec_0001",
                )
            ],
        )


def test_base_node_writes_timeline(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)

    node = _OkNode("node_00", "输入验证")
    context = WorkflowContext(run_id="run_test", input_file="in.xlsx", records=[{"id": "x"}])
    result = node.invoke(context)

    node_run = result.get_node_run("node_00")
    assert node_run is not None
    assert node_run.status == "completed"
    assert node_run.metrics.processed_count == 1
    assert "records" in node_run.output_keys
    assert node_run.snapshot_ref == "snapshot://run_test/node_00"

    persisted = store.get_run("run_test")
    assert persisted is not None
    snapshot = store.get_snapshot("run_test", "node_00")
    assert snapshot[0]["id"] == "rec_0001"
    assert snapshot[0]["身份证"].startswith("1")
    assert "*" in snapshot[0]["身份证"]


def test_failed_node_marks_timeline(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)

    node = _FailNode("node_03", "匹配媒体库")
    context = WorkflowContext(run_id="run_fail", input_file="in.xlsx", records=[{"id": "rec_0001"}])
    try:
        node.invoke(context)
        assert False, "should terminate"
    except WorkflowTerminated:
        pass

    node_run = context.get_node_run("node_03")
    assert node_run.status == "failed"
    assert node_run.error
    issues = store.list_issues("run_fail", node_id="node_03")
    assert issues[0]["code"] == "TEST_FAIL"


def test_query_views(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)

    node = _OkNode("node_00", "输入验证")
    context = WorkflowContext(run_id="run_view", input_file="in.xlsx", records=[{"id": "x"}], run_status="running")
    store.save_run(context)
    node.invoke(context)
    context.run_status = "completed"
    store.save_run(context)

    query = WorkflowQueryService(store)
    listed = query.list_runs()
    assert listed["runs"][0]["run_id"] == "run_view"

    overview = query.get_run("run_view")
    assert overview["status"] == "completed"
    assert "node_00" in overview["progress"]["completed"]
    assert overview["counts"]["records"] == 1

    node_view = query.get_node("run_view", "node_00")
    assert node_view["status"] == "completed"
    assert node_view["output_summary"]["sample"][0]["媒体"] == "媒体A"

    record = query.get_record("run_view", "rec_0001")
    assert record["record"]["id"] == "rec_0001"
    assert "*" in record["record"]["账号"]

    schema = query.get_workflow_schema()
    assert schema["node_count"] == 7

    listed_records = query.list_records("run_view")
    assert listed_records["total"] == 1
    assert listed_records["records"][0]["id"] == "rec_0001"

    funnel = query.get_funnel("run_view")
    assert funnel["input"] == 1

    summarized = query.summarize_issues("run_view")
    assert summarized["total"] == 0

    waited = query.wait_run("run_view", timeout_seconds=1, interval_seconds=0.2)
    assert waited["status"] == "completed"
    assert waited["timed_out"] is False


def test_query_missing_run(tmp_path):
    store = reset_run_store(tmp_path / "workflow.db")
    query = WorkflowQueryService(store)
    try:
        query.get_run("nope")
        assert False
    except WorkflowQueryError:
        pass


def test_redact_sensitive_fields():
    projected = project_record({"id": "rec_0001", "身份证": "123456", "媒体": "A"})
    assert projected["身份证"] == "1****6"
    assert projected["媒体"] == "A"


def test_start_workflow_job_rejects_missing_file(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)
    try:
        start_workflow_job(str(tmp_path / "missing.xlsx"), table_dir=str(tmp_path))
        assert False
    except WorkflowStartError as exc:
        assert "不存在" in str(exc)


def test_workflow_creation_still_runnable():
    workflow = create_workflow()
    assert hasattr(workflow, "invoke")


def _seed_finance_run(store) -> str:
    context = WorkflowContext(
        run_id="run_funnel",
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
            },
            {
                "id": "rec_0002",
                "媒体": "媒体B",
                "platform": "weibo",
                "标题": "媒体未匹配",
                "media_match_status": "pending_confirmation",
                "account_match_status": "skipped",
                "processable": False,
            },
            {
                "id": "rec_0003",
                "媒体": "媒体C",
                "platform": "zhihu",
                "标题": "账户缺失",
                "media_match_status": "matched",
                "account_match_status": "not_found",
                "processable": False,
            },
        ],
        quote_details={
            "details": [
                {"id": "rec_0001", "媒体": "媒体A", "费用": 100, "eligible_for_monthly_summary": True},
            ],
            "total_count": 1,
            "total_fee": 100,
            "excluded_count": 2,
        },
        run_status="completed",
    )
    context.add_issue(
        level="error",
        code="MEDIA_NOT_FOUND",
        message="媒体B不在库",
        node_id="node_03",
        record_id="rec_0002",
    )
    context.add_issue(
        level="error",
        code="ACCOUNT_NOT_FOUND",
        message="媒体C无账户",
        node_id="node_04",
        record_id="rec_0003",
    )
    context.add_issue(
        level="error",
        code="MEDIA_NOT_FOUND",
        message="另一条媒体缺失",
        node_id="node_03",
        record_id="rec_0002",
    )
    store.save_run(context)
    store.save_node_snapshot(context, "node_05")
    return context.run_id


def test_list_records_and_issue_summary(tmp_path):
    store = reset_run_store(tmp_path / "workflow.db")
    run_id = _seed_finance_run(store)
    query = WorkflowQueryService(store)

    dropped = query.list_records(run_id, processable=False)
    assert dropped["total"] == 2
    assert {item["id"] for item in dropped["records"]} == {"rec_0002", "rec_0003"}

    media_b = query.list_records(run_id, media="媒体B")
    assert media_b["total"] == 1
    assert media_b["records"][0]["issue_count"] == 2

    with_issues = query.list_records(run_id, has_issue=True)
    assert with_issues["total"] == 2

    search = query.list_records(run_id, q="账户缺失")
    assert search["records"][0]["id"] == "rec_0003"

    grouped = query.summarize_issues(run_id)
    assert grouped["total"] == 3
    media_group = next(item for item in grouped["groups"] if item["code"] == "MEDIA_NOT_FOUND")
    assert media_group["count"] == 2
    assert media_group["node_id"] == "node_03"


def test_get_funnel_counts_drop_reasons(tmp_path):
    store = reset_run_store(tmp_path / "workflow.db")
    run_id = _seed_finance_run(store)
    query = WorkflowQueryService(store)
    funnel = query.get_funnel(run_id)

    assert funnel["input"] == 3
    assert funnel["media_matched"] == 2
    assert funnel["media_pending"] == 1
    assert funnel["account_matched"] == 1
    assert funnel["account_skipped"] == 1
    assert funnel["processable"] == 1
    assert funnel["quoted"] == 1
    assert funnel["excluded_from_fee"] == 2
    assert funnel["in_payment"] == 1
    assert funnel["total_fee"] == 100
    codes = {item["code"]: item["count"] for item in funnel["drop_reasons"]}
    assert codes["MEDIA_NOT_FOUND"] == 2
    assert codes["ACCOUNT_NOT_FOUND"] == 1


def test_list_runs_filters_by_input_file(tmp_path):
    store = reset_run_store(tmp_path / "workflow.db")
    store.save_run(WorkflowContext(run_id="run_a", input_file="./table/1-链接.xlsx", run_status="completed"))
    store.save_run(WorkflowContext(run_id="run_b", input_file="./other/foo.xlsx", run_status="failed"))
    query = WorkflowQueryService(store)

    matched = query.list_runs(input_file="1-链接.xlsx")
    assert [item["run_id"] for item in matched["runs"]] == ["run_a"]

    failed = query.list_runs(status="failed")
    assert [item["run_id"] for item in failed["runs"]] == ["run_b"]


def test_wait_run_times_out_while_running(tmp_path):
    store = reset_run_store(tmp_path / "workflow.db")
    store.save_run(WorkflowContext(run_id="run_wait", input_file="in.xlsx", run_status="running"))
    query = WorkflowQueryService(store)
    result = query.wait_run("run_wait", timeout_seconds=1, interval_seconds=0.2)
    assert result["status"] == "running"
    assert result["timed_out"] is True


def test_failed_node_is_not_completed(tmp_path, monkeypatch):
    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)

    node = _FailNode("node_03", "匹配媒体库")
    context = WorkflowContext(run_id="run_incomplete", input_file="in.xlsx", records=[{"id": "rec_0001"}])
    try:
        node.invoke(context)
        assert False, "should terminate"
    except WorkflowTerminated:
        pass

    assert "node_03" not in context.completed_nodes
    persisted = store.get_run("run_incomplete")
    assert persisted["completed_nodes"] == []


def test_runtime_params_are_self_describing(tmp_path, monkeypatch):
    from workflows.paths import runtime_db_path, runtime_params

    monkeypatch.setenv("WORKFLOW_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setenv("WORKFLOW_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("WORKFLOW_TABLE_DIR", str(tmp_path / "tables"))
    input_file = tmp_path / "1-链接.xlsx"
    input_file.write_bytes(b"")

    params = runtime_params(run_id="run_abc", input_file=input_file)
    assert params["run_id"] == "run_abc"
    assert params["input_file"] == str(input_file.resolve())
    assert params["table_dir"] == str((tmp_path / "tables").resolve())
    assert params["table_3"].endswith("3-媒体库.xlsx")
    assert params["table_4"].endswith("4-账户信息.xlsx")
    assert params["table_5"].endswith("5-费用.xlsx")
    assert params["output_dir"] == str((tmp_path / "out" / "run_abc").resolve())
    assert (tmp_path / "out" / "run_abc").is_dir()
    assert runtime_db_path() == (tmp_path / "rt" / "workflow.db").resolve()


def test_isolated_run_stores_do_not_mix(tmp_path):
    from workflows.runtime.store import RunStore

    store_a = RunStore(tmp_path / "backend" / "workflow.db")
    store_b = RunStore(tmp_path / "mcp" / "workflow.db")
    store_a.save_run(WorkflowContext(run_id="run_backend", input_file="a.xlsx", run_status="completed"))
    store_b.save_run(WorkflowContext(run_id="run_mcp", input_file="b.xlsx", run_status="completed"))
    assert store_a.get_run("run_mcp") is None
    assert store_b.get_run("run_backend") is None
    assert store_a.get_run("run_backend")["run_id"] == "run_backend"


def test_start_job_puts_artifacts_under_run_id(tmp_path, monkeypatch):
    from openpyxl import Workbook

    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)
    monkeypatch.setattr("workflows.runtime.jobs.get_run_store", lambda: store)
    monkeypatch.setattr("workflows.runtime.jobs.run_workflow", lambda **kwargs: None)

    input_file = tmp_path / "1-链接.xlsx"
    book = Workbook()
    book.save(input_file)
    output_root = tmp_path / "out"
    result = start_workflow_job(
        str(input_file),
        table_dir=str(tmp_path),
        output_dir=str(output_root),
    )
    run_id = result["run_id"]
    assert result["output_dir"] == str((output_root / run_id).resolve())
    assert (output_root / run_id).is_dir()
    assert result["paths"]["runtime_db"]
    assert result["paths"]["table_3"].endswith("3-媒体库.xlsx")
    persisted = store.get_run(run_id)
    assert persisted is not None
    overview = WorkflowQueryService(store).get_run(run_id)
    assert overview["output_dir"] == result["output_dir"]
    assert overview["paths"]["table_dir"] == str(tmp_path.resolve())


def test_run_workflow_writes_under_run_id(tmp_path, monkeypatch):
    from workflows.models import NodeMetrics, NodeOutput
    from workflows.nodes.base import BaseNode
    from workflows.workflow_run import run_workflow

    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)
    monkeypatch.setattr("workflows.workflow_run.run_store.get_run_store", lambda: store)
    monkeypatch.setenv("WORKFLOW_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setenv("WORKFLOW_OUTPUT_DIR", str(tmp_path / "out"))

    class _Passthrough(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            return NodeOutput.create_success(metrics=NodeMetrics())

    monkeypatch.setattr(
        "workflows.workflow_run.create_nodes",
        lambda: [_Passthrough("node_00", "输入验证")],
    )
    input_file = tmp_path / "1-链接.xlsx"
    input_file.write_bytes(b"x")
    context = run_workflow(
        input_file=str(input_file),
        table_dir=str(tmp_path),
        run_id="run_paths",
    )
    expected = tmp_path / "out" / "run_paths"
    assert Path(context.config["output_dir"]) == expected.resolve()
    assert expected.is_dir()
    assert context.config["paths"]["table_3"].endswith("3-媒体库.xlsx")
    assert context.config["paths"]["runtime_db"].endswith("workflow.db")
    persisted = store.get_run("run_paths")
    assert persisted is not None
    assert "run_paths" in (json.loads(persisted["paths_json"])["output_dir"])


def test_run_workflow_does_not_nest_existing_run_dir(tmp_path, monkeypatch):
    from workflows.models import NodeMetrics, NodeOutput
    from workflows.nodes.base import BaseNode
    from workflows.workflow_run import run_workflow

    store = reset_run_store(tmp_path / "workflow.db")
    monkeypatch.setattr("workflows.runtime.store.get_run_store", lambda: store)
    monkeypatch.setattr("workflows.workflow_run.run_store.get_run_store", lambda: store)

    class _Passthrough(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            return NodeOutput.create_success(metrics=NodeMetrics())

    monkeypatch.setattr(
        "workflows.workflow_run.create_nodes",
        lambda: [_Passthrough("node_00", "输入验证")],
    )
    input_file = tmp_path / "1-链接.xlsx"
    input_file.write_bytes(b"x")
    already = tmp_path / "out" / "run_nested"
    context = run_workflow(
        input_file=str(input_file),
        table_dir=str(tmp_path),
        run_id="run_nested",
        config={"output_dir": str(already)},
    )
    assert Path(context.config["output_dir"]) == already.resolve()
    assert not (already / "run_nested").exists()
