# 约稿费用验收 POC 工作流架构技术书（平台预留版）

版本：v0.2  
定位：当前 POC 可运行闭环 + 面向未来工作流平台的扩展接口  
技术栈：Python 3.14、LangChain、LangGraph、openpyxl、HTTP MCP  
依据资料：流程/1.md、流程/2.md、table 目录下 6 份 Excel 样例  
编写日期：2026-08-19

> 本文档是上一版架构书的修订版。设计重点是先把当前约稿费用验收 POC 做成稳定、可测试、可查询的独立工作流，同时在边界处预留未来平台所需的接口。当前不实现完整的工作流市场、通用 DSL、多租户控制台和复杂调度中心。

## 1. 核心结论

当前 POC 应被实现为一个“可注册的工作流执行单元”，而不是一段只能由命令行启动的脚本。

当前版本只需要完成以下事情：

1. 通过明确的运行请求启动工作流。
2. 使用 LangGraph 执行固定的约稿费用验收流程。
3. 通过统一的节点状态模型查询每个节点。
4. 通过 HTTP MCP 暴露启动、查询、异常和产物接口。
5. 生成约稿、约稿费用合计、6-付款和异常清单。
6. 保存日志、检查点、输入输出引用和计算依据。
7. 保留未来平台接入所需的稳定协议，但不提前实现完整平台。

未来平台只需要知道以下接口：

~~~text
工作流元数据
    -> 输入参数和文件
    -> 启动运行
    -> 查询运行状态
    -> 接收节点事件
    -> 处理 issue
    -> 获取输出产物
~~~

## 2. POC 与未来平台的边界

### 2.1 当前 POC 负责

- 约稿费用验收领域逻辑；
- Excel 输入解析和结果生成；
- 链接清洗、分组、去重和平台识别；
- 页面核验、标题/日期提取和截图归档；
- 媒体库、账户信息、费用规则匹配；
- 约稿明细和月度汇总；
- 付款模板生成；
- LangGraph 编排、检查点和重试；
- HTTP MCP 服务；
- 节点状态和结构化日志。

### 2.2 未来平台负责

- 工作流注册和版本管理；
- 工作流列表、搜索和权限；
- 对话式 Agent；
- 人工运行界面；
- 节点状态可视化；
- 通用任务队列；
- 多工作流编排；
- 多租户和组织权限；
- 统一文件上传和产物预览；
- 统一通知、事件总线和审计中心。

### 2.3 当前不做但必须留接口

| 未来能力 | 当前 POC 做法 | 预留接口 |
|---|---|---|
| 工作流注册 | 固定 WorkflowManifest | manifest 文件或 manifest 接口 |
| 平台统一启动 | HTTP MCP workflow_start | 标准 RunRequest |
| 平台统一状态 | MCP 查询 + 本地事件日志 | NodeEvent 和 RunStatus |
| 平台统一产物 | 本地 artifacts 目录 | ArtifactStore |
| 平台统一异常处理 | issue JSON + 重跑 | IssueResolver |
| 平台统一模型 | LangChain 模型适配器 | ModelProvider |
| 平台统一存储 | SQLite/JSONL | StateStore、EventStore |
| 平台统一调度 | 当前简单 Worker | ExecutionBackend |

原则是：当前实现接口，不实现完整平台。未来只替换适配器，不修改约稿费用领域节点。

## 3. 现有业务和样例事实

### 3.1 业务链路

~~~text
1-链接
  -> 2-约稿资料
  -> 3-媒体库
  -> 4-账户信息
  -> 5-费用
  -> 约稿
  -> 约稿费用合计
  -> 6-付款
~~~

流程/2.md 还要求清洗和拆分原始链接、区分主发布链接和同步平台、补充发布信息、匹配参考表、计算金额并输出异常和归档材料。

### 3.2 Excel 样例审计

| 文件 | 实际结构 | 处理要求 |
|---|---|---|
| 1-链接.xlsx | Sheet1，44 行、2 列；媒体名只在链接组首行出现；存在主题行 | 继承媒体和主题上下文，单元格内拆分 URL |
| 2-约稿资料.xlsx | 约稿、约稿费用合计两个 Sheet；含截图公式、日期序列和长链接 | 支持导入，也能重新生成 |
| 3-媒体库.xlsx | 4 个媒体，含级别、粉丝量、媒体人和主页 | 建立标准媒体记录和别名 |
| 4-账户信息.xlsx | 4 个账户，含户名、身份证、银行卡、电话、开户行 | 敏感字段加密、日志脱敏 |
| 5-费用.xlsx | 等级、视频费用、图文费用 | POC 按等级和约稿类型匹配 |
| 6-付款.xlsx | 固定 4 行模板头，第 5 行起写订单，B/F 列有汇总公式 | 保留模板头、样式、列顺序和公式 |

