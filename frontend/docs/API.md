# 约稿平台 · 前端所需 API 说明书

本文档是 React 前端与 `src/workflows/backend` 的 HTTP 合同。实现以后端代码为准，字段与路径必须保持一致。

- 基础路径：`/api/v1`
- 协议：HTTPS（本地 HTTP 即可）
- 数据格式：JSON，UTF-8；上传 Excel 时为二进制或 `multipart/form-data`
- 鉴权：`Authorization: Bearer <access_token>`，登录 / 注册除外
- 时间：ISO 8601，建议带时区，例如 `2026-08-20T10:28:00+08:00`
- 金额：数字，单位 **元**，保留到分时用小数；前端展示时四舍五入到整数
- 跨域：允许前端来源（开发默认 `http://127.0.0.1:5173`）

---

## 0. 角色与权限

| role | 中文 | 职责 |
| --- | --- | --- |
| `admin` | 管理员 | 全部接口；审核用户；上传基础配置表 |
| `operator` | 业务人员 | 日常上传链接表、修正媒体名、处理异常、下载结果 |
| `finance` | 财务 | 只读约稿 / 费用；下载付款文件；不能上传任务、不能改配置 |
| `viewer` | 只读访客 | 只读概览、约稿资料、费用分析 |

未登录：`401`。角色不足：`403`，body 见错误格式。账号 `pending` / `disabled` 禁止登录。

页面与接口对应关系：

| 能力 | 允许角色 | 接口 |
| --- | --- | --- |
| 登录注册、当前用户 | 游客 / 已登录 | `/auth/*` |
| 首页概览 | 全部已登录 | `GET /dashboard/overview` |
| 上传并跑任务 | admin, operator | `/tasks/validate` `/corrections` `/run` |
| 查任务 / 约稿明细 | 全部已登录 | `GET /tasks/{id}` `GET /tasks/latest` |
| 月度分析 | 全部已登录 | `GET /analytics/monthly` |
| 异常核验 | admin, operator | `/exceptions*` |
| 下载结果文件 | admin, operator, finance | `GET /tasks/{id}/files/*` |
| 基础配置 | 读：已登录；写：admin | `/config*` |
| 用户管理 | admin | `/users*` |

---

## 1. 统一约定

### 1.1 成功

- `200`：返回 JSON 对象或数组
- `201`：创建成功（注册、建任务均可，前端兼容 200）
- `202`：异步已接受（启动工作流）
- `204`：无 body（登出可用 200 `{ok:true}`）

### 1.2 错误

```json
{
  "detail": "给人看的中文原因",
  "code": "MEDIA_NOT_IN_LIBRARY",
  "field_errors": {
    "email": "该邮箱已注册"
  }
}
```

| HTTP | 典型 code | 场景 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 缺文件、金额未对齐 |
| 401 | `UNAUTHENTICATED` `INVALID_CREDENTIALS` | 未登录 / 密码错 |
| 403 | `FORBIDDEN` `ACCOUNT_PENDING` `ACCOUNT_DISABLED` `ACCOUNT_INACTIVE` | 角色或账号状态 |
| 404 | `NOT_FOUND` | 任务 / 用户 / 文件不存在 |
| 409 | `EMAIL_TAKEN` `TASK_CONFLICT` | 邮箱占用、任务状态不允许该操作 |
| 422 | `UNPROCESSABLE` | 媒体名不在允许列表 |
| 500 | `INTERNAL` | 工作流内部错误，任务应变 `failed` |

前端用 `detail` 直接展示。`code` 用于分支，不要改已列出的取值。

### 1.3 分页（预留）

当前列表量小，前端 **不传分页参数**。若后端分页，请同时支持不分页的全量返回，或使用：

```text
GET /resource?page=1&page_size=50
```

```json
{ "items": [], "total": 0, "page": 1, "page_size": 50 }
```

未实现分页时直接返回数组即可，前端已按数组解析的接口：用户列表、异常列表。

---

## 2. 鉴权

Token 建议 JWT。`access_token` 有效期 2 小时，`refresh_token` 7 天。前端目前只存 token，登录后用 access 调接口；刷新接口后端已实现，前端暂未自动续期。

