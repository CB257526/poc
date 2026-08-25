# 约稿工作流 MCP 服务

Agent 可以通过 MCP：

1. **启动**一次完整工作流（传入表1 `1-链接.xlsx` 路径）
2. **查询**跑到哪了、某个节点输出了什么、报了什么错、某条记录为什么没进付款表

运行记录写入独立目录，**默认不和 HTTP 后端 / CLI 共用**：

- MCP：`runtime-mcp/workflow.db`，产物 `output-mcp/<run_id>/`
- CLI / HTTP 后端：`runtime/workflow.db`，产物 `output/<run_id>/`

用 `WORKFLOW_RUNTIME_DIR` / `WORKFLOW_OUTPUT_DIR` 可再改。同一进程里的 `get_run_store()` 仍是单例，所以后端服务和 MCP **必须分进程、分目录**启动，否则运行记录会串。

不传 Excel 二进制，不改参考表。产物文件仍落在磁盘 / HTTP 下载。

---

## 协议分层

按 MCP 标准拆成三类，不要混用。

| 能力 | 谁触发 | 协议方法 | 本服务里做什么 |
| --- | --- | --- | --- |
| **Tools** | 模型按需调用 | `tools/list`、`tools/call` | 带过滤的查询。问题里有 run_id / node_id / 过滤条件时走这里。 |
| **Resources** | 应用读取上下文 | `resources/list`、`resources/templates/list`、`resources/read` | 固定 URI 文档。没有过滤参数，适合「打开说明书 / 打开这次运行」。 |
| **Prompts** | 用户显式触发 | `prompts/list`、`prompts/get` | 排错话术模板，告诉模型先调哪些 tool。 |

传输：远端用 **Streamable HTTP**（MCP 标准远程传输）。内网不鉴权。本地调试可用 stdio。

---

## 启动

```bash
# 远端 / 内网（默认）
uv run workflow-mcp --transport streamable-http --host 0.0.0.0 --port 8100 --path /mcp

# 仅本机
uv run workflow-mcp --transport streamable-http --host 127.0.0.1 --port 8100 --path /mcp

# stdio（Claude Code / Cursor 拉起子进程）
uv run workflow-mcp --transport stdio
```

环境变量（与 CLI 参数等价）：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `WORKFLOW_MCP_TRANSPORT` | `streamable-http` | `stdio` / `streamable-http` / `sse` |
| `WORKFLOW_MCP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `WORKFLOW_MCP_PORT` | `8100` | HTTP 端口 |
| `WORKFLOW_MCP_PATH` | `/mcp` | Streamable HTTP 路径 |
| `WORKFLOW_RUNTIME_DIR` | 仓库 `runtime-mcp/` | SQLite 所在目录。后端请保持 `runtime/`，不要设成同一个 |
| `WORKFLOW_OUTPUT_DIR` | 仓库 `output-mcp/` | 产物根目录，实际写入 `<dir>/<run_id>/` |
| `WORKFLOW_TABLE_DIR` | 仓库 `table/` | 参考表目录（3/4/5） |

Agent 连接地址：`http://<host>:8100/mcp`。

Claude Code / 其它 MCP 客户端示例（远端）：

```json
{
  "mcpServers": {
    "byd-workflow": {
      "url": "http://127.0.0.1:8100/mcp"
    }
  }
}
```

stdio 示例：

```json
{
  "mcpServers": {
    "byd-workflow": {
      "command": "uv",
      "args": ["run", "workflow-mcp", "--transport", "stdio"],
      "cwd": "/absolute/path/to/workflow"
    }
  }
}
```

---

## Tools

实现：`src/workflows/mcp_server.py`。返回 JSON 字符串。找不到对象时返回：

```json
{"error": {"code": "NOT_FOUND", "message": "运行不存在: ..."}}
```

账户字段（身份证、账号、户名、电话）在快照里默认打码。

### `start_run`

传入表1路径，**后台**启动节点 0—6。立即返回 `run_id`，不等待爬取结束。

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `input_file` | string | 必填 | 表1路径，即 `1-链接.xlsx` |
| `table_dir` | string | `WORKFLOW_TABLE_DIR` 或 `./table` | 参考表目录（3-媒体库、4-账户信息、5-费用） |
| `output_dir` | string | `WORKFLOW_OUTPUT_DIR` 或 `output-mcp/` | 产物**根**目录，实际写入 `<output_dir>/<run_id>/` |