### 3.3 样例核算基线

| 媒体 | 约稿类型 | 等级 | 单价 | 数量 | 小计 |
|---|---|---|---:|---:|---:|
| Alex Cui | 视频 | FA | 2000 | 1 | 2000 |
| Johnny Durn | 图文 | FB | 800 | 1 | 800 |
| Oxygen | 图文 | FC | 600 | 2 | 1200 |
| 景行 | 图文 | FC | 600 | 2 | 1200 |
| 合计 |  |  |  | 6 | 5200 |

必须满足：

~~~text
有效约稿明细金额 = 月度合计金额 = 付款金额
有效约稿明细数量 = 月度汇总数量
~~~

## 4. 总体架构：POC 优先，边界可替换

### 4.1 当前部署架构

MCP 独立部署为 HTTP 服务。POC 阶段可以把 HTTP MCP 和 LangGraph Worker 放在同一台机器或同一进程，但代码必须分成协议层和执行层。

~~~text
其他平台 / Agent / 人工平台
              |
              | HTTPS + MCP Streamable HTTP
              v
        quotation-mcp-server
              |
              +-- MCP 协议适配层
              +-- 运行请求校验
              +-- 状态和产物查询
              +-- 任务提交
              |
              v
        workflow-runtime
              |
              +-- LangGraph StateGraph
              +-- 领域节点
              +-- Checkpoint
              +-- EventStore
              +-- ArtifactStore
~~~

推荐地址：

~~~text
https://<server-host>/mcp
~~~

### 4.2 当前 POC 到未来平台

| 层 | 当前 POC | 未来替换方向 |
|---|---|---|
| MCP | 独立 HTTP 服务 | 平台统一 MCP 网关或保留独立 MCP |
| 运行 | 简单 Worker | 统一任务队列和 Worker 池 |
| 状态 | SQLite + JSONL | PostgreSQL + 事件总线 |
| 文件 | 本地 artifacts/run_id | MinIO/S3 |
| 页面访问 | 当前服务内 httpx/Playwright | 独立抓取服务 |
| LLM | LangChain 适配器 | 平台统一 ModelProvider |
| UI | 当前不实现 | 平台根据 NodeEvent 展示 |

### 4.3 不提前引入的复杂性

当前不实现通用工作流 DSL、拖拽设计器、多租户数据库、分布式事件总线、复杂 Agent 规划器、工作流市场和真实银行接口。

## 5. 必须现在确定的扩展协议

### 5.1 WorkflowManifest

Manifest 描述工作流名称、版本、输入、输出、能力和入口，不暴露内部节点实现。

~~~json
{
  "workflow_name": "quotation_fee_acceptance",
  "display_name": "约稿费用验收",
  "workflow_version": "0.2.0",
  "runtime": {
    "engine": "langgraph",
    "entrypoint": "workflow.graph:build_graph"
  },
  "transport": {
    "protocol": "mcp",
    "transport": "streamable-http",
    "endpoint": "/mcp"
  },
  "inputs": [
    {"name": "1-链接", "kind": "xlsx", "required": true},
    {"name": "3-媒体库", "kind": "xlsx", "required": true},
    {"name": "4-账户信息", "kind": "xlsx", "required": true},
    {"name": "5-费用", "kind": "xlsx", "required": true},
    {"name": "6-付款模板", "kind": "xlsx", "required": false},
    {"name": "target_month", "kind": "string", "required": true}
  ],
  "outputs": [
    {"name": "约稿.xlsx", "kind": "xlsx"},
    {"name": "约稿费用合计.xlsx", "kind": "xlsx"},
    {"name": "6-付款.xlsx", "kind": "xlsx", "sensitivity": "L3"},
    {"name": "异常清单.xlsx", "kind": "xlsx"},
    {"name": "运行报告.json", "kind": "json"}
  ],
  "capabilities": {
    "supports_resume": true,
    "supports_node_status": true,
    "supports_issue_resolution": true,
    "supports_cancel": true
  }
}
~~~

### 5.2 RunRequest

