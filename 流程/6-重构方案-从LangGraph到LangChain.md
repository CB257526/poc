# 重构方案：从 LangGraph 到 LangChain

**日期**: 2026-08-20  
**背景**: 发现固定工作流场景使用 LangGraph 过于复杂，state 传递增加不必要的抽象

---

## 🎯 重构目标

### 问题分析

**LangGraph 的问题**：
1. **过度设计**: 对于固定顺序的工作流，StateGraph 是杀鸡用牛刀
2. **State 复杂度**: 需要定义完整的 TypedDict，编写 reducer 函数，管理全局状态
3. **不直观**: 节点间通过 state 字典传递，而不是直接的数据对象
4. **样板代码多**: 每个节点都要处理 state 的读取和更新

**适合 LangGraph 的场景**：
- 动态路由（根据条件跳转到不同分支）
- 循环和递归（需要多次经过同一节点）
- 人工介入（human-in-the-loop）
- 复杂的状态依赖

**我们的场景**：
- ✅ 固定的线性流程（node0 → node1 → ... → node6）
- ✅ 简单的条件终止（有错误就终止）
- ✅ 节点间数据依赖简单（上游输出 → 下游输入）
- ❌ 不需要动态路由
- ❌ 不需要循环
- ❌ 不需要人工介入

**结论**: 用 LangChain 的 Chain/Runnable 更合适

---

## 📐 新架构设计

### 核心思想

1. **数据流代替状态流**: 节点间传递 Pydantic 对象，不是字典
2. **组合代替图**: 用 `RunnableSequence` 组合节点
3. **中间件模式**: 用装饰器处理横切关注点（日志、追踪、错误）
4. **保持能力**: 错误收集、状态追踪、MCP接口一个不少

### 对比

| 维度 | LangGraph（旧） | LangChain（新） |
|------|----------------|----------------|
| 工作流定义 | StateGraph + add_node/add_edge | RunnableSequence |
| 数据传递 | WorkflowState (TypedDict) | WorkflowContext (Pydantic) |
| 节点实现 | 继承 BaseNode，返回 state 字典 | Runnable，返回数据对象 |
| 错误处理 | 在 state 中收集 issues | 在 context 中收集 issues |
| 状态追踪 | node_statuses in state | 运行时管理器 |
| 条件终止 | add_conditional_edges | 节点内抛异常或返回标志 |
| 代码量 | ~2000行 | 预计 ~1200行 |

---

## 🏗️ 新架构组件

### 1. 数据模型（models.py）

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class Issue(BaseModel):
    """问题记录"""
    level: str  # warning, error, critical
    code: str
    message: str
    node_id: str
    record_id: Optional[str] = None
    details: Dict[str, Any] = {}

class NodeMetrics(BaseModel):
    """节点执行指标"""
    processed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    duration_ms: float = 0

class WorkflowContext(BaseModel):
    """工作流上下文 - 贯穿整个流程"""
    # 元信息
    run_id: str
    run_started_at: datetime
    
    # 输入
    input_file: str
    table_dir: str
    
    # 数据
    records: List[Dict[str, Any]] = []
    quote_details: Optional[Dict[str, Any]] = None
    monthly_summary: Optional[Dict[str, Any]] = None
    payment_rows: Optional[List[Dict[str, Any]]] = None
    
    # 追踪
    issues: List[Issue] = []
    current_node: Optional[str] = None
    completed_nodes: List[str] = []
    
    # 产物
    output_files: Dict[str, str] = {}
    
    class Config:
        arbitrary_types_allowed = True

class NodeOutput(BaseModel):
    """节点输出"""
    success: bool
    issues: List[Issue] = []
    metrics: NodeMetrics
    data: Dict[str, Any] = {}  # 更新到 context 的数据
```

### 2. 节点基类（nodes/base.py）

```python
from langchain_core.runnables import Runnable
from workflow.models import WorkflowContext, NodeOutput, NodeMetrics
from workflow.services import get_logger
import time

logger = get_logger()

