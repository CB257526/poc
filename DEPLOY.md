# 约稿费用验收工作流 · CLI 跑批手册

整站（uv + FastAPI + React）请看仓库根目录 [部署启动手册.md](./部署启动手册.md)。下文只覆盖 **不走网页、用命令行跑工作流**。

本手册面向一台全新机器（macOS / Linux 服务器均可），从安装 `uv` 开始，直到能跑通完整流程并拿到 Excel 产物。

当前环境约定：

- 包管理：**uv**（不要用 pip 直接装依赖）
- Python：**>= 3.12**（仓库 `.python-version` 为 `3.14`，uv 会按这个版本拉解释器）
- 入口：`uv run python -m workflows run ...`
- 知乎爬取：**推荐安装系统 Google Chrome**，无头即可；没有 Chrome 时回退 Playwright Chromium（知乎需 headful / Xvfb）

---

## 0. 你将得到什么

输入：

| 文件 | 是否必须 | 作用 |
|------|----------|------|
| `table/1-链接.xlsx` | 必须（本次运行输入） | 主题、媒体、发布/同步链接 |
| `table/3-媒体库.xlsx` | 必须 | 媒体级别、粉丝量 |
| `table/4-账户信息.xlsx` | 必须 | 户名、身份证、卡号、电话、开户行 |
| `table/5-费用.xlsx` | 必须 | 等级 × 视频费用 / 图文费用 |
| `table/2-约稿资料.xlsx` | 否 | 仅样例，工作流**不会读取** |
| `table/6-付款.xlsx` | 否 | 仅样例，工作流**不会读取** |

输出（写到 `./output/<run_id>/`）：

- `2-约稿资料_完善版_YYYYMMDD_HHMMSS.xlsx`  
  Sheet：`约稿`、`约稿费用合计`
- `付款表_YYYYMMDD_HHMMSS.xlsx`  
  Sheet：`上传模板`（云账户 `TEMPLATE-BANK-YZH006`）

中间产物：`screenshots/`（嵌入「作品截图」列，可事后清理）。

---

## 1. 系统准备

### 1.1 确认操作系统

```bash
uname -s          # Darwin = macOS，Linux = 服务器
uname -m          # arm64 / x86_64
```

### 1.2 网络

需要能访问：

- GitHub / PyPI（或你们的镜像）——装 uv、Python、依赖
- Playwright 浏览器下载源
- 待爬平台（至少知乎；有微博等链接时还要能打开对应站点）

公司网络若拦截外网，先配好代理 / 镜像再继续。

### 1.3 Linux 浏览器（推荐系统 Chrome）

**新方案（2026-08）**：安装系统 Google Chrome，知乎可无头抓取，不需要 Xvfb。

Debian / Ubuntu：

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
google-chrome --version
```

或通过 APT 源（持续更新）：

```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install -y google-chrome-stable
```

RHEL / CentOS / Rocky：

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
sudo yum install -y ./google-chrome-stable_current_x86_64.rpm
```

macOS 自带 Chrome 可直接用；没有 Chrome 的话用 Homebrew：`brew install --cask google-chrome`。

**旧方案（回退）**：没有 Chrome 时用 Playwright 自带 Chromium，知乎仍需 headful（无桌面需 Xvfb）。

```bash
# Debian / Ubuntu
sudo apt-get install -y xvfb

# RHEL / CentOS
sudo yum install -y xorg-x11-server-Xvfb
```

命令要用 `xvfb-run -a` 包裹（见第 7 节）。**推荐直接装系统 Chrome**，更简洁。

---

## 2. 安装 uv

官方安装脚本（推荐）：

macOS / Linux：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

装完后让当前 shell 能找到命令（新开一个终端通常也会自动生效）：

```bash
# 常见安装位置
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

若公司禁止 curl 执行脚本，可改用 pipx / 包管理器，只要最终 `uv --version` 能跑即可。

验证：

```bash
uv --version
# 期望类似：uv 0.x.x
```

---

## 3. 拿到代码

```bash
git clone <本仓库地址> workflow
cd workflow
```

已在机器上的目录则直接 `cd` 进去。确认根目录有这些文件：

```
pyproject.toml
uv.lock
src/workflows/
table/
```

---

## 4. 安装 Python 与项目依赖

uv 会读取 `.python-version`（当前为 `3.14`）和 `uv.lock`，创建 `.venv` 并装齐依赖。

```bash
# 若本机还没有对应 Python，uv 会自动下载
uv python install

