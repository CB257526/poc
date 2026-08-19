# 约稿费用验收 POC 工作流架构技术书

> 说明：本文件为 v0.1 历史版本。当前请以同目录下的《3-约稿费用验收POC架构技术书-v2.md》（平台预留版）为准，尤其是 HTTP MCP、运行协议和未来平台扩展接口设计。

版本：v0.1  
适用范围：约稿费用验收 POC、LangChain/LangGraph 工作流、MCP 对外复用  
依据资料：流程/1.md、流程/2.md、table 目录下 6 份 Excel 样例  
编写日期：2026-08-19

## 1. 文档目的

本文档将约稿费用验收 POC 从“人工在多张 Excel 之间复制、查找、核对、计算”的过程，落成一个可运行、可恢复、可审计、可通过 MCP 复用的工作流方案。

本文档解决以下问题：

1. 明确系统边界、技术架构和部署方式。
2. 将业务流程拆成无交互节点的 LangGraph 状态图。
3. 为每个节点定义输入、输出、实时状态、错误、重试和幂等规则。
4. 统一 Excel、标准化领域数据和最终付款文件之间的数据契约。
5. 设计 MCP 工具、资源和查询接口，供其他平台复用。
6. 设计结构化日志、审计、敏感信息保护和运行监控。
7. 给出 POC 到生产化的实施顺序、测试方案和验收标准。

本文档是实现方案，不替代业务方对发布形式、约稿类型、计费口径和最终付款的审核。系统可以自动执行确定性工作，但不应让模型在没有证据的情况下替业务方作出不可逆的付款决定。

## 2. 已读取资料和现状结论

### 2.1 业务链路

当前链路为：

~~~text
1-链接
  -> 2-约稿资料
  -> 3-媒体库补充媒体级别、粉丝量
  -> 4-账户信息补充收款和身份信息
  -> 5-费用匹配基础金额
  -> 约稿单次明细
  -> 约稿费用合计（媒体、月份维度）
  -> 6-付款（银行卡付款模板）
~~~

流程/2.md 还要求对链接进行清洗、拆分、去重、主发布链接与同步平台识别、页面标题/发布日期/截图采集，以及输出异常清单、人工修改记录和归档材料。

### 2.2 样例表格审计

| 文件 | 实际工作表和规模 | 实际字段或结构 | 对架构的影响 |
|---|---|---|---|
| 1-链接.xlsx | Sheet1，44 行、2 列 | A 列在媒体首行或“主题”行出现；B 列包含一条或多条带平台前缀的链接 | 需要按组继承媒体和主题，不能按单行直接解析 |
| 2-约稿资料.xlsx | 约稿 9 行×23 列；约稿费用合计 8 行×14 列 | 已经包含两个中间结果工作表，含截图公式、Excel 日期序列、同步平台长文本 | 既要支持导入现有结果，也要重新生成规范结果 |
| 3-媒体库.xlsx | Sheet1，5 行×18 列 | 媒体名称、级别、粉丝量、媒体人、平台主页、身份证号等 | 媒体名称不能作为唯一主键，需建立规范媒体 ID 和别名映射 |
| 4-账户信息.xlsx | Sheet1，5 行×13 列 | 媒体、户名、身份证号、银行卡、电话、开户行和城市 | 含身份证、银行卡、电话等敏感字段，日志和 MCP 返回必须脱敏 |
| 5-费用.xlsx | Sheet1，4 行×3 列 | 等级、视频费用、图文费用；没有发布形式、平台、版本、生效日期 | POC 采用兼容适配器；生产模型预留扩展维度 |
| 6-付款.xlsx | 上传模板，9423 行×8 列 | 前 4 行为固定模板头，第 5 行起写付款订单，B/F 列参与汇总公式 | 生成时必须保留模板头、公式和列顺序，不可把业务字段直接写入模板 |

### 2.3 样例数据中的重要事实和风险

1. 1-链接.xlsx 的媒体名称只出现在每个链接组的第一行，后续行需要继承最近的有效媒体名称；“主题1”和“主题2”不是媒体名称，应作为批次或主题上下文。
2. 单元格中存在中文平台前缀、换行、首尾引号、短链后的分享口令和额外描述，链接解析必须先提取 URL，再保留原文。
3. 同一媒体可以有多条约稿记录。例如 Oxygen 和景行在样例中各有两条明细，必须保留明细，之后再汇总。
4. 2-约稿资料.xlsx 的截图字段是 _xlfn.DISPIMG 公式，不应把公式字符串当作可审计截图；系统需要将截图保存为独立产物并记录哈希。
5. Excel 日期可能以序列号保存，账户生日还存在“11月1日”这种不含年份的文本，日期规范化必须保留原值和解析置信度。
6. 5-费用.xlsx 当前只按等级和约稿类型给价，流程文档中提到的发布形式、平台、规则版本和生效日期属于未来扩展维度，不能假定当前文件已经具备这些列。
7. 6-付款.xlsx 的模板说明要求单个批次最多 10000 条订单，金额列按元、四舍五入至分，且批次号需要和文件名一致。
8. 账户信息属于高敏感数据。原始文件、工作流状态、日志和 MCP 响应必须分层授权和脱敏。

### 2.4 样例的核算基线

按样例中的明细金额：

| 媒体 | 明细 | 单价 | 数量 | 小计 |
|---|---:|---:|---:|---:|
| Alex Cui | 视频、FA | 2000 | 1 | 2000 |
| Johnny Durn | 图文、FB | 800 | 1 | 800 |
| Oxygen | 图文、FC | 600 | 2 | 1200 |
| 景行 | 图文、FC | 600 | 2 | 1200 |
| 合计 |  |  | 6 | 5200 |

工作流必须通过以下不变量：

~~~text
有效明细金额之和 = 约稿费用合计金额之和 = 付款订单金额之和
有效明细数量之和 = 汇总数量之和 = 付款订单对应的有效约稿数量
~~~

任何不满足不变量的运行，均不得生成“可付款”状态的结果。

## 3. 目标、非目标和设计原则

### 3.1 目标

- 一次运行接收 1-链接、3-媒体库、4-账户信息、5-费用和可选的 2-约稿资料/6-付款模板。
- 自动清洗和标准化 Excel，保留每个字段的来源位置和转换记录。
- 对链接进行解析、去重、分组、平台识别、页面核验和截图归档。
- 使用媒体库、账户信息和费用规则完成匹配与确定性计算。
- 自动生成约稿、约稿费用合计和 6-付款三个结果产物。
- 每个节点均可查询 pending/running/succeeded/failed/blocked/skipped、输入摘要、输出摘要、耗时、错误和重试次数。
- 工作流可以从检查点恢复，可以按节点重试，可以基于幂等键避免重复付款文件。
- 以 MCP 工具和资源暴露启动、查询、异常处理、产物下载和日志检索能力。

### 3.2 非目标