人和 Agent 将来都提交同一种运行请求。当前 HTTP MCP 直接采用该结构。

~~~json
{
  "idempotency_key": "client-key-001",
  "workflow_name": "quotation_fee_acceptance",
  "workflow_version": "0.2.0",
  "inputs": {
    "1-链接": {"artifact_id": "art_links"},
    "3-媒体库": {"artifact_id": "art_media"},
    "4-账户信息": {"artifact_id": "art_accounts"},
    "5-费用": {"artifact_id": "art_fees"},
    "6-付款模板": {"artifact_id": "art_payment_template"}
  },
  "parameters": {
    "target_month": "2026-02",
    "fetch_pages": true,
    "capture_screenshot": true,
    "exclude_unresolved_from_payment": true
  },
  "request_context": {
    "tenant_id": "demo",
    "actor_id": "business-user",
    "source": "mcp"
  }
}
~~~

### 5.3 RunStatus

~~~json
{
  "run_id": "run_20260819_001",
  "workflow_name": "quotation_fee_acceptance",
  "workflow_version": "0.2.0",
  "status": "running",
  "current_node": "match_media",
  "progress": {
    "total_nodes": 18,
    "completed_nodes": 10,
    "processed_records": 20,
    "issue_count": 2
  },
  "created_at": "2026-08-19T01:23:45Z",
  "updated_at": "2026-08-19T01:25:12Z"
}
~~~

运行状态只保存摘要，不能放身份证、银行卡和完整手机号。

### 5.4 NodeEvent

未来平台的节点状态展示直接消费 NodeEvent。当前 POC 先写入 JSONL，并由 MCP 查询。

~~~json
{
  "event_id": "evt_...",
  "run_id": "run_...",
  "node_id": "match_media",
  "event_type": "progress",
  "status": "running",
  "attempt": 1,
  "progress": {
    "processed": 12,
    "total": 20,
    "succeeded": 10,
    "needs_review": 2,
    "failed": 0
  },
  "input_ref": "art_normalized_...",
  "output_ref": null,
  "trace_id": "trace_...",
  "occurred_at": "2026-08-19T01:25:12Z"
}
~~~

事件类型固定为：

~~~text
run_created
node_started
node_progress
node_succeeded
node_blocked
node_failed
issue_created
artifact_created
run_succeeded
run_needs_review
run_failed
run_cancelled
~~~

### 5.5 ArtifactRef

~~~json
{
  "artifact_id": "art_quote_detail",
  "run_id": "run_...",
  "kind": "xlsx",
  "logical_name": "约稿",
  "filename": "约稿.xlsx",
  "storage_key": "runs/run_.../output/约稿.xlsx",
  "sha256": "sha256:...",
  "size_bytes": 12345,
  "sensitivity": "L1",
  "created_by": "render_artifacts",
  "download_expires_at": "2026-08-20T01:25:12Z"
}
~~~

未来将本地 storage_key 替换成对象存储 Key，不改变 MCP 返回结构。

## 6. LangGraph 工作流设计

### 6.1 主图

~~~mermaid
flowchart TD
    A["start_run"] --> B["ingest_files"]
    B --> C["inspect_and_bind_schema"]
    C --> D["normalize_reference_data"]
    D --> E["parse_and_group_links"]
    E --> F["deduplicate_links"]
    F --> G["classify_primary_and_sync"]
    G --> H["fetch_and_extract_pages"]
    H --> I["validate_publication_evidence"]
    I --> J["match_media"]
    J --> K["match_account"]
    K --> L["match_fee_rule"]
    L --> M["calculate_quote_details"]
    M --> N["build_quote_detail"]
    N --> O["aggregate_monthly"]
    O --> P["validate_payment_rows"]
    P --> Q["render_artifacts"]
    Q --> R["finalize_run"]
~~~

图中不设置等待人工输入的节点。单条记录异常写入 issue，工作流继续处理其他记录；运行结束后通过 succeeded、needs_review 或 failed 表达结果。

### 6.2 子图

| 子图 | 节点 | 可重跑边界 |
|---|---|---|
| ingest | 导入、Schema 识别、参考数据规范化 | 输入文件变更时重跑 |
| evidence | 链接解析、去重、主次链接、页面证据 | 链接或页面策略变更时重跑 |
| enrichment | 媒体、账户、费用匹配 | 参考表或映射修订时重跑 |
| settlement | 计算、明细、汇总、付款校验 | issue 解决后重跑 |
| export | Excel、异常、报告生成 | 模板或导出失败时重跑 |