返回：`run_id`、`status=running`、`paths`（数据库、表1/3/4/5、产物目录）。之后用 `wait_run`（或 `get_run`）跟踪；`node_02` 爬取可能要数十秒。

文件不存在或不是 xlsx 时：

```json
{"error": {"code": "INVALID_INPUT", "message": "输入文件不存在: ..."}}
```

MCP 标注：`readOnlyHint=false`（会真正跑工作流并写产物）。

### `list_runs`

最近运行列表。

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `status` | string \| null | null | `pending` / `running` / `completed` / `failed` / `terminated` |
| `limit` | int | 20 | 最大 100 |
| `input_file` | string \| null | null | 输入路径模糊匹配，如 `1-链接.xlsx` |
| `since` / `until` | string \| null | null | `started_at` 的 ISO 时间范围 |

返回每条：`run_id`、`status`、时间、`current_node`、`input_file`、记录数、已完成节点、issue 计数、`stale`。

### `get_run`

一次运行总览。不含整份 records。

| 参数 | 必填 |
| --- | --- |
| `run_id` | 是 |

返回：状态、进度（completed / remaining）、issue 计数、各节点摘要、产物 key、约稿费用摘要。`running` 且超过 15 分钟无心跳会标 `stale`。

### `wait_run`

阻塞等到终态，避免 Agent 反复调 `get_run`。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `run_id` | 必填 | |
| `timeout_seconds` | 60 | 最大 120 |
| `interval_seconds` | 2 | 轮询间隔 |

到达 `completed` / `failed` / `terminated` 时返回与 `get_run` 相同的总览，并带 `timed_out=false`。超时则返回当前快照，`timed_out=true`。

### `get_node`

某个节点当时干了什么。这是「输出了什么 / 报了什么错」的主入口。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `run_id` | 必填 | |
| `node_id` | 必填 | `node_00` … `node_06` |
| `sample_size` | 5 | 输出样本条数 |
| `include_records` | false | true 时给该节点脱敏快照全量 |

返回：status、metrics（条数 / 耗时）、本节点 issues、`output_summary.sample`。

### `list_issues`

按运行过滤问题。

| 参数 | 说明 |
| --- | --- |
| `run_id` | 必填 |
| `node_id` | 可选 |
| `level` | `warning` / `error` / `critical` |
| `code` | 如 `MEDIA_NOT_IN_LIBRARY` |
| `record_id` | 如 `rec_0001` |

### `summarize_issues`

按 `code` / `level` / `node_id` 聚合。排错先看这个，再按需 `list_issues`。

| 参数 | 说明 |
| --- | --- |
| `run_id` | 必填 |
| `node_id` / `level` | 可选过滤 |

返回：`groups[{code, level, node_id, count, sample_record_ids, sample_message}]`。

### `list_records`

一次运行的记录目录，不含整行明细。

| 参数 | 说明 |
| --- | --- |
| `run_id` | 必填 |
| `processable` | 可选 bool |
| `media` / `platform` / `q` | 模糊匹配 |
| `media_match_status` / `account_match_status` | 精确匹配 |
| `has_issue` | 可选 bool |
| `limit` / `offset` | 分页，limit 最大 200 |

返回每条：`id`、媒体、平台、匹配状态、`processable`、费用、`issue_count`。

### `get_funnel`

财务漏斗：输入 → 媒体匹配 → 账户匹配 → processable → 约稿明细 → 付款表，以及按错误码掉量。

### `get_record`

一条记录在各节点的字段变化。用来回答「为什么没进付款表」。

| 参数 | 必填 |
| --- | --- |
| `run_id` | 是 |
| `record_id` | 是 |

返回：当前脱敏记录、相关 issues、按节点的 lineage。关注 `processable`、`media_match_status`、`account_match_status`。

### `list_artifacts`

列出产物文件名和大小，不含二进制。

### `describe_artifact`

描述某个产物。

| 参数 | 说明 |
| --- | --- |
| `run_id` | 必填 |
| `file_key` | `payment` 或 `quote_detail` |