- POC 阶段不直接调用银行或付款接口，不自动发起真实付款。
- 不使用 LLM 直接决定金额、银行卡、身份证号或是否付款。
- 不要求工作流绕过登录、验证码或页面访问控制。
- 不把 Excel 作为长期业务数据库；Excel 是输入/输出格式，规范化数据进入可查询存储。
- 不在 LangGraph 节点中嵌入聊天式人工确认。人工处理以外部异常解决接口完成。

### 3.3 设计原则

1. 确定性优先：字段清洗、匹配、金额计算、汇总和付款校验使用普通 Python 代码。
2. 模型受约束：LLM 只处理页面内容理解、平台/标题/日期候选提取和异常原因归类，所有输出使用结构化 Schema，并保留证据。
3. 证据优先：每个关键字段都能回溯到源文件单元格、页面快照、规则版本或人工修订。
4. 失败可见：单条记录异常不应吞掉；记录进入 issue 清单，节点仍可处理其他独立记录。
5. 结果分级：同时输出完整结果和可付款结果；有未解决异常时，完整结果可供复核，但付款结果必须排除不合格记录。
6. 无交互节点：图内没有等待用户输入的节点，运行一次后得到 succeeded/needs_review/failed；外部平台使用查询和解决接口推进后续运行。
7. 版本固定：工作流版本、提示词版本、规则版本、源文件哈希和代码版本必须随运行归档。

## 4. 总体技术架构

### 4.1 逻辑架构

~~~mermaid
flowchart LR
    A["MCP 客户端/其他平台"] --> B["MCP Server"]
    B --> C["运行编排服务"]
    C --> D["LangGraph StateGraph"]
    D --> E["文件导入与规范化"]
    D --> F["链接核验与页面提取"]
    D --> G["媒体/账户/费用匹配"]
    D --> H["金额计算与汇总"]
    D --> I["Excel 结果渲染"]
    C --> J["检查点与状态库"]
    C --> K["结构化日志与审计库"]
    D --> L["对象存储/本地产物目录"]
    F --> M["HTTP 页面访问/浏览器截图"]
    G --> N["参考数据快照"]
    I --> L
    J --> B
    K --> B
    L --> B
~~~

### 4.2 组件职责

| 组件 | POC 推荐实现 | 生产演进方向 |
|---|---|---|
| 工作流运行时 | Python 3.14、LangGraph StateGraph | 保持 LangGraph，使用任务队列扩展并发 |
| LLM 调用 | LangChain ChatModel + 结构化输出 | OpenAI/兼容模型，可按节点配置模型 |
| 检查点 | SQLite checkpointer | PostgreSQL checkpointer，按 run_id、node_id 索引 |
| 规范化数据 | SQLite/SQLModel 或 JSONL | PostgreSQL，敏感字段独立加密列 |
| 产物存储 | 工作区 artifacts/run_id | S3/MinIO，版本化和生命周期管理 |
| 页面抓取 | httpx，必要时 Playwright | 独立浏览器服务，域名白名单和限流 |
| MCP 传输 | stdio | Streamable HTTP；需要时保留 stdio |
| 日志 | JSONL + Python logging | OpenTelemetry + 日志平台 + 指标系统 |
| Excel 读写 | openpyxl，模板渲染器 | openpyxl 结合对象存储和异步导出 |
| 服务接口 | MCP 为主，可附带 FastAPI 健康检查 | MCP 网关、鉴权、租户隔离和审计 |

### 4.3 推荐运行模式

POC 本地模式：

~~~text
MCP 客户端 --stdio--> workflow_mcp_server
                                  |
                                  +-- LangGraph
                                  +-- SQLite
                                  +-- ./artifacts/<run_id>/
~~~

共享服务模式：

~~~text
MCP 客户端 --Streamable HTTP--> MCP 网关
                                  |
                                  +-- 运行服务/任务队列
                                  +-- PostgreSQL
                                  +-- MinIO/S3
                                  +-- 浏览器抓取服务
~~~

共享服务下客户端只拿到 run_id、脱敏状态和 artifact_id，不直接获得服务器本地路径。

## 5. 工作流状态图设计

### 5.1 图级流程

~~~mermaid
flowchart TD
    S["start_run"] --> A["ingest_files"]
    A --> B["inspect_and_bind_schema"]
    B --> C["normalize_reference_data"]
    C --> D["parse_and_group_links"]
    D --> E["deduplicate_links"]
    E --> F["classify_primary_and_sync"]
    F --> G["fetch_and_extract_pages"]
    G --> H["validate_publication_evidence"]
    H --> I["match_media"]
    I --> J["match_account"]
    J --> K["match_fee_rule"]
    K --> L["calculate_quote_details"]
    L --> M["build_quote_detail"]
    M --> N["aggregate_monthly"]
    N --> O["validate_payment_rows"]
    O --> P["render_artifacts"]
    P --> Q["finalize_run"]
    Q --> E1["end"]
    Q --> E2["end_needs_review"]
    Q --> E3["end_failed"]
~~~

每个节点返回统一的 NodeResult，并通过状态写入器记录实时状态。节点内的单条记录异常不会使整个图立即中断；只有文件不可读、Schema 无法识别、规则快照缺失、产物写入失败等运行级错误才走 end_failed。

### 5.2 子图划分

| 子图 | 包含节点 | 输出 |
|---|---|---|
| ingest_subgraph | start_run、ingest_files、inspect_and_bind_schema | 规范化文件和字段绑定 |
| evidence_subgraph | parse_and_group_links、deduplicate_links、classify_primary_and_sync、fetch_and_extract_pages、validate_publication_evidence | 链接、页面证据和发稿核验状态 |
| enrichment_subgraph | normalize_reference_data、match_media、match_account、match_fee_rule | 媒体、账户、费用规则匹配结果 |
| settlement_subgraph | calculate_quote_details、build_quote_detail、aggregate_monthly、validate_payment_rows | 约稿明细、月度合计和付款行 |
| export_subgraph | render_artifacts、finalize_run | Excel、JSON、异常和审计产物 |

子图是代码和状态管理边界，不是人工交互边界。

### 5.3 状态值

| 状态 | 含义 | 是否终态 |
|---|---|---|
| pending | 已入图但尚未执行 | 否 |
| running | 正在执行 | 否 |
| succeeded | 节点完成，输出满足节点契约 | 是 |
| failed | 节点级不可恢复错误，或重试耗尽 | 是 |
| blocked | 由于输入异常无法继续，但不等待图内交互 | 是 |
| skipped | 根据分支或配置跳过 | 是 |

运行级 result_status：

| 值 | 含义 |
|---|---|
| running | 仍在执行 |
| succeeded | 所有必需节点成功且无未解决阻断异常 |
| needs_review | 工作流完成但有待处理 issue；可下载复核产物，不可标记为可付款 |
| failed | 运行级错误或必需产物生成失败 |
| cancelled | 由外部取消 |

