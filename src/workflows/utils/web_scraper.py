"""网页爬取服务 - 基于Playwright异步并发"""

import asyncio
from typing import List, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from workflows.services import get_logger
from workflows.utils.parsers import get_parser

logger = get_logger()


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
    便捷函数：并发爬取发布信息

    采用完全隔离策略：每个URL使用独立的browser实例
    这样可以避免被知乎识别为批量自动化爬虫

    Args:
        records: 记录列表

    Returns:
        带爬取结果的记录列表
    """
    # 完全串行，每个URL独立的browser实例
    for record in records:
        url = record.get("primary_link")
        platform = record.get("primary_platform", "unknown")

        if not url:
            continue

        logger.info("scraping_page", url=url, platform=platform)

        try:
            # 每个URL使用独立的playwright实例
            playwright = await async_playwright().start()

            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ]
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: , loadTimes: function() {}, csi: function() {}};
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
            """)

            page = await context.new_page()
            page.set_default_timeout(30000)

            # 随机延迟
            import random
            await asyncio.sleep(random.uniform(2.0, 5.0))

            # 访问页面
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # 检查HTML
            html = await page.content()
            logger.info("page_loaded", url=url, html_length=len(html), has_zse_ck="zse-ck" in html)

            # 获取解析器并解析
            from workflows.utils.parsers import get_parser
            parser = get_parser(platform)
            result = await parser.parse(page, url)

            logger.info("scraping_success", url=url, title=result.get("title", "")[:50])

            # 合并结果
            record["scraped_title"] = result.get("title")
            record["scraped_publish_date"] = result.get("publish_date")
            record["scraped_article_type"] = result.get("article_type")
            record["scraped_screenshot"] = result.get("screenshot_path")

            # 清理
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()

        except Exception as e:
            logger.error("scraping_failed", url=url, error=str(e))
            record["scrape_error"] = str(e)

    return records
