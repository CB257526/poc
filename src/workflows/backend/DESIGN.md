# 后端设计说明

本文描述 `src/workflows/backend/` 的实际实现，与前端合同 `frontend/docs/API.md` 对齐。HTTP 契约以 API.md 为准；本文讲后端内部怎么走。

- 入口：`workflows.backend.main:app`
- 前缀：`/api/v1`
- 鉴权：`Authorization: Bearer <access_token>`
- 错误体：`{ "detail": "...", "code": "...", "field_errors": { ... } }`

---

## 1. 目录与职责

```
src/workflows/backend/
├── main.py            FastAPI 应用、CORS、错误处理、启动种子
├── database.py        SQLite 引擎（runtime/backend.db）
├── models.py          User / Task / ConfigFile / FeeException
├── auth.py            bcrypt、JWT、get_current_user、require_role
├── errors.py          ApiError
├── seed.py            种子账号、id 生成
├── config_store.py    配置表 kind → table/ 落盘
├── task_support.py    表1预检、任务 JSON、入账口径、异常比对
├── jobs.py            后台调用 run_workflow，回写进度与产物
└── routers/
    ├── auth.py
    ├── users.py
    ├── config.py
    ├── tasks.py       含文件下载
    ├── dashboard.py
    ├── analytics.py
    └── exceptions.py
```

工作流本身不在 backend 里改写。backend 只负责：收文件、落库、调用

```python
run_workflow(
    input_file=task.input_file_path,
    table_dir=str(default_table_dir()),   # 默认仓库 table/
    config={"media_name_corrections": {...}},
    run_id=task.run_id,
    on_progress=...,
)
```

节点：`node_00` 输入预检 → `node_01` 链接解析 → `node_02` 资料整理 → `node_03` 媒体匹配 → `node_04` 账户补全 → `node_05` 费用计算 → `node_06` 付款生成。

---

## 2. 路径与数据落盘

由 `workflows.paths` 统一：

| 用途                   | 默认                    | 环境变量                 |
| ---------------------- | ----------------------- | ------------------------ |
| 后端 SQLite、上传的表1 | `runtime/`            | `WORKFLOW_RUNTIME_DIR` |
| 工作流运行库           | `runtime/workflow.db` | 同上                     |
| 参考表 3/4/5           | `table/`              | `WORKFLOW_TABLE_DIR`   |
| 一次运行产物           | `output/{run_id}/`    | `WORKFLOW_OUTPUT_DIR`  |

一次任务对应的文件：

- 表1：`runtime/uploads/{task_id}.xlsx`（原始二进制，修正时不改这个文件）
- 媒体库 / 账户 / 费用：`table/3-媒体库.xlsx`、`4-账户信息.xlsx`、`5-费用.xlsx`
- 约稿资料、付款表：`output/{run_id}/2-约稿资料_完善版_{ts}.xlsx`、`付款表_{ts}.xlsx`

`run_id` 与 `task_id` 都是字符串。工作流按 `run_id` 隔离产物。

---

## 3. 启动时做什么

`main.on_startup`：

1. `init_db()`：`create_all` 建表（SQLite WAL + FK）
2. `seed_users()`：四个 active 账号（已存在则跳过）
3. `ensure_config_rows()`：扫 `table/`，把已有 xlsx 标成 `configured=true`

种子：

| id      | email              | role     | 密码      |
| ------- | ------------------ | -------- | --------- |
| u_admin | admin@byd.local    | admin    | Passw0rd! |
| u_op    | operator@byd.local | operator | 同上      |
| u_fin   | finance@byd.local  | finance  | 同上      |
| u_view  | viewer@byd.local   | viewer   | 同上      |

---

## 4. 鉴权

JWT：`sub` = 用户字符串 id，`type` = `access` | `refresh`。

- access 7200 秒，refresh 7 天
- 密码：`bcrypt.hashpw` / `checkpw`（不用 passlib）
- 未带 token / token 无效：`401 UNAUTHENTICATED`
- pending 登录：`403 ACCOUNT_PENDING`；disabled：`403 ACCOUNT_DISABLED`
- 角色不够：`403 FORBIDDEN`

`@byd.local` 被 email-validator 当成保留域，登录/注册用普通字符串，只检查含 `@`。

角色矩阵见 API.md 第 0 节。实现就是 `require_role("admin", "operator")` 这类依赖。

---

## 5. 接口流程

### 5.1 认证 `/api/v1/auth`