需要下载文件时走工作流自己的 HTTP/磁盘路径，不在 MCP 里传 xlsx。

### `get_workflow_schema`

静态说明书：7 个节点的顺序、读写字段、典型错误码。第一次对话应先调这个（或读 resource `workflow://schema`）。

节点 ID：

| ID | 名称 |
| --- | --- |
| `node_00` | 输入验证 |
| `node_01` | 填写约稿资料基础信息 |
| `node_02` | 完善发布信息（爬取） |
| `node_03` | 匹配媒体库 |
| `node_04` | 匹配账户信息 |
| `node_05` | 计算费用 |
| `node_06` | 生成付款表 |

---

## Resources

固定 URI，无过滤参数。需要过滤用对应 tool。

| URI | 内容 |
| --- | --- |
| `workflow://schema` | 与 `get_workflow_schema` 相同的静态说明书 |
| `workflow://runs` | 最近 20 次运行（无 status 过滤） |
| `workflow://runs/{run_id}` | 与 `get_run` 相同的总览 |
| `workflow://runs/{run_id}/nodes/{node_id}` | 与 `get_node` 默认参数相同的节点详情 |
| `workflow://runs/{run_id}/issues` | 该次运行全部 issues（不过滤） |

MIME：`application/json`。

---

## Prompts

用户从客户端选模板时触发，不是模型自己发现就调用。

| 名称 | 参数 | 作用 |
| --- | --- | --- |
| `run_workflow` | `input_file` | 用 `start_run` 启动，再 `get_run` 跟踪直到结束 |
| `inspect_run` | `run_id` | 检查一次运行：总览 → issues → 失败节点 |
| `inspect_node` | `run_id`, `node_id` | 检查单个节点的输出和报错 |
| `explain_record` | `run_id`, `record_id` | 解释一条记录为何可能未入账 |

---

## 推荐调用顺序

启动并跟踪：

1. `start_run(input_file="./table/1-链接.xlsx")` 拿到 `run_id`
2. `wait_run` 直到 `completed` / `failed` / `terminated`（可超时后再调）
3. 失败或条数对不上则 `get_funnel` / `summarize_issues` / `list_records` / `get_node`

只查历史：

1. 读 `workflow://schema` 或调 `get_workflow_schema`
2. `list_runs` 找到 `run_id`
3. `get_run` → `get_funnel` / `summarize_issues` / `list_records` / `get_node` / `get_record`

---

## 数据从哪来

```
CLI run_workflow
    → BaseNode 每步写入 RunStore（SQLite）
        → WorkflowQueryService（摘要 + 脱敏）
            → MCP tools / resources
```

关键代码：

- 服务入口：`src/workflows/mcp_server.py`
- 启动：`src/workflows/runtime/jobs.py`
- 持久化：`src/workflows/runtime/store.py`
- 节点说明书：`src/workflows/runtime/catalog.py`

没有运行记录时，`list_runs` 返回空列表；对其它 tool 传不存在的 `run_id` 会得到 `NOT_FOUND`。

---

## 安全

- 内网部署，**不鉴权**。不要把端口暴露到公网。
- `start_run` 会在本机读 Excel、爬网页、写输出目录。路径必须是 MCP 进程能访问的本地/内网路径。
- 查询结果脱敏：快照投影字段白名单，敏感列打码。
- 产物只给路径元数据和摘要，不经 MCP 传 xlsx。

---

## 手工验收

先跑一遍工作流（会写 `runtime/workflow.db`），再开 MCP，再用客户端打每个 tool。仓库里的脚本：

```bash
# 终端 1：MCP 默认写 runtime-mcp / output-mcp，不要和后端抢 runtime/
uv run workflow-mcp \
  --transport streamable-http --host 127.0.0.1 --port 8100 --path /mcp

# 终端 2：直接 start_run → wait_run
uv run python mcp/smoke_client.py
```

和 HTTP 后端同时跑时：

```bash
# 后端 / CLI（默认）
uv run python -m workflows run --input table/1-链接.xlsx
# → runtime/workflow.db ， output/<run_id>/

# MCP
uv run workflow-mcp --runtime-dir ./runtime-mcp --output-dir ./output-mcp
# → runtime-mcp/workflow.db ， output-mcp/<run_id>/
```
