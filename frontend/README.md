# 约稿平台前端

本目录是约稿平台的 Streamlit 前端，通过 HTTP API 调用 `src/workflows/` 中的 FastAPI 后端和节点 0—6 工作流。

## 目录结构

```text
frontend/
├── app.py              # Streamlit 页面与接口调用逻辑
├── requirements.txt    # 前端独立依赖
└── README.md           # 前后端联调说明
```

后端主要文件：

```text
src/workflows/api.py          # HTTP API
src/workflows/workflow_run.py # 工作流入口
src/workflows/nodes/          # 节点0—6
```

## 1. 启动后端

在第一个终端中执行：

```bash
cd /Users/yangtianyu/Desktop/BYD/poc
uv sync
uv run playwright install chromium
uv run uvicorn workflows.api:app --host 127.0.0.1 --port 8000
```

验证后端：

```bash
curl http://127.0.0.1:8000/health
```

正常返回：

```json
{"status":"ok"}
```

接口文档地址：`http://127.0.0.1:8000/docs`。

## 2. 启动前端

在第二个终端中执行：

```bash
cd /Users/yangtianyu/Desktop/BYD/poc
python -m pip install -r frontend/requirements.txt
python -m streamlit run frontend/app.py --server.port 8501
```

访问：`http://127.0.0.1:8501`。

## 3. 环境变量

前端默认连接本机 `8000` 端口：

```text
WORKFLOW_API_URL=http://127.0.0.1:8000
```

部署或连接其他后端时：

```bash
WORKFLOW_API_URL=https://api.example.com \
python -m streamlit run frontend/app.py
```

可配置项：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WORKFLOW_API_URL` | `http://127.0.0.1:8000` | 后端 API 根地址 |
| `WORKFLOW_API_TIMEOUT` | `30` | 前端接口超时秒数 |

后端可配置项：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WORKFLOW_TABLE_DIR` | `./table` | 媒体库、账户、费用等基础表目录 |
| `WORKFLOW_RUNTIME_DIR` | `./runtime` | 上传文件、任务和输出文件目录 |
| `CORS_ORIGINS` | `*` | 允许访问 API 的前端来源，多个值用逗号分隔 |

## 4. 真实业务流程

```text
上传 1-链接.xlsx
        ↓
节点0输入预检
        ↓
媒体名称是否全部匹配 3-媒体库.xlsx？
   ├─ 否：暂停 → 页面修改媒体名 → 重新执行节点0
   └─ 是：启动节点1—6
        ↓
查询任务状态
        ↓
下载约稿资料和付款文件
```

媒体名称匹配规则：

- 去除普通空格和全角空格。
- 英文名称忽略大小写。
- 必须唯一匹配媒体库中的一个标准媒体名称。
- 未匹配记录不会继续计算费用，也不会进入付款或月度汇总。
- 修正值通过原 Excel 行号与后端记录对应。

## 5. API 对接

### 5.1 上传并预检表1

```http
POST /api/v1/tasks/validate
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

<Excel 二进制内容>
```

需要修改媒体名称时：

```json
{
  "task_id": "任务ID",
  "status": "needs_correction",
  "records": [
    {
      "record_id": "rec_0001",
      "row_number": 16,
      "topic": "主题1",
      "media_name": "汽车之加",
      "link_count": 8,
      "link_preview": "https://example.com/..."
    }
  ],
  "allowed_media_names": ["汽车之家", "懂车帝"]
}
```

### 5.2 提交媒体名称修正

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

键是表1中的原始 Excel 行号，值是媒体库中的标准媒体名称。返回 `ready` 后才能启动后续工作流。

### 5.3 启动节点1—6

```http
POST /api/v1/tasks/{task_id}/run
```

成功返回 HTTP `202`：

```json
{
  "task_id": "任务ID",
  "status": "running"
}
```

### 5.4 查询任务状态

```http
GET /api/v1/tasks/{task_id}
```

状态值：

| 状态 | 含义 | 前端行为 |
| --- | --- | --- |
| `needs_correction` | 输入存在错误 | 展示修改面板，禁止继续 |
| `ready` | 输入预检通过 | 允许启动节点1—6 |
| `running` | 后台处理中 | 展示处理状态并定期查询 |
| `completed` | 处理完成 | 展示统计和下载按钮 |
| `failed` | 处理失败 | 展示问题信息，不计入月度汇总 |

### 5.5 下载结果文件

```http
GET /api/v1/tasks/{task_id}/files/quote_detail
GET /api/v1/tasks/{task_id}/files/payment
```

对应文件：

- `quote_detail`：完善后的 `2-约稿资料`。
- `payment`：生成的 `6-付款`。

### 5.6 查询当月累计与 TOP 媒体

```http
GET /api/v1/analytics/monthly?month=2026-08
```

不传 `month` 时默认查询当前自然月。接口只统计校验通过并成功完成的任务，返回批次数、约稿数量、总费用、平均每批费用、批次明细和 TOP 媒体。

## 6. 数据统计口径

只有同时满足以下条件的记录才允许进入财务和月度统计：

- 媒体名称唯一匹配。
- 媒体等级和粉丝量完整。
- 账户所需字段完整。
- 费用规则匹配成功。
- 记录被标记为 `processable=True`。
- 费用明细被标记为 `eligible_for_monthly_summary=True`。

待修改、待确认、匹配失败或处理失败的记录均不会进入：

- 约稿费用明细；
- 付款文件；
- 本次费用统计；
- 当月约稿数量；
- 当月费用汇总。

## 7. 开发说明

- 未上传文件时，前端使用模拟数据展示 UI 流程。
- 上传真实文件后，前端会调用 FastAPI，不再使用模拟处理结果。
- 原始 Excel 不会被覆盖；在线修正作为任务参数提交，最终生成新的结果文件。
- 当前 POC 的任务运行状态保存在后端内存中，服务重启后会丢失；已完成任务的月度统计会保存到 `runtime/workflow.db`。正式部署建议将任务状态也迁移到数据库或 Redis。

## 8. 常见问题

### 前端提示无法连接后端

确认后端已启动，并访问：

```text
http://127.0.0.1:8000/health
```

### Playwright 提示找不到 Chromium

```bash
uv run playwright install chromium
```

### 修改媒体名后仍不能继续

修正值必须来自接口返回的 `allowed_media_names`，并确保页面中所有未匹配记录都已修改。

### 错误数据是否计入当月统计

不会。后端在节点5和节点6分别执行过滤，避免异常记录进入费用、付款和月度汇总。
