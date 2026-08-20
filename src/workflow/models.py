"""数据模型定义

使用TypedDict定义工作流状态和数据结构，避免Pydantic的序列化开销
"""

from typing import TypedDict, List, Dict, Any, Optional, Literal, Annotated
import operator


# === 节点状态 ===

NodeStatusType = Literal["pending", "running", "completed", "failed", "skipped"]


class NodeStatus(TypedDict, total=False):
    """节点执行状态"""
    node_id: str
    node_name: str
    status: NodeStatusType
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_ms: Optional[float]
    error: Optional[str]
    metrics: Dict[str, Any]


# === 节点输出 ===

class NodeOutput(TypedDict, total=False):
    """节点执行输出的标准格式"""
    success: bool
    node_id: str
    node_name: str
    data: Dict[str, Any]
    issues: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    error: Optional[str]


# === 业务数据模型 ===

class SyncLink(TypedDict):
    """同步平台链接"""
    url: str
    platform: str
    raw_text: str


class QuoteRecord(TypedDict, total=False):
    """约稿记录"""
    # 基础标识
    record_id: str
    media_name: str
    topic: Optional[str]
    
    # 链接信息 (节点1填写)
    primary_link: Optional[str]
    primary_platform: Optional[str]
    sync_links: List[SyncLink]
    
    # 发布信息 (节点2填写)
    publish_form: Optional[str]      # 发布形式：图文/视频
    quote_type: Optional[str]        # 约稿类型
    platform: Optional[str]          # 平台
    title: Optional[str]             # 标题
    screenshot: Optional[str]        # 作品截图路径
    publish_date: Optional[str]      # 发布日期
    quote_count: Optional[int]       # 约稿数量
    
    # 媒体信息 (节点3填写)
    media_level: Optional[str]       # 媒体级别
    fans_count: Optional[int]        # 粉丝量
    
    # 账户信息 (节点4填写)
    account_name: Optional[str]      # 户名
    id_card: Optional[str]           # 身份证
    account_number: Optional[str]    # 账号
    phone: Optional[str]             # 电话
    bank: Optional[str]              # 开户行
    bank_city: Optional[str]         # 开户行所在城市
    
    # 费用信息 (节点5填写)
    base_amount: Optional[float]     # 基础金额
    total_amount: Optional[float]    # 合计金额
    fee_detail_id: Optional[str]     # 费用明细ID
    
    # 元数据
    source_row: int                  # 来源行号
    is_duplicate: bool               # 是否重复


class QuoteDetail(TypedDict):
    """约稿费用明细表记录"""
    detail_id: str
    media_name: str
    platform: str
    quote_type: str
    title: str
    publish_date: str
    base_amount: float
    bonus_amount: float
    total_amount: float


class MonthlySummary(TypedDict):
    """月度汇总记录"""
    month: str
    media_name: str
    total_count: int
    total_amount: float
    details: List[str]  # detail_id列表


class PaymentRow(TypedDict):
    """付款表记录"""
    account_name: str
    id_card: str
    account_number: str
    phone: str
    bank: str
    bank_city: str
    amount: float
    month: str


# === 问题记录 ===

class Issue(TypedDict, total=False):
    """问题/警告记录"""
    level: Literal["warning", "error"]
    code: str
    message: str
    node_id: str
    record_id: Optional[str]
    field: Optional[str]
    details: Dict[str, Any]


# === 工作流状态 ===

class WorkflowState(TypedDict):
    """
    工作流全局状态
    
    使用Annotated + operator.add实现自动累积：
    - issues: 每个节点产生的问题自动追加
    - records: 每个节点更新的记录自动合并
    """
    # 运行元数据
    run_id: str
    run_started_at: str
    config: Dict[str, Any]
    
    # 输入输出
    input_file: str
    table_paths: Dict[str, str]
    table_metadata: Dict[str, Any]
    
    # 业务数据 - 使用Annotated + operator.add实现自动累积
    records: Annotated[List[QuoteRecord], operator.add]
    quote_details: Optional[List[QuoteDetail]]
    monthly_summary: Optional[List[MonthlySummary]]
    payment_rows: Optional[List[PaymentRow]]
    
    # 产物
    output_files: Dict[str, str]
    
    # 问题收集 - 使用Annotated + operator.add实现自动累积
    issues: Annotated[List[Issue], operator.add]
    
    # 节点状态
    node_statuses: Dict[str, NodeStatus]
    
    # 全局指标
    metrics: Dict[str, Any]
