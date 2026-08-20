# 约稿费用验收工作流 - 重构版

基于 **LangChain** 的轻量级工作流实现，摒弃了 LangGraph 的复杂状态管理。

## 🎯 重构原因

经过实际调研，发现对于**固定顺序的业务流程**：

❌ **LangGraph 的问题**：
- StateGraph 的全局状态传递过于复杂
- TypedDict + Annotated reducer 学习曲线陡峭
- 条件路由对于简单的顺序流程是过度设计
- 检查点持久化对于非交互场景意义不大

✅ **新方案优势**：
- 使用 LangChain 的 `RunnableSequence` 组合节点
- 节点间通过 `WorkflowContext` 对象直接传递
- 更简洁、更直观、更容易理解和维护

## 📊 架构对比

### 旧架构（LangGraph）
```python
# 复杂的状态定义
class WorkflowState(TypedDict):
    issues: Annotated[list, add]  # 需要理解 Annotated reducer
    node_statuses: Annotated[Dict, merge_func]
    # ... 10+ 个字段

# 节点返回增量更新
def execute(state: WorkflowState) -> WorkflowState:
    return {
        "issues": [...],  # 会自动合并
        "node_statuses": {...}
    }

# 复杂的图定义
workflow.add_conditional_edges(
    "node_01",
    should_continue,  # 额外的路由函数
    {"continue": "node_02", "end": END}
)
```

### 新架构（LangChain）
```python
# 简单的 Pydantic 模型
class WorkflowContext(BaseModel):
    run_id: str
    records: List[Dict] = []
    issues: List[Issue] = []
    # 清晰的字段，直接修改

# 节点直接修改上下文
def process(self, context: WorkflowContext) -> NodeOutput:
    context.records.append(...)  # 直接操作
    context.add_issue(...)
    return NodeOutput.create_success(...)

# 简洁的链式组合
workflow = (
    Node00Input()
    | Node01FillBasic()
    | Node02FillPublication()
    # ... 只有在需要分支时才考虑复杂路由
)
```

## 🏗️ 新架构设计

### 核心组件

1. **WorkflowContext** - Pydantic模型
   - 存储工作流状态
   - 提供辅助方法（如 `add_issue()`, `has_critical_errors()`）
   - 可以直接修改字段

2. **BaseNode** - 节点基类
   - 实现 LangChain 的 `Runnable` 接口
   - 自动处理日志、错误、终止条件
   - 子类只需实现 `process()` 方法

3. **NodeOutput** - 节点输出
   - 标准化的节点返回格式
   - 包含成功/失败状态、指标、问题列表

4. **工作流链** - RunnableSequence
   - 使用 `|` 运算符组合节点
   - 自动传递上下文
   - 遇到 critical 错误自动终止

### 数据流

```
输入文件
    ↓
Node00Input (验证输入)
    ↓
WorkflowContext {records: [...]}
    ↓
Node01FillBasic (解析链接)
    ↓
WorkflowContext {records: [...更新后], issues: [...]}
    ↓
Node02... (后续节点)
    ↓
最终 WorkflowContext
```

## 📁 新文件结构

```
src/workflow/
├── models_new.py           # WorkflowContext, Issue, NodeOutput 等模型
├── nodes/
│   ├── base_new.py         # BaseNode 基类
│   ├── node_00_input_new.py
│   └── node_01_fill_basic_new.py
├── workflow_new.py         # 工作流定义和执行
└── __main___new.py         # 命令行入口（新版）

tests/
└── test_new_architecture.py  # 新架构测试（14个测试全部通过）
```

## 🚀 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 运行工作流

```bash
# 使用新版命令行（开发中）
python -m workflow run_new --input ./table/1-链接.xlsx

# 或直接在代码中使用
from workflow.workflow_new import run_workflow

context = run_workflow(
    input_file="./table/1-链接.xlsx",
    table_dir="./table"
)

# 检查结果
print(f"处理了 {len(context.records)} 条记录")
print(f"发现 {len(context.issues)} 个问题")
if context.has_critical_errors():
    print("有严重错误！")
```

### 3. 运行测试

```bash
# 新架构测试
pytest tests/test_new_architecture.py -v

# 结果：14 passed ✅
```

## ✨ 核心特性

### 1. 简单直观的上下文

