"""节点基类 - 基于 LangChain Runnable"""

from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.runnables import Runnable
import time

from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger

logger = get_logger()


class WorkflowTerminated(Exception):
    """工作流终止异常"""
    pass


class BaseNode(Runnable[WorkflowContext, WorkflowContext], ABC):
    """
    节点基类，实现 LangChain 的 Runnable 接口

    核心改进：
    1. 不再使用全局 state 字典，而是传递 WorkflowContext 对象
    2. 节点间数据通过对象字段传递，更直观
    3. 子类只需实现 process() 方法，返回 NodeOutput
    4. 自动处理日志、错误、终止逻辑
    """

    def __init__(self, node_id: str, node_name: str):
        """
        初始化节点

        Args:
            node_id: 节点ID，如 "node_00"
            node_name: 节点名称，如 "输入验证"
        """
        super().__init__()
        self.node_id = node_id
        self.node_name = node_name

    def invoke(
        self,
        input: WorkflowContext,
        config: Optional[dict] = None
    ) -> WorkflowContext:
        """
        执行节点（Runnable 接口方法）

        Args:
            input: 工作流上下文
            config: 可选的运行配置

        Returns:
            更新后的工作流上下文

        Raises:
            WorkflowTerminated: 当需要终止工作流时
        """
        context = input
        start_time = time.time()

        # 更新当前节点
        context.current_node = self.node_id

        logger.info(
            "node_started",
            node_id=self.node_id,
            node_name=self.node_name,
            run_id=context.run_id
        )

        try:
            # 执行节点的具体逻辑
            output = self.process(context)

            # 更新上下文：将 output.data 中的数据写入 context
            if output.data:
                for key, value in output.data.items():
                    if hasattr(context, key):
                        setattr(context, key, value)
                    else:
                        logger.warning(
                            "unknown_context_field",
                            field=key,
                            node_id=self.node_id
                        )

            # 添加问题
            context.issues.extend(output.issues)

            # 标记节点完成
            context.completed_nodes.append(self.node_id)

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "node_completed",
                node_id=self.node_id,
                node_name=self.node_name,
                run_id=context.run_id,
                success=output.success,
                duration_ms=duration_ms,
                processed_count=output.metrics.processed_count,
                success_count=output.metrics.success_count,
                error_count=output.metrics.error_count,
                issues_count=len(output.issues)
            )

            # 检查是否应该终止工作流
            if self._should_terminate(context):
                termination_reason = self._get_termination_reason(context)
                logger.warning(
                    "workflow_terminating",
                    node_id=self.node_id,
                    reason=termination_reason
                )
                raise WorkflowTerminated(termination_reason)

            return context

        except WorkflowTerminated:
            # 重新抛出终止异常
            raise

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"

            logger.error(
                "node_failed",
                node_id=self.node_id,
                node_name=self.node_name,
                run_id=context.run_id,
                error=error_msg,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                exc_info=True
            )

            # 添加 critical 级别的 issue
            context.add_issue(
                level="critical",
                code="NODE_EXECUTION_FAILED",
                message=f"节点 {self.node_name} 执行失败: {error_msg}",
                node_id=self.node_id,
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            # 节点执行失败，终止工作流
            raise WorkflowTerminated(
                f"节点 {self.node_id} ({self.node_name}) 执行失败"
            ) from e

    def _should_terminate(self, context: WorkflowContext) -> bool:
        """
        检查是否应该终止工作流

        终止条件：
        1. 有 critical 级别的错误
        2. 没有记录可处理（在输入验证后）

        Args:
            context: 工作流上下文

        Returns:
            是否应该终止
        """
        # 检查 critical 错误
        if context.has_critical_errors():
            return True

        # 检查记录数（只在输入验证后检查）
        if self.node_id != "node_00" and not context.records:
            return True

        return False

    def _get_termination_reason(self, context: WorkflowContext) -> str:
        """获取终止原因"""
        if context.has_critical_errors():
            critical_issues = context.get_issues_by_level("critical")
            return f"检测到 {len(critical_issues)} 个严重错误"

        if not context.records:
            return "没有记录可处理"

        return "未知原因"

    @abstractmethod
    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        节点的具体处理逻辑

        子类必须实现此方法

        Args:
            context: 工作流上下文（可以读取，但不要直接修改）

        Returns:
            节点输出，包含：
            - success: 是否成功
            - issues: 产生的问题
            - metrics: 执行指标
            - data: 需要更新到 context 的数据
        """
        pass

    def _create_success_output(
        self,
        processed_count: int,
        success_count: int,
        data: Optional[dict] = None,
        issues: Optional[list] = None,
        duration_ms: float = 0
    ) -> NodeOutput:
        """
        便捷方法：创建成功输出

        Args:
            processed_count: 处理的记录数
            success_count: 成功的记录数
            data: 更新到 context 的数据
            issues: 问题列表
            duration_ms: 耗时

        Returns:
            NodeOutput 对象
        """
        metrics = NodeMetrics(
            processed_count=processed_count,
            success_count=success_count,
            error_count=processed_count - success_count,
            duration_ms=duration_ms
        )

        return NodeOutput.create_success(
            metrics=metrics,
            data=data,
            issues=issues or []
        )

    def _create_failure_output(
        self,
        processed_count: int,
        success_count: int,
        issues: list,
        data: Optional[dict] = None,
        duration_ms: float = 0
    ) -> NodeOutput:
        """
        便捷方法：创建失败输出

        Args:
            processed_count: 处理的记录数
            success_count: 成功的记录数
            issues: 问题列表
            data: 更新到 context 的数据
            duration_ms: 耗时

        Returns:
            NodeOutput 对象
        """
        metrics = NodeMetrics(
            processed_count=processed_count,
            success_count=success_count,
            error_count=processed_count - success_count,
            duration_ms=duration_ms
        )

        return NodeOutput.create_failure(
            metrics=metrics,
            issues=issues,
            data=data
        )