### 6.3 状态定义

节点状态：pending、running、succeeded、blocked、failed、skipped。

运行状态：

| 状态 | 含义 |
|---|---|
| running | 仍在执行 |
| succeeded | 必需节点成功且无未解决阻断 issue |
| needs_review | 已生成结果，但仍有业务异常，不可直接付款 |
| failed | 运行级失败 |
| cancelled | 外部取消 |

## 7. 节点设计与流程思路

### 7.1 启动和导入

#### start_run

- 输入：RunRequest。
- 输出：run_id、RunContext、初始节点状态。
- 工作：校验工作流版本、输入 artifact、幂等键和目标月份。
- 不使用 LLM。
- 失败：请求无效、幂等键冲突、文件引用不存在。

#### ingest_files

- 使用 openpyxl 读取 xlsx。
- 保存文件 SHA-256、Sheet、行列数、表头、公式和原始单元格引用。
- 原始文件只读保存，输出写入新的运行目录。
- 不使用 LLM。

#### inspect_and_bind_schema

- 根据文件名、Sheet 名、表头、列别名和固定模板头绑定逻辑表。
- 6-付款.xlsx 必须校验前 4 行模板头。
- LLM 只在字段名变化时提供映射候选，最终由 Schema 规则确认。

### 7.2 链接整理

#### normalize_reference_data

- 清洗媒体库、账户信息和费用表。
- 生成带版本号的参考数据快照。
- 账户原始值进入受保护存储，节点只携带引用或脱敏值。
- 费用适配器把当前表转换成“等级 + 约稿类型 -> 单价”。
- 不使用 LLM。

#### parse_and_group_links

处理顺序：

~~~text
读取原始行
  -> 继承最近媒体名称
  -> 识别主题上下文
  -> 从单元格提取所有 http/https URL
  -> 识别域名平台
  -> 保存原文、行号和列号
  -> 生成 LinkRecord
~~~

不使用 LLM。未知域名标记为 unknown，不猜测平台。

#### deduplicate_links

- 生成 canonical_url。
- 处理尾斜杠和无意义追踪参数。
- 保留原始 URL。
- 同组重复可排除；跨媒体重复必须生成高优先级 issue。
- 不使用 LLM。

#### classify_primary_and_sync

主链接判断顺序：

~~~text
已有 2-约稿资料值
  > 业务平台优先级配置
  > 页面证据
  > LLM 候选
~~~

LLM 只输出候选平台、置信度和理由。没有唯一候选时生成 primary_link_ambiguous，不强行选择。

### 7.3 页面证据

#### fetch_and_extract_pages

- httpx 先请求公开页面。
- 必要时使用 Playwright。
- 采集 HTTP 状态、标题、作者、发布日期、页面快照和截图。
- 登录、验证码、403 或超时时，生成 needs_review。
- 页面适配器优先使用 CSS/XPath 规则。
- DOM 规则无法提取时，LLM 根据页面文本摘要提取候选字段。

LLM 输出必须包含：

~~~json
{
  "value": "2026-02-03T10:30:00+08:00",
  "confidence": 0.91,
  "evidence_text": "发表于 2026-02-03",
  "source_ref": "art_html_..."
}
~~~

#### validate_publication_evidence

校验主链接访问、标题、发布日期、截图、作者/账号证据、重复链接和有效发稿状态。LLM 可以帮助归类异常和摘要证据，但最终状态由代码规则决定。

#### 发布形式和约稿类型

已有 2-约稿资料.xlsx 字段优先；缺失时使用平台规则和页面证据，最后才使用 LLM 给候选：

~~~text
发布形式：原创 / 通稿
约稿类型：视频 / 图文
~~~

低置信度字段不进入可付款集合。

### 7.4 参考数据匹配

#### match_media

匹配顺序为媒体 ID、标准媒体名称、主页 URL、已批准别名。0 个匹配或多个冲突匹配生成 issue。不使用 LLM 做最终匹配。

#### match_account

根据媒体 ID 或标准媒体名称匹配账户，校验户名、身份证格式、银行卡格式、手机号格式、开户行和城市。不使用 LLM，不能推断缺失敏感字段。

#### match_fee_rule

POC 规则：

~~~text
费用键 = 媒体级别 + 约稿类型
单条基础金额 = 匹配到的单价
~~~