## 6. 统一数据契约

### 6.1 RunContext

~~~json
{
  "run_id": "run_20260819_01H...",
  "idempotency_key": "sha256:...",
  "workflow_name": "quotation_fee_acceptance",
  "workflow_version": "0.1.0",
  "code_revision": "git:...",
  "requester": {
    "tenant_id": "demo",
    "actor_id": "mcp-client",
    "role": "business"
  },
  "source_files": [
    {
      "artifact_id": "art_input_links",
      "logical_name": "1-链接",
      "filename": "1-链接.xlsx",
      "sha256": "sha256:...",
      "size_bytes": 12345
    }
  ],
  "reference_snapshot_ids": {
    "media": "media_snapshot_...",
    "accounts": "account_snapshot_...",
    "fees": "fee_snapshot_..."
  },
  "config": {
    "target_month": "2026-02",
    "fetch_pages": true,
    "capture_screenshot": true,
    "exclude_unresolved_from_payment": true
  }
}
~~~

### 6.2 记录级通用字段

所有领域记录包含 record_id、run_id、source_refs、lineage、status、issues、created_at 和 updated_at。完整原文保存在 artifact，状态只保存可查询摘要。

### 6.3 LinkRecord

~~~json
{
  "record_id": "linkrec_...",
  "group_id": "group_topic1_alex",
  "media_raw": "Alex Cui",
  "media_name_candidate": "Alex Cui",
  "topic": "主题1",
  "raw_text": "知乎： https://www.zhihu.com/...",
  "url": "https://www.zhihu.com/...",
  "canonical_url": "https://www.zhihu.com/...",
  "platform": "知乎",
  "platform_confidence": 0.99,
  "is_primary": true,
  "link_role": "primary",
  "http_status": 200,
  "content_hash": "sha256:...",
  "duplicate_of": null,
  "source_ref": {
    "artifact_id": "art_input_links",
    "sheet": "Sheet1",
    "row": 7,
    "column": "B"
  }
}
~~~

### 6.4 PublicationRecord

~~~json
{
  "record_id": "pub_...",
  "group_id": "group_topic1_alex",
  "media_name": "Alex Cui",
  "primary_url": "https://www.zhihu.com/zvideo/...",
  "sync_links": [
    {
      "platform": "微信视频号",
      "url": "https://weixin.qq.com/...",
      "canonical_url": "https://weixin.qq.com/..."
    }
  ],
  "platform": "知乎",
  "publication_form": "原创",
  "quotation_type": "视频",
  "title": "...",
  "published_at": "2026-02-...",
  "submitted_at": null,
  "screenshot_artifact_id": "art_screenshot_...",
  "evidence": {
    "title_source": "page_meta",
    "date_source": "page_dom",
    "author_source": "page_dom",
    "page_snapshot_artifact_id": "art_html_...",
    "confidence": 0.93
  },
  "publication_status": "valid"
}
~~~

### 6.5 MediaProfile、AccountProfile、FeeRule

MediaProfile 至少包含 media_id、media_name、aliases、level、fans、contact_name、phone 和 source_snapshot_id。

AccountProfile 的原始值只在受保护存储中保存，工作流内部使用引用：

~~~json
{
  "account_id": "acct_...",
  "media_id": "media_...",
  "holder_name": "崔诚靓",
  "id_number_ref": "secret://account/.../id",
  "bank_account_ref": "secret://account/.../card",
  "phone_ref": "secret://account/.../phone",
  "bank_name": "中国农业银行 上海翔殷路支行",
  "bank_city": "上海",
  "match_status": "matched"
}
~~~

FeeRule 同时支持当前 POC 和扩展规则：

~~~json
{
  "fee_rule_id": "fee_...",
  "level": "FC",
  "quotation_type": "图文",
  "publication_form": null,
  "platform": null,
  "unit_price": 600.0,
  "reward_price": 0.0,
  "currency": "CNY",
  "effective_from": null,
  "effective_to": null,
  "rule_version": "poc-2026-08",
  "source_snapshot_id": "fee_snapshot_..."
}
~~~

### 6.6 QuoteDetail、MonthlySummary、PaymentRow

~~~json
{
  "quote_id": "quote_...",
  "publication_record_id": "pub_...",
  "media_id": "media_...",
  "target_month": "2026-02",
  "quantity": 1,
  "unit_base_amount": 600.0,
  "base_amount": 600.0,
  "reward_amount": 0.0,
  "total_amount": 600.0,
  "fee_rule_id": "fee_...",
  "settlement_eligible": true,
  "calculation_trace": {
    "formula": "unit_base_amount * quantity + reward_amount",
    "rounding": "HALF_UP_2",
    "inputs": ["fee_...", "quantity=1"]
  }
}
~~~

MonthlySummary 的分组键固定为 tenant_id + target_month + media_id + account_id。同一媒体同月出现多个账户时，不能静默合并，必须生成 account_conflict issue。

PaymentRow 到 6-付款模板的映射：

| PaymentRow | 6-付款.xlsx |
|---|---|
| batch_no | 第 3 行 A 列，且与文件名一致 |
| bank_account | 第 5 行起 B 列 |
| holder_name | 第 5 行起 C 列 |
| id_number | 第 5 行起 D 列 |
| phone | 第 5 行起 E 列 |
| payable_amount | 第 5 行起 F 列 |
| remark | 第 5 行起 G 列 |

## 7. 节点详细设计

以下节点名称作为稳定的 node_id，写入状态、日志、检查点和审计记录。节点实现必须保持输入输出契约兼容。

### 7.1 start_run

| 项目 | 设计 |
|---|---|
| 目的 | 创建 run_id、校验幂等键、锁定工作流和规则版本 |
| 输入 | requester、输入 artifact_id、配置、idempotency_key |
| 输出 | RunContext、初始 NodeStatus |
| 确定性 | 100% 代码 |
| 失败条件 | 缺少必填输入、幂等键冲突且参数不同、版本不存在 |
| 重试 | 不重试；修正请求后新建运行 |
| 幂等 | 输入文件哈希 + 参考快照哈希 + 配置规范化 JSON 哈希 |

### 7.2 ingest_files

| 项目 | 设计 |
|---|---|
| 目的 | 读取 xlsx，扫描 Sheet、尺寸、表头、公式、空行和文件元数据 |
| 输入 | RunContext、输入文件 |
| 输出 | RawWorkbook、WorkbookProfile、source_file 记录 |
| 确定性 | 100% 代码 |
| 失败条件 | 文件损坏、非 xlsx、大小超过限制、恶意压缩包、无法读取 |
| 重试 | 磁盘/对象存储临时错误可重试 2 次；文件错误不重试 |
| 指标 | files_total、files_ok、files_failed、bytes_read |

