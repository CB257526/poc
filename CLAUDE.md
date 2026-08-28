# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

约稿费用验收系统：LangGraph 工作流（节点 0–6）+ FastAPI `/api/v1` + React 前端。HTTP 合同以 `frontend/docs/API.md` 为准；后端内部流程见 `src/workflows/backend/DESIGN.md`。整站部署看根目录 `部署启动手册.md`，纯 CLI 跑批看 `DEPLOY.md`，内网 Docker 看 `服务器部署手册.md`，不用 Docker 的内网隔离部署看 `内网部署.md`。

## 命令

所有后端 / CLI / 测试命令的 cwd 必须是**仓库根**，不要 `cd src`。包管理只认 `uv` + `pyproject.toml` / `uv.lock`，不要 `pip install`。

```bash
uv sync
uv run playwright install chromium          # 节点 2 抓页面；Linux 再加 install-deps
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --host 0.0.0.0 --port 8000
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --reload --host 0.0.0.0 --port 8000
PYTHONPATH=src uv run python scripts/init_db.py   # 可选；uvicorn 启动时也会建库+种子
uv run python -m workflows run --input table_test/1-链接.xlsx --table-dir ./table
uv run python -m workflows run --input table_test/1-链接.xlsx --output json
```

`pytest` 未写入 `pyproject.toml`。要跑测试先 `uv add --dev pytest`：

```bash
uv run pytest tests/ -q
uv run pytest tests/test_nodes.py -q
uv run pytest tests/test_nodes.py::test_node_03_normalize_name -q
```

前端（另开终端）：

```bash
cd frontend
cp env.example .env          # 首次；VITE_API_BASE_URL 默认 http://127.0.0.1:8000
npm install
npm run dev                  # http://127.0.0.1:5173，代理 /api → 8000
npm run build                # tsc --noEmit && vite build → frontend/dist
npm run preview
```

健康检查：`GET /health` → `{"status":"ok"}`。Swagger：`http://127.0.0.1:8000/docs`。

种子账号密码均为 `Passw0rd!`：`admin@byd.local`、`operator@byd.local`、`finance@byd.local`、`viewer@byd.local`。新注册默认 `operator` + `pending`，管理员在用户管理改成 `active` 后才能登录。

可选 MCP 观测（与 HTTP 后端分目录，默认不鉴权，不要对公网暴露）：

```bash
PYTHONPATH=src uv run python -m workflows.mcp_server --host 0.0.0.0 --port 8100 --path /mcp
```

## 架构

浏览器 → FastAPI → `run_workflow()`（LangGraph 节点 0–6）。backend 不改写节点，只负责收文件、落库、调工作流、回写进度与产物。

```
仓库根
├── src/workflows/
│   ├── backend/          FastAPI（main:app）；routers 在 backend/routers/
│   ├── nodes/            node_00 … node_06
│   ├── workflow_run.py   工作流入口
│   ├── paths.py          runtime/output/table 路径，环境变量可整段挪走
│   ├── utils/web_scraper.py + utils/parsers/   节点 2 抓页面
│   └── mcp_server.py     可选观测
├── frontend/             React + Vite；HTTP 合同 docs/API.md
├── table/                参考表 3/4/5（必填，按文件名前缀匹配）
├── table_test/           联调样例，不要当生产 table/
├── runtime/              SQLite、上传的表 1（自动创建）
└── output/{run_id}/      约稿资料、付款表（自动创建）
```

路径由 `workflows.paths` 统一：`WORKFLOW_RUNTIME_DIR`（默认 `runtime/`）、`WORKFLOW_OUTPUT_DIR`（`output/`）、`WORKFLOW_TABLE_DIR`（`table/`）。MCP 默认改用 `runtime-mcp/` / `output-mcp/`，不要和 HTTP 后端混用。

工作流：`node_00` 输入预检 → `node_01` 链接解析 → `node_02` Playwright 抓标题/日期/类型/截图 → `node_03` 媒体匹配 → `node_04` 账户补全 → `node_05` 费用计算 → `node_06` 生成约稿资料与付款表。表 2、表 6 由 node_06 写出，配置接口不要求也不接受这两张。

节点 2 会按主链接平台选解析器（知乎 / 微博 / B 站 / 微信 / 抖音 / 小红书 / 懂车帝 / 易车 / 今日头条 / 百家号 / 搜狐 / 快手，否则 generic）。知乎爬取：**推荐系统 Google Chrome 无头**；没有 Chrome 时回退 Playwright Chromium（知乎需 headful / Xvfb）。并发由 `WEB_SCRAPER_CONCURRENCY` 控制，默认 2。

SQLite：`runtime/backend.db`（用户/任务）+ `runtime/workflow.db`（工作流 checkpoint）。**uvicorn 只用 1 个 worker**，多进程会抢同一任务、写坏库。后台任务走 FastAPI BackgroundTasks（`backend/jobs.py`）。

鉴权：JWT 写在 `backend/auth.py`，`SECRET_KEY` 目前硬编码。CORS 写死 `http://127.0.0.1:5173` 与 `http://localhost:5173`（`backend/main.py`）。根目录 `.env.example` 里的 `SECRET_KEY` / `FRONTEND_URL` / `BACKEND_HOST` **当前代码并未读取**。前端 `VITE_API_BASE_URL` 只在 `npm run build` 时打进包；留空则请求走相对路径 `/api/...`（适合 nginx 同源反代）。

`config.yaml` 的 `llm.enabled` 为 false，运行时不调用外部 LLM。`frontend/requirements.txt` 是旧 Streamlit 残留，可忽略。`frontend/index.html` 引用了 Google Fonts，内网无外网时字体请求会失败（有系统中文字体兜底）。

生产构建：内网 Docker 双容器见 `服务器部署手册.md`。不用 Docker 时 nginx 托管 `frontend/dist`，把 `/api/` 反代到 `127.0.0.1:8000`，前端 `VITE_API_BASE_URL` 留空；或把 CORS 与 `VITE_API_BASE_URL` 一起改成真实 origin。
