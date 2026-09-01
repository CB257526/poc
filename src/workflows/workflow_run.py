"""工作流定义与逐步执行。"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from workflows.models import WorkflowContext
from workflows.nodes.base import BaseNode, WorkflowTerminated
from workflows.nodes.node_00_input import Node00Input
from workflows.nodes.node_01_fill_basic import Node01FillBasic
from workflows.nodes.node_02_fill_publication import Node02FillPublication
from workflows.nodes.node_03_match_media import Node03MatchMedia
from workflows.nodes.node_04_match_account import Node04MatchAccount
from workflows.nodes.node_05_calculate_fee import Node05CalculateFee
from workflows.nodes.node_06_generate_payment import Node06GeneratePayment
from workflows.paths import default_table_dir, runtime_params, run_output_dir
from workflows.runtime import store as run_store
from workflows.services import get_logger

logger = get_logger()


def create_nodes() -> list[BaseNode]:
    """按固定顺序创建节点实例。"""
    return [
        Node00Input(),
        Node01FillBasic(),
        Node02FillPublication(),
        Node03MatchMedia(),
        Node04MatchAccount(),
        Node05CalculateFee(),
        Node06GeneratePayment(),
    ]


def create_workflow():
    """保留 | 链式组合，供现有测试使用。"""
    nodes = create_nodes()
    workflow = nodes[0]
    for node in nodes[1:]:
        workflow = workflow | node
    return workflow


def _persist(context: WorkflowContext) -> None:
    try:
        run_store.get_run_store().save_run(context)
    except Exception:
        logger.warning("run_store_save_failed", run_id=context.run_id, exc_info=True)


def run_workflow(
    input_file: str,
    table_dir: str | None = None,
    config: dict = None,
    run_id: str | None = None,
    on_progress: Callable[[WorkflowContext], None] | None = None,
) -> WorkflowContext:
    """
    逐步运行工作流，每步刷新 RunStore，供 MCP / HTTP 查询进度。
    产物写到 output/{run_id}/，运行记录写到 WORKFLOW_RUNTIME_DIR（默认仓库 runtime/）。
    """
    run_id = run_id or f"run_{int(time.time() * 1000)}_{os.getpid()}"
    table_dir = str(Path(table_dir).expanduser().resolve() if table_dir else default_table_dir())
    input_file = str(Path(input_file).expanduser().resolve())
    config = dict(config or {})
    output_root = config.get("output_root")
    if not output_root and config.get("output_dir"):
        configured = Path(str(config["output_dir"])).expanduser()
        # 后端如果已经传入 output/<run_id>，不要再套一层
        output_root = configured.parent if configured.name == run_id else configured
    params = runtime_params(
        run_id=run_id,
        input_file=input_file,
        table_dir=table_dir,
        output_root_dir=output_root,
    )
    config.update({
        "output_root": params["output_root"],
        "output_dir": params["output_dir"],
        "runtime_dir": params["runtime_dir"],
        "runtime_db": params["runtime_db"],
        "paths": params,
    })
    run_output_dir(run_id, params["output_root"])
    context = WorkflowContext(
        run_id=run_id,
        run_started_at=datetime.now(),
        input_file=input_file,
        table_dir=table_dir,
        config=config,
        run_status="running",
    )

    # 把 run_id 绑定到当前协程/线程的日志上下文，节点内所有结构化日志自动带上 run_id
    try:
        import structlog.contextvars
    except ImportError:
        structlog.contextvars = None
    if structlog.contextvars is not None:
        structlog.contextvars.bind_contextvars(run_id=run_id)

    logger.info(
        "workflow_started",
        run_id=run_id,
        input_file=input_file,
        table_dir=table_dir,
        output_dir=params["output_dir"],
        runtime_db=params["runtime_db"],
    )
    _persist(context)

    try:
        for node in create_nodes():
            context = node.invoke(context)
            if on_progress:
                on_progress(context)

        context.run_status = "failed" if context.has_critical_errors() else "completed"
        context.run_finished_at = datetime.now()
        _persist(context)

        logger.info(
            "workflow_completed",
            run_id=run_id,
            completed_nodes=len(context.completed_nodes),
            total_records=len(context.records),
            issues_count=len(context.issues),
            critical_count=len(context.get_issues_by_level("critical")),
            error_count=len(context.get_issues_by_level("error")),
            warning_count=len(context.get_issues_by_level("warning")),
        )
        return context

    except WorkflowTerminated as e:
        context.run_status = "terminated"
        context.run_finished_at = datetime.now()
        context.termination_reason = context.termination_reason or str(e)
        _persist(context)
        logger.warning(
            "workflow_terminated",
            run_id=run_id,
            reason=str(e),
            completed_nodes=len(context.completed_nodes),
            issues_count=len(context.issues),
        )
        return context

    except Exception as e:
        context.run_status = "failed"
        context.run_finished_at = datetime.now()
        logger.error(
            "workflow_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        context.add_issue(
            level="critical",
            code="WORKFLOW_EXECUTION_FAILED",
            message=f"工作流执行失败: {str(e)}",
            node_id=context.current_node or "unknown",
        )
        context.termination_reason = str(e)
        _persist(context)
        return context
