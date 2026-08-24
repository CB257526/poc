"""易车平台解析器"""

from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path
from datetime import datetime
import re

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()


class YicheParser(BaseParser):
    """易车平台解析器"""

    def __init__(self):
        super().__init__("易车")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析易车页面"""
        await self.wait_for_content(page)

        # 标题：优先<h2>，fallback到<title>
        title = await self._safe_text(page, "h2")
        if not title:
            title = await self._safe_text(page, "title")
            if title:
                # 去除"_易车号"等后缀
                title = re.sub(r'_易车.*', '', title).strip()

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
            # 方法1: .pubTime class
            date_elem = await page.query_selector(".pubTime")
            if date_elem:
                text = await date_elem.inner_text()
                # 格式: "2026-01-22 12:41:52"
                if text and len(text) >= 10:
                    return text[:10]
            
            # 方法2: 正则搜索
            html = await page.content()
            matches = re.findall(r'20\d{2}-\d{2}-\d{2}', html[:50000])
            if matches:
                return matches[0]
        except Exception as e:
            logger.warning("yiche_date_extract_failed", error=str(e))

        return datetime.now().strftime("%Y-%m-%d")

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"yiche_{url_hash}.png"
        filepath = Path("screenshots") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)
