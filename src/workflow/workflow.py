"""工作流定义"""

import time
from datetime import datetime
from langchain_core.runnables import RunnableSequence

from workflow.models import WorkflowContext
from workflow.nodes.base import WorkflowTerminated
from workflow.nodes.node_00_input import Node00Input
from workflow.nodes.node_01_fill_basic import Node01FillBasic
from workflow.nodes.node_02_fill_publication import Node02FillPublication
from workflow.nodes.node_03_match_media import Node03MatchMedia
from workflow.nodes.node_04_match_account import Node04MatchAccount
from workflow.nodes.node_05_calculate_fee import Node05CalculateFee
from workflow.nodes.node_06_generate_payment import Node06GeneratePayment
from workflow.services import get_logger

logger = get_logger()


def create_workflow() -> RunnableSequence:
    """
    创建工作流链

    使用 LangChain 的 RunnableSequence 组合节点
    比 LangGraph 的 StateGraph 更简洁直观

    Returns:
        可执行的工作流链
    """
    return (
        Node00Input()
        | Node01FillBasic()
        | Node02FillPublication()
        | Node03MatchMedia()
        | Node04MatchAccount()
        | Node05CalculateFee()
        | Node06GeneratePayment()
    )


def run_workflow(
    input_file: str,
    table_dir: str = "./table",
    config: dict = None
) -> WorkflowContext:
    """
    运行工作流

    Args:
        input_file: 输入文件路径
        table_dir: 表格目录
        config: 可选配置

    Returns:
        最终的工作流上下文
    """
    # 生成运行ID
    run_id = f"run_{int(time.time() * 1000)}"

    # 创建初始上下文
    context = WorkflowContext(
        run_id=run_id,
        run_started_at=datetime.now(),
        input_file=input_file,
        table_dir=table_dir,
        config=config or {}
    )

    logger.info(
        "workflow_started",
        run_id=run_id,
        input_file=input_file,
        table_dir=table_dir
    )

    # 创建并执行工作流
    workflow = create_workflow()

    try:
        # 执行工作流链
        result = workflow.invoke(context)

        logger.info(
            "workflow_completed",
            run_id=run_id,
            completed_nodes=len(result.completed_nodes),
            total_records=len(result.records),
            issues_count=len(result.issues),
            critical_count=len(result.get_issues_by_level("critical")),
            error_count=len(result.get_issues_by_level("error")),
            warning_count=len(result.get_issues_by_level("warning"))
        )

        return result

    except WorkflowTerminated as e:
        logger.warning(
            "workflow_terminated",
            run_id=run_id,
            reason=str(e),
            completed_nodes=len(context.completed_nodes),
            issues_count=len(context.issues)
        )
        return context

    except Exception as e:
        logger.error(
            "workflow_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        # 添加 critical issue
        context.add_issue(
            level="critical",
            code="WORKFLOW_EXECUTION_FAILED",
            message=f"工作流执行失败: {str(e)}",
            node_id=context.current_node or "unknown"
        )
        return context
