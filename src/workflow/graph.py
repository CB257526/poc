"""LangGraph工作流定义"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from workflow.models import WorkflowState
from workflow.nodes import Node00Input, Node01FillBasic
from workflow.config import config
from typing import Literal
import structlog

logger = structlog.get_logger()


def should_continue(state: WorkflowState) -> Literal["continue", "end"]:
    """
    条件路由函数：根据状态决定是否继续执行

    判断逻辑：
    1. 如果有严重错误（critical级别），终止流程
    2. 如果记录数为0，终止流程
    3. 否则继续

    Args:
        state: 当前工作流状态

    Returns:
        "continue" 或 "end"
    """
    # 检查是否有严重错误
    critical_errors = [
        issue for issue in state.get("issues", [])
        if issue.get("level") == "critical"
    ]

    if critical_errors:
        logger.warning(
            "workflow_terminated_by_critical_error",
            error_count=len(critical_errors)
        )
        return "end"

    # 检查是否有记录
    records = state.get("records", [])
    if not records:
        logger.warning("workflow_terminated_no_records")
        return "end"

    return "continue"


def create_workflow() -> StateGraph:
    """
    创建工作流图

    Returns:
        配置好的StateGraph实例
    """
    # 创建图
    workflow = StateGraph(WorkflowState)

    # === 添加节点 ===
    node_00 = Node00Input()
    node_01 = Node01FillBasic()

    workflow.add_node("node_00_input", node_00)
    workflow.add_node("node_01_fill_basic", node_01)

    # TODO: 添加其他节点（节点2-6）
    # workflow.add_node("node_02_fill_publication", node_02)
    # workflow.add_node("node_03_match_media", node_03)
    # workflow.add_node("node_04_match_account", node_04)
    # workflow.add_node("node_05_calculate_fee", node_05)
    # workflow.add_node("node_06_generate_payment", node_06)

    # === 设置入口 ===
    workflow.set_entry_point("node_00_input")

    # === 添加边（定义流程） ===
    workflow.add_edge("node_00_input", "node_01_fill_basic")

    # 添加条件分支：节点1后检查是否继续
    workflow.add_conditional_edges(
        "node_01_fill_basic",
        should_continue,
        {
            "continue": END,  # TODO: 改为 "node_02_fill_publication"
            "end": END
        }
    )

    # TODO: 添加其他边
    # workflow.add_conditional_edges(
    #     "node_02_fill_publication",
    #     should_continue,
    #     {"continue": "node_03_match_media", "end": END}
    # )
    # workflow.add_conditional_edges(
    #     "node_03_match_media",
    #     should_continue,
    #     {"continue": "node_04_match_account", "end": END}
    # )
    # workflow.add_conditional_edges(
    #     "node_04_match_account",
    #     should_continue,
    #     {"continue": "node_05_calculate_fee", "end": END}
    # )
    # workflow.add_conditional_edges(
    #     "node_05_calculate_fee",
    #     should_continue,
    #     {"continue": "node_06_generate_payment", "end": END}
    # )
    # workflow.add_edge("node_06_generate_payment", END)

    logger.info("workflow_graph_created", nodes=2)

    return workflow


def create_runnable_workflow():
    """
    创建可执行的工作流（带检查点）

    Returns:
        编译好的可执行工作流
    """
    # 获取检查点数据库路径
    checkpoint_db = config.get_checkpoint_db()

    # 创建检查点保存器
    checkpointer = SqliteSaver.from_conn_string(checkpoint_db)

    # 创建并编译工作流
    workflow = create_workflow()
    runnable = workflow.compile(checkpointer=checkpointer)

    logger.info(
        "runnable_workflow_created",
        checkpoint_db=checkpoint_db
    )

    return runnable
