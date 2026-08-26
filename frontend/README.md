# 约稿平台前端（React）

由 `app.py`（Streamlit POC）迁移而来的 React 单页应用。业务页面、处理流程、费用统计口径与原 Streamlit 版一致；额外补齐了登录 / 注册、角色权限、基础配置与用户管理。

Streamlit 源码仍保留在 `app.py`，仅作对照，不再作为运行入口。

## 技术栈

- Vite 7 + React 19 + TypeScript
- React Router 7
- Recharts（柱状图 / 折线图）
- 无 UI 组件库，样式对齐原 POC：品牌蓝 `#165DFF`、侧栏 `#102A56`

## 本地启动

```bash
cd frontend
cp env.example .env   # 首次
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

默认 `VITE_USE_MOCK=true`，不依赖后端即可走完全部页面。

对接真实后端时：

```bash
# .env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK=false
```

开发代理：`/api` → `http://127.0.0.1:8000`（见 `vite.config.ts`）。后端需允许前端来源 CORS。

## 演示账号

密码均为 `Passw0rd!`

| 邮箱 | 角色 | 说明 |
| --- | --- | --- |
| admin@byd.local | 管理员 | 全部页面 + 配置 / 用户审核 |
| operator@byd.local | 业务人员 | 上传处理、异常核验、导出 |
| finance@byd.local | 财务 | 查看资料 / 费用、下载付款文件 |
| viewer@byd.local | 只读访客 | 仅概览、约稿资料、费用分析 |
| new.user@byd.local | 待审核 | 无法登录 |

注册新账号后状态为「待审核」，需管理员在「用户管理」通过。

## 页面与角色

| 路由 | 页面 | admin | operator | finance | viewer |
| --- | --- | :---: | :---: | :---: | :---: |
| `/login` `/register` | 登录 / 注册 | 游客 | 游客 | 游客 | 游客 |
| `/` | 首页概览 | ✓ | ✓ | ✓ | ✓ |
| `/processing` | 数据处理 | ✓ | ✓ | | |
| `/quotes` | 约稿资料 | ✓ | ✓ | ✓ | ✓ |
| `/analytics` | 费用分析 | ✓ | ✓ | ✓ | ✓ |
| `/exceptions` | 异常提醒 | ✓ | ✓ | | |
| `/exports` | 文件输出 | ✓ | ✓ | ✓ | |
| `/config` | 基础配置 | ✓ | | | |
| `/users` | 用户管理 | ✓ | | | |

无权限访问时展示「无访问权限」，侧栏不显示对应入口。

## 业务处理流程（与原 Streamlit 一致）

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
├── app.py                 # 原 Streamlit，仅对照
├── docs/API.md            # 前端所需后端接口（后端开发以这份为准）
├── src/
│   ├── api/               # HTTP 客户端 + Mock 实现
│   ├── auth/              # 登录态、路由守卫
│   ├── layout/            # 侧栏布局
│   ├── mock/data.ts       # 演示数据
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
