# 知乎无头爬取方案（2026-08）

## 问题

Playwright 自带的 Chromium 无头模式会被知乎识别并重定向到 `unhuman` 安全验证页，无法获取标题、日期等信息。旧方案要求知乎链接必须走 `headless=False`（弹出浏览器窗口），在无桌面的 Linux 服务器上需要 Xvfb 虚拟显示。

## 解决方案

**系统安装的 Google Chrome 无头模式可以过知乎反爬。**

Playwright 的 `channel="chrome"` 可以调用系统 Chrome 而不是自带的 Chromium。实测该 Chrome 在 `headless=True` 下能正常抓取知乎标题、日期、文章类型和截图，无需弹窗或 Xvfb。

### 技术原理

知乎的反爬机制能识别 Playwright 自带 Chromium 的浏览器指纹，但无法识别正式发布的 Google Chrome。启动参数 `channel="chrome"` + `headless=True` + stealth JS 隐藏自动化特征后，知乎将其视为普通无头 Chrome 浏览器。

### 代码实现

`src/workflows/utils/web_scraper.py` 已更新：

1. 优先尝试 `channel="chrome"` 启动系统 Chrome（无头）
2. 如果系统没有 Chrome，回退到 Playwright 自带 Chromium（知乎仍需 headful / Xvfb）
3. 环境变量 `WEB_SCRAPER_BROWSER` 可强制选择：
   - `chrome`: 只用系统 Chrome
   - `bundled` / `playwright`: 只用自带 Chromium
   - 默认：先试 Chrome，失败再试 Chromium

### Ubuntu 服务器部署

#### 1. 安装 Google Chrome（稳定版）

```bash
# 下载官方 .deb 包
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 安装（会自动拉依赖）
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# 验证
google-chrome --version
# Google Chrome 131.0.6778.108
```

或通过 APT 源（持续更新）：

```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install -y google-chrome-stable
```

#### 2. 去掉 Xvfb（不再需要）

旧的 systemd service 配置：

```ini
# 旧方案（不再需要）
ExecStart=/usr/bin/xvfb-run -a /opt/workflow/.venv/bin/uvicorn ...
```

新配置（直接启动）：

```ini
# 新方案
ExecStart=/opt/workflow/.venv/bin/uvicorn workflows.backend.main:app --host 127.0.0.1 --port 8000
```

不再需要：
- ❌ `sudo apt install xvfb`
- ❌ `xvfb-run -a` 包裹命令
- ❌ `DISPLAY` 环境变量

#### 3. Playwright 浏览器（可选）

如果服务器没有外网或无法安装 Chrome，仍可用 Playwright 自带 Chromium：

```bash
uv run playwright install chromium
uv run playwright install-deps chromium  # Linux 系统库
```

此时知乎链接会回退到 headful 模式，仍需 Xvfb。但**推荐直接装系统 Chrome**，无头更简洁。

### 内网/离线部署

构建机（能联网）：

```bash
# 下载 Chrome .deb
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 拷贝到 vendor/
cp google-chrome-stable_current_amd64.deb vendor/
```

生产机（隔离内网）：

```bash
sudo apt install -y /opt/workflow/vendor/google-chrome-stable_current_amd64.deb
```

### 环境变量

| 变量 | 值 | 说明 |
|---|---|---|
| `WEB_SCRAPER_BROWSER` | `chrome` / `bundled` / 空 | 强制浏览器选择；默认先试 Chrome |
| `WEB_SCRAPER_HEADLESS` | `1` | 强制无头（测试用，生产不要设） |
| `WEB_SCRAPER_HEADFUL` | `1` | 强制弹窗（调试用） |
| `WEB_SCRAPER_CONCURRENCY` | `2` | 并发页面数 |

### 验证

```bash
# 测试知乎抓取（本地）
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from workflows.utils.web_scraper import scrape_publications
records = [{
    'id': '1',
    'primary_link': 'https://www.zhihu.com/question/1997735046166099243/answer/1997772213143766041',
    'primary_platform': '知乎'
}]
print(asyncio.run(scrape_publications(records))[0].get('scraped_title'))
"
```

日志应显示：
```
{"channel": "chrome", "headless": true, "has_zhihu": true, "event": "browser_launched"}
{"event": "scraping_success", "title": "比亚迪起诉..."}
```

### 回退路径

1. 系统有 Chrome → 无头运行 ✅
2. 没有 Chrome，有 Playwright Chromium → 知乎走 headful（需 Xvfb）⚠️
3. 都没有 → 启动失败 ❌

推荐部署时直接装系统 Chrome，覆盖路径 1。

### 对比

|  | 旧方案 | 新方案（Chrome 无头） |
|---|---|---|
| Ubuntu 无桌面 | 需要 Xvfb | **不需要** |
| systemd 配置 | `xvfb-run -a ...` | 直接 `uvicorn ...` |
| 浏览器 | Playwright Chromium | 系统 Google Chrome |
| 知乎模式 | headful（弹窗） | headless（后台） |
| 依赖安装 | `apt install xvfb` + `playwright install chromium` | `apt install google-chrome-stable` |
| 日志特征 | `headless=False` | `headless=True, channel=chrome` |

### 已知限制

- **系统 Chrome 版本**：需 Chrome 90+；Ubuntu 20.04+ 官方源的版本可用
- **ARM 架构**：Google 官方不提供 ARM64 Linux Chrome；ARM 服务器仍需 Chromium + Xvfb
- **其他平台**：微博、B站、抖音等在 Playwright Chromium 无头下正常，不受此问题影响

### 更新日志

- 2026-08-27: 实现 Chrome 无头方案，去掉知乎必须 Xvfb 的限制
- 之前: 知乎强制 headful，Linux 无桌面需 Xvfb