读取时同时保存 data_only=False 和 data_only=True 视图，防止把公式和公式计算值混淆。原始文件采用只读访问，规范化结果写入新的运行目录。

### 7.3 inspect_and_bind_schema

| 项目 | 设计 |
|---|---|
| 目的 | 将实际 Sheet 和列绑定到逻辑表，记录字段映射和置信度 |
| 输入 | WorkbookProfile、表模板注册表 |
| 输出 | SchemaBinding、字段缺失/多余 issue |
| 确定性 | 代码优先，必要时 LLM 仅给候选映射 |
| 关键规则 | 表名、固定表头、别名和列位置联合识别；不得只按文件名识别 |
| 阻断条件 | 核心表无法绑定、付款模板头被修改 |
| 重试 | 不盲目重试；改用模板配置或补充文件 |

模板注册表保存逻辑表名、允许的 Sheet 名、列别名、类型、是否必填、敏感等级、版本和兼容策略。

### 7.4 normalize_reference_data

| 项目 | 设计 |
|---|---|
| 目的 | 规范化媒体库、账户信息和费用表，生成引用快照 |
| 输入 | 3-媒体库、4-账户信息、5-费用 |
| 输出 | MediaProfile、AccountProfile、FeeRule、快照哈希 |
| 关键规则 | 去除首尾空格，保留原值；身份证/银行卡/电话只做格式校验；金额使用 Decimal |
| POC 费用适配 | 将视频费用、图文费用转换为 quotation_type 维度，publication_form/platform 为空 |
| 阻断条件 | 费用等级重复且单价冲突；同媒体同账户键对应多个不一致账户 |
| 重试 | 不重试，数据问题转 issue |

### 7.5 parse_and_group_links

| 项目 | 设计 |
|---|---|
| 目的 | 将 1-链接.xlsx 转为一条 URL 一个 LinkRecord，并继承媒体、主题和批次上下文 |
| 输入 | 原始 Sheet 行 |
| 输出 | LinkRecord 列表、分组统计 |
| 关键规则 | 识别 http/https URL；删除首尾引号；去除分享口令污染；保留 raw_text；媒体名沿组继承 |
| 平台识别 | URL 域名注册表优先；未知域名标记 unknown，不猜测 |
| 阻断条件 | 有 URL 但没有可继承媒体上下文 |
| 重试 | 不重试 |

平台注册表至少覆盖知乎、微博、微信/视频号、B 站、抖音、小红书、易车、懂车帝、百家号、头条、搜狐、汽车之家。

### 7.6 deduplicate_links

| 项目 | 设计 |
|---|---|
| 目的 | 识别同组重复、跨组重复和规范化 URL 重复 |
| 输入 | LinkRecord |
| 输出 | duplicate_of、dedup_group_id、去重统计 |
| 规范化 | 小写域名、移除无意义尾斜杠、按平台规则处理追踪参数；原 URL 永久保留 |
| 规则 | 同一 canonical_url 默认只保留一条；跨媒体重复不自动删除，生成高优先级 issue |
| 重试 | 不重试 |

### 7.7 classify_primary_and_sync

| 项目 | 设计 |
|---|---|
| 目的 | 为每个约稿组选择一个主发布链接，其余链接作为同步链接 |
| 输入 | LinkRecord 分组、平台优先级配置、可选 LLM 候选 |
| 输出 | primary_url、sync_links、classification_reason |
| 确定性规则 | 业务配置的主平台优先级 > 2-约稿资料已有值 > 页面证据 > LLM 候选 |
| 低置信度 | 没有唯一主链接时，保留所有候选并生成 primary_link_ambiguous issue |
| 重试 | 规则读取错误可重试；分类结果不因重试改变 |

LLM 输出只允许为候选列表和理由，最终选择由规则引擎完成。流程图不暂停等待人工。

### 7.8 fetch_and_extract_pages

| 项目 | 设计 |
|---|---|
| 目的 | 访问主发布链接，提取标题、平台、作者、发布日期并生成页面快照/截图 |
| 输入 | PublicationRecord |
| 输出 | PageEvidence、截图 artifact_id、HTTP/浏览器指标 |
| 访问策略 | httpx 先请求；需要 JavaScript 时再进入受控 Playwright；每个域名限流 |
| LLM 范围 | 页面文本已获取但 DOM 规则无法解析时，结构化提取标题/日期候选并返回证据片段 |
| 阻断条件 | 登录/验证码、禁止访问、页面持续失败；生成 needs_review 而不是伪造字段 |
| 重试 | 网络超时 2 次指数退避；403/验证码不超过 1 次 |

截图命名包含 run_id、publication_record_id 和页面哈希，PNG/JPEG 作为独立 artifact。截图不可只保存在模型上下文。

### 7.9 validate_publication_evidence

| 项目 | 设计 |
|---|---|
| 目的 | 校验链接、标题、截图、发布日期和约稿类型是否足以证明有效发稿 |
| 输入 | PublicationRecord、PageEvidence、配置 |
| 输出 | publication_status、evidence_score、issues |
| 校验 | 主链接可访问、标题非空、发布日期可解析、截图存在或明确缺失原因、重复链接未计费 |
| 结果 | valid、needs_review、invalid、excluded |
| 重试 | 纯校验不重试 |

发布时间必须区分 published_at、submitted_at、source_submitted_at。无法识别年份的日期不能直接当作结算月份。

### 7.10 match_media

| 项目 | 设计 |
|---|---|
| 目的 | 使用媒体 ID、标准名称、主页 URL 和已确认别名匹配媒体库 |
| 输入 | PublicationRecord、MediaProfile 快照 |
| 输出 | media_id、级别、粉丝量、match_method、match_confidence |
| 优先级 | media_id > exact name > canonical profile URL > approved alias；禁止无证据模糊匹配 |
| 阻断条件 | 0 个匹配、多个冲突匹配、媒体库字段缺失 |
| 重试 | 不重试；修改别名映射后重跑匹配子图 |

### 7.11 match_account

| 项目 | 设计 |
|---|---|
| 目的 | 为媒体匹配唯一有效收款账户 |
| 输入 | media_id、媒体名、AccountProfile 快照 |
| 输出 | account_id、受保护字段引用、脱敏摘要、match_status |
| 校验 | 户名、身份证号格式、银行卡格式、电话格式、开户行城市完整性 |
| 阻断条件 | 无账户、多账户冲突、账户失效、关键字段缺失 |
| 重试 | 不重试 |

MCP 默认只返回 6228********6271 形式的掩码。只有具备付款导出权限的服务端任务可以解密并写入 6-付款文件。

### 7.12 match_fee_rule

| 项目 | 设计 |
|---|---|
| 目的 | 根据媒体级别、约稿类型、发布形式、平台和生效日期匹配唯一费用规则 |
| 输入 | PublicationRecord、MediaProfile、FeeRule 快照 |
| 输出 | fee_rule_id、unit_base_amount、unit_reward_amount、match_status |
| POC 兼容 | 当前 5-费用.xlsx 映射为 level + quotation_type；缺失维度按 null 参与键 |
| 阻断条件 | 无规则、多规则价格冲突、日期不在有效期、数量非法 |
| 重试 | 不重试 |

