"""平台解析器基类"""

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
        """截当前视口。像素密度由浏览器 context 的 device_scale_factor 决定。"""
        url_hash = md5(url.encode()).hexdigest()[:8]
        filepath = Path("screenshots") / f"{self.platform_name}_{url_hash}.png"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(filepath), full_page=False, type="png")
        return str(filepath)