class BaseNode(Runnable[WorkflowContext, WorkflowContext]):
    """
    节点基类，实现 Runnable 接口
    
    子类只需实现 process() 方法
    """
    
    def __init__(self, node_id: str, node_name: str):
        self.node_id = node_id
        self.node_name = node_name
    
    def invoke(
        self, 
        context: WorkflowContext, 
        config: Optional[dict] = None
    ) -> WorkflowContext:
        """
        执行节点逻辑
        
        Args:
            context: 工作流上下文
            config: 可选配置
            
        Returns:
            更新后的上下文
        """
        start_time = time.time()
        context.current_node = self.node_id
        
        logger.info("node_started", 
                   node_id=self.node_id, 
                   node_name=self.node_name,
                   run_id=context.run_id)
        
        try:
            # 执行节点逻辑
            output = self.process(context)
            
            # 更新上下文
            if output.data:
                for key, value in output.data.items():
                    setattr(context, key, value)
            
            context.issues.extend(output.issues)
            context.completed_nodes.append(self.node_id)
            
            duration_ms = (time.time() - start_time) * 1000
            
            logger.info("node_completed",
                       node_id=self.node_id,
                       success=output.success,
                       duration_ms=duration_ms,
                       issues_count=len(output.issues))
            
            # 检查是否应该终止
            if self._should_terminate(context):
                raise WorkflowTerminated(f"在节点 {self.node_id} 后终止")
            
            return context
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("node_failed",
                        node_id=self.node_id,
                        error=str(e),
                        duration_ms=duration_ms)
            
            # 添加 critical issue
            context.issues.append(Issue(
                level="critical",
                code="NODE_EXECUTION_FAILED",
                message=f"节点 {self.node_name} 执行失败: {str(e)}",
                node_id=self.node_id
            ))
            
            raise WorkflowTerminated(f"节点 {self.node_id} 失败") from e
    
    def _should_terminate(self, context: WorkflowContext) -> bool:
        """检查是否应该终止工作流"""
        # 有 critical 错误
        if any(i.level == "critical" for i in context.issues):
            return True
        
        # 没有记录
        if not context.records:
            return True
        
        return False
    
    @abstractmethod
    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        节点的具体逻辑
        
        Args:
            context: 工作流上下文（只读）
            
        Returns:
            节点输出（包含 issues 和要更新的数据）
        """
        pass

class WorkflowTerminated(Exception):
    """工作流终止异常"""
    pass
```

### 3. 工作流定义（workflow.py）

```python
from langchain_core.runnables import RunnableSequence
from workflow.models import WorkflowContext
from workflow.nodes import (
    Node00Input,
    Node01FillBasic,
    # Node02, Node03, ...
)

def create_workflow() -> RunnableSequence:
    """创建工作流链"""
    return (
        Node00Input("node_00", "输入验证")
        | Node01FillBasic("node_01", "填写基础信息")
        # | Node02FillPublication("node_02", "完善发布信息")
        # | Node03MatchMedia("node_03", "匹配媒体库")
        # | Node04MatchAccount("node_04", "匹配账户信息")
        # | Node05CalculateFee("node_05", "计算费用")
        # | Node06GeneratePayment("node_06", "生成付款表")
    )

def run_workflow(input_file: str, table_dir: str = "./table") -> WorkflowContext:
    """
    运行工作流
    
    Args:
        input_file: 输入文件路径
        table_dir: 表格目录
        
    Returns:
        最终的上下文
    """
    # 创建初始上下文
    context = WorkflowContext(
        run_id=f"run_{int(time.time())}",
        run_started_at=datetime.now(),
        input_file=input_file,
        table_dir=table_dir
    )
    
    # 创建并执行工作流
    workflow = create_workflow()
    
    try:
        result = workflow.invoke(context)
        logger.info("workflow_completed", run_id=context.run_id)
        return result
    except WorkflowTerminated as e:
        logger.warning("workflow_terminated", 
                      run_id=context.run_id,
                      reason=str(e))
        return context
```

### 4. 节点实现示例（nodes/node_01_fill_basic.py）

```python
from workflow.nodes.base import BaseNode
from workflow.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflow.services import ExcelService

class Node01FillBasic(BaseNode):
    """节点1: 填写约稿资料基础信息"""
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        处理逻辑：
        1. 读取记录
        2. 解析链接
        3. 识别平台
        4. 区分主次链接
        """
        excel = ExcelService()
        issues = []
        metrics = NodeMetrics()
        
        # 从 context 读取数据
        records = context.records
        metrics.processed_count = len(records)
        
        # 处理每条记录
        for record in records:
            try:
                # 业务逻辑...
                url = record.get("链接")
                if not url:
                    issues.append(Issue(
                        level="error",
                        code="MISSING_URL",
                        message="缺少链接",
                        node_id=self.node_id,
                        record_id=record.get("id")
                    ))
                    continue
                
                # 解析平台
                platform = self._parse_platform(url)
                record["平台"] = platform
                
                metrics.success_count += 1
                
            except Exception as e:
                issues.append(Issue(
                    level="error",
                    code="PROCESS_FAILED",
                    message=str(e),
                    node_id=self.node_id,
                    record_id=record.get("id")
                ))
                metrics.error_count += 1
        
        # 返回结果
        return NodeOutput(
            success=metrics.error_count == 0,
            issues=issues,
            metrics=metrics,
            data={"records": records}  # 更新 context.records
        )
    
    def _parse_platform(self, url: str) -> str:
        """解析平台"""
        # 实现...
        pass
