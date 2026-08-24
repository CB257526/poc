"""微博平台解析器"""

import re
from datetime import datetime
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()


class WeiboParser(BaseParser):
    """微博平台解析器"""

    def __init__(self):
        super().__init__("微博")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析微博页面"""
        await self.wait_for_content(page)

        # 标题：从<title>去除"- 微博"后缀
        title = await self._safe_text(page, "title")
        if title:
            title = title.replace(" - 微博", "").replace("微博正文 - 微博", "").strip()
        
        # 发布日期：._time_xxx class，格式 "26-1-22 12:33"
        publish_date = await self._extract_date(page)

        # 文章类型：检查是否有视频
        has_video = await page.query_selector("video")
        article_type = "视频" if has_video else "图文"

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
            # 查找 ._time_ 开头的class
            time_elem = await page.query_selector('[class*="_time_"]')
            if time_elem:
                text = await time_elem.inner_text()
                text = text.strip()
                
                # 格式: "26-1-22 12:33" → "2026-01-22"
                match = re.match(r'(\d{2})-(\d{1,2})-(\d{1,2})', text)
                if match:
                    year = "20" + match.group(1)
                    month = match.group(2).zfill(2)
                    day = match.group(3).zfill(2)
                    return f"{year}-{month}-{day}"
        except Exception as e:
            logger.warning("weibo_date_extract_failed", error=str(e))

        return datetime.now().strftime("%Y-%m-%d")

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"weibo_{url_hash}.png"
        filepath = Path("screenshots") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)