未来可扩展为媒体级别、发布形式、约稿类型、平台、生效日期和规则版本。规则和版本必须进入计算追踪。不使用 LLM。

### 7.5 结算和导出

#### calculate_quote_details

~~~text
基础金额 = 单价 × 约稿数量
总金额 = 基础金额 + 奖励金额
~~~

使用 Decimal 和 ROUND_HALF_UP，不使用 float。未通过证据、媒体、账户或费用校验的记录不能进入可付款集合。

#### build_quote_detail

- 一篇有效稿件一条明细。
- 同一媒体同月多篇保留多行。
- 每行记录原始链接、标题、发布日期、截图、匹配结果和计算追踪。

#### aggregate_monthly

按“租户 + 目标月份 + media_id + account_id”汇总约稿数量、基础金额、奖励金额和合计费用。一个媒体同月多个账户不能静默合并。

#### validate_payment_rows

付款前检查户名、身份证、银行卡、电话、金额、重复付款、issue、订单数上限和三方金额一致性。不使用 LLM。

#### render_artifacts

生成约稿.xlsx、约稿费用合计.xlsx、6-付款.xlsx、异常清单.xlsx、运行报告.json、规范化 JSON 和审计事件。6-付款模板保留前 4 行、列顺序、样式和公式。

#### finalize_run

~~~text
存在技术失败 -> failed
存在未解决业务 issue -> needs_review
全部通过且对账一致 -> succeeded
~~~

## 8. LLM 使用边界汇总

### 8.1 建议使用 LLM

| 功能 | 使用方式 | 结果约束 |
|---|---|---|
| 表头和字段候选映射 | 识别不同版本字段名 | Schema 规则最终确认 |
| 主链接候选 | 根据平台和页面语义生成候选 | 规则引擎最终选择 |
| 标题提取 | DOM 规则失效时从页面文本提取 | 必须有证据片段 |
| 发布日期提取 | 页面有多个日期时生成候选 | 必须有证据和置信度 |
| 原创/通稿候选 | 从页面内容判断 | 低置信度进入 issue |
| 视频/图文候选 | 结合页面结构判断 | 低置信度进入 issue |
| 证据摘要 | 把技术证据转为业务说明 | 不能改变有效性结果 |
| 异常描述 | 生成可读 issue message | 稳定 issue code 由代码产生 |

### 8.2 禁止 LLM 决定

- 最终媒体匹配；
- 最终账户匹配；
- 身份证、银行卡和电话；
- 费用规则和单价；
- 约稿数量；
- 金额计算；
- 月度汇总；
- 是否进入付款表；
- 最终付款金额；
- 付款模板列值。

### 8.3 LLM 调用规范

- 使用 LangChain ChatModel。
- temperature=0 或等价设置。
- 使用 Pydantic/JSON Schema 结构化输出。
- 提供来源引用、证据文本和置信度。
- 不发送完整 PII。
- 模型不可直接访问文件写入、付款导出和权限工具。
- 限流或解析失败最多重试 2 次，失败后降级为 needs_review。
- 记录模型、提示词版本、Schema 版本、Token 数和耗时。

## 9. 状态、检查点和日志

### 9.1 POC 存储

~~~text
SQLite
  - runs
  - node_status
  - issues
  - checkpoints
  - artifacts

JSONL
  - events.jsonl
  - audit.jsonl
  - logs.jsonl
~~~

未来替换为 PostgreSQL 或事件总线时，保持以下接口不变：

~~~python
class StateStore(Protocol):
    # 中文注释：保存运行摘要和节点最新状态
    def save_run_status(self, status: RunStatus) -> None: ...

    # 中文注释：按运行和节点查询状态，供 MCP 和平台调用
    def get_node_status(self, run_id: str, node_id: str) -> NodeStatus: ...

class EventStore(Protocol):
    # 中文注释：追加不可变事件，保证状态可以重放
    def append(self, event: NodeEvent) -> None: ...

    # 中文注释：按游标读取事件，支持断线后的增量同步
    def read_after(self, run_id: str, cursor: str | None) -> list[NodeEvent]: ...
~~~

### 9.2 节点状态

每个节点至少保存 run_id、node_id、status、attempt、开始和结束时间、progress、输入输出引用、last_error 和 checkpoint_id。

### 9.3 日志字段

每条结构化日志至少包含 timestamp、level、event_type、run_id、node_id、trace_id、span_id、attempt、record_id、input_ref、output_ref、metrics、error_code、code_revision 和 redaction_version。