```python
# 直接修改字段
context.records.append(new_record)
context.add_issue(level="warning", code="TEST", message="...")

# 辅助方法
if context.has_critical_errors():
    # 终止流程
    
issues = context.get_issues_by_level("error")
```

### 2. 清晰的节点实现

```python
class MyNode(BaseNode):
    def __init__(self):
        super().__init__("my_node", "我的节点")
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 1. 从 context 读取数据
        records = context.records
        
        # 2. 处理逻辑
        for record in records:
            # ... 处理
            if error:
                issues.append(Issue(...))
        
        # 3. 更新 context
        context.records = processed_records
        
        # 4. 返回结果
        return NodeOutput.create_success(
            metrics=NodeMetrics(
                processed_count=len(records),
                success_count=success_count
            ),
            issues=issues
        )
```

### 3. 自动错误处理

```python
# BaseNode 自动处理：
# - 节点异常 → 转为 critical issue → 终止流程
# - 遇到 critical issue → 抛出 WorkflowTerminated
# - 没有记录 → 提前终止

# 你只需专注业务逻辑
```

### 4. 灵活组合

```python
# 简单的顺序流程
workflow = Node1() | Node2() | Node3()

# 需要条件分支时，可以使用 RunnableBranch
from langchain_core.runnables import RunnableBranch

workflow = (
    Node1()
    | RunnableBranch(
        (lambda ctx: ctx.has_critical_errors(), stop_node),
        Node2()  # 默认分支
    )
    | Node3()
)
```

## 📊 性能对比

| 维度 | LangGraph | LangChain (新) |
|------|-----------|----------------|
| 代码复杂度 | ⭐⭐⭐⭐ | ⭐⭐ |
| 学习曲线 | 陡峭 | 平缓 |
| 状态管理 | 增量更新 + reducer | 直接修改对象 |
| 调试难度 | 较难 | 容易 |
| 扩展性 | 强（支持复杂图） | 中（顺序流程） |
| 适用场景 | 复杂的条件分支 | 固定的业务流程 |

## 🔄 迁移指南

### 旧代码（LangGraph）

```python
def execute(self, state: WorkflowState) -> NodeOutput:
    # 返回增量更新
    return {
        "issues": [new_issue],  # 会被 add reducer 合并
        "records": new_records   # 会被直接替换
    }
```

### 新代码（LangChain）

```python
def process(self, context: WorkflowContext) -> NodeOutput:
    # 直接修改 context
    context.issues.append(new_issue)
    context.records = new_records
    
    # 返回本节点的输出（不是状态更新）
    return NodeOutput.create_success(
        metrics=NodeMetrics(...),
        issues=[new_issue]
    )
```

## 🎯 设计原则

1. **简单优先** - 不用图，直到需要分支
2. **显式优于隐式** - 直接修改 context，不用 reducer
3. **最小抽象** - 只抽象必要的基类和模型
4. **易于测试** - Pydantic 模型，纯函数逻辑
5. **渐进式增强** - 先顺序流程，需要时再加分支

## 🚧 当前进度

- ✅ 新架构设计完成
- ✅ 核心模型定义（WorkflowContext, Issue, NodeOutput）
- ✅ 节点基类（BaseNode）
- ✅ 节点0：输入验证
- ✅ 节点1：填写基础信息
- ✅ 工作流定义和执行
- ✅ 14个单元测试全部通过
- ⏳ 命令行入口（待集成）
- ⏳ 节点2-6（待实现）
- ⏳ MCP服务器适配（待更新）
- ⏳ 端到端测试（待添加）

## 📚 相关文档

- [LangChain Runnables 文档](https://python.langchain.com/docs/concepts/runnables/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- 旧版文档: `README.md`（基于 LangGraph）

## 💡 何时使用 LangGraph

如果你的工作流有以下需求，考虑回到 LangGraph：

- ✅ 复杂的条件分支（3个以上分支点）
- ✅ 需要循环执行某些节点
- ✅ 需要人工审核点（暂停/恢复）
- ✅ 需要持久化检查点以支持恢复
- ✅ 多个并行路径

对于**固定顺序的业务流程**，新架构更合适。

## 🤝 贡献

欢迎反馈和建议！如果你发现新架构有问题或可以改进的地方，请提出 issue。
