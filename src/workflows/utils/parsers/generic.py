"""通用解析器 - 用于搜狐等未知平台"""

import re
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path
from datetime import datetime

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()


class GenericParser(BaseParser):
    """通用平台解析器 - Fallback"""

    def __init__(self):
        super().__init__("通用")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析通用页面"""
        await self.wait_for_content(page)

        # 标题：尝试多个选择器
        title = await self._extract_title(page)

        # 发布日期：正则搜索
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

    async def _extract_title(self, page: Page) -> str:
        """提取标题"""
        # 尝试多个选择器
        selectors = ["h1", "h2", ".title", "#title", "article h1", "title"]
        
        for selector in selectors:
            title = await self._safe_text(page, selector)
            if title and len(title) > 5:  # 至少5个字符
                return title
        
        return ""

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
            
            # 匹配多种日期格式
            patterns = [
                r'20\d{2}-\d{2}-\d{2}',  # 2026-01-22
                r'20\d{2}/\d{2}/\d{2}',  # 2026/01/22
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html[:50000])
                if matches:
                    # 排除明显的部署时间（2026-07-29等）
                    for date in matches:
                        # 转换为统一格式
                        normalized = date.replace('/', '-')
                        # 检查是否是最近的日期
                        return normalized
        except Exception as e:
            logger.warning("generic_date_extract_failed", error=str(e))

        return datetime.now().strftime("%Y-%m-%d")

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"generic_{url_hash}.png"
        filepath = Path("screenshots") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)