### 2.1 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

请求：

```json
{
  "email": "operator@byd.local",
  "password": "Passw0rd!"
}
```

成功 `200`：

```json
{
  "user": {
    "id": "u_op",
    "email": "operator@byd.local",
    "name": "业务经办",
    "role": "operator",
    "status": "active",
    "created_at": "2026-07-08T09:00:00+08:00",
    "last_login_at": "2026-08-25T09:40:00+08:00"
  },
  "tokens": {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "token_type": "bearer",
    "expires_in": 7200
  }
}
```

失败：密码错 `401 INVALID_CREDENTIALS`；待审核 `403 ACCOUNT_PENDING`；停用 `403 ACCOUNT_DISABLED`。

### 2.2 注册

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "email": "new@byd.local",
  "name": "张三",
  "password": "Passw0rd!"
}
```

规则：

- 邮箱唯一，企业邮箱格式
- 密码至少 8 位
- 新用户 `role=operator`，`status=pending`
- **不能立刻登录**

成功 `201`：

```json
{ "message": "注册成功，请等待管理员审核后再登录" }
```

邮箱占用 `409 EMAIL_TAKEN`。

### 2.3 当前用户

```http
GET /api/v1/auth/me
Authorization: Bearer <token>
```

返回 `User` 对象（同登录里的 `user`）。token 无效 `401`。

### 2.4 登出

```http
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

服务端作废 refresh（若有）。返回 `204` 或 `{ "ok": true }`。

### 2.5 刷新（可选，前端暂未接）

```http
POST /api/v1/auth/refresh
{ "refresh_token": "<jwt>" }
```

返回新的 `tokens` 对象。

---

## 3. 用户管理（admin）

### 3.1 列表

```http
GET /api/v1/users
```

返回 `User[]`。建议按 `pending` 优先、再按 `created_at` 倒序。

`User` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 稳定主键 |
| email | string | 登录名 |
| name | string | 显示名 |
| role | `admin` `operator` `finance` `viewer` | 角色 |
| status | `pending` `active` `disabled` | 账号状态 |
| created_at | string | 注册时间 |
| last_login_at | string \| null | 最近成功登录 |

### 3.2 更新角色 / 状态

```http
PATCH /api/v1/users/{user_id}
Content-Type: application/json
```

```json
{ "role": "finance", "status": "active" }
```

两个字段都可选。前端场景：

- 审核通过：`{ "status": "active" }`
- 停用：`{ "status": "disabled" }`
- 改角色：`{ "role": "viewer" }`

不能停用自己（建议 `400`）。返回更新后的 `User`。

---

## 4. 首页概览

```http
GET /api/v1/dashboard/overview
```

```json
{
  "latest_task": { "...Task 或 null" },
  "task_status_label": "已完成",
  "media_count": 6,
  "quote_count": 5,
  "total_fee": 197800,
  "type_distribution": [
    { "content_type": "图文", "quote_count": 4 },
    { "content_type": "视频", "quote_count": 1 }
  ],
  "pending_exceptions": 1,
  "config_ready": true
}
```

口径：

- 数字只统计 **校验通过且可入账** 的记录（见第 10 节）
- 无已完成任务时：`latest_task=null`，数值可为 0；前端会显示空态，不要返回演示假数据
- `task_status_label` 建议：`待处理` / `处理中` / `已完成` / `失败` / `待修正`
- `type_distribution` 按约稿类型聚合，`content_type` 用业务原词：`图文`、`视频`（兼容 `文章`、`图文类`、`视频类`）

---

## 5. 基础配置

业务人员日常 **只上传链接表（表 1）**。管理员只需维护下面 3 个参考表。约稿资料（表 2）和付款表（表 6）由工作流 `node_06` 按固定模板生成，**不要上传、也不纳入配置检查**。

| kind | 文件 | 用途 |
| --- | --- | --- |
| `media_library` | 3-媒体库.xlsx | 标准媒体名、等级、粉丝量 |
| `accounts` | 4-账户信息.xlsx | 收款账户 |
| `fee_rules` | 5-费用.xlsx | 等级 × 图文/视频单价 |