**POST `/login`**

1. 规范化 email（strip + lower）
2. 查用户；密码不对 → `401 INVALID_CREDENTIALS`
3. 看 `status`：pending / disabled / 非 active 分别 403
4. 写 `last_login_at`
5. 返回 `{ user, tokens }`，**不是**扁平 TokenResponse

**POST `/register`** → 201，`role=operator`、`status=pending`，不能立刻登录。邮箱占用 `409 EMAIL_TAKEN`。

**GET `/me`** → User。**POST `/logout`** → `{ok:true}`（当前不维护服务端黑名单）。**POST `/refresh`** 用 refresh JWT 换新 tokens。

### 5.2 用户 `/api/v1/users`（admin）

**GET /** 全量数组，pending 优先。

**PATCH `/{user_id}`** `{role?, status?}`。不能停用自己。

### 5.3 配置 `/api/v1/config`

三个 kind：`media_library` / `accounts` / `fee_rules`（对应 `table/` 里的 3/4/5）。表 2、表 6 由工作流固定生成，不进配置。

磁盘文件名：

- `3-媒体库.xlsx`
- `4-账户信息.xlsx`
- `5-费用.xlsx`

**GET `/config`**（已登录）：扫磁盘 + 库，返回 `{ all_ready, files[3] }`。缺文件则该项 `configured=false`。`all_ready` 只看这三项。

**POST `/config/files`**（admin，multipart：`kind` + `file`）：

1. kind 非法或非 xlsx → 400
2. 字节写入 `table/` 的规范文件名（覆盖）
3. 更新 `config_files` 行：`configured=true`、`updated_by=admin.id`
4. 返回最新整个 ConfigStatus

工作流读表只看 `table/` 路径，不读数据库里的 blob。

### 5.4 上传表 1：`POST /api/v1/tasks/validate`

这是前端处理页的入口。前端把 `1-链接.xlsx` **整文件当 body** 打过来：

```
POST /api/v1/tasks/validate
Authorization: Bearer <admin|operator>
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
<body = xlsx bytes>
```

也兼容 `multipart/form-data` 字段 `file`。

后端逐步做：

1. **鉴权**：仅 admin / operator。finance / viewer → 403。
2. **读字节**：raw body 或 multipart。空文件 / 非 xlsx → 400 `VALIDATION_ERROR`。
3. **落盘**：`runtime/uploads/{task_id}.xlsx`。`task_id`、`run_id` 此时就生成。这个路径之后会原样传给 `run_workflow(input_file=...)`。
4. **预检 `preview_validate(path)`**（不跑节点 1–6）：
   - 用 `ExcelService.read_link_sheet` 解析分层表（主题行 / 媒体+链接 / 续链接）
   - 用 Node00 的 `_merge_duplicate_media` 按主题+媒体合并
   - 读 `table/3-媒体库.xlsx`，名称归一化（去空格/全角空格、小写）后比对
   - 每条记录带原 Excel `row_number`（修正接口的 key）
   - 未命中：`match_status=unmatched`，`issues[].code=MEDIA_NOT_IN_LIBRARY`，并给 `suggested_name`
5. **建 Task 行**：`status` 为 `ready`（全匹配）或 `needs_correction`。JSON 列写入 records / issues / allowed_media。进度先记 `completed_nodes=["node_00"]`。
6. **返回 ValidateTaskResponse**：`task_id, status, allowed_media_names, records, issues`。

预检失败（读不出媒体/链接）会删掉刚写的上传文件并 400。

注意：预检通过 **不等于** 工作流已跑。此时还没有约稿资料、没有付款表。前端看到 `ready` 会立刻 POST `/run`。

### 5.5 修正媒体名：`POST /api/v1/tasks/{id}/corrections`

仅 `needs_correction`，否则 `409 TASK_CONFLICT`。

Body：`{ "media_name_corrections": { "<row_number>": "<媒体库标准名>" } }`。

1. value 必须在 `allowed_media_names`，否则 `422 UNPROCESSABLE`
2. 合并进 `task.corrections_json`（按行号累积，不改原始 xlsx）
3. 再次 `preview_validate(path, corrections)`：预检时用修正名替换该行媒体
4. 全过 → `ready`；仍有未匹配 → 继续 `needs_correction`

真正跑工作流时，同一份 dict 作为 `config["media_name_corrections"]` 交给 Node00，Node00 按 `row_number` 覆盖后再走完整校验。

### 5.6 启动工作流：`POST /api/v1/tasks/{id}/run`

仅 `ready` → `202 { task_id, status: "running" }`。

1. 把 Task 标成 `running` 并 commit
2. FastAPI `BackgroundTasks` 调 `jobs.execute_workflow(task_id)`，接口立刻返回
3. 前端每 1.5s `GET /tasks/{id}` 看 progress

`execute_workflow`：

1. 读 Task：`input_file_path`、`corrections_json`、`run_id`
2. 调 `run_workflow(...)`，`table_dir` 固定当前 `table/`
3. `on_progress` 每完成一个节点写 `progress_json`（`completed_nodes`、`current_node`、`total_nodes=7`）
4. 结束：
   - 失败 / terminated / critical → `failed`，`error` 中文原因，不入月度
   - 成功 → `completed`；从 context 抽 **可入账** 明细（`eligible_for_monthly_summary is True`）写成英文 `quote_summary`；记下 quote/payment 绝对路径
5. 对照「约稿」与「约稿费用合计」两个 sheet，不一致则插入 `exceptions`（待确认）

产物目录：`output/{run_id}/`。下载接口读 Task 上存的绝对路径，不扫目录猜文件。

### 5.7 查任务

**GET `/tasks/{id}`**（已登录）→ Task：status、progress、quote_summary、files、issues。运行中 `quote_summary` 可为 null。

**GET `/tasks/latest`** → 最近一条；没有则 JSON `null`（200）。

### 5.8 下载

admin / operator / finance。viewer 403。任务未 `completed` → 409。

- `GET /tasks/{id}/files/quote_detail` → 完善后的约稿资料 xlsx
- `GET /tasks/{id}/files/payment` → 付款表 xlsx
- `GET /tasks/{id}/files/archive` → zip，两个 xlsx 都打进去。`Content-Disposition` 用 RFC 5987（中文文件名不能直接放 latin-1 头）

### 5.9 首页 `GET /dashboard/overview`

已登录。数字只来自 **最近一条任务且已 completed** 的 `quote_summary`（可入账口径）。没有完成任务时 `latest_task=null`、计数 0，不造假数据。

`pending_exceptions`：`exceptions.status != 已解决` 的条数。`config_ready` 来自配置三项（媒体库 / 账户 / 费用）是否齐。

### 5.10 月度 `GET /analytics/monthly?month=YYYY-MM`

只统计 `completed` 任务里 `quote_summary.details`。每条明细按 **`publish_date` 所在月** 归入，不是按任务完成月。缺日期才退回任务 `updated_at`。

图文：`图文` / `文章` / `图文类`；视频：`视频` / `视频类`。无数据返回全 0 + 空数组，不 404。

### 5.11 异常 `/api/v1/exceptions`

工作流成功后比对两个子表：

- `detail_fee`：约稿 sheet 按媒体加总（基础金额 + 奖励金额）
- `summary_fee`：约稿费用合计 sheet 的合计费用

不一致才建异常，状态 `待确认`。完全一致不建（或把旧异常标已解决）。

**GET /** 可带 `task_id`。返回数组。

**PATCH `/{exception_id}`** `{ summary_fees: { 媒体名: 金额 } }`：

- 每个媒体必须 `summary == detail`，否则 `400 AMOUNTS_MISMATCH`
- 通过则回写 xlsx「约稿费用合计」，状态改 `待校对`

**POST `/reaudit`**：所有「待校对且已有 correction」→ `已解决`，返回 `{resolved, remaining}`。

---

## 6. 任务状态机

```
validate ──► needs_correction ──corrections──► ready ──run──► running ──► completed
                 │                                  │              └──► failed
                 └──仍不匹配─────────────────────────┘
```

非法跳转一律 `409 TASK_CONFLICT`（例如 completed 再 run、ready 时 corrections）。

---

## 7. 入账口径

月度、首页、quote_summary.details **只含**：

- 任务 `status=completed`
- 明细 `eligible_for_monthly_summary is True`（Node05/06 已过滤未匹配、不可处理记录）

failed / 未匹配 / 待确认费用 **不得** 进月度数字。异常页本身是人工核验层，不替代入账过滤。

---

## 8. 和前端的对应关系

前端 `frontend/src/api/index.ts` 调的就是这些路径。不要再实现已删除的旧 API（无 `/api/v1`、整数 task id、multipart validate、`/config/upload/{kind}` 等）。