日志不能包含完整身份证、银行卡、手机号、Cookie、Authorization 和上传文件原文。

### 9.4 敏感字段脱敏

~~~text
身份证：前 3 位 + ********* + 后 4 位
银行卡：前 4 位 + ******** + 后 4 位
手机号：前 3 位 + **** + 后 4 位
~~~

完整敏感值只允许在受保护存储和受权限控制的付款文件生成阶段读取。

## 10. HTTP MCP 设计

### 10.1 传输协议

MCP 使用 Streamable HTTP，独立部署在单独服务器上：

~~~text
https://workflow.example.com/mcp
~~~

不把 stdio 作为远程部署方式。POC 的 MCP Server 可以和 Worker 部署在同一台机器，但 HTTP 接入层和执行层仍应分模块。

### 10.2 MCP 工具

| 工具 | 用途 |
|---|---|
| workflow_manifest | 返回 WorkflowManifest |
| workflow_start | 接收 RunRequest，异步创建 run_id |
| workflow_get_status | 查询运行级状态 |
| workflow_get_node | 查询单节点状态 |
| workflow_get_events | 按 cursor 增量读取 NodeEvent |
| workflow_get_issues | 查询异常和解决 Schema |
| workflow_resolve_issues | 提交结构化 resolution 并创建新 revision |
| workflow_list_artifacts | 查询产物清单 |
| workflow_download_artifact | 获取短期下载 URL 或 binary resource |
| workflow_get_logs | 分页查询脱敏日志 |
| workflow_retry | 重试幂等节点或子图 |
| workflow_cancel | 取消运行 |
| workflow_health | 查询服务和依赖健康状态 |

workflow_start 不同步等待长流程完成，只返回：

~~~json
{
  "run_id": "run_...",
  "status": "running",
  "status_uri": "workflow://runs/run_.../status"
}
~~~

### 10.3 MCP 资源

~~~text
workflow://runs/{run_id}/status
workflow://runs/{run_id}/nodes
workflow://runs/{run_id}/events
workflow://runs/{run_id}/issues
workflow://runs/{run_id}/artifacts
workflow://runs/{run_id}/lineage/{record_id}
workflow://schemas/{workflow_version}
~~~

### 10.4 HTTP 服务要求

- 使用 HTTPS。
- 使用 OAuth2/JWT 或平台 API Key。
- 每个请求携带 tenant_id、actor_id、trace_id。
- 限制请求体大小和文件大小。
- 文件使用 artifact_id，不接受服务器本地路径。
- 普通查询不返回 L3 敏感数据。
- 所有工具调用写审计事件。
- 下载链接使用短期签名并自动过期。

## 11. 异常处理和无交互运行

### 11.1 不在图内等待人工

LangGraph 不设置等待用户填写的节点。运行完成后通过状态表示 succeeded、needs_review 或 failed，人工或 Agent 通过 MCP 查询和解决 issue。

### 11.2 Issue 结构

~~~json
{
  "issue_id": "iss_...",
  "run_id": "run_...",
  "node_id": "classify_primary_and_sync",
  "record_id": "pub_...",
  "code": "primary_link_ambiguous",
  "severity": "high",
  "status": "open",
  "field": "primary_url",
  "candidate_values": ["https://...", "https://..."],
  "evidence_refs": ["art_html_..."],
  "resolution_schema": {
    "type": "object",
    "required": ["primary_url"]
  },
  "message": "同一约稿组存在多个候选主发布链接"
}
~~~

### 11.3 外部处理流程

~~~text
workflow_get_issues
    -> 人或 Agent 提交结构化 resolution
    -> workflow_resolve_issues
    -> 生成新 revision
    -> 重跑受影响子图
    -> 重新对账
    -> 重新生成产物
~~~

不得通过自由文本直接修改金额、银行卡、身份证和付款金额。

## 12. 幂等、重试和一致性

### 12.1 幂等键

~~~text
输入文件 SHA-256
  + 参考数据快照 SHA-256
  + 规范化运行参数
  + workflow_version
~~~

同一 idempotency_key 和同一输入指纹返回原有 run_id；同一 Key 但输入不同则拒绝。

### 12.2 重试

| 类型 | 策略 |
|---|---|
| 磁盘或存储临时错误 | 最多重试 2 次 |
| 页面超时 | 指数退避，最多 2 次 |
| 403、登录、验证码 | 不无限重试，转 needs_review |
| LLM 限流 | 最多重试 2 次，失败转 needs_review |
| Excel 字段缺失 | 不重试，生成 issue |
| 金额对账失败 | 立即 failed，不自动重试 |
| 付款模板头不一致 | 立即 failed，不自动重试 |

