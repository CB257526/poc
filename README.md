# 约稿费用验收工作流

基于 LangGraph 和 FastAPI 的可复用工作流 POC，用于自动化处理约稿费用验收流程。

## 📋 项目概述

这是一个工作流POC项目，设计为未来平台的可复用组件。工作流处理从链接表到付款表的完整约稿费用验收流程。

### 核心特性

- ✅ **简化架构**: 8个节点（1输入 + 7业务），避免过度抽象
- ✅ **按需读取**: 状态只传路径，节点按需读取表格
- ✅ **错误继续**: 收集所有问题，不中断流程
- ✅ **智能路由**: 条件分支自动判断是否继续执行
- ✅ **状态追踪**: 每个节点的实时状态、输入输出可查询
- ✅ **结构化日志**: 使用 structlog 的 JSON 日志
- ✅ **MCP接口**: HTTP 协议的 MCP 服务器，供外部平台调用
- ✅ **检查点**: LangGraph 内置持久化，支持恢复和查询
- ✅ **增量更新**: 使用Annotated reducer模式，高效状态管理

## 🏗️ 技术栈

- **工作流引擎**: LangGraph（StateGraph + SqliteSaver）
- **Excel处理**: openpyxl
- **日志**: structlog
- **API服务**: FastAPI + Uvicorn
- **数据验证**: Pydantic
- **配置管理**: PyYAML

## 📁 项目结构

```
workflow/
├── src/workflow/
│   ├── __main__.py          # 命令行入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型（TypedDict）
│   ├── graph.py             # LangGraph工作流定义
│   ├── mcp_server.py        # MCP HTTP服务器
│   ├── services/            # 基础服务层
│   │   ├── excel.py         # Excel读写
│   │   ├── logger.py        # 日志配置
│   │   ├── issues.py        # 问题收集器
│   │   └── storage.py       # 文件存储
│   ├── nodes/               # 工作流节点
│   │   ├── base.py          # 节点基类
│   │   ├── node_00_input.py          # 节点0: 输入验证
│   │   ├── node_01_fill_basic.py     # 节点1: 填写基础信息
│   │   └── ...              # 节点2-6（待实现）
│   └── runtime/             # 运行时管理
│       └── workflow_runtime.py
├── table/                   # 表格目录
│   ├── 3-媒体库.xlsx
│   ├── 4-账户信息.xlsx
│   └── 5-费用.xlsx
├── config.yaml              # 配置文件
├── pyproject.toml
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 准备表格

确保 `./table` 目录下有以下必需表格：
- `3-媒体库.xlsx`
- `4-账户信息.xlsx`
- `5-费用.xlsx`

### 3. 运行工作流

```bash
# 方式1: 使用命令行
python -m workflow run --input ./table/1-链接.xlsx

# 方式2: 使用安装的命令
workflow run --input ./table/1-链接.xlsx

# 指定表格目录
workflow run --input /path/to/1-链接.xlsx --table-dir /path/to/table

# JSON格式输出
workflow run --input ./table/1-链接.xlsx --output json
```

### 4. 启动MCP服务器

```bash
# 使用默认配置（0.0.0.0:8000）
python -m workflow serve

# 指定地址和端口
python -m workflow serve --host 127.0.0.1 --port 9000
```

### 5. 调用MCP API

```bash
# 启动工作流
curl -X POST http://localhost:8000/tools/workflow_start \
  -H "Content-Type: application/json" \
  -d '{"input_file": "./table/1-链接.xlsx"}'

# 查询工作流状态
curl http://localhost:8000/tools/workflow_status/<run_id>

# 查询节点状态
curl http://localhost:8000/tools/workflow_node_status/<run_id>/node_00

# 获取问题列表
curl http://localhost:8000/tools/workflow_get_issues/<run_id>

# 列出产物
curl http://localhost:8000/tools/workflow_list_artifacts/<run_id>

# API文档
open http://localhost:8000/docs
```

## 🔧 配置

编辑 `config.yaml` 来自定义配置：

```yaml
workflow:
  name: "quotation-fee-workflow"
  checkpoint_db: "checkpoints.db"

tables:
  dir: "./table"

storage:
  artifacts_dir: "./artifacts"
  logs_dir: "./logs"

logging:
  level: "INFO"
  format: "json"

api:
  host: "0.0.0.0"
  port: 8000
```

## 📊 工作流节点

### 当前实现

- ✅ **节点0**: 输入验证 - 验证表1和参考表
- ✅ **节点1**: 填写基础信息 - 解析链接、识别平台、区分主次链接

### 待实现

- ⏳ **节点2**: 完善发布信息 - 提取标题、日期、类型
- ⏳ **节点3**: 匹配媒体库 - 补充媒体级别、粉丝量
- ⏳ **节点4**: 匹配账户信息 - 补充收款信息
- ⏳ **节点5**: 计算费用 - 匹配费用规则，生成明细
- ⏳ **节点6**: 生成付款表 - 月度汇总，输出Excel

## 🔍 查询运行状态

```bash
# 命令行查询
workflow status <run_id>