# 按 lockfile 同步虚拟环境（可复现）
uv sync
```

验证：

```bash
uv run python -c "import sys; print(sys.version); import playwright, openpyxl, PIL; print('ok')"
```

说明：

- **不要** `pip install -r ...`，依赖以 `uv.lock` 为准。
- `pytest` 未写进 `pyproject.toml`。要跑测试再执行：

```bash
uv add --dev pytest
```

日常只跑工作流可以不装 pytest。

---

## 5. 安装 Playwright 浏览器

**方案 A（推荐）**：用系统 Chrome，不装 Playwright 浏览器。

系统已有 Chrome（第 1.3 节装的）即可，爬虫会自动调用。

**方案 B（回退）**：没有系统 Chrome 时，装 Playwright 自带 Chromium。

```bash
uv run playwright install chromium
```

Linux 再装系统依赖（缺库时浏览器会秒崩）：

```bash
uv run playwright install-deps chromium
```

macOS 通常不需要 `install-deps`。

验证（无界面探测，不等于知乎能爬；知乎还要看是否有系统 Chrome）：

```bash
uv run python - <<'PY'
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com", wait_until="load")
        print("title:", await page.title())
        await browser.close()

asyncio.run(main())
PY
```

能打印 `Example Domain` 即 Chromium 可用。

---

## 6. 准备业务表格

把四张业务表放到 `table/`（文件名必须对得上，扩展名 `.xlsx`）：

```
table/
  1-链接.xlsx      # 每次运行的输入
  3-媒体库.xlsx
  4-账户信息.xlsx
  5-费用.xlsx
```

仓库里若已有样例表，可直接用来验收部署。换正式数据时只替换对应 xlsx，**不要改文件名**。

`1-链接` 约定（与 Node00 / Node01 一致）：

- 主题、媒体、链接
- 同一媒体多条链接写在同一单元格（多行文本）或按表结构展开
- 媒体名称必须能在 `3-媒体库` 里匹配到（去空格、忽略大小写）
- 主链接优先级：**知乎 > 微博 > 第一条**

`5-费用` 表头需含：`等级`、`视频费用`、`图文费用`。

---

## 7. 跑通第一次

在项目根目录：

### macOS / 有系统 Chrome 的 Linux

直接运行，无头抓取知乎（不会弹窗）：

```bash
uv run python -m workflows run --input table/1-链接.xlsx
```

指定表格目录：

```bash
uv run python -m workflows run \
  --input table/1-链接.xlsx \
  --table-dir ./table
```

### Linux 无桌面、没有 Chrome（回退 Xvfb）

如果用 Playwright Chromium 且有知乎链接，需要 Xvfb：

```bash
xvfb-run -a uv run python -m workflows run --input table/1-链接.xlsx
```

**推荐直接装系统 Chrome（见第 1.3 节），无需 Xvfb。**

样例表规模（约 6 条主链接）在本机大约 **20 秒**；服务器网络差会更久。
  --input table/1-链接.xlsx \
  --table-dir ./table
```

JSON 报告：

```bash
uv run python -m workflows run --input table/1-链接.xlsx --output json
```

### 无桌面 Linux（推荐系统 Chrome）

有系统 Chrome（第 1.3 节）时直接运行，无头模式：

```bash
uv run python -m workflows run --input table/1-链接.xlsx
```

没有 Chrome、用 Playwright Chromium 时需 Xvfb：

```bash
xvfb-run -a uv run python -m workflows run --input table/1-链接.xlsx
```

样例表规模（约 6 条主链接）在本机大约 **20 秒**；服务器网络差会更久。

成功时终端末尾类似：

```
完成节点: 7/7
Critical: 0 / Error: 0 / Warning: 0
payment: ./output/<run_id>/付款表_YYYYMMDD_HHMMSS.xlsx
quote_detail: ./output/<run_id>/2-约稿资料_完善版_YYYYMMDD_HHMMSS.xlsx
工作流成功完成
```

退出码：`0` 成功；有 critical 或未捕获异常为 `1`。

---

## 8. 验收产物

```bash
ls -l output/<run_id>/
```

打开约稿资料，至少确认：

- Sheet：`约稿`、`约稿费用合计`
- `约稿` 表头到「同步平台」（共 20 列）
- 有开户行、开户行所在城市、基础金额
- 末行「合计」+ `=SUM(R2:R…)`
- 同步链接很多的媒体，「平台」为「多平台」

打开付款表，至少确认：

- 只有 Sheet `上传模板`
- `A1` = `TEMPLATE-BANK-YZH006`
- 数据从第 5 行起：账号、户名、身份证、电话、基础服务费
- **没有**「付款汇总 / 约稿明细 / 月度汇总」

---

## 9. 常用调参

| 变量 / 项 | 默认 | 说明 |
|-----------|------|------|
| `WEB_SCRAPER_CONCURRENCY` | `2` | 同时打开的页面数。弱机（约 4C4G）建议保持 `1` 或 `2`，加大容易超时、被拦 |
| Playwright 超时 | 60s / 页 | 写在爬虫代码里，一般不用改 |
| `config.yaml` | 日志级别等 | 当前 CLI **主要靠命令行参数**；表格目录用 `--table-dir` |

