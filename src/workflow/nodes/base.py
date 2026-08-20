"""节点基类定义"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import time
from datetime import datetime
from workflow.models import WorkflowState, NodeOutput, NodeStatus
from workflow.services import get_logger

logger = get_logger()


class BaseNode(ABC):
    """
    节点基类，提供统一的节点执行框架

    所有业务节点都继承此基类，只需实现 execute 方法
    基类负责：
    - 日志记录
    - 状态更新（使用Annotated reducer模式）
    - 错误处理
    - 性能监控
    """

    def __init__(self, node_id: str, node_name: str):
        """
        初始化节点

        Args:
            node_id: 节点ID，如 "node_00"
            node_name: 节点名称，如 "输入节点"
        """
        self.node_id = node_id
        self.node_name = node_name

    def __call__(self, state: WorkflowState) -> WorkflowState:
        """
        节点执行入口

        使用Annotated reducer模式返回增量更新
        LangGraph会自动合并issues和metrics

        Args:
            state: 当前工作流状态

        Returns:
            状态更新字典（增量，不是完整状态）
        """
        start_time = time.time()
        run_id = state.get("run_id", "unknown")

        logger.info(
            "node_started",
            node_id=self.node_id,
            node_name=self.node_name,
            run_id=run_id
        )

        # 创建running状态
        node_status: NodeStatus = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "error": None,
            "metrics": {}
        }

        try:
            # 执行节点的具体逻辑
            result: NodeOutput = self.execute(state)

            # 计算耗时
            duration_ms = (time.time() - start_time) * 1000

            # 更新节点状态为 completed
            node_status.update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "duration_ms": duration_ms,
                "metrics": result.get("metrics", {})
            })

            logger.info(
                "node_completed",
                node_id=self.node_id,
                node_name=self.node_name,
                run_id=run_id,
                duration_ms=duration_ms,
                status=result.get("status"),
                processed_count=result.get("processed_count", 0),
                success_count=result.get("success_count", 0),
                issues_count=len(result.get("issues", []))
            )

            # 返回增量更新（Annotated reducer会自动合并）
            updates: WorkflowState = {
                "node_statuses": {self.node_id: node_status},
                "issues": result.get("issues", []),
                "metrics": result.get("metrics", {})
            }

            # 如果有data字段，合并到更新中
            if "data" in result and result["data"]:
                for key, value in result["data"].items():
                    if key in ["records", "quote_details", "monthly_summary",
                               "payment_rows", "output_files", "table_paths",
                               "table_metadata"]:
                        updates[key] = value  # type: ignore

            return updates

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"

            logger.error(
                "node_failed",
                node_id=self.node_id,
                node_name=self.node_name,
                run_id=run_id,
                error=error_msg,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                exc_info=True
            )

            # 更新节点状态为 failed
            node_status.update({
                "status": "failed",
                "completed_at": datetime.now().isoformat(),
                "duration_ms": duration_ms,
                "error": error_msg
            })

            # 创建critical级别的issue
            critical_issue = {
                "level": "critical",
                "code": "NODE_EXECUTION_FAILED",
                "message": f"节点 {self.node_name} 执行失败: {error_msg}",
                "node_id": self.node_id,
                "details": {
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            }

            # 返回增量更新（包含critical issue）
            return {
                "node_statuses": {self.node_id: node_status},
                "issues": [critical_issue],
                "metrics": {}
            }

    @abstractmethod
    def execute(self, state: WorkflowState) -> NodeOutput:
        """
        节点的具体执行逻辑

        子类必须实现此方法

        Args:
            state: 当前工作流状态

        Returns:
            节点输出，包含 status, data, issues, metrics 等
        """
        pass

    def _get_table_path(self, state: WorkflowState, table_name: str) -> str:
        """
        从状态中获取表格路径

        Args:
            state: 工作流状态
            table_name: 表格名称，如 "3-媒体库"

        Returns:
            表格文件路径

        Raises:
            ValueError: 如果表格路径不存在
        """
        table_paths = state.get("table_paths", {})
        if table_name not in table_paths:
            raise ValueError(f"表格 {table_name} 的路径不存在")
        return table_paths[table_name]

    def _create_success_output(
        self,
        data: Dict[str, Any],
        processed_count: int = 0,
        success_count: int = 0,
        issues: list = None,
        metrics: Dict[str, Any] = None
    ) -> NodeOutput:
        """
        创建成功的节点输出

        Args:
            data: 处理后的数据
            processed_count: 处理的记录数
            success_count: 成功的记录数
            issues: 问题列表
            metrics: 统计指标

        Returns:
            标准的节点输出
        """
        return {
            "status": "success" if not issues or all(i["level"] == "warning" for i in issues) else "partial_success",
            "processed_count": processed_count,
            "success_count": success_count,
            "data": data,
            "issues": issues or [],
            "metrics": metrics or {}
        }
