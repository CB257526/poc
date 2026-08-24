"""今日头条平台解析器"""

import re
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path
from datetime import datetime

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()


class ToutiaoParser(BaseParser):
    """今日头条平台解析器"""

    def __init__(self):
        super().__init__("今日头条")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析今日头条页面"""
        await self.wait_for_content(page)

        # 标题
        title = await self._safe_text(page, "h1")
        if not title:
            title = await self._safe_text(page, "title")

        # 发布日期
        publish_date = await self._extract_date(page)

        # 文章类型：默认图文
        article_type = "图文"

        # 截图
        screenshot_path = await self._take_screenshot(page, url)

        return {
            "title": title or "未能提取标题",
            "publish_date": publish_date,
            "article_type": article_type,
            "screenshot_path": screenshot_path
        }

    async def _safe_text(self, page: Page, selector: str) -> str:
        """安全地提取文本"""
        try:
            text = await page.text_content(selector, timeout=3000)
            return text.strip() if text else ""
        except Exception:
            return ""

    async def _extract_date(self, page: Page) -> str:
        """提取发布日期"""
        try:
            # 在页面内容中搜索日期格式
            html = await page.content()
            
            # 匹配 YYYY-MM-DD 格式
            matches = re.findall(r'20\d{2}-\d{2}-\d{2}', html[:50000])
            if matches:
                # 返回第一个匹配的日期
                return matches[0]
        except Exception as e:
            logger.warning("toutiao_date_extract_failed", error=str(e))

        return datetime.now().strftime("%Y-%m-%d")

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"toutiao_{url_hash}.png"
        filepath = Path("screenshots") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)
