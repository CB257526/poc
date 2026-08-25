# 约稿费用验收工作流

基于 **LangChain** 的轻量级工作流实现，专为固定顺序的业务流程设计。

## 🎯 设计理念

对于**固定顺序的业务流程**，采用最简单直接的方式：

✅ **核心优势**：
- 使用 LangChain 的 `RunnableSequence` 组合节点
- 节点间通过 `WorkflowContext` 对象直接传递
- 简洁、直观、易于理解和维护
- 只在真正需要分支时才引入复杂路由

## 📊 架构设计

### 工作流定义
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

## 🏗️ 架构组件

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

## 📁 项目结构

```
src/workflow/
├── models.py              # WorkflowContext, Issue, NodeOutput 等模型
├── nodes/
│   ├── base.py            # BaseNode 基类
│   ├── node_00_input.py   # 节点0: 输入验证
│   ├── node_01_fill_basic.py      # 节点1: 填写基础信息
│   ├── node_02_fill_publication.py # 节点2: 完善发布信息
│   ├── node_03_match_media.py     # 节点3: 匹配媒体库
│   ├── node_04_match_account.py   # 节点4: 匹配账户信息
│   ├── node_05_calculate_fee.py   # 节点5: 计算费用
│   └── node_06_generate_payment.py # 节点6: 生成付款表
├── workflow.py            # 工作流定义和执行
├── config.py              # 配置管理
├── services/              # 基础服务（Excel、日志、存储）
└── __main__.py            # 命令行入口

tests/
├── test_architecture.py   # 架构测试（14个测试）
└── test_nodes.py          # 节点测试（6个测试）
```

## 🚀 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 运行工作流

```bash
# 命令行方式
python -m workflow run --input ./table/1-链接.xlsx

# 或在代码中使用
from workflow.workflow import run_workflow

context = run_workflow(
    input_file="./table/1-链接.xlsx",
    table_dir="./table"
)

# 检查结果
print(f"处理了 {len(context.records)} 条记录")
print(f"发现 {len(context.issues)} 个问题")

if context.has_critical_errors():
    print("有严重错误")
```

### 3. 运行测试

```bash
pytest tests/ -v
# 20 passed ✅
```

### 4. 启动 MCP 观测服务（远端 / 内网）

工作流每次运行会把节点时间线、issues、脱敏快照写入 SQLite，产物写到 `output/<run_id>/`。
路径由 `workflows.paths.runtime_params()` 自述（数据库、表1/3/4/5、产物目录）。

MCP 与 HTTP 后端**不要共用同一份库**：MCP 进程默认 `runtime-mcp/` + `output-mcp/`，
CLI / 后端默认 `runtime/` + `output/`。也可用环境变量整段挪走：

| 变量 | CLI / HTTP 默认 | MCP 进程默认 |
| --- | --- | --- |
| `WORKFLOW_RUNTIME_DIR` | `runtime/` | `runtime-mcp/` |
| `WORKFLOW_OUTPUT_DIR` | `output/` | `output-mcp/` |
| `WORKFLOW_TABLE_DIR` | `table/` | `table/` |

```bash
uv run workflow-mcp --transport streamable-http --host 0.0.0.0 --port 8100 --path /mcp
```

Agent 侧连接：`http://<host>:8100/mcp`。

| 能力 | 协议方法 | 用途 |
| --- | --- | --- |
| Tools | `tools/call` | 带过滤的查询：`list_runs`、`get_run`、`wait_run`、`get_funnel`、`get_node`、`list_issues`、`summarize_issues`、`list_records`、`get_record`、`list_artifacts`、`describe_artifact`、`get_workflow_schema`；写：`start_run` |
| Resources | `resources/read` | 固定文档：`workflow://schema`、`workflow://runs`、`workflow://runs/{run_id}`、`workflow://runs/{run_id}/nodes/{node_id}` |
| Prompts | `prompts/get` | 用户触发的排错模板：`inspect_run`、`inspect_node`、`explain_record` |

