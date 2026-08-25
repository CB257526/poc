"""约稿工作流 MCP 服务。

协议分层：
- Tools（模型调用）：带过滤的查询，如 list_issues / get_node
- Resources（应用读取）：固定 URI 文档，如 workflow://schema、workflow://runs/{run_id}
- Prompts（用户触发）：排错模板

远端默认走 Streamable HTTP（MCP 标准远程传输），内网不鉴权。
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from workflows.runtime.jobs import WorkflowStartError, start_workflow_job
from workflows.runtime.views import WorkflowQueryError, WorkflowQueryService


mcp = MCPServer(
    name="byd-workflow",
    title="约稿费用工作流观测",
    instructions=(
        "约稿费用验收工作流：可用 start_run 按表1路径后台启动完整流程，"
        "再用 wait_run / get_run / get_funnel / list_records 查询进度、漏斗和记录。"
        "产物写在 output-mcp/<run_id>/（与 HTTP 后端的 output/ 隔离）。"
        "账户、身份证、银行卡字段默认脱敏。"
        "与后端隔离依赖 WORKFLOW_RUNTIME_DIR / WORKFLOW_OUTPUT_DIR，MCP 进程已有独立默认值。"
    ),
)


def _query() -> WorkflowQueryService:
    return WorkflowQueryService()


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _error(exc: Exception) -> str:
    if isinstance(exc, WorkflowQueryError):
        return _ok({"error": {"code": "NOT_FOUND", "message": str(exc)}})
    if isinstance(exc, WorkflowStartError):
        return _ok({"error": {"code": "INVALID_INPUT", "message": str(exc)}})
    return _ok({"error": {"code": "INTERNAL", "message": str(exc)}})


# ---------------------------------------------------------------------------
# Tools
# 查询类：模型按需调用，带过滤。
# 写操作：start_run 后台启动完整工作流，立即返回 run_id。
# ---------------------------------------------------------------------------

@mcp.tool(
    name="start_run",
    description=(
        "传入表1（1-链接.xlsx）路径，后台启动完整工作流（节点0—6）。"
        "立即返回 run_id，不会等跑完。随后用 wait_run 或 get_run 查看进度。"
    ),
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
def start_run(
    input_file: str,
    table_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """启动一次完整工作流。

    Args:
        input_file: 表1路径，即 1-链接.xlsx
        table_dir: 参考表目录，默认 WORKFLOW_TABLE_DIR 或仓库 table/（需含 3-媒体库、4-账户信息、5-费用）
        output_dir: 产物根目录，实际写入 <output_dir>/<run_id>/。默认 WORKFLOW_OUTPUT_DIR 或仓库 output/
    """
    try:
        return _ok(start_workflow_job(
            input_file=input_file,
            table_dir=table_dir,
            output_dir=output_dir,
        ))
    except Exception as exc:
        return _error(exc)

@mcp.tool(
    name="list_runs",
    description="列出最近的工作流运行。可按 status / 输入文件名 / 时间范围过滤。",
)
def list_runs(
    status: Optional[str] = None,
    limit: int = 20,
    input_file: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> str:
    """列出最近运行。

    Args:
        status: 可选过滤，pending/running/completed/failed/terminated
        limit: 返回条数，默认 20，最大 100
        input_file: 可选，按输入路径模糊匹配，如 1-链接.xlsx
        since: 可选，started_at 下限，ISO 时间
        until: 可选，started_at 上限，ISO 时间
    """
    try:
        return _ok(_query().list_runs(
            status=status,
            limit=limit,
            input_file=input_file,
            since=since,
            until=until,
        ))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="get_run",
    description="一次运行的总览：状态、当前节点、进度、issue 计数、产物 key。不含整份 records。running 过久会标 stale。",
)
def get_run(run_id: str) -> str:
    """获取运行总览。

    Args:
        run_id: 运行 ID，例如 run_1724...
    """
    try:
        return _ok(_query().get_run(run_id))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="wait_run",
    description=(
        "等待一次运行到达 completed/failed/terminated，或超时返回当前总览。"
        "start_run 之后优先用这个，避免反复轮询 get_run。超时上限 120 秒。"
    ),
)
def wait_run(
    run_id: str,
    timeout_seconds: float = 60,
    interval_seconds: float = 2,
) -> str:
    """等待运行结束。

    Args:
        run_id: 运行 ID
        timeout_seconds: 最长等待秒数，默认 60，最大 120
        interval_seconds: 轮询间隔，默认 2
    """
    try:
        return _ok(_query().wait_run(
            run_id,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        ))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="get_node",
    description="查询某个节点当时的状态、指标、报错和输出摘要。这是「节点输出了什么 / 报了什么错」的主入口。",
)
def get_node(
    run_id: str,
    node_id: str,
    sample_size: int = 5,
    include_records: bool = False,
) -> str:
    """查询单节点执行情况。

    Args:
        run_id: 运行 ID
        node_id: 节点 ID，如 node_03
        sample_size: 输出样本条数，默认 5
        include_records: true 时返回该节点快照全量（已脱敏），默认 false
    """
    try:
        return _ok(_query().get_node(
            run_id,
            node_id,
            sample_size=sample_size,
            include_records=include_records,
        ))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="list_issues",
    description="按运行过滤问题列表。可按 node_id / level / code / record_id 缩小范围。",
)
def list_issues(
    run_id: str,
    node_id: Optional[str] = None,
    level: Optional[str] = None,
    code: Optional[str] = None,
    record_id: Optional[str] = None,
) -> str:
    """列出一次运行中的问题。

    Args:
        run_id: 运行 ID
        node_id: 可选，仅该节点
        level: 可选，warning/error/critical
        code: 可选，如 MEDIA_NOT_IN_LIBRARY
        record_id: 可选，如 rec_0001
    """
    try:
        return _ok(_query().list_issues(
            run_id,
            node_id=node_id,
            level=level,
            code=code,
            record_id=record_id,
        ))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="summarize_issues",
    description="按 code/level/node 聚合一次运行的问题。排错第一步用这个，不要先 dump 全量 list_issues。",
)
def summarize_issues(
    run_id: str,
    node_id: Optional[str] = None,
    level: Optional[str] = None,
) -> str:
    """聚合问题。

    Args:
        run_id: 运行 ID
        node_id: 可选，仅该节点
        level: 可选，warning/error/critical
    """
    try:
        return _ok(_query().summarize_issues(run_id, node_id=node_id, level=level))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="list_records",
    description=(
        "列出一次运行中的记录目录（id/媒体/匹配状态/是否可入账），不含整行明细。"
        "回答「哪些没进付款表」前先调这个，再对单条 get_record。"
    ),
)
def list_records(
    run_id: str,
    processable: Optional[bool] = None,
    media: Optional[str] = None,
    platform: Optional[str] = None,
    media_match_status: Optional[str] = None,
    account_match_status: Optional[str] = None,
    has_issue: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """列出记录目录。

    Args:
        run_id: 运行 ID
        processable: 可选，true 只看可入账，false 只看被剔除
        media: 可选，媒体名模糊匹配
        platform: 可选，平台模糊匹配
        media_match_status: 可选，如 matched / pending_confirmation / incomplete
        account_match_status: 可选，如 matched / not_found / skipped
        has_issue: 可选，是否关联 issue
        q: 可选，在 id/媒体/标题/url 中搜索
        limit: 默认 50，最大 200
        offset: 分页偏移
    """
    try:
        return _ok(_query().list_records(
            run_id,
            processable=processable,
            media=media,
            platform=platform,
            media_match_status=media_match_status,
            account_match_status=account_match_status,
            has_issue=has_issue,
            q=q,
            limit=limit,
            offset=offset,
        ))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="get_funnel",
    description="一次运行的财务漏斗：输入多少、媒体/账户匹配、processable、进约稿、进付款表、按错误码掉量。",
)
def get_funnel(run_id: str) -> str:
    """查询财务漏斗。

    Args:
        run_id: 运行 ID
    """
    try:
        return _ok(_query().get_funnel(run_id))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="get_record",
    description="一条记录在各节点的字段变化和相关问题。用于回答「为什么这条没进付款表」。",
)
def get_record(run_id: str, record_id: str) -> str:
    """查询单条记录的流转。

    Args:
        run_id: 运行 ID
        record_id: 记录 ID，如 rec_0001
    """
    try:
        return _ok(_query().get_record(run_id, record_id))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="list_artifacts",
    description="列出一次运行生成的产物（付款表、约稿资料）。只返回文件名和大小，不含二进制。",
)
def list_artifacts(run_id: str) -> str:
    """列出产物。

    Args:
        run_id: 运行 ID
    """
    try:
        return _ok(_query().list_artifacts(run_id))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="describe_artifact",
    description="描述某个产物文件的含义和摘要。需要文件本体时提示走 HTTP 下载，不在 MCP 里传 xlsx。",
)
def describe_artifact(run_id: str, file_key: str) -> str:
    """描述产物。

    Args:
        run_id: 运行 ID
        file_key: 产物 key，如 payment 或 quote_detail
    """
    try:
        return _ok(_query().describe_artifact(run_id, file_key))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="get_workflow_schema",
    description="静态说明书：7 个节点的顺序、读写字段、典型错误码。第一次对话应先调这个。",
)
def get_workflow_schema() -> str:
    """返回工作流静态 schema。"""
    try:
        return _ok(_query().get_workflow_schema())
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Resources：应用侧只读文档。URI 固定或模板化，不带过滤参数。
# ---------------------------------------------------------------------------

@mcp.resource(
    "workflow://schema",
    name="workflow-schema",
    title="工作流节点说明书",
    description="固定 7 节点顺序、读写字段、错误码。",
    mime_type="application/json",
)
def resource_schema() -> str:
    return _ok(_query().get_workflow_schema())


@mcp.resource(
    "workflow://runs",
    name="workflow-runs",
    title="最近运行列表",
    description="最近 20 次运行的摘要。",
    mime_type="application/json",
)
def resource_runs() -> str:
    return _ok(_query().list_runs(limit=20))


@mcp.resource(
    "workflow://runs/{run_id}",
    name="workflow-run",
    title="单次运行总览",
    description="一次运行的状态、进度和节点摘要。",
    mime_type="application/json",
)
def resource_run(run_id: str) -> str:
    try:
        return _ok(_query().get_run(run_id))
    except Exception as exc:
        return _error(exc)


@mcp.resource(
    "workflow://runs/{run_id}/nodes/{node_id}",
    name="workflow-node",
    title="单节点执行详情",
    description="某次运行中某个节点的指标、问题和输出样本。",
    mime_type="application/json",
)
def resource_node(run_id: str, node_id: str) -> str:
    try:
        return _ok(_query().get_node(run_id, node_id))
    except Exception as exc:
        return _error(exc)


@mcp.resource(
    "workflow://runs/{run_id}/issues",
    name="workflow-issues",
    title="一次运行的全部问题",
    description="未过滤的 issue 列表。需要过滤时请用 list_issues 工具。",
    mime_type="application/json",
)
def resource_issues(run_id: str) -> str:
    try:
        return _ok(_query().list_issues(run_id))
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Prompts：用户显式触发的排错模板，不是模型自动调用的工具。
# ---------------------------------------------------------------------------

@mcp.prompt(
    name="run_workflow",
    title="按表1启动工作流并跟踪",
    description="根据 1-链接.xlsx 路径启动完整流程，再查询进度。",
)
def prompt_run_workflow(input_file: str) -> str:
    return (
        f"请用 start_run 启动工作流，input_file=`{input_file}`，table_dir 默认 ./table。\n"
        "拿到 run_id 后用 wait_run 等到 completed / failed / terminated（可超时后再调一次）。\n"
        "若失败或条数对不上，用 get_funnel、summarize_issues、list_records、get_node 说明卡在哪。"
    )


@mcp.prompt(
    name="inspect_run",
    title="检查一次工作流运行",
    description="根据 run_id 检查执行情况、失败节点和问题。",
)
def prompt_inspect_run(run_id: str) -> str:
    return (
        f"请检查工作流运行 `{run_id}`。\n"
        "1. 用 get_run 看总览和当前/失败节点；若 stale 说明进程可能已死。\n"
        "2. 用 get_funnel 看从输入到付款表掉了多少。\n"
        "3. 用 summarize_issues 看主要错误码，必要时再 list_issues。\n"
        "4. 对失败节点调用 get_node；对漏掉的记录用 list_records(processable=false) 再 get_record。\n"
        "5. 用中文给出：跑到哪了、谁失败、影响哪些记录、下一步建议。"
    )


@mcp.prompt(
    name="inspect_node",
    title="检查某个节点",
    description="查看指定节点的输出、指标和报错。",
)
def prompt_inspect_node(run_id: str, node_id: str) -> str:
    return (
        f"请检查运行 `{run_id}` 的节点 `{node_id}`。\n"
        "调用 get_node，必要时再用 list_issues(node_id=...)。\n"
        "说明该节点处理了多少条、成功/失败、写出了哪些字段、报了哪些错。"
    )


@mcp.prompt(
    name="explain_record",
    title="解释一条记录为何未入账",
    description="追踪单条记录在各节点的字段变化。",
)
def prompt_explain_record(run_id: str, record_id: str) -> str:
    return (
        f"运行 `{run_id}` 中的记录 `{record_id}` 为什么可能没进入付款表？\n"
        "先 get_funnel 看整体掉量，再 get_record 结合 processable / "
        "media_match_status / account_match_status 和 issues 解释原因。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="约稿工作流 MCP 服务（只读观测）")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.getenv("WORKFLOW_MCP_TRANSPORT", "streamable-http"),
        help="MCP 传输。远端部署用 streamable-http。",
    )
    parser.add_argument("--host", default=os.getenv("WORKFLOW_MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WORKFLOW_MCP_PORT", "8100")))
    parser.add_argument("--path", default=os.getenv("WORKFLOW_MCP_PATH", "/mcp"))
    parser.add_argument(
        "--runtime-dir",
        default=os.getenv("WORKFLOW_RUNTIME_DIR"),
        help="运行库目录。默认仓库 runtime-mcp/，与 HTTP 后端的 runtime/ 隔离。",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("WORKFLOW_OUTPUT_DIR"),
        help="产物根目录。实际写入 <dir>/<run_id>/。默认仓库 output-mcp/。",
    )
    parser.add_argument(
        "--table-dir",
        default=os.getenv("WORKFLOW_TABLE_DIR"),
        help="默认参考表目录。",
    )
    args = parser.parse_args()
    from workflows.paths import project_root

    # MCP 进程自己的默认目录，避免和同仓库 HTTP 后端共用 workflow.db / output/
    if args.runtime_dir:
        os.environ["WORKFLOW_RUNTIME_DIR"] = args.runtime_dir
    else:
        os.environ.setdefault("WORKFLOW_RUNTIME_DIR", str(project_root() / "runtime-mcp"))
    if args.output_dir:
        os.environ["WORKFLOW_OUTPUT_DIR"] = args.output_dir
    else:
        os.environ.setdefault("WORKFLOW_OUTPUT_DIR", str(project_root() / "output-mcp"))
    if args.table_dir:
        os.environ["WORKFLOW_TABLE_DIR"] = args.table_dir

    if args.transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
        )
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