费用匹配键必须写入 calculation_trace，保证财务可以复算。

### 7.13 calculate_quote_details

| 项目 | 设计 |
|---|---|
| 目的 | 为每条有效稿件计算单价、基础金额、奖励金额和总金额 |
| 输入 | PublicationRecord、FeeRule、quantity |
| 输出 | QuoteDetail |
| 公式 | base_amount = unit_base_amount × quantity；total_amount = base_amount + reward_amount |
| 精度 | Decimal 计算，最终金额以元保留 2 位，ROUND_HALF_UP |
| 保护 | 未通过发稿核验、媒体匹配、账户匹配或费用匹配的记录不可进入可付款集合 |
| 重试 | 不重试；同一输入必须得到相同结果 |

### 7.14 build_quote_detail

| 项目 | 设计 |
|---|---|
| 目的 | 生成约稿明细表结构，合并业务字段、证据字段、匹配字段和计算字段 |
| 输入 | QuoteDetail、PublicationRecord、MediaProfile、AccountProfile |
| 输出 | 约稿明细数据集、列级 lineage |
| 规则 | 一篇有效稿件一条明细；同一媒体同月多篇不合并；无效或重复记录进入 excluded/异常区域 |
| 校验 | 明细数量、单价和金额均非负；每行必须有 quote_id |
| 重试 | 可从检查点重试 |

### 7.15 aggregate_monthly

| 项目 | 设计 |
|---|---|
| 目的 | 按 target_month + media_id + account_id 汇总约稿数量和金额 |
| 输入 | 约稿明细 |
| 输出 | 约稿费用合计 |
| 公式 | summary_base = sum(base_amount)；summary_reward = sum(reward_amount)；summary_total = sum(total_amount) |
| 规则 | 账户冲突不可静默合并；月份缺失的记录进入 issue |
| 校验 | 汇总与明细逐组对账，合计必须一致 |
| 重试 | 可从检查点重试 |

### 7.16 validate_payment_rows

| 项目 | 设计 |
|---|---|
| 目的 | 将汇总数据转为付款行并执行付款前最后校验 |
| 输入 | MonthlySummary、账户受保护引用、业务复核结果 |
| 输出 | PaymentRow、payment_eligible、付款校验报告 |
| 校验 | 户名/身份证/账号/电话完整；金额 > 0；同批次账户是否重复；不超过模板 10000 行；金额合计一致 |
| 规则 | exclude_unresolved_from_payment=true 时，未解决 issue 的行不进入 PaymentRow |
| 重试 | 不重试；修复数据后重跑该子图 |

### 7.17 render_artifacts

| 项目 | 设计 |
|---|---|
| 目的 | 渲染规范 JSON、异常清单、约稿.xlsx、约稿费用合计.xlsx 和 6-付款.xlsx |
| 输入 | QuoteDetail、MonthlySummary、PaymentRow、模板文件 |
| 输出 | ArtifactManifest、sha256、文件大小和行数 |
| Excel 规则 | 保留 6-付款模板前 4 行、列顺序、样式和公式；仅填充第 5 行起的订单 |
| 安全 | 输出文件权限最小化，敏感文件单独标记 protected |
| 重试 | 临时文件校验哈希后原子提交；写入失败可重试 2 次 |

推荐产物：

~~~text
artifacts/<run_id>/
  input/
  normalized/
  evidence/
  output/约稿.xlsx
  output/约稿费用合计.xlsx
  output/6-付款.xlsx
  output/异常清单.xlsx
  output/运行报告.json
  audit/events.jsonl
~~~

### 7.18 finalize_run

| 项目 | 设计 |
|---|---|
| 目的 | 汇总节点状态、统计、issue、产物和最终运行状态 |
| 输入 | 全部 NodeResult、ArtifactManifest |
| 输出 | RunSummary |
| 结果规则 | 必需节点失败 -> failed；节点完成但 unresolved issue > 0 -> needs_review；全量通过 -> succeeded |
| 关键校验 | 明细/汇总/付款金额和数量不变量；产物哈希；审计事件完整性 |
| 重试 | 不重试 |

## 8. 无交互设计和异常闭环

### 8.1 为什么不在图内加入人工节点

MCP 调用者可能是后台平台、定时任务或另一个 Agent，不一定能处理 LangGraph 的中断与表单输入。将人工交互放进图内会导致调用方必须理解图的暂停协议、运行长期占用连接，且重试时容易重复执行前置步骤。因此工作流只负责自动处理和输出异常，人工处理通过外部查询/命令接口完成。

### 8.2 Issue 数据结构

~~~json
{
  "issue_id": "iss_...",
  "run_id": "run_...",
  "record_id": "pub_...",
  "node_id": "classify_primary_and_sync",
  "code": "primary_link_ambiguous",
  "severity": "high",
  "status": "open",
  "field": "primary_url",
  "candidate_values": ["https://...", "https://..."],
  "evidence_refs": ["art_html_..."],
  "message": "同一约稿组存在多个候选主发布链接",
  "resolution_schema": {
    "type": "object",
    "required": ["primary_url"]
  },
  "created_at": "2026-08-19T01:23:45Z",
  "resolved_at": null,
  "resolved_by": null
}
~~~

### 8.3 异常分级

| 级别 | 示例 | 自动处理 |
|---|---|---|
| info | 发现额外空列、非关键字段被忽略 | 记录并继续 |
| warning | 页面标题来自 meta、账户字段存在空格 | 记录并继续 |
| high | 主链接不唯一、媒体多匹配、费用规则冲突 | 记录，相关行不进入付款 |
| critical | 文件损坏、付款模板被改写、金额对账失败 | 运行失败，不生成可付款产物 |

### 8.4 外部异常解决

MCP 客户端先调用 workflow_get_issues 获取 issue，再调用 workflow_resolve_issues 提交结构化 resolution。解决后有两种模式：

1. 重跑模式：原始输入 + resolution snapshot 重新执行受影响子图，生成新 revision。
2. 只修订模式：只允许修订白名单字段，重新执行校验、计算、汇总和导出；所有修改写入 audit_event。

POC 推荐重跑模式，逻辑简单、可审计。系统不允许通过自由文本修改金额或账户字段。

## 9. LangChain 与 LangGraph 实现约束

### 9.1 StateGraph 状态建议

Python 实现时，建议使用 TypedDict 或 Pydantic 模型定义状态。状态只保存可序列化的引用和摘要，大文件、截图和原始工作簿写入 artifact store。

