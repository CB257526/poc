"""微信公众号平台解析器"""

import re
from datetime import datetime
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path

from .base import BaseParser


class WeixinParser(BaseParser):
    """微信公众号平台解析器"""

    def __init__(self):
        super().__init__("微信公众号")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析微信公众号文章"""
        await self.wait_for_content(page)
        await self._save_html_sample(page)

        # 标题
        title = await self._extract_title(page)

        # 发布日期
        publish_date = await self._extract_date(page)

        # 文章类型（公众号主要是图文，少量视频号）
        article_type = await self._detect_type(page)

        # 截图
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
            "#activity-name",
            ".rich_media_title",
            "h1",
            "h2.rich_media_title",
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
            "#publish_time",
            ".publish_time",
            "[class*='time']",
            "meta[property='article:published_time']",
        ]

        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    date_str = await page.get_attribute(selector, "content")
                else:
                    date_str = await page.text_content(selector, timeout=3000)

                if date_str:
                    parsed = self._parse_date_text(date_str)
                    if parsed:
                        return parsed
            except Exception:
                continue

        return datetime.now().strftime("%Y-%m-%d")

    def _parse_date_text(self, text: str) -> str:
        """解析日期文本"""
        # YYYY-MM-DD
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if match:
            return match.group(0)

        # YYYY年MM月DD日
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return ""

    async def _detect_type(self, page: Page) -> str:
        """检测文章类型"""
        # 检查视频标签
        video_selectors = [
            "video",
            "iframe[data-vid]",
            "[class*='video']",
        ]

        for selector in video_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    return "视频"
            except Exception:
                continue

        return "图文"

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib

        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"weixin_{url_hash}.png"
        filepath = Path("screenshots") / filename

        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)

    async def _save_html_sample(self, page: Page):
        """保存HTML样本"""
        filepath = Path("web_data") / "微信公众号.html"
        if not filepath.exists():
            html = await page.content()
            filepath.write_text(html, encoding="utf-8")
