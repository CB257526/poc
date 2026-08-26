# 约稿费用验收系统

工作流（LangGraph 节点 0–6）+ FastAPI `/api/v1` + React 前端。HTTP 合同以 `frontend/docs/API.md` 为准。

## 结构

```
src/workflows/          工作流核心
  backend/              FastAPI（见该目录 DESIGN.md / DEPLOY.md）
  nodes/                node_00 … node_06
frontend/               React
table/                  参考表 3/4/5（及可选 2/6）
runtime/                SQLite、上传的表1（自动创建）
output/{run_id}/        约稿资料、付款表（自动创建）
```

## 启动后端（uv）

在仓库根：

```bash
uv sync
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --host 0.0.0.0 --port 8000
```

- 文档：http://127.0.0.1:8000/docs
- 健康检查：`GET /health` → `{"status":"ok"}`

种子账号（密码均为 `Passw0rd!`）：`admin@byd.local`、`operator@byd.local`、`finance@byd.local`、`viewer@byd.local`。

更完整的接口流程、表1 如何入库、如何拉起工作流：`src/workflows/backend/DESIGN.md`。  
安装、环境变量、curl 联调：`src/workflows/backend/DEPLOY.md`。

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

http://127.0.0.1:5173 ，开发时请求后端 `http://127.0.0.1:8000`。