~~~python
class WorkflowState(TypedDict):
    # 中文注释：运行身份和版本，用于幂等、追踪和重放
    run: RunContext
    # 中文注释：按节点保存最新状态，查询接口直接读取该字段的投影
    node_status: dict[str, NodeStatus]
    # 中文注释：规范化后的轻量记录，完整原文通过 artifact_id 引用
    records: RecordCollections
    # 中文注释：所有异常均结构化保存，不使用隐藏的字符串错误
    issues: list[Issue]
    # 中文注释：生成的文件、截图、快照和报告清单
    artifacts: list[ArtifactRef]
    # 中文注释：对账指标和运行级结果
    metrics: RunMetrics
~~~

代码中的注释必须使用中文，尤其是状态合并、重试、敏感字段处理和金额计算等容易误解的部分。

### 9.2 节点包装器

所有节点通过统一包装器执行：

~~~text
node_wrapper(node_id, handler):
  1. 写入 running 事件
  2. 读取输入摘要和上次检查点
  3. 执行业务 handler
  4. 校验 NodeOutput Schema
  5. 写入 output_ref、metrics 和 succeeded
  6. 捕获异常，分类为 retryable/non_retryable
  7. 写入 failed/blocked 和 issue
  8. 保存检查点
~~~

包装器不能记录完整身份证号、银行卡号、电话、页面 Cookie 或授权头。

### 9.3 LLM 调用边界

允许调用 LLM 的节点：

- inspect_and_bind_schema：只生成字段映射候选。
- classify_primary_and_sync：只生成候选平台和理由。
- fetch_and_extract_pages：只在 DOM 规则无法解析时提取标题/日期候选。
- validate_publication_evidence：只做证据摘要和异常归类。

禁止调用 LLM 的节点：

- normalize_reference_data。
- match_media 的最终决策。
- match_account。
- match_fee_rule。
- calculate_quote_details。
- aggregate_monthly。
- validate_payment_rows。
- render_artifacts。

LLM 请求统一要求：

- temperature=0 或模型等价的确定性设置。
- Pydantic/JSON Schema 结构化输出。
- 提供 source_refs 和 evidence。
- 解析失败最多重试一次。
- 不把完整 PII 放进提示词。
- 记录 model、prompt_version、response_schema_version 和 token 用量。

## 10. 文件和数据处理规范

### 10.1 Excel 导入

1. 先计算文件 SHA-256，再复制到运行输入目录。
2. 校验扩展名、MIME、压缩包成员和大小上限。
3. 首行识别不能只依赖第一行；6-付款固定模板必须按四行头校验。
4. 原始单元格保留 raw_value、显示值和解析值。
5. 空行、空列和公式单元格不直接丢弃，保留清洗统计。
6. 读写分离：原始文件只读，输出生成新文件。

### 10.2 链接处理

链接字段拆成：

~~~text
raw_text -> extracted_url -> canonical_url -> platform -> link_role
~~~

不得因为 URL 规范化而丢失原始字符串。短链、分享口令、查询参数和跳转链都需在 PageEvidence 中保留。

### 10.3 日期处理

统一转换为带时区的 ISO 8601：

~~~text
published_at: 2026-02-03T12:34:00+08:00
target_month: 2026-02
~~~

Excel 序列日期根据工作簿日期系统转换；只有“11月1日”的值保留 original_value，并标记 year_missing，不允许自动推断结算月份。

### 10.4 金额处理

- 使用 Decimal，不使用 float。
- 费用输入统一为元。
- 结算行最终保留 2 位小数，ROUND_HALF_UP。
- 奖励金额为空按 0 处理，但记录 reward_defaulted=true。
- 所有计算输出保存公式、输入引用和规则版本。

## 11. MCP 封装设计

### 11.1 MCP Server 定位

MCP Server 是工作流的稳定适配层，不把 LangGraph 内部节点暴露成一堆不可控的低层操作。外部平台只需要提交输入、查询运行、处理 issue 和下载产物。

建议服务名：quotation-fee-workflow。

### 11.2 MCP 工具

#### workflow_start

启动一次完整运行，返回 run_id，不阻塞等待最终结果。

请求：

~~~json
{
  "idempotency_key": "client-defined-key",
  "input_artifacts": [
    {"artifact_id": "art_1_links"},
    {"artifact_id": "art_3_media"},
    {"artifact_id": "art_4_accounts"},
    {"artifact_id": "art_5_fees"}
  ],
  "template_artifact_id": "art_6_payment_template",
  "target_month": "2026-02",
  "options": {
    "fetch_pages": true,
    "capture_screenshot": true,
    "exclude_unresolved_from_payment": true
  }
}
~~~

返回：

~~~json
{
  "run_id": "run_...",
  "result_status": "running",
  "status_uri": "workflow://runs/run_.../status"
}
~~~

#### workflow_get_status

参数：run_id、include_node_summary、include_metrics。返回运行级状态、当前节点、已完成节点、issue 数量、产物数量和对账指标。默认不返回 PII。

#### workflow_get_node

参数：run_id、node_id、include_input_summary、include_output_summary。返回节点状态、开始/结束时间、attempt、耗时、输入/输出 artifact 引用、记录计数、错误摘要和 lineage。

#### workflow_get_issues

参数：run_id、status、severity、page、page_size。返回结构化 issue 和解决 Schema，不返回未授权的敏感字段。

#### workflow_resolve_issues

参数：run_id、resolutions、mode。resolution 必须符合 issue 提供的 JSON Schema；mode 为 rerun 或 revise。接口写审计事件并返回新 revision/run_id。

#### workflow_list_artifacts

参数：run_id、kind、sensitivity。返回 artifact_id、逻辑名、文件名、大小、哈希、生成节点、下载过期时间。

#### workflow_download_artifact

参数：artifact_id、format。返回短期签名 URL 或 MCP binary resource。付款文件需要额外权限。

#### workflow_get_logs

参数：run_id、node_id、level、from、to、cursor、limit、redact=true。支持分页和按 trace_id 查询。

#### workflow_retry

参数：run_id、node_id、record_ids（可选）。只允许重试失败且幂等的节点；金额和付款导出节点重试前必须校验输入版本未变化。

#### workflow_cancel

参数：run_id、reason。取消尚未开始的任务并写审计记录；已提交的原子导出不删除，标记为 cancelled。

#### workflow_health

返回工作流版本、MCP 协议版本、模型可用性、存储、浏览器抓取器和队列健康状态。

### 11.3 MCP 资源

建议提供只读资源：

~~~text
workflow://runs/{run_id}/status
workflow://runs/{run_id}/issues
workflow://runs/{run_id}/artifacts
workflow://runs/{run_id}/lineage/{record_id}
workflow://runs/{run_id}/logs
workflow://schemas/{workflow_version}
workflow://fee-rules/{snapshot_id}
~~~

资源内容默认是 JSON，账户信息以引用或掩码返回。MCP 工具负责改变运行状态，资源负责读取状态，保持查询和命令边界清晰。

