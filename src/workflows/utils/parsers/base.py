"""平台解析器基类"""

import asyncio
from abc import ABC, abstractmethod
from hashlib import md5
from pathlib import Path
from typing import Dict, Any
from playwright.async_api import Page


class BaseParser(ABC):
    """平台解析器抽象基类"""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    @abstractmethod
    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """
        解析页面内容

        Args:
            page: Playwright Page对象
            url: 目标URL

        Returns:
            {
                "title": str,           # 文章标题
                "publish_date": str,    # 发布日期 YYYY-MM-DD
                "article_type": str,    # "视频" | "图文"
                "screenshot_path": str  # 截图临时文件路径
            }
        """
        pass

    async def wait_for_content(self, page: Page, timeout: int = 10000):
        """等待页面内容加载完成"""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # networkidle可能超时，降级为domcontentloaded
            await page.wait_for_load_state("domcontentloaded", timeout=5000)

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截当前视口。像素密度由浏览器 context 的 device_scale_factor 决定。

        知乎等页面字体请求可能一直不完，截图会等字体加载而卡住整条爬取。
        这里加 8s 超时，失败只返回空路径、不抛异常，让标题/日期仍能落库。
        """
        url_hash = md5(url.encode()).hexdigest()[:8]
        filepath = Path("screenshots") / f"{self.platform_name}_{url_hash}.png"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._wait_for_visible_images(page)
            await asyncio.wait_for(
                page.screenshot(path=str(filepath), full_page=False, type="png"),
                timeout=8,
            )
        except Exception:
            return ""
        return str(filepath)

    async def _wait_for_visible_images(self, page: Page) -> None:
        """截图前等待当前视口内图片渲染，超时后正常降级截图。

        页面正文出现后，头像和正文配图仍可能通过懒加载异步请求。先给页面
        两秒缓冲，再检测可见 ``img`` 是否已有有效像素；最多额外等待四秒，
        避免失败的图片请求拖住整批任务。
        """
        try:
            await asyncio.sleep(2)
            await page.evaluate(
                """() => {
                    for (const img of document.querySelectorAll('img')) {
                        const rect = img.getBoundingClientRect();
                        const visible = rect.bottom > 0 && rect.top < window.innerHeight
                            && rect.right > 0 && rect.left < window.innerWidth;
                        if (visible) img.loading = 'eager';
                    }
                }"""
            )
            await page.wait_for_function(
                """() => [...document.querySelectorAll('img')]
                    .filter((img) => {
                        const rect = img.getBoundingClientRect();
                        return rect.bottom > 0 && rect.top < window.innerHeight
                            && rect.right > 0 && rect.left < window.innerWidth;
                    })
                    .every((img) => img.complete && img.naturalWidth > 0)""",
                timeout=4000,
            )
            # 图片解码完成后给浏览器一个短暂绘制窗口。
            await asyncio.sleep(0.3)
        except Exception:
            # 图片可能被登录、CDN 或防盗链限制；不因此中断截图和后续流程。
            pass
