"""网页爬取服务 - 基于Playwright异步并发"""

import asyncio
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from workflows.services import get_logger
from workflows.utils.parsers import get_parser

logger = get_logger()

# 必须覆盖 headless Chrome 自带的 HeadlessChrome UA，否则知乎会直接返回异常 JSON。
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

STEALTH_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
            {name: 'Native Client', filename: 'internal-nacl-plugin'}
        ]
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en']
    });
"""

_TRUE_FLAGS = {"1", "true", "yes", "on"}
_SYSTEM_CHANNELS = {"chrome", "chromium", "msedge", "chrome-beta", "chrome-dev"}

# 这些状态码几乎不可能再解析出标题/日期，继续等 networkidle / 截图只会拖死整批。
# 不含 403/429：知乎反爬经常先给 403，真实 Chrome 仍可能渲染出正文。
FAIL_FAST_STATUS = {400, 401, 404, 405, 410, 451, 500, 502, 503, 504}

NETWORK_ERROR_MARKERS = (
    "net::ERR_NAME_NOT_RESOLVED",
    "net::ERR_CONNECTION_REFUSED",
    "net::ERR_CONNECTION_TIMED_OUT",
    "net::ERR_CONNECTION_RESET",
    "net::ERR_CONNECTION_ABORTED",
    "net::ERR_INTERNET_DISCONNECTED",
    "net::ERR_ADDRESS_UNREACHABLE",
    "net::ERR_NETWORK_CHANGED",
    "net::ERR_EMPTY_RESPONSE",
    "net::ERR_TIMED_OUT",
    "net::ERR_SSL_PROTOCOL_ERROR",
    "net::ERR_CERT_",
    "NS_ERROR_UNKNOWN_HOST",
    "NS_ERROR_CONNECTION_REFUSED",
)

_MISSING_PAGE_MARKERS = (
    "404 not found",
    "404页面",
    "页面不存在",
    "找不到页面",
    "内容不存在",
    "该内容已被删除",
    "page not found",
    "sorry, the page you visited does not exist",
)

# 知乎对云服务器 IP 段反爬极严：www.zhihu.com / api.zhihu.com 直连会 403。
# 但 link.zhihu.com 短链中转页不设防，会种下 _xsrf/BEC cookie 再 JS 跳到目标，
# 从同一 context 跟过去就能拿到正文。本地（住宅 IP）可绕过，服务器必须走这条。
_ZHIHU_LINK_BASE = "https://link.zhihu.com/?target="


def _env_flag(name: str, env: Optional[Mapping[str, str]] = None) -> bool:
    raw = (env if env is not None else os.environ).get(name, "").strip().lower()
    return raw in _TRUE_FLAGS


def _env_int(name: str, default: int, env: Optional[Mapping[str, str]] = None) -> int:
    raw = (env if env is not None else os.environ).get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def looks_like_missing_page(title: str) -> bool:
    """HTTP 仍可能是 200，但标题已经是站点自己的 404 页。"""
    text = (title or "").strip().lower()
    if not text:
        return False
    if text in {"404", "404 not found"}:
        return True
    return any(marker in text for marker in _MISSING_PAGE_MARKERS)


def classify_scrape_failure(
    status: Optional[int],
    final_url: str = "",
    error: Optional[str] = None,
) -> Optional[str]:
    """能立刻判定打不开时返回原因，否则 None（继续解析）。"""
    err = error or ""
    if err:
        if "Timeout" in err or "timeout" in err.lower():
            return f"页面加载超时: {err[:200]}"
        for marker in NETWORK_ERROR_MARKERS:
            if marker in err:
                return f"网络错误: {marker}"
        if "net::ERR_" in err:
            return f"网络错误: {err[:200]}"

    url = (final_url or "").lower()
    if url.startswith("chrome-error://") or url.startswith("chrome://network-error"):
        return "网络错误: 浏览器无法打开该地址"

    if status is not None and status in FAIL_FAST_STATUS:
        return f"HTTP {status}"
    return None


def resolve_channel_candidates(
    env: Optional[Mapping[str, str]] = None,
) -> List[Optional[str]]:
    """
    决定按什么顺序尝试启动浏览器。

    None 表示 Playwright 自带的 Chromium。知乎能识别这份 Chromium 的无头指纹，
    所以默认先试本机 Google Chrome（channel=chrome），失败再回退自带浏览器。
    """
    source = env if env is not None else os.environ
    requested = source.get("WEB_SCRAPER_BROWSER", "").strip().lower()
    if requested in {"bundled", "playwright"}:
        return [None]
    if requested in _SYSTEM_CHANNELS:
        return [requested, None]
    return ["chrome", None]


def resolve_headless(
    has_zhihu: bool,
    using_system_browser: bool,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """
    True = 无头。本机 Chrome 无头即可过知乎；自带 Chromium 抓知乎仍需有界面。
    WEB_SCRAPER_HEADFUL=1 强制弹窗；WEB_SCRAPER_HEADLESS=1 强制无头。
    """
    source = env if env is not None else os.environ
    if _env_flag("WEB_SCRAPER_HEADFUL", source):
        return False
    if _env_flag("WEB_SCRAPER_HEADLESS", source):
        return True
    if using_system_browser:
        return True
    return not has_zhihu


async def _launch_browser(playwright, has_zhihu: bool) -> Browser:
    """优先用本机 Chrome 无头；没有 Chrome 时回退自带 Chromium（知乎仍走 headful）。"""
    last_error: Optional[Exception] = None
    for channel in resolve_channel_candidates():
        using_system = channel is not None
        headless = resolve_headless(has_zhihu, using_system)
        launch_kwargs: Dict[str, object] = {
            "headless": headless,
            "args": BROWSER_LAUNCH_ARGS,
        }
        if channel:
            launch_kwargs["channel"] = channel
        try:
            browser = await playwright.chromium.launch(**launch_kwargs)
            logger.info(
                "browser_launched",
                channel=channel or "bundled-chromium",
                headless=headless,
                has_zhihu=has_zhihu,
            )
            return browser
        except Exception as e:
            last_error = e
            logger.warning(
                "browser_launch_failed",
                channel=channel or "bundled-chromium",
                headless=headless,
                error=str(e),
            )
    raise last_error if last_error else RuntimeError("未能启动浏览器")


class WebScraperService:
    """网页爬取服务 - 使用Playwright headless模式"""

    def __init__(self, max_concurrent: int = 5, timeout: int = 30000):
        """
        Args:
            max_concurrent: 最大并发数
            timeout: 页面加载超时（毫秒）
        """
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._browser: Browser = None
        self._context: BrowserContext = None

    async def __aenter__(self):
        """上下文管理器入口"""
        playwright = await async_playwright().start()

        # 使用更真实的浏览器配置来绕过反爬
        # 使用headless模式
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',  # 隐藏自动化特征
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # 更完整的浏览器指纹
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
        )

        # 注入JavaScript来隐藏webdriver特征
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 修改permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // 模拟chrome对象
            window.chrome = {
                runtime: {},
                loadTimes: function() ,
                csi: function() {},
                app: {}
            };

            // 伪造plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                    {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
                ]
            });

            // 伪造languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
        """)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    async def scrape_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        并发爬取多条记录的主链接

        Args:
            records: 记录列表，每条包含 primary_link 和 primary_platform

        Returns:
            带爬取结果的记录列表
        """
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # 并发爬取
        tasks = [
            self._scrape_one_with_semaphore(record, semaphore)
            for record in records
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for record, result in zip(records, results):
            if isinstance(result, Exception):
                logger.error(
                    "scrape_failed",
                    url=record.get("primary_link"),
                    error=str(result)
                )
                record["scrape_error"] = str(result)
            elif result:
                # 合并爬取结果到record
                record.update(result)

        return records

    async def _scrape_one_with_semaphore(
        self,
        record: Dict[str, Any],
        semaphore: asyncio.Semaphore
    ) -> Dict[str, Any]:
        """带信号量控制的单条爬取"""
        async with semaphore:
            return await self._scrape_one(record)

    async def _scrape_one(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        爬取单条记录

        Args:
            record: 包含 primary_link 和 primary_platform

        Returns:
            {
                "scraped_title": str,
                "scraped_publish_date": str,
                "scraped_article_type": str,
                "scraped_screenshot": str
            }
        """
        url = record.get("primary_link")
        platform = record.get("primary_platform", "unknown")

        if not url:
            return {}

        logger.info("scraping_page", url=url, platform=platform)

        try:
            # 创建新页面
            page = await self._context.new_page()
            page.set_default_timeout(self.timeout)

            try:
                # 添加随机延迟（模拟人类行为）
                import random
                await asyncio.sleep(random.uniform(1.0, 3.0))

                # 访问页面 - 使用networkidle等待JavaScript渲染完成
                await page.goto(url, wait_until="networkidle")

                # 额外等待确保动态内容加载
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # 调试：检查HTML长度
                html = await page.content()
                logger.info("page_loaded", url=url, html_length=len(html), has_zse_ck="zse-ck" in html)

                # 获取解析器
                parser = get_parser(platform)

                # 解析内容
                result = await parser.parse(page, url)

                logger.info(
                    "scraping_success",
                    url=url,
                    title=result.get("title", "")[:50]
                )

                # 返回带前缀的字段
                return {
                    "scraped_title": result.get("title"),
                    "scraped_publish_date": result.get("publish_date"),
                    "scraped_article_type": result.get("article_type"),
                    "scraped_screenshot": result.get("screenshot_path"),
                }

            finally:
                await page.close()

        except Exception as e:
            logger.error("scraping_failed", url=url, error=str(e))
            raise