### 11.4 MCP 传输和鉴权

- 本地工具集成：stdio，进程级隔离，适合当前 POC。
- 远程调用：Streamable HTTP，使用 OAuth2/JWT 或平台现有服务身份。
- 每个请求携带 tenant_id、actor_id、trace_id。
- 权限至少分为 business_read、business_resolve、finance_export、admin_audit。
- finance_export 才能获取完整付款文件；普通状态查询不得返回身份证和银行卡明文。

## 12. 实时状态、事件和日志系统

### 12.1 状态查询模型

状态写入采用“事件追加 + 当前投影”：

~~~text
NodeStarted -> Progress -> NodeSucceeded
                         -> NodeFailed
                         -> NodeBlocked
~~~

事件是不可变记录，当前状态是可重建投影。这样既能实时查询，也能在状态库损坏时从事件重放。

### 12.2 NodeStatus 数据结构

~~~json
{
  "run_id": "run_...",
  "node_id": "match_media",
  "status": "running",
  "attempt": 1,
  "started_at": "2026-08-19T01:23:45.123Z",
  "ended_at": null,
  "progress": {
    "processed": 12,
    "total": 20,
    "succeeded": 10,
    "needs_review": 2,
    "failed": 0
  },
  "input_summary": {
    "record_count": 20,
    "artifact_ids": ["art_normalized_..."]
  },
  "output_summary": null,
  "last_error": null,
  "checkpoint_id": "ckpt_..."
}
~~~

### 12.3 结构化日志字段

每条日志至少包含 timestamp、level、event_type、run_id、node_id、trace_id、span_id、attempt、record_id（可选）、input_ref、output_ref、metrics、error_code、redaction 和 code_revision。

示例：

~~~json
{
  "timestamp": "2026-08-19T01:25:12.123Z",
  "level": "INFO",
  "event_type": "record_processed",
  "run_id": "run_...",
  "node_id": "match_fee_rule",
  "record_id": "pub_...",
  "metrics": {
    "matched": 1,
    "unit_price": 600.0
  },
  "input_ref": "fee_snapshot_...",
  "code_revision": "git:abc123"
}
~~~

### 12.4 敏感信息日志策略

- 身份证只显示前 3 位和后 4 位。
- 银行卡只显示前 4 位和后 4 位。
- 电话只显示前 3 位和后 4 位。
- 原始账户对象不进入 LLM prompt、普通日志、MCP status 和 issue message。
- 页面 Cookie、Authorization、上传文件原文和截图中的敏感区域不得写入日志。
- 敏感日志单独加密、独立权限、短期留存。

### 12.5 指标

运行级指标：

- workflow_runs_total 按 result_status、workflow_version、tenant 统计。
- workflow_duration_seconds。
- issue_total 按 node_id、code、severity 统计。
- payment_eligible_amount 和 payment_excluded_amount。

节点级指标：

- node_duration_seconds。
- node_records_processed_total。
- node_retry_total。
- page_fetch_success_rate、page_fetch_latency_seconds。
- llm_call_total、llm_error_total、llm_tokens_total。
- artifact_write_failures_total。

## 13. 检查点、重试、幂等和一致性

### 13.1 检查点

每个节点成功、失败或 blocked 后保存检查点，内容包括 run_id、node_id、checkpoint_id、输入 artifact 哈希、参考快照版本、可序列化输出摘要、事件游标、workflow_version 和 code_revision。截图、原始文件、Excel 和页面 HTML 只保存 artifact 引用。

### 13.2 重试策略

| 错误类别 | 策略 |
|---|---|
| 网络超时、对象存储暂时不可用 | 指数退避，最多 2-3 次 |
| 页面 403、验证码、登录 | 不做无限重试，直接 needs_review |
| Excel 字段缺失、费用规则冲突 | 不重试，生成 issue |
| LLM 限流/暂时错误 | 退避重试，最多 2 次；输出必须通过 Schema |
| 输出文件写入失败 | 临时文件 + 原子替换，最多 2 次 |
| 付款模板头不匹配、对账失败 | 立即 failed，禁止自动重试 |

### 13.3 幂等

- 同一 run 的 node_id + input_fingerprint + config_fingerprint 只允许生成一个有效输出。
- 产物路径包含 run_id 和 revision，不覆盖历史文件。
- 付款导出使用 payment_batch_id，重复导出生成相同哈希并返回已有 artifact。
- 解决 issue 后生成新 revision，旧 revision 只读。

### 13.4 一致性

导出前执行三方对账：

~~~text
sum(QuoteDetail.total_amount where settlement_eligible)
  == sum(MonthlySummary.summary_total)
  == sum(PaymentRow.payable_amount)
~~~

数量、分组键、账户引用和规则引用同时对账。任何不一致均写 critical issue 并阻止 payment_eligible。

## 14. 安全、隐私和合规

### 14.1 数据分级

| 等级 | 数据 | 处理 |
|---|---|---|
| L0 | 节点状态、计数、耗时 | 可被普通状态查询读取 |
| L1 | 媒体名、平台、标题、URL | 按租户授权读取 |
| L2 | 户名、电话、粉丝量 | 默认掩码，业务角色可读 |
| L3 | 身份证、银行卡、付款文件 | 加密存储，finance_export 才可导出 |

### 14.2 外部页面访问

- 只允许配置的公开域名。
- 解析 URL 后拒绝 localhost、私网、保留地址和非 HTTP(S) 协议。
- 限制最大响应体、跳转次数、页面执行时间和截图大小。
- 不绕过登录、验证码、付费墙或平台访问控制。
- 页面内容作为不可信输入，禁止让其改变系统工具权限或执行任意代码。

### 14.3 文件安全

- 上传文件先做扩展名、MIME、压缩包和大小检查。
- 原始文件只读保存，病毒扫描通过后再解析。
- 输出文件使用临时目录生成并校验哈希，再原子发布。
- 文件下载使用短期签名 URL，过期自动失效。

## 15. 代码目录和模块边界

建议最终实现为以下结构：

~~~text
src/workflow/
  __init__.py
  config.py                  # 中文注释：环境变量和运行配置
  graph.py                   # 中文注释：组装 LangGraph 主图和子图
  state.py                   # 中文注释：WorkflowState、NodeStatus、RunContext
  nodes/
    run.py                   # 中文注释：启动、终结和状态写入
    ingest.py                # 中文注释：Excel 导入、Schema 绑定
    links.py                 # 中文注释：链接提取、去重、主次链接分类
    evidence.py              # 中文注释：页面访问、元数据提取、截图
    matching.py              # 中文注释：媒体、账户、费用匹配
    settlement.py            # 中文注释：金额计算、明细和汇总
    export.py                # 中文注释：Excel、JSON、异常和报告
  domain/
    models.py                # 中文注释：领域模型和 Pydantic Schema
    rules.py                 # 中文注释：平台、匹配、金额和校验规则
    issues.py                # 中文注释：稳定 issue code 和解决 Schema
  adapters/
    excel.py                 # 中文注释：openpyxl 读写和模板适配
    browser.py               # 中文注释：httpx/Playwright 访问适配
    llm.py                   # 中文注释：LangChain 结构化模型适配
    storage.py               # 中文注释：artifact、checkpoint、snapshot 存储
  observability/
    events.py                # 中文注释：事件、日志、指标和脱敏
  mcp_server.py              # 中文注释：MCP 工具和资源