本地调试也可用 stdio：

```bash
uv run workflow-mcp --transport stdio
```

## 🔧 开发指南

### 工作流节点说明

完整的工作流包含7个节点：

1. **Node00Input** - 输入验证
   - 验证输入文件存在且格式正确
   - 验证参考表格文件存在
   - 读取输入Excel并初始化records

2. **Node01FillBasic** - 填写基础信息
   - 解析链接，提取URL
   - 识别平台（知乎、微博、B站等）
   - 按媒体分组，区分主链接和同步链接
   - 检查重复链接

3. **Node02FillPublication** - 完善发布信息
   - 从约稿资料表中匹配标题、发布日期
   - 提取文章类型和截图路径
   - 验证必填字段

4. **Node03MatchMedia** - 匹配媒体库
   - 从媒体库表中匹配媒体等级
   - 获取粉丝数信息
   - 验证媒体信息完整性

5. **Node04MatchAccount** - 匹配账户信息
   - 从账户信息表中匹配付款信息
   - 包括收款方、开户行、账号、联系方式
   - 验证账户信息完整性

6. **Node05CalculateFee** - 计算费用
   - 从费用表中读取费用规则
   - 根据媒体等级和文章类型计算费用
   - 生成约稿明细数据

7. **Node06GeneratePayment** - 生成付款表
   - 按月度、按收款方汇总费用
   - 生成月度汇总表
   - 生成包含3个Sheet的Excel文件：
     - 付款汇总（按收款方）
     - 约稿明细（所有记录）
     - 月度汇总（按月份）

### 添加新节点

```python
from workflow.nodes.base import BaseNode
from workflow.models import WorkflowContext, NodeOutput

class Node02FillPublication(BaseNode):
    def __init__(self):
        super().__init__("node_02", "完善发布信息")
    
    def process(self, context: WorkflowContext) -> NodeOutput:
        # 处理每条记录
        for record in context.records:
            # 提取标题、日期等
            record["title"] = self._extract_title(record)
            record["pub_date"] = self._extract_date(record)
        
        return NodeOutput.create_success(
            processed_count=len(context.records),
            success_count=len(context.records)
        )
```

### 注册到工作流

```python
# workflow.py
from workflow.nodes.node_02_fill_publication import Node02FillPublication

def create_workflow() -> Runnable:
    return (
        Node00Input()
        | Node01FillBasic()
        | Node02FillPublication()  # 添加新节点
        # ... 更多节点
    )
```

## 📊 工作流节点

- ✅ **节点0**: 输入验证 - 验证表1和参考表
- ✅ **节点1**: 填写基础信息 - 解析链接、识别平台、区分主次链接
- ⏳ **节点2**: 完善发布信息 - 提取标题、日期、类型
- ⏳ **节点3**: 匹配媒体库 - 补充媒体级别、粉丝量
- ⏳ **节点4**: 匹配账户信息 - 补充收款信息
- ⏳ **节点5**: 计算费用 - 匹配费用规则，生成明细
- ⏳ **节点6**: 生成付款表 - 月度汇总，输出Excel

## 🎯 设计原则

1. **简单优先** - 用最直接的方式实现功能
2. **状态透明** - 直接修改上下文，不依赖隐式合并
3. **错误继续** - 收集所有问题，不中断流程
4. **易于测试** - 每个节点可独立测试
5. **按需复杂** - 只在需要时引入分支逻辑

## 📝 配置

编辑 `config.yaml`：

```yaml
workflow:
  name: "quotation-fee-workflow"

tables:
  dir: "./table"

storage:
  artifacts_dir: "./output"
  logs_dir: "./logs"

logging:
  level: "INFO"
  format: "json"
```

## 📚 相关文档

- [流程文档](./流程/2.md) - 详细业务流程
- [重构总结](./流程/6-重构总结.md) - 架构演进过程
- [迁移计划](./MIGRATION.md) - 从LangGraph迁移的详细步骤

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

待定
