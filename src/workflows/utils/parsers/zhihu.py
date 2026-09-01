"""知乎解析器"""

import re
from typing import Dict, Any
from playwright.async_api import Page
from datetime import datetime, timedelta, timezone

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()

class ZhihuParser(BaseParser):
    """知乎平台解析器"""

    def __init__(self):
        super().__init__("知乎")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        """解析知乎页面"""
        await self.wait_for_content(page)

        # 标题：从 h1 或 title 标签
        title = await self._extract_title(page)

        # 发布日期：从页面文本中提取
        publish_date = await self._extract_date(page, url)

        # 文章类型：判断是视频还是图文
        article_type = await self._determine_article_type(page, url)

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
        # 中转跳转后页面 <title> 一定非空且带「 - 知乎」后缀，最可靠，优先取它。
        try:
            doc_title = await page.title()
        except Exception:
            doc_title = ""
        doc_title = doc_title.replace(" - 知乎", "").strip()
        if doc_title:
            return doc_title

        # 再尝试具体选择器
        selectors = [
            "h1.QuestionHeader-title",
            "h1.ZVideo-title",
            "h1",
        ]

        for selector in selectors:
            text = await self._safe_text(page, selector)
            if text:
                return text

        return ""

    async def _safe_text(self, page: Page, selector: str) -> str:
        """安全地提取文本"""
        try:
            text = await page.text_content(selector, timeout=3000)
            return text.strip() if text else ""
        except Exception:
            return ""

    def _extract_answer_id(self, url: str) -> str:
        """从URL提取答案ID"""
        match = re.search(r'/answer/(\d+)', url)
        return match.group(1) if match else ""

    def _parse_iso_date(self, content: str) -> str:
        """将 meta 中的 ISO 时间（UTC）转为北京时间日期 YYYY-MM-DD"""
        if not content:
            return ""
        try:
            dt = datetime.fromisoformat(content.replace("Z", "+00:00"))
            return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    async def _extract_date(self, page: Page, url: str) -> str:
        """提取发布日期"""
        try:
            # 1. 问答页：定位到URL对应的那条回答，读取其 dateCreated meta
            #    （问题页有多条回答，必须按 answer id 定位，否则会取到别人的回答时间）
            answer_id = self._extract_answer_id(url)
            if answer_id:
                meta = await page.query_selector(
                    f'[name="{answer_id}"] meta[itemprop="dateCreated"]'
                )
                if meta:
                    content = await meta.get_attribute("content")
                    date = self._parse_iso_date(content)
                    if date:
                        return date

            # 2. 通用 meta：文章页/视频页
            for selector in (
                'meta[itemprop="dateCreated"]',
                'meta[property="article:published_time"]',
            ):
                meta = await page.query_selector(selector)
                if meta:
                    content = await meta.get_attribute("content")
                    date = self._parse_iso_date(content)
                    if date:
                        return date

            # 3. 页面可见文本："发布于 YYYY-MM-DD"（视频页走这条）
            body_text = await page.text_content("body")
            match = re.search(r'(?:发布于|编辑于)\s*(\d{4})-(\d{1,2})-(\d{1,2})', body_text)
            if match:
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # 4. "YYYY年MM月DD日"格式
            match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', body_text)
            if match:
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        except Exception as e:
            logger.warning("zhihu_date_extract_failed", error=str(e))

        # Fallback: 当前日期
        return datetime.now().strftime("%Y-%m-%d")

    async def _determine_article_type(self, page: Page, url: str) -> str:
        """判断文章类型"""
        if "/zvideo/" in url:
            return "视频"
        return "图文"