```

---

## 📊 迁移计划

### 阶段1: 核心重构（2-3小时）
1. ✅ 编写新的数据模型（models.py）
2. ✅ 重写节点基类（nodes/base.py）
3. ✅ 创建工作流定义（workflow.py）
4. ✅ 迁移 services 层（保持不变）

### 阶段2: 节点迁移（1-2小时）
1. ✅ 迁移 Node00（输入验证）
2. ✅ 迁移 Node01（填写基础信息）
3. ⏳ 编写新的测试

### 阶段3: 接口适配（1小时）
1. ✅ 更新 MCP 服务器
2. ✅ 更新命令行工具
3. ✅ 更新运行时管理器

### 阶段4: 测试和文档（1小时）
1. ⏳ 端到端测试
2. ⏳ 更新 README
3. ⏳ 更新架构文档

---

## 💡 保留的能力

| 能力 | LangGraph实现 | LangChain实现 |
|------|--------------|--------------|
| 错误收集 | state["issues"] | context.issues |
| 状态追踪 | state["node_statuses"] | context.completed_nodes + 外部追踪 |
| 日志记录 | structlog | structlog（保持不变）|
| 条件终止 | add_conditional_edges | _should_terminate() + WorkflowTerminated |
| 检查点 | SqliteSaver | 可选：自定义保存/恢复 |
| MCP接口 | FastAPI | FastAPI（保持不变）|

---

## 🎯 预期效果

### 代码简化
- **减少 40%+ 代码量**: 去掉 StateGraph、Reducer、TypedDict 相关代码
- **更直观**: 节点间传递 Pydantic 对象，不是字典
- **更少样板**: 节点只需实现 process()，不需要处理 state 合并

### 开发效率
- **更容易理解**: 顺序执行，数据流清晰
- **更容易调试**: 直接看 context 对象，不是全局 state
- **更容易扩展**: 添加节点就是添加一个 Runnable

### 性能
- **更快**: 少了 StateGraph 的调度开销
- **更轻**: 不需要 SqliteSaver（可选）

---

## ❓ FAQ

### Q: 完全抛弃 LangGraph 吗？
**A**: 不是完全抛弃，而是"只在必要时使用"。如果未来需要动态路由、循环等复杂逻辑，可以局部使用 LangGraph 作为某个节点的实现。

### Q: 如何处理并行执行？
**A**: LangChain 的 `RunnableParallel` 可以实现并行，例如：
```python
parallel_step = RunnableParallel({
    "media": Node03MatchMedia(),
    "account": Node04MatchAccount()
})
```

### Q: 检查点怎么办？
**A**: 如果真的需要检查点（暂停/恢复），可以：
1. 自定义保存/恢复逻辑（序列化 context）
2. 或者只在需要检查点的子流程中使用 LangGraph

### Q: 会破坏已有功能吗？
**A**: 不会。MCP 接口、日志、错误收集等核心能力都保留，只是实现方式更简洁。

---

## 📝 总结

从 LangGraph 到 LangChain 的重构，本质是**选择合适的抽象层次**：

- **LangGraph**: 为复杂的、动态的、有状态的工作流设计
- **LangChain**: 为固定的、线性的、数据流式的任务设计

我们的场景明显属于后者，重构后会更简洁、更易维护。