### 12.3 一致性校验

~~~text
sum(有效 QuoteDetail.total_amount)
  == sum(MonthlySummary.total_amount)
  == sum(PaymentRow.payable_amount)
~~~

不一致时不得生成可付款状态。

## 13. 安全设计

### 13.1 数据分级

| 等级 | 示例 | 默认访问 |
|---|---|---|
| L0 | 节点状态、计数、耗时 | 可查询 |
| L1 | 媒体名、平台、标题、URL | 业务用户 |
| L2 | 户名、电话、粉丝量 | 掩码后返回 |
| L3 | 身份证、银行卡、付款文件 | finance_export 权限 |

### 13.2 页面访问

- 只允许配置的公开域名；
- 拒绝 localhost、私网地址和非 HTTP(S) URL；
- 限制响应体、跳转次数、执行时间和截图大小；
- 不绕过登录、验证码和付费墙；
- 页面文本作为不可信输入，不允许改变工具权限。

### 13.3 文件安全

- 校验扩展名、MIME、压缩包和大小；
- 原始输入只读保存；
- 输出先写临时文件、校验哈希后原子发布；
- 付款文件单独加密或限制权限；
- 下载链接短期有效。

## 14. 代码模块和扩展接口

推荐当前 POC 目录：

~~~text
src/workflow/
  config.py                  # 中文注释：读取运行配置和环境变量
  manifest.py                # 中文注释：输出 WorkflowManifest
  state.py                   # 中文注释：定义 RunContext、RunStatus、NodeStatus
  graph.py                   # 中文注释：组装 LangGraph 主图
  nodes/
    run.py                   # 中文注释：启动、终结和状态更新
    ingest.py                # 中文注释：Excel 导入和 Schema 绑定
    links.py                 # 中文注释：链接拆分、去重、分组和平台识别
    evidence.py              # 中文注释：页面访问、字段提取和截图
    matching.py              # 中文注释：媒体、账户、费用规则匹配
    settlement.py            # 中文注释：金额计算、明细和汇总
    export.py                # 中文注释：Excel、异常和报告导出
  domain/
    models.py                # 中文注释：领域数据模型和 Schema
    rules.py                 # 中文注释：平台、费用、校验和异常规则
    issues.py                # 中文注释：稳定 issue code 和解决结构
  adapters/
    excel.py                 # 中文注释：Excel 读写和付款模板适配
    browser.py               # 中文注释：HTTP 和浏览器访问适配
    llm.py                   # 中文注释：LangChain 模型调用适配
    storage.py               # 中文注释：文件、状态、事件和检查点存储
  protocols/
    run_request.py           # 中文注释：运行请求和运行结果协议
    events.py                # 中文注释：NodeEvent 协议
    artifacts.py             # 中文注释：ArtifactRef 协议
  mcp_server.py              # 中文注释：HTTP MCP 工具和资源
  worker.py                  # 中文注释：后台运行 LangGraph
tests/
  unit/
  integration/
  contract/
  fixtures/
~~~

### 14.1 适配器接口

~~~python
class ArtifactStore(Protocol):
    # 中文注释：保存输入、截图、Excel 和 JSON，并返回稳定的 ArtifactRef
    def put(self, data: bytes, metadata: ArtifactMetadata) -> ArtifactRef: ...

    # 中文注释：根据 artifact_id 读取文件，屏蔽本地目录和对象存储差异
    def get(self, artifact_id: str) -> BinaryIO: ...

