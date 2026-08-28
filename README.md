# 约稿费用验收系统

工作流（LangGraph 节点 0–6）+ FastAPI `/api/v1` + React 前端。HTTP 合同以 `frontend/docs/API.md` 为准。

**从零部署（uv + 后端 + 前端）：** [部署启动手册.md](./部署启动手册.md)

**公司内网 Docker（推荐）：** [服务器部署手册.md](./服务器部署手册.md)

**不用 Docker 的内网隔离部署：** [内网部署.md](./内网部署.md)

## 结构

```
src/workflows/          工作流核心
  backend/              FastAPI（DESIGN.md / DEPLOY.md）
  nodes/                node_00 … node_06
frontend/               React
table/                  参考表 3/4/5
runtime/                SQLite、上传的表1（自动创建）
output/{run_id}/        约稿资料、付款表（自动创建）
```

## 快速启动（uv）

仓库根：

```bash
uv sync
uv run playwright install chromium  # 或系统装 Google Chrome（推荐，知乎无头可用）
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --host 0.0.0.0 --port 8000
```

另一个终端：

```bash
cd frontend
npm install
npm run dev
```

- 前端：http://127.0.0.1:5173
- API：http://127.0.0.1:8000/docs
- 健康检查：`GET /health` → `{"status":"ok"}`

种子账号密码均为 `Passw0rd!`：`admin@byd.local`、`operator@byd.local`、`finance@byd.local`、`viewer@byd.local`。

参考表放在 `table/`（3-媒体库 / 4-账户信息 / 5-费用）。表 2、表 6 由工作流生成，不必配置。