弱服务器示例：

```bash
WEB_SCRAPER_CONCURRENCY=1 uv run python -m workflows run --input table/1-链接.xlsx
```

没有 Chrome、用 Chromium + Xvfb：

```bash
WEB_SCRAPER_CONCURRENCY=1 xvfb-run -a \
  uv run python -m workflows run --input table/1-链接.xlsx
```

---

## 10. 目录与权限

工作流会在项目根下写：

```
output/<run_id>/   # Excel 产物（gitignore）
runtime/           # CLI / HTTP 运行库 workflow.db
runtime-mcp/       # MCP 独立运行库（不要和后端混用）
screenshots/       # 临时截图（gitignore）
logs/              # 若启用文件日志
```

部署账号需要对项目目录可写。用 systemd / cron 时，`WorkingDirectory` 必须是仓库根目录，否则相对路径 `./table`、`./output` 会找不到。MCP 与 HTTP 后端同时跑时，务必分目录：`--runtime-dir` / `WORKFLOW_RUNTIME_DIR`。

cron 示例（每天 9 点，有系统 Chrome）：

```cron
0 9 * * * cd /opt/workflow && /home/deploy/.local/bin/uv run python -m workflows run --input table/1-链接.xlsx >> logs/cron.log 2>&1
```

没有 Chrome、用 Chromium + Xvfb：

```cron
0 9 * * * cd /opt/workflow && /usr/bin/xvfb-run -a /home/deploy/.local/bin/uv run python -m workflows run --input table/1-链接.xlsx >> logs/cron.log 2>&1
```

把 `/opt/workflow`、uv 路径换成实际位置。cron 环境没有交互 PATH，务必写绝对路径。

---

## 11. 测试（可选）

```bash
uv add --dev pytest    # 仅首次
uv run pytest tests/ -q
```

当前节点测试应全部通过。集成爬取不在单元测试里，以第 7 节真跑为准。

---

## 12. 故障排查

| 现象 | 处理 |
|------|------|
| `uv: command not found` | `export PATH="$HOME/.local/bin:$PATH"`，或重新装 uv |
| `requires-python >=3.12` | `uv python install` |
| `ModuleNotFoundError: playwright` | 在仓库根执行 `uv sync`，用 `uv run` 而不是系统 python |
| `Executable doesn't exist` / 浏览器启动失败 | 方案 A：`google-chrome --version` 确认系统 Chrome；方案 B：`uv run playwright install chromium`；Linux 再 `install-deps` |
| 知乎标题是安全验证 / 空白 / `zse-ck` | 日志看 `channel`：`chrome` 为系统 Chrome；`bundled-chromium` 为 Playwright 自带。自带版本被知乎拦，建议装系统 Chrome（第 1.3 节） |
| 知乎仍需 Xvfb / 弹窗 | 系统没有 Chrome，回退到自带 Chromium headful。装 Chrome 即可无头：`sudo apt install ./google-chrome-stable_current_amd64.deb` |
| `Timeout 60000ms exceeded` | 网络慢或并发太大。设 `WEB_SCRAPER_CONCURRENCY=1` 重跑 |
| `媒体库中没有这个媒体` | `1-链接` 的媒体名和 `3-媒体库` 不一致 |
| `NO_QUOTE_DETAILS` / 费用为 0 | 等级或文章类型没对上 `5-费用` |
| SSH 无 X11 且用自带 Chromium | Chromium headful 需要显示。方案 A：装系统 Chrome 走无头；方案 B：用 `xvfb-run -a` 包裹命令 |
| 权限错误写不了 Excel | 检查对 `output/`、`screenshots/` 的写权限 |

日志是 JSON 行，关键事件：`scraping_page`、`scraping_success`、`scraping_failed`、`workflow_completed`。

---

## 13. 最小检查清单

部署完成后按顺序打勾：

1. [ ] `uv --version` 正常  
2. [ ] `uv sync` 成功，`.venv` 存在  
3. [ ] Linux 已装系统 Chrome（推荐）或 Playwright Chromium  
4. [ ] `google-chrome --version` 能输出版本号（方案 A）或 `uv run playwright install chromium` 成功（方案 B）  
5. [ ] `table/` 中 3 / 4 / 5 三张表齐全（表 1 是每次输入，不要放这里）  
6. [ ] 完整命令退出码 0，节点 7/7  
7. [ ] `output/<run_id>/` 里约稿资料 2 个 Sheet、付款表为云账户模板  

全部完成后，这台机器就可以按第 10 节日常跑批。
