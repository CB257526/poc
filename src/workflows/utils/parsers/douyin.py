"""抖音平台解析器"""

import re
from datetime import datetime
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path

from .base import BaseParser

class DouyinParser(BaseParser):
    """抖音平台解析器"""

    def __init__(self):
        super().__init__("抖音")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析抖音视频"""
        await self.wait_for_content(page)
        await self._save_html_sample(page)

        title = await self._extract_title(page)
        publish_date = await self._extract_date(page)
        article_type = "视频"  # 抖音主要是短视频
        screenshot_path = await self._take_screenshot(page, url)

        return {
            "title": title,
            "publish_date": publish_date,
            "article_type": article_type,
            "screenshot_path": screenshot_path
        }

    async def _extract_title(self, page: Page) -> str:
        """提取标题/描述"""
        selectors = [
            "[class*='title']",
            "[class*='desc']",
            "h1",
            ".video-title",
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

    async def _save_html_sample(self, page: Page):
        """保存HTML样本"""
        filepath = Path("web_data") / "抖音.html"
        if not filepath.exists():
            html = await page.content()
            filepath.write_text(html, encoding="utf-8")
