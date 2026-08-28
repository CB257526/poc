"""搜狐平台解析器"""

import re
from datetime import datetime
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path

from .base import BaseParser

class SohuParser(BaseParser):
    """搜狐平台解析器"""

    def __init__(self):
        super().__init__("搜狐")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析搜狐文章"""
        await self.wait_for_content(page)
        await self._save_html_sample(page)

        title = await self._extract_title(page)
        publish_date = await self._extract_date(page)
        article_type = await self._detect_type(page)
        screenshot_path = await self._take_screenshot(page, url)

        return {
            "title": title,
            "publish_date": publish_date,
            "article_type": article_type,
            "screenshot_path": screenshot_path
        }

    async def _extract_title(self, page: Page) -> str:
        """提取标题"""
        selectors = [
            ".article-title",
            "h1",
            ".title",
        ]

        for selector in selectors:
            try:
                text = await page.text_content(selector, timeout=3000)
                if text and len(text.strip()) > 0:
                    return text.strip()[:200]
            except Exception:
                continue

        return "未能提取标题"

    async def _extract_date(self, page: Page) -> str:
        """提取发布日期"""
        selectors = [
            "[class*='time']",
            "[class*='date']",
            "time",
        ]

        for selector in selectors:
            try:
                text = await page.text_content(selector, timeout=3000)
                if text:
                    parsed = self._parse_date_text(text)
                    if parsed:
                        return parsed
            except Exception:
                continue

        return datetime.now().strftime("%Y-%m-%d")

    def _parse_date_text(self, text: str) -> str:
        """解析日期文本"""
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if match:
            return match.group(0)

        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return ""

    async def _detect_type(self, page: Page) -> str:
        """检测内容类型"""
        video_selectors = ["video", "[class*='video']"]

        for selector in video_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    return "视频"
            except Exception:
                continue

        return "图文"

    async def _save_html_sample(self, page: Page):
        """保存HTML样本"""
        filepath = Path("web_data") / "搜狐.html"
        if not filepath.exists():
            html = await page.content()
            filepath.write_text(html, encoding="utf-8")
