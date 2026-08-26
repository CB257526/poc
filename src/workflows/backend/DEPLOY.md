# 后端部署与启动

包管理：**uv**（`pyproject.toml`）。不要用仓库根已经删掉的 `requirements-backend.txt` / `start-backend.sh`。

Python：`>=3.12`（本机当前 3.14 可用）。工作目录必须是**仓库根**，因为 hatch 包是 `src/workflows`。

---

## 1. 目录约定

在仓库根执行所有命令。

```
workflow/                          # 仓库根 = cwd
├── pyproject.toml
├── uv.lock
├── src/workflows/backend/         # FastAPI
├── table/                         # 参考表 2–6（工作流读取）
│   ├── 3-媒体库.xlsx              # 必填
│   ├── 4-账户信息.xlsx            # 必填
│   └── 5-费用.xlsx                # 必填
├── table_test/                    # 联调用的样例表1等，不要当生产 table/
├── runtime/                       # 自动创建：backend.db、uploads、workflow.db
└── output/{run_id}/               # 自动创建：约稿资料、付款表
```

Node00 启动时检查 `table/` 里 3/4/5 是否存在。缺文件工作流会 critical 失败。2、6 是模板/样例，管理员可通过配置接口覆盖。

---

## 2. 安装

```bash
cd /path/to/workflow
uv sync
```

后端额外依赖已写在 `pyproject.toml`：fastapi、uvicorn、sqlalchemy、python-jose、bcrypt、python-multipart、email-validator 等。不要再 `pip install` 一份平行环境。

可选：预装 Playwright 浏览器（节点 2 抓取页面用）。没装时抓取可能走降级/失败，视站点而定。

```bash
uv run playwright install chromium
```

---

## 3. 环境变量

可选。不设则用仓库内默认路径。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `WORKFLOW_RUNTIME_DIR` | `<repo>/runtime` | SQLite、表1 上传 |
| `WORKFLOW_OUTPUT_DIR` | `<repo>/output` | 每次 run 的 xlsx |
| `WORKFLOW_TABLE_DIR` | `<repo>/table` | 媒体库/账户/费用 |
| `WORKFLOW_INPUT_FILE` | `table/1-链接.xlsx` | 仅 CLI 工作流默认输入；HTTP 不用这个，HTTP 用上传路径 |

JWT 密钥目前写在 `auth.py` 的 `SECRET_KEY`。上生产前改掉。

CORS 允许：`http://127.0.0.1:5173`、`http://localhost:5173`。

---

## 4. 启动

数据库和种子账号在 **uvicorn 启动时自动创建**，一般不必单独跑 init。

```bash
cd /path/to/workflow
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --host 0.0.0.0 --port 8000
```

开发热重载：

```bash
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --reload --host 0.0.0.0 --port 8000
```

手动灌库（可选）：

```bash
PYTHONPATH=src uv run python scripts/init_db.py
```

健康检查：

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}
```

- API：http://127.0.0.1:8000
- Swagger：http://127.0.0.1:8000/docs
- 前端开发服默认打 `http://127.0.0.1:8000/api/v1`

若出现 `ModuleNotFoundError: workflows`：确认 cwd 是仓库根，且带了 `PYTHONPATH=src`（或已 `uv sync` 把包装进当前环境）。不要 `cd src` 再启动。

若 `Address already in use`：换端口或杀掉占用 8000 的进程。

---

## 5. 种子账号

首次启动写入，已存在则不覆盖密码。

| 邮箱 | 角色 | 密码 |
| --- | --- | --- |
| admin@byd.local | admin | Passw0rd! |
| operator@byd.local | operator | Passw0rd! |
| finance@byd.local | finance | Passw0rd! |
| viewer@byd.local | viewer | Passw0rd! |

新注册用户默认 operator + pending，管理员在用户页 PATCH `status=active` 后才能登录。

登录：

```bash
curl -s http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@byd.local","password":"Passw0rd!"}'
```

