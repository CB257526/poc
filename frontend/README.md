# 约稿平台前端（React）

对接 `src/workflows/backend` 的 FastAPI（`/api/v1`）。页面与角色权限见 `docs/API.md`。

## 启动

先起后端（仓库根目录）：

```bash
uv sync
PYTHONPATH=src uv run uvicorn workflows.backend.main:app --host 0.0.0.0 --port 8000
```

再起前端：

```bash
cd frontend
cp env.example .env   # 首次
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。`VITE_API_BASE_URL` 默认 `http://127.0.0.1:8000`。开发时也可留空，走 Vite 代理 `/api` → 8000。

## 种子账号

密码均为 `Passw0rd!`（后端 `seed.py` 写入）

| 邮箱 | 角色 |
| --- | --- |
| admin@byd.local | 管理员 |
| operator@byd.local | 业务人员 |
| finance@byd.local | 财务 |
| viewer@byd.local | 只读 |

注册新账号后状态为「待审核」，需管理员在「用户管理」通过。

## 页面与角色

| 路由 | 页面 | admin | operator | finance | viewer |
| --- | --- | :---: | :---: | :---: | :---: |
| `/login` `/register` | 登录 / 注册 | 游客 | 游客 | 游客 | 游客 |
| `/` | 首页概览 | ✓ | ✓ | ✓ | ✓ |
| `/processing` | 数据处理 | ✓ | ✓ | | |
| `/quotes` | 约稿资料 | ✓ | ✓ | ✓ | ✓ |
| `/analytics` | 费用分析 | ✓ | ✓ | ✓ | ✓ |
| `/exports` | 文件输出 | ✓ | ✓ | ✓ | |
| `/config` | 基础配置 | ✓ | | | |
| `/users` | 用户管理 | ✓ | | | |

无权限访问时展示「无访问权限」，侧栏不显示对应入口。无任务时页面展示空态，不再使用演示数据。

## 业务处理流程

```text
上传 1-链接.xlsx
        ↓
POST /api/v1/tasks/validate   节点0 输入预检
        ↓
媒体名称是否全部匹配媒体库？
   ├─ 否：暂停 → 页面下拉修改 → POST .../corrections
   └─ 是：POST .../run 启动节点1—6
        ↓
轮询 GET /api/v1/tasks/{id}
        ↓
约稿资料 / 费用分析 / 下载文件
```

未匹配媒体名不会进入费用、付款和月度汇总。

## 目录

```text
frontend/
├── docs/API.md            # 前后端 HTTP 合同
├── src/
│   ├── api/               # 真实后端客户端
│   ├── auth/              # 登录态、路由守卫
│   ├── layout/            # 侧栏布局
│   ├── pages/             # 各业务页
│   └── types/             # 与接口对齐的类型
├── env.example
└── vite.config.ts
```

## 构建

```bash
npm run build
npm run preview
```