class ModelProvider(Protocol):
    # 中文注释：只提供结构化候选提取，不暴露付款和写文件能力
    def structured_extract(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...

class ExecutionBackend(Protocol):
    # 中文注释：提交工作流并返回 run_id，当前可同步包装为后台任务
    def submit(self, request: RunRequest) -> str: ...

class IssueResolver(Protocol):
    # 中文注释：保存结构化解决方案并创建新的运行版本
    def resolve(self, run_id: str, resolutions: list[IssueResolution]) -> str: ...
~~~

当前可以使用本地实现，未来平台接入时替换实现类。

## 15. 测试策略

### 15.1 单元测试

- 1-链接媒体和主题上下文继承；
- URL 提取、引号清洗、平台识别；
- canonical_url 去重；
- Excel 日期序列和日期文本；
- 媒体精确匹配和冲突匹配；
- 账户格式校验和脱敏；
- FA/FB/FC + 视频/图文费用适配；
- Decimal 金额计算；
- 月度汇总和三方对账；
- 6-付款模板四行头和订单写入；
- NodeEvent 和 ArtifactRef Schema。

### 15.2 样例集成验收

使用 table 目录样例验证：

1. 1-链接.xlsx 解析出 6 个约稿组、4 个唯一媒体。
2. 3-媒体库和 4-账户信息匹配 4 个媒体。
3. 5-费用.xlsx 转换为等级和约稿类型规则。
4. 有效明细金额为 5200。
5. 约稿费用合计金额为 5200。
6. 6-付款.xlsx 生成 4 条付款订单，金额为 5200。
7. 任一付款行可以反查到原始单元格和费用规则。
8. HTTP MCP 可以启动运行、查询节点、查询事件和下载产物。

### 15.3 恢复测试

- 节点执行中进程退出；
- 重新启动 Worker；
- 从 checkpoint 继续；
- 不重复生成付款文件；
- 原有事件和日志完整保留。

### 15.4 MCP 契约测试

- Manifest 可读取；
- RunRequest 校验必填文件和月份；
- 重复幂等 Key 返回原 run_id；
- 普通查询不返回 L3 数据；
- issue resolution 生成新 revision；
- artifact 下载权限正确；
- 事件 cursor 可以增量读取。

## 16. 实施顺序

### 阶段一：确定性业务内核

1. 定义领域模型、RunRequest、RunStatus、NodeEvent、ArtifactRef。
2. 实现 Excel 导入、链接处理、参考数据规范化。
3. 实现媒体、账户、费用匹配。
4. 实现金额、汇总和付款校验。
5. 用样例达到 5200 元基线。

### 阶段二：LangGraph 编排

1. 把业务函数包装为 18 个节点。
2. 加入统一节点状态包装器。
3. 加入 checkpoint、幂等和重试。
4. 输出运行报告和异常清单。

### 阶段三：HTTP MCP

1. 实现 workflow_manifest。
2. 实现 workflow_start 和 workflow_get_status。
3. 实现 workflow_get_node 和 workflow_get_events。
4. 实现 artifact、issue、日志和取消接口。
5. 使用 HTTPS、鉴权和脱敏。

### 阶段四：受控 LLM

1. 增加字段映射候选。
2. 增加主链接和同步平台候选。
3. 增加页面标题和日期 fallback。
4. 建立模型输出评估集。

### 阶段五：未来平台接入

未来平台只需要读取 WorkflowManifest、上传或引用输入 artifact、提交 RunRequest、订阅 NodeEvent 或通过 MCP 查询、展示节点状态和异常、调用 issue resolution、下载 ArtifactRef 对应产物。

不需要修改约稿费用的领域计算节点。

## 17. 后期可能需要改动的部分

| 当前实现 | 未来可能替换为 |
|---|---|
| SQLite 状态库 | PostgreSQL |
| JSONL 事件 | Redis Stream、Kafka 或平台事件总线 |
| 本地文件目录 | MinIO/S3 |
| 单进程 Worker | 任务队列和 Worker 集群 |
| 本地 MCP Server | 平台统一 MCP 网关 |
| 当前配置文件 | 平台工作流注册中心 |
| 简单 NodeEvent 查询 | SSE/WebSocket 实时推送 |
| 单租户配置 | 多租户权限和密钥管理 |

真正不能轻易改变的部分是 RunRequest、RunStatus、NodeEvent、ArtifactRef、Issue、节点 ID、费用计算追踪和三方对账不变量。

## 18. 最终设计判断

当前 POC 最适合采用以下方案：

~~~text
业务逻辑：按当前约稿费用验收场景实现
节点编排：使用 LangGraph
模型调用：使用 LangChain，限制在候选提取和证据理解
对外调用：使用独立 HTTP MCP
运行状态：现在就使用 RunStatus 和 NodeEvent
文件结果：现在就使用 ArtifactRef
异常处理：现在就使用 Issue 和 resolution
存储和调度：先用简单实现，通过 Protocol 预留替换点
~~~

这样当前可以快速完成 POC 并验证业务价值。未来平台接入时，主要替换运行后端、事件存储、产物存储和前端展示，不需要重写约稿费用验收的核心节点。