成功体是 `{ "user": {...}, "tokens": { "access_token", "refresh_token", "token_type": "bearer", "expires_in": 7200 } }`。后续请求：

```
Authorization: Bearer <access_token>
```

---

## 6. 准备参考表

把 3/4/5 放到 `table/`（文件名必须带「3-媒体库」这种前缀，工作流按文件名找）。

也可以登录管理员后上传：

```bash
TOKEN=...
curl -s http://127.0.0.1:8000/api/v1/config/files \
  -H "Authorization: Bearer $TOKEN" \
  -F kind=media_library \
  -F file=@./table_test/3-媒体库.xlsx
```

`kind`：`quote_template` | `media_library` | `accounts` | `fee_rules` | `payment_template`。上传会覆盖 `table/` 里对应规范文件名。

`GET /api/v1/config` 看五项是否 `configured`。`all_ready=true` 后处理页才亮绿灯。

---

## 7. 跑一条完整任务（联调）

表1 必须是 **xlsx 二进制 body**，不是 JSON，也不是默认 multipart 字段名以外的东西。

```bash
TOKEN=...   # operator 或 admin
curl -s http://127.0.0.1:8000/api/v1/tasks/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  --data-binary @./table_test/1-链接.xlsx
```

返回 `task_id` + `status`：

- `needs_correction`：按 `records[].row_number` 提交标准名
  ```bash
  curl -s http://127.0.0.1:8000/api/v1/tasks/$TASK/corrections \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"media_name_corrections":{"16":"汽车之家"}}'
  ```
- `ready`：启动
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/v1/tasks/$TASK/run \
    -H "Authorization: Bearer $TOKEN"
  ```

轮询（节点 2 会抓网页，可能几十秒）：

```bash
curl -s http://127.0.0.1:8000/api/v1/tasks/$TASK \
  -H "Authorization: Bearer $TOKEN"
```

`status=completed` 且 `progress.completed_nodes` 长度为 7 即成功。产物在 `output/<run_id>/`。下载：

```bash
curl -OJ http://127.0.0.1:8000/api/v1/tasks/$TASK/files/quote_detail \
  -H "Authorization: Bearer $TOKEN"
curl -OJ http://127.0.0.1:8000/api/v1/tasks/$TASK/files/payment \
  -H "Authorization: Bearer $TOKEN"
curl -OJ http://127.0.0.1:8000/api/v1/tasks/$TASK/files/archive \
  -H "Authorization: Bearer $TOKEN"
```

finance 可以下载，不能 validate/run。viewer 只能看任务和统计。

---

## 8. 前端一起开

```bash
cd frontend
npm install
npm run dev
```

浏览器 http://127.0.0.1:5173 ，接口打到 8000。确认后端 CORS 已包含该 origin。

---

## 9. 常见问题

**登录 422 / 邮箱校验失败**  
当前实现已不再用 EmailStr。若仍 422，确认打的是 `/api/v1/auth/login` 且 JSON 字段是 `email` / `password`。

**validate 400「尚未配置媒体库」**  
`table/3-媒体库.xlsx` 不存在。先放文件或走配置上传。

**run 409 TASK_CONFLICT**  
任务不是 `ready`（还在 needs_correction / 已经 running / completed）。

**工作流 failed**  
看 `GET /tasks/{id}` 的 `error`，以及控制台 structlog。典型原因：缺 3/4/5、表1 解析失败、节点 critical。失败任务不进月度统计。

**循环导入 / 起不来**  
`workflows.runtime` 已对 `start_workflow_job` 做惰性导入。从仓库根、`PYTHONPATH=src` 启动。

**换机器 / 清数据**  
删 `runtime/backend.db` 会丢掉用户和任务元数据；`runtime/uploads` 是表1；`output/` 是产物。参考表在 `table/`，清库不会删 xlsx。

**生产建议**  
改 JWT 密钥；不要把种子密码用于公网；用进程管理（systemd / supervisor）跑 uvicorn；`table/` 与 `runtime/` 做备份；单 worker 即可（SQLite + BackgroundTasks 不适合多进程抢同一任务）。