# Python API
from workflow.runtime import WorkflowRuntime

runtime = WorkflowRuntime()
status = runtime.get_run_status(run_id)
node_status = runtime.get_node_status(run_id, "node_01")
issues = runtime.get_issues(run_id, level="error")
```

## 📝 日志

日志存储在 `./logs` 目录下：
- 格式: JSON（结构化）
- 文件名: `workflow_YYYYMMDD.log`
- 同时输出到控制台

日志示例：
```json
{
  "event": "node_started",
  "node_id": "node_01",
  "node_name": "填写约稿资料基础信息",
  "run_id": "run_abc123",
  "timestamp": "2026-08-20T10:30:00.123456"
}
```

## 🔌 MCP接口设计

### 核心工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `workflow_start` | `POST /tools/workflow_start` | 启动工作流 |
| `workflow_status` | `GET /tools/workflow_status/{run_id}` | 查询运行状态 |
| `workflow_node_status` | `GET /tools/workflow_node_status/{run_id}/{node_id}` | 查询节点状态 |
| `workflow_get_issues` | `GET /tools/workflow_get_issues/{run_id}` | 获取问题列表 |
| `workflow_list_artifacts` | `GET /tools/workflow_list_artifacts/{run_id}` | 列出产物 |
| `workflow_download_artifact` | `GET /tools/workflow_download_artifact/{run_id}/{artifact_name}` | 下载产物 |

### 特点

- ✅ HTTP协议（不是stdio）
- ✅ RESTful风格
- ✅ 完整的OpenAPI文档（/docs）
- ✅ 适合单独部署为服务

## 🎯 设计原则

### 1. 简单优先
- 使用框架能力，不自研
- 粗粒度业务节点（7个），不过度拆分
- 直接的数据流，避免复杂抽象

### 2. 状态最小化
- 状态只传路径和中间结果
- 表格按需读取，不一次性加载

### 3. 错误不中断
- 收集所有问题，继续执行
- 最后统一报告

### 4. 可观测性
- 每个节点的详细状态
- 结构化日志
- 问题追踪到记录级别

### 5. 平台集成友好
- MCP HTTP接口
- 状态可查询
- 非交互式设计

## 🚧 当前进度

- ✅ 项目架构设计
- ✅ 基础服务层（Excel、日志、存储、问题收集）
- ✅ 数据模型定义
- ✅ 节点基类（Annotated reducer模式）
- ✅ 节点0（输入验证）
- ✅ 节点1（填写基础信息）
- ✅ LangGraph工作流定义（条件路由）
- ✅ 运行时管理器
- ✅ MCP HTTP服务器
- ✅ 命令行工具
- ✅ 基础测试套件
- ✅ 条件路由测试
- ✅ SqliteSaver检查点集成修复
- ✅ 完整工作流测试通过
- ⏳ 节点2-6（待实现）
- ⏳ 完整的业务流程测试

## 🎯 最近改进 (2026-08-20)

### 1. 条件分支路由
- 智能判断是否继续执行：检测critical错误和空记录
- 自动终止流程，避免无意义的后续节点执行
- 完整的单元测试覆盖

### 2. Annotated Reducer模式
- 节点返回增量更新，而不是完整状态拷贝
- LangGraph自动合并issues和metrics
- 更高效的状态管理，减少内存占用

### 3. Critical级别错误
- 新增critical级别（高于error）
- 节点执行异常自动标记为critical
- 条件路由检测critical错误并终止流程

## 📚 相关文档

- [流程文档](./流程/2.md) - 详细业务流程
- [架构设计](./流程/4-架构设计-重构版.md) - 技术架构说明

## 🤝 开发指南

### 添加新节点

1. 在 `src/workflow/nodes/` 创建新文件
2. 继承 `BaseNode` 并实现 `execute` 方法
3. 在 `graph.py` 中注册节点
4. 更新 `nodes/__init__.py`

示例：
```python
from workflow.nodes.base import BaseNode
from workflow.models import WorkflowState, NodeOutput

class Node02FillPublication(BaseNode):
    def __init__(self):
        super().__init__("node_02", "完善发布信息")

    def execute(self, state: WorkflowState) -> NodeOutput:
        # 实现节点逻辑
        return self._create_success_output(
            data={},
            processed_count=0,
            success_count=0
        )
```

## 📄 License

待定

## 👤 作者

待定