### 5.1 查询状态

```http
GET /api/v1/config
```

全部已登录可读（处理页要展示「已配置」灯）。

```json
{
  "all_ready": true,
  "files": [
    {
      "kind": "media_library",
      "label": "媒体库",
      "configured": true,
      "filename": "3-媒体库.xlsx",
      "updated_at": "2026-08-12T14:20:00+08:00",
      "updated_by": "u_admin"
    }
  ]
}
```

`files` 必须覆盖上述 3 个 kind，缺文件则 `configured=false`。`all_ready` 仅当这三项都在 `table/` 中存在为 true。非法 `kind`（含已废弃的 `quote_template` / `payment_template`）上传返回 `400`。

### 5.2 上传 / 覆盖

```http
POST /api/v1/config/files
Authorization: Bearer <admin>
Content-Type: multipart/form-data
```

字段：

- `kind`：上表枚举
- `file`：`.xlsx`

成功返回最新的整个 `ConfigStatus`。非 xlsx 或 kind 非法：`400`。

---

## 6. 任务工作流

这是从 Streamlit 迁过来的核心链路。状态机：

```text
validate ──► needs_correction ──corrections──► ready ──run──► running ──► completed
                 │                                  │              └──► failed
                 └──仍不匹配─────────────────────────┘
```

| status | 含义 | 前端 |
| --- | --- | --- |
| `needs_correction` | 媒体名未全部匹配 | 修正表格，禁止 run |
| `ready` | 预检通过 | 立即 POST run |
| `running` | 节点 1—6 执行中 | 每 1.5s 轮询 |
| `completed` | 成功 | 展示明细和下载 |
| `failed` | 失败 | 展示 `error`，不入月度汇总 |
| `cancelled` | 用户取消（可选） | 回到空闲 |

节点进度 `completed_nodes` 使用：

`node_00` 输入预检 · `node_01` 链接解析 · `node_02` 资料整理 · `node_03` 媒体匹配 · `node_04` 账户补全 · `node_05` 费用计算 · `node_06` 付款生成

`total_nodes` 固定 `7`。前端进度条 = `len(completed_nodes) / 7`。

### 6.1 上传并预检