tests/
  fixtures/
  unit/
  integration/
  contract/
  e2e/
~~~

目录只是建议，第一版可以从当前项目的最小模块开始，但领域模型、节点 ID、事件字段和 MCP 工具名称应保持稳定。

## 16. 测试和验收方案

### 16.1 单元测试

- Excel 日期序列、日期文本和时区转换。
- URL 提取、引号清洗、短链和分享口令处理。
- 媒体上下文继承和主题分组。
- canonical_url 去重。
- 媒体精确匹配、别名匹配和冲突匹配。
- 账户字段格式校验和掩码。
- POC 费用适配器：FA/FB/FC + 视频/图文。
- Decimal 金额计算和 HALF_UP_2 舍入。
- 月度汇总和三方对账。
- 6-付款模板四行头校验、订单写入和公式更新。

### 16.2 契约测试

- 每个节点输入和输出必须通过 Pydantic/JSON Schema。
- NodeStatus、Issue、ArtifactManifest 字段版本兼容。
- MCP 工具参数校验、错误码和权限矩阵。
- workflow_get_status 绝不返回未授权 PII。

### 16.3 集成测试

使用 table 目录样例验证：

1. 1-链接.xlsx 解析出 6 个约稿组、4 个唯一媒体，并正确继承媒体名称和主题。
2. 2-约稿资料.xlsx 可作为已有结果导入，截图公式被识别为需要独立 artifact 的引用，而不是可见截图。
3. 3-媒体库、4-账户信息匹配 4 个样例媒体。
4. 5-费用.xlsx 生成 3 个等级、2 个约稿类型的兼容规则。
5. QuoteDetail、MonthlySummary、PaymentRow 金额均与 5200 元基线一致。
6. 6-付款.xlsx 输出保留前 4 行模板，生成 4 条有效付款订单，F 列合计为 5200。

若页面访问失败导致某条记录 needs_review，测试应同时验证“完整结果存在、付款结果排除该条”的行为。

### 16.4 异常测试

- 缺少 1-链接文件。
- 1-链接出现无媒体上下文 URL。
- 同一 canonical_url 跨媒体重复。
- 多个主平台候选。
- 页面 403、超时、验证码和标题为空。
- 媒体库 0/1/多匹配。
- 账户缺失、账户冲突、银行卡长度异常。
- 费用规则缺失或冲突。
- 约稿数量为 0、负数或非数字。
- 付款模板头被修改、订单超过 10000 条。
- 中途进程退出后从 checkpoint 恢复。
- 重复 workflow_start 不产生重复付款 artifact。

### 16.5 POC 验收标准

| 类别 | 通过标准 |
|---|---|
| 完整性 | 主流程节点全部可运行，能够产出 3 个结果表、异常清单和运行报告 |
| 可追溯 | 任一付款行可反查 MonthlySummary、QuoteDetail、PublicationRecord、原始单元格 |
| 正确性 | 金额/数量三方对账通过，费用规则引用明确 |
| 可恢复 | 节点失败可查询、可重试，进程重启后可从检查点继续 |
| 可查询 | MCP 可查询运行、节点、issue、日志和 artifact |
| 安全性 | 普通状态接口不泄露身份证、银行卡和完整手机号 |
| 无交互 | 图内没有等待人工输入的节点，异常通过外部 issue API 闭环 |
| 兼容性 | 6-付款模板的固定头、列顺序、公式和批次号规则不被破坏 |

## 17. 实施顺序

### 阶段一：数据和确定性内核

1. 建立模板注册表、领域模型和 artifact 存储。
2. 实现 Excel 导入、Schema 绑定、链接解析和参考数据快照。
3. 实现媒体/账户/费用匹配、金额计算、汇总和三方对账。
4. 用当前样例达到 5200 元基线。

### 阶段二：证据和结果产物

1. 实现页面访问、标题/日期提取和截图产物。
2. 实现约稿、约稿费用合计、6-付款和异常清单渲染。
3. 加入审计、脱敏和结果版本。

### 阶段三：LangGraph 和状态查询

1. 将确定性模块包装为节点。
2. 接入 checkpoint、NodeStatus 投影和重试策略。
3. 增加运行报告、指标和恢复测试。

### 阶段四：MCP

1. 实现 workflow_start、workflow_get_status、workflow_get_node。
2. 实现 issue、artifact、日志和重试工具。
3. 先支持 stdio，再增加 Streamable HTTP、鉴权和多租户。

### 阶段五：受控 LLM 增强

1. 为字段映射、平台分类和页面提取增加结构化 LLM fallback。
2. 建立提示词版本、模型输出评估和人工参考集。
3. LLM 只提高召回率，不改变费用和付款确定性逻辑。

## 18. 待业务确认的配置项

以下内容在代码实现前必须配置化并由业务方确认：

1. 每个约稿组的主平台优先级，以及“多平台”是否允许作为平台值。
2. 发布形式（原创/通稿）的判定证据和费用是否受其影响。
3. 约稿类型（视频/图文）的判定规则，以及同一组混合类型的拆分口径。
4. 同步平台是否只保存 URL，还是同时保存平台名称和数量。
5. 页面实际发布日期无法读取时是否允许使用供应商提交时间。
6. 费用规则是否按发布形式、平台、月份、生效日期进一步细分。
7. 奖励金额的来源、计算方式和是否计入付款。
8. 账户冲突时是阻止整条媒体、只阻止该月，还是进入人工复核队列。
9. 付款备注、批次号命名和同一银行卡跨媒体合并规则。
10. 业务复核与财务审核是否由外部系统完成，以及 resolution 的角色权限。

在这些配置确认前，系统应采用保守策略：无法确定就生成 issue，不猜测、不计入可付款集合。

## 19. 结论

本方案把约稿费用验收拆为“输入快照、证据核验、参考数据匹配、确定性结算、模板导出、状态审计、MCP 复用”七个稳定边界。LangGraph 负责可恢复的节点编排，LangChain 负责受约束的模型调用，普通代码负责所有关键业务规则和金额计算，MCP 负责跨平台的命令与查询。

第一版实现应优先完成确定性内核和当前 Excel 样例闭环，再加入页面抓取和 LLM fallback。这样即使页面不可访问或模型不可用，仍能生成可解释的异常结果，不会把不确定信息静默带入付款文件。
