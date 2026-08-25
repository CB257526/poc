"""新的数据模型 - 基于 Pydantic"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional
from datetime import datetime

NodeStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["pending", "running", "completed", "failed", "terminated"]


class Issue(BaseModel):
    """问题记录"""
    level: str = Field(..., description="warning, error, critical")
    code: str = Field(..., description="问题代码")
    message: str = Field(..., description="问题描述")
    node_id: str = Field(..., description="产生问题的节点ID")
    record_id: Optional[str] = Field(None, description="关联的记录ID")
    details: Dict[str, Any] = Field(default_factory=dict, description="额外细节")


class NodeMetrics(BaseModel):
    """节点执行指标"""
    processed_count: int = Field(0, description="处理的记录数")
    success_count: int = Field(0, description="成功的记录数")
    error_count: int = Field(0, description="失败的记录数")
    duration_ms: float = Field(0, description="执行耗时（毫秒）")


class NodeRun(BaseModel):
    """单次运行中一个节点的时间线记录，供查询层 / MCP 读取。"""
    node_id: str
    node_name: str
    status: NodeStatus = "pending"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    metrics: NodeMetrics = Field(default_factory=NodeMetrics)
    issue_count: int = 0
    output_keys: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    snapshot_ref: Optional[str] = None


class WorkflowContext(BaseModel):
    """
    工作流上下文 - 贯穿整个流程的数据载体

    设计原则：
    - 使用 Pydantic 而不是 TypedDict，提供更好的类型检查和验证
    - 节点间直接传递 context 对象，而不是全局 state 字典
    - 数据更新通过 Pydantic 的字段赋值，而不是字典合并
    """

    # === 元信息 ===
    run_id: str = Field(..., description="运行ID")
    run_started_at: datetime = Field(default_factory=datetime.now, description="开始时间")

    # === 输入 ===
    input_file: str = Field(..., description="输入文件路径")
    table_dir: str = Field(default="./table", description="表格目录")

    # === 配置（可选）===
    config: Dict[str, Any] = Field(default_factory=dict, description="运行时配置")

    # === 业务数据 ===
    records: List[Dict[str, Any]] = Field(default_factory=list, description="记录列表")
    quote_details: Optional[Dict[str, Any]] = Field(None, description="约稿明细")
    monthly_summary: Optional[Dict[str, Any]] = Field(None, description="月度汇总")
    payment_rows: Optional[List[Dict[str, Any]]] = Field(None, description="付款表行")

    # === 追踪信息 ===
    issues: List[Issue] = Field(default_factory=list, description="问题列表")
    current_node: Optional[str] = Field(None, description="当前执行的节点")
    completed_nodes: List[str] = Field(default_factory=list, description="已完成的节点")
    node_runs: List[NodeRun] = Field(default_factory=list, description="各节点执行时间线")
    run_status: RunStatus = Field("pending", description="整次运行状态")
    run_finished_at: Optional[datetime] = Field(None, description="结束时间")
    termination_reason: Optional[str] = Field(None, description="提前终止原因")

    # === 产物 ===
    output_files: Dict[str, str] = Field(default_factory=dict, description="输出文件映射")

    # === 表格路径缓存 ===
    table_paths_cache: Dict[str, str] = Field(default_factory=dict, description="表格路径缓存", exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def get_table_path(self, table_name: str) -> str:
        """
        获取表格路径（带缓存）

        Args:
            table_name: 表格名称，如 "3-媒体库"

        Returns:
            表格文件的绝对路径
        """
        if table_name not in self.table_paths_cache:
            import os
            # 查找表格文件
            for ext in ['.xlsx', '.xls']:
                path = os.path.join(self.table_dir, f"{table_name}{ext}")
                if os.path.exists(path):
                    self.table_paths_cache[table_name] = path
                    break
            else:
                raise FileNotFoundError(f"表格 {table_name} 不存在于 {self.table_dir}")

        return self.table_paths_cache[table_name]

    def has_critical_errors(self) -> bool:
        """检查是否有严重错误"""
        return any(issue.level == "critical" for issue in self.issues)

    def get_issues_by_level(self, level: str) -> List[Issue]:
        """按级别获取问题"""
        return [issue for issue in self.issues if issue.level == level]

    def add_issue(
        self,
        level: str,
        code: str,
        message: str,
        node_id: str,
        record_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """便捷方法：添加问题"""
        self.issues.append(Issue(
            level=level,
            code=code,
            message=message,
            node_id=node_id,
            record_id=record_id,
            details=details or {}
        ))

    def get_node_run(self, node_id: str) -> Optional[NodeRun]:
        """按节点 ID 取时间线记录。"""
        for node_run in self.node_runs:
            if node_run.node_id == node_id:
                return node_run
        return None

    def upsert_node_run(self, node_run: NodeRun) -> NodeRun:
        """插入或替换某个节点的时间线。"""
        for index, existing in enumerate(self.node_runs):
            if existing.node_id == node_run.node_id:
                self.node_runs[index] = node_run
                return node_run
        self.node_runs.append(node_run)
        return node_run


class NodeOutput(BaseModel):
    """
    节点输出

    节点执行后返回此对象，包含：
    - 是否成功
    - 产生的问题
    - 执行指标
    - 需要更新到 context 的数据
    """
    success: bool = Field(..., description="是否成功")
    issues: List[Issue] = Field(default_factory=list, description="问题列表")
    metrics: NodeMetrics = Field(default_factory=NodeMetrics, description="执行指标")
    data: Dict[str, Any] = Field(default_factory=dict, description="更新到 context 的数据")

    @classmethod
    def create_success(
        cls,
        metrics: NodeMetrics,
        data: Optional[Dict[str, Any]] = None,
        issues: Optional[List[Issue]] = None
    ) -> "NodeOutput":
        """创建成功输出"""
        return cls(
            success=True,
            metrics=metrics,
            data=data or {},
            issues=issues or []
        )

    @classmethod
    def create_failure(
        cls,
        metrics: NodeMetrics,
        issues: List[Issue],
        data: Optional[Dict[str, Any]] = None
    ) -> "NodeOutput":
        """创建失败输出"""
        return cls(
            success=False,
            metrics=metrics,
            issues=issues,
            data=data or {}
        )