```http
POST /api/v1/tasks/validate
Authorization: Bearer <admin|operator>
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

Body 为 **Excel 二进制**（不是 multipart）。对应文件 `1-链接.xlsx`。

解析规则（与原表 1 两列分层模板一致）：

- 第 1 列主题 / 媒体名，第 2 列链接
- 仅第 1 列有值、第 2 列空：切换主题
- 第 1、2 列都有值：新的媒体块开始
- 仅第 2 列有值：属于当前媒体的链接

成功 `200`：

```json
{
  "task_id": "task_20260825_001",
  "status": "needs_correction",
  "allowed_media_names": ["36氪汽车", "懂车帝", "汽车之家"],
  "records": [
    {
      "record_id": "rec_0003",
      "row_number": 16,
      "topic": "主题1",
      "media_name": "汽车之加",
      "link_count": 8,
      "link_preview": "https://example.com/autohome/1",
      "match_status": "unmatched",
      "suggested_name": "汽车之家"
    }
  ],
  "issues": [
    {
      "record_id": "rec_0003",
      "node_id": "node_00",
      "code": "MEDIA_NOT_IN_LIBRARY",
      "message": "媒体名称无法匹配媒体库",
      "severity": "error"
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| record_id | 后端生成，稳定 |
| row_number | **原 Excel 行号**，修正接口的 key |
| match_status | `matched` / `unmatched`。匹配规则：去普通空格和全角空格，英文忽略大小写，必须唯一命中媒体库 |
| suggested_name | 未匹配时的近似建议；已匹配为空字符串 |
| allowed_media_names | 媒体库标准名全集，前端下拉只允许这些值 |
| issues[].code | 未匹配必须是 `MEDIA_NOT_IN_LIBRARY` |
| issues[].node_id | 产生该问题的节点，预检为 `node_00`；工作流为 `node_01`–`node_06`。未归属节点时可省略或为 `null` |

全部匹配时 `status` 为 `ready`，`issues` 为空。文件无法解析：`400`，例如「没有读取到有效的媒体与链接」。

> 兼容：若暂时不返回 `match_status`，前端也可根据 `issues` 里 `MEDIA_NOT_IN_LIBRARY` 的 `record_id` 判断。**请同时返回 `match_status`。**

### 6.2 提交媒体名称修正

```http
POST /api/v1/tasks/{task_id}/corrections
Content-Type: application/json
```

```json
{
  "media_name_corrections": {
    "16": "汽车之家"
  }
}
```

- key = 原表行号字符串
- value = `allowed_media_names` 中的标准名
- 只改媒体名，不改原始 Excel 文件
- 仅 `needs_correction` 可调用，否则 `409 TASK_CONFLICT`

返回体与 6.1 相同。仍有未匹配则继续 `needs_correction`；全部通过则为 `ready`。

### 6.3 启动节点 1—6

```http
POST /api/v1/tasks/{task_id}/run
```

仅 `ready` 可启动。成功 `202`：

```json
{ "task_id": "task_20260825_001", "status": "running" }
```

`needs_correction` 时 `409`。工作流在后台跑，接口立即返回。

### 6.4 查询任务

```http
GET /api/v1/tasks/{task_id}
```

```json
{
  "task_id": "task_20260825_001",
  "status": "completed",
  "filename": "1-链接.xlsx",
  "created_at": "2026-08-20T10:12:00+08:00",
  "updated_at": "2026-08-20T10:28:00+08:00",
  "created_by": "u_op",
  "error": null,
  "progress": {
    "completed_nodes": ["node_00", "node_01", "node_02", "node_03", "node_04", "node_05", "node_06"],
    "total_nodes": 7,
    "current_node": null
  },
  "quote_summary": {
    "media_count": 5,
    "quote_count": 5,
    "total_fee": 197800,
    "text_fee": 153600,
    "video_fee": 44100,
    "details": [
      {
        "media_name": "36氪汽车",
        "platform": "知乎",
        "content_type": "图文",
        "media_level": "A",
        "followers": "500万",
        "quote_count": 1,
        "unit_price": 5000,
        "amount": 60000,
        "status": "完成",
        "title": "新能源渗透率观察",
        "publish_url": "https://example.com/36kr/1",
        "publish_date": "2026-08-18"
      }
    ]
  },
  "files": [
    { "key": "quote_detail", "filename": "2-约稿资料_完成版.xlsx", "ready": true },
    { "key": "payment", "filename": "6-付款.xlsx", "ready": true }
  ],
  "issues": [
    {
      "record_id": "rec_0001",
      "node_id": "node_03",
      "code": "MEDIA_NOT_FOUND",
      "message": "媒体库未找到该媒体",
      "severity": "error"
    }
  ]
}
```

`quote_summary.details` 只含可入账记录。运行中 `quote_summary` 可为 `null`，`files` 为空数组。失败时 `error` 为中文原因。

`issues` 来自工作流 `context.issues`（含 `node_id`）。任务仍在跑时也会随进度写入，前端应展示而不是忽略。工作流未捕获的崩溃会追加 `code=WORKFLOW_CRASH`、`severity=critical`。

前端约定：`GET /tasks/{id}` 轮询失败、后端宕机（`TypeError`）或 `500 INTERNAL` 都要展示 `detail`，不要吞掉。

> 兼容原 Streamlit：若 `details` 暂用中文 key（`媒体` `平台` `文章类型` `媒体等级` `粉丝量` `基础金额` `费用` `标题` `链接` `发布日期`），后端 **不要再这样返回**。请用本文英文字段。

### 6.5 任务列表

```http
GET /api/v1/tasks
```

已登录可读。按 `created_at` **倒序**返回 `Task[]`（与 6.4 同一对象）。没有任务时返回 `[]`。

约稿资料页用这个接口列出每一次处理记录，再按选中的 `task_id` 展示该次 `quote_summary.details`。不要只返回最近一条。

### 6.6 最近一次任务

```http
GET /api/v1/tasks/latest
```

当前用户可见范围内最近一条任务。没有则 `200 null` 或 `404`（前端按空处理，建议 `200 null`）。

文件输出页、首页仍可打这个接口拿最近一条。约稿资料页请用 6.5 列表。

### 6.7 下载单个结果文件

```http
GET /api/v1/tasks/{task_id}/files/{file_key}
```

`file_key`：

| key | 文件 | Content-Type |
| --- | --- | --- |
| `quote_detail` | 完善后的 2-约稿资料 | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `payment` | 6-付款 | 同上 |

响应为文件二进制。请带：

```http
Content-Disposition: attachment; filename="2-约稿资料_完成版.xlsx"
```

任务未完成或文件未生成：`409` 或 `404`。

### 6.8 打包下载

```http
GET /api/v1/tasks/{task_id}/files/archive
```

ZIP，内含上述两个 xlsx。`Content-Type: application/zip`。

前端文件名：`约稿费用验收_处理结果.zip`。

---

## 7. 费用分析

```http
GET /api/v1/analytics/monthly?month=2026-08
```

- `month` 可选，格式 `YYYY-MM`，默认当前自然月
- **只统计** `completed` 且记录 `eligible_for_monthly_summary=true` 的任务
- `failed` / 未匹配 / 待确认 **不得计入**

```json
{
  "month": "2026-08",
  "batch_count": 7,
  "quote_count": 848,
  "total_fee": 461200,
  "average_batch_fee": 65886,
  "batches": [
    {
      "task_id": "task_demo_001",
      "processed_at": "2026-08-20T10:28:00+08:00",
      "quote_count": 256,
      "total_fee": 231600,
      "text_fee": 153600,
      "video_fee": 78000
    }
  ],
  "top_media": [
    { "media": "36氪汽车", "total_fee": 60000 }
  ]
}
```

`batches` 按时间升序。`top_media` 按费用降序，前端默认取前 5，后端可返回 Top 10。

无数据时不要 404，返回全 0 和空数组。

图文 / 视频划分：`content_type ∈ {图文, 文章, 图文类}` 为图文；`{视频, 视频类}` 为视频。

---

## 8. 异常（费用一致性）

对应原「异常提醒」页：核对「约稿」子表与「约稿费用合计」子表。

状态：`待确认` → 人工改汇总金额并保存 → `待校对` → 点「重新校对」→ `已解决`。

### 8.1 列表

```http
GET /api/v1/exceptions?task_id={optional}
```

返回 `ExceptionItem[]`。

```json
{
  "exception_id": "ex_001",
  "task_id": "task_20260825_001",
  "target": "费用核算结果",
  "issue": "两个子表费用不一致",
  "suggestion": "核对「约稿」与「约稿费用合计」的媒体费用及总费用",
  "status": "待确认",
  "correction": "",
  "calculation": [
    {
      "media_name": "汽车之家",
      "platform": "微博",
      "content_type": "视频",
      "work_count": 3,
      "fee_rule": "B级视频核定价",
      "unit_price": 5500,
      "expected_fee": 16500
    }
  ],
  "compare": [
    {
      "media_name": "汽车之家",
      "detail_fee": 44000,
      "summary_fee": 43000,
      "status": "不一致"
    }
  ]
}
```

`calculation`：系统按费用规则拆开的应计明细，只读。  
`compare`：逐媒体对照。`detail_fee` 来自「约稿」子表，只读；`summary_fee` 来自「约稿费用合计」，可被 8.2 修改。

无异常返回 `[]`。不要为了演示造假数据。

### 8.2 保存核验（改汇总金额）

```http
PATCH /api/v1/exceptions/{exception_id}
Content-Type: application/json
```

```json
{
  "summary_fees": {
    "36氪汽车": 60000,
    "懂车帝": 48000,
    "汽车之家": 44000,
    "车云网": 28800
  }
}
```

后端必须校验：每个媒体 `summary_fee == detail_fee`，且两边总额相等。不满足：

```json
{ "detail": "请先修改红色金额，确保两个子表中各媒体费用及总费用全部一致。", "code": "AMOUNTS_MISMATCH" }
```

HTTP `400`。通过后：

- 写回「约稿费用合计」
- `status = 待校对`
- `correction` 例如：`两个子表费用已一致，总费用 ¥197,800`

返回更新后的 `ExceptionItem`。

### 8.3 重新校对

```http
POST /api/v1/exceptions/reaudit
```

把所有 `待校对` 且 `correction` 非空的项标为 `已解决`。若业务上还要再跑一遍费用规则，在此接口内执行。

```json
{ "resolved": 1, "remaining": 0 }
```

`resolved` 为当前已解决总数（或本次新解决数，前端只展示文案，建议：**本次校对后处于已解决的条数** 与 **仍未解决条数**）。

---

## 9. 健康检查（建议）

```http
GET /health
```

```json
{ "status": "ok" }
```

不鉴权。前端未强制调用，部署探测会用。

---

## 10. 入账口径（必须前后端一致）

同时满足才进入约稿明细、付款文件、本次费用、当月汇总：

1. 媒体名称唯一匹配媒体库
2. 媒体等级、粉丝量完整
3. 账户必填字段完整
4. 费用规则匹配成功
5. 记录 `processable=true`
6. 费用明细 `eligible_for_monthly_summary=true`

以下 **不得** 进入上述任何统计：

- 待修改媒体名
- 待确认 / 核验未通过
- 匹配失败
- 任务 `failed`

---

## 11. 前端调用一览

| 方法 | 路径 | 页面 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 登录 |
| POST | `/api/v1/auth/register` | 注册 |
| GET | `/api/v1/auth/me` | 启动时恢复会话 |
| POST | `/api/v1/auth/logout` | 退出 |
| GET | `/api/v1/dashboard/overview` | 首页 |
| GET | `/api/v1/config` | 数据处理、基础配置 |
| POST | `/api/v1/config/files` | 基础配置 |
| POST | `/api/v1/tasks/validate` | 数据处理 · 开始处理 |
| POST | `/api/v1/tasks/{id}/corrections` | 数据处理 · 重新校验 |
| POST | `/api/v1/tasks/{id}/run` | 预检通过后自动调用 |
| GET | `/api/v1/tasks` | 约稿资料 · 历次处理 |
| GET | `/api/v1/tasks/{id}` | 处理中轮询 |
| GET | `/api/v1/tasks/latest` | 文件输出、首页兼容 |
| GET | `/api/v1/tasks/{id}/files/{key}` | 文件输出 |
| GET | `/api/v1/tasks/{id}/files/archive` | 打包下载 |
| GET | `/api/v1/analytics/monthly` | 费用分析 |
| GET | `/api/v1/exceptions` | 异常提醒 |
| PATCH | `/api/v1/exceptions/{id}` | 保存核验 |
| POST | `/api/v1/exceptions/reaudit` | 重新校对 |
| GET | `/api/v1/users` | 用户管理 |
| PATCH | `/api/v1/users/{id}` | 改角色 / 审核 / 停用 |

原 Streamlit 已使用、请继续保留语义的接口：`validate`、`corrections`、`run`、`GET task`、`files/quote_detail`、`files/payment`、`analytics/monthly`。其余为本次为登录、权限、配置、异常持久化新增。

---

## 12. 实现顺序建议

1. 鉴权 + 用户表 + 四个角色
2. 配置文件存取（可先读本地 `table/` 目录，再做成上传覆盖）
3. 任务：validate / corrections / run / get / files（接现有工作流节点 0—6）
4. `quote_summary` 英文字段、入账过滤
5. `dashboard/overview` + `analytics/monthly` 持久化
6. 异常表：任务完成后若两子表不一致则生成 `ExceptionItem`
7. CORS、token 过期、任务状态落库（不要只放内存）

---

## 13. 示例账号（联调）

后端可内置与前端 Mock 相同的种子，便于对照：

| email | password | role | status |
| --- | --- | --- | --- |
| admin@byd.local | Passw0rd! | admin | active |
| operator@byd.local | Passw0rd! | operator | active |
| finance@byd.local | Passw0rd! | finance | active |
| viewer@byd.local | Passw0rd! | viewer | active |