async def scrape_publications(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    并发爬取发布信息。

    新策略（2026-08）：
    - 优先用系统 Google Chrome 无头（channel=chrome）过知乎反爬
    - 没有 Chrome 时回退 Playwright 自带 Chromium（知乎仍需 headful / Xvfb）
    - 环境变量 WEB_SCRAPER_BROWSER 可强制 bundled / chrome
    - 环境变量 WEB_SCRAPER_HEADLESS=1 强制无头（测试用）
    - WEB_SCRAPER_NAV_TIMEOUT 导航超时毫秒，默认 15000
    - WEB_SCRAPER_RECORD_TIMEOUT 单条总超时秒，默认 45；404/DNS 等会提前放弃

    Args:
        records: 记录列表

    Returns:
        带爬取结果的记录列表
    """
    import random

    has_zhihu = any(r.get("primary_platform") == "知乎" for r in records)
    playwright = await async_playwright().start()

    try:
        browser = await _launch_browser(playwright, has_zhihu)

        try:
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,
                user_agent=DEFAULT_USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )

            await context.add_init_script(STEALTH_INIT_SCRIPT)

            try:
                concurrency = _env_int("WEB_SCRAPER_CONCURRENCY", 2)
                nav_timeout_ms = _env_int("WEB_SCRAPER_NAV_TIMEOUT", 15000)
                # 正常页还要解析 + 截图，不能压得太短；坏链靠 HTTP/网络错误立刻停，不靠这个。
                record_timeout_s = _env_int("WEB_SCRAPER_RECORD_TIMEOUT", 45)
                semaphore = asyncio.Semaphore(max(1, concurrency))
                # 知乎经 link 中转对同 IP 并发敏感：多路并发中转会被风控拖慢（实测并发2全超时、
                # 串行全成功）。知乎强制并发 1，其它平台用上面那个。
                zhihu_semaphore = asyncio.Semaphore(1)

                async def fetch_and_parse(record, url: str, platform: str) -> None:
                    page = await context.new_page()
                    page.set_default_timeout(nav_timeout_ms)
                    try:
                        await asyncio.sleep(random.uniform(0.2, 0.6))
                        try:
                            if platform == "知乎":
                                # 云服务器 IP 直连 www.zhihu.com 会 403；先经 link.zhihu.com 中转，
                                # 让知乎种下 cookie，再等 JS 跳到真实地址。本地（住宅 IP）同样适用。
                                # 中转页不稳定（实测 2-15s 波动），goto 超时放宽到 30s，失败重试一次。
                                zhihu_timeout = max(nav_timeout_ms, 30000)
                                for attempt in range(2):
                                    try:
                                        await page.goto(
                                            _ZHIHU_LINK_BASE + quote(url, safe=""),
                                            wait_until="domcontentloaded",
                                            timeout=zhihu_timeout,
                                        )
                                        break
                                    except Exception:
                                        if attempt == 1:
                                            raise
                                        await asyncio.sleep(1)
                                # 中转页跳到目标后还会再导航几次；等标题非空再往下走，
                                # 不要用 networkidle（知乎会持续请求导致永不 idle）。上限 15s。
                                for _ in range(30):
                                    try:
                                        if (await page.title()).strip():
                                            break
                                    except Exception:
                                        pass
                                    await asyncio.sleep(0.5)
                                response = None
                            else:
                                response = await page.goto(
                                    url,
                                    wait_until="domcontentloaded",
                                    timeout=nav_timeout_ms,
                                )
                        except Exception as e:
                            reason = classify_scrape_failure(None, page.url, str(e))
                            record["scrape_error"] = reason or str(e)
                            logger.warning(
                                "scrape_aborted",
                                url=url,
                                reason=record["scrape_error"],
                            )
                            return

                        status = response.status if response is not None else None
                        reason = classify_scrape_failure(status, page.url, None)
                        if reason is None:
                            try:
                                title = await page.title()
                            except Exception:
                                title = ""
                            if looks_like_missing_page(title):
                                reason = f"页面不存在（{title[:80]}）"
                        if reason:
                            record["scrape_error"] = reason
                            logger.warning(
                                "scrape_aborted",
                                url=url,
                                reason=reason,
                                status=status,
                            )
                            return

                        try:
                            await page.wait_for_selector(
                                "h1, .QuestionHeader-title, .Post-Title, .ContentItem-title",
                                timeout=8000,
                                state="visible",
                            )
                        except Exception:
                            await asyncio.sleep(0.8)

                        html = await page.content()
                        logger.info(
                            "page_loaded",
                            url=url,
                            html_length=len(html),
                            has_zse_ck="zse-ck" in html,
                            status=status,
                        )

                        parser = get_parser(platform)
                        result = await parser.parse(page, url)

                        logger.info(
                            "scraping_success",
                            url=url,
                            title=result.get("title", "")[:50],
                        )

                        record["scraped_title"] = result.get("title")
                        record["scraped_publish_date"] = result.get("publish_date")
                        record["scraped_article_type"] = result.get("article_type")
                        record["scraped_screenshot"] = result.get("screenshot_path")
                    finally:
                        await page.close()

                async def scrape_one_record(record):
                    lock = zhihu_semaphore if record.get("primary_platform") == "知乎" else semaphore
                    async with lock:
                        url = record.get("primary_link")
                        platform = record.get("primary_platform", "unknown")
                        if not url:
                            return

                        logger.info("scraping_page", url=url, platform=platform)

                        # 知乎链路长：中转(最多30s) + 标题轮询 + networkidle(10s) + 截图，
                        # 单条上限单独放宽到 90s，其它平台维持 record_timeout_s。
                        budget = (
                            max(5, record_timeout_s, 90)
                            if platform == "知乎"
                            else max(5, record_timeout_s)
                        )
                        try:
                            await asyncio.wait_for(
                                fetch_and_parse(record, url, platform),
                                timeout=budget,
                            )
                        except asyncio.TimeoutError:
                            record["scrape_error"] = (
                                f"页面加载超时（{budget}s）"
                            )
                            logger.error(
                                "scraping_failed",
                                url=url,
                                error=record["scrape_error"],
                            )
                        except Exception as e:
                            reason = classify_scrape_failure(None, "", str(e))
                            record["scrape_error"] = reason or str(e)
                            logger.error("scraping_failed", url=url, error=record["scrape_error"])

                await asyncio.gather(*[scrape_one_record(r) for r in records])

            finally:
                await context.close()

        finally:
            await browser.close()

    finally:
        await playwright.stop()

    return records
