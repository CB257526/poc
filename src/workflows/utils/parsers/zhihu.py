"""知乎解析器"""

import re
import json
from typing import Dict, Any
from playwright.async_api import Page
from pathlib import Path
from datetime import datetime

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

        # 发布日期：从JSON数据中提取
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
        # 尝试多个选择器
        selectors = [
            "h1.QuestionHeader-title",
            "h1.ZVideo-title",
            "h1",
            "title"
        ]

        for selector in selectors:
            text = await self._safe_text(page, selector)
            if text:
                # 清理title标签的后缀
                if selector == "title":
                    text = text.replace(" - 知乎", "").strip()
                return text

        return ""

    async def _safe_text(self, page: Page, selector: str) -> str:
        """安全地提取文本"""
        try:
            text = await page.text_content(selector, timeout=3000)
            return text.strip() if text else ""
        except Exception:
            return ""

    async def _extract_date(self, page: Page, url: str) -> str:
        """从页面JSON数据中提取发布日期"""
        try:
            # 获取页面HTML
            html = await page.content()
            
            # 查找 <script id="js-initialData"> 中的JSON
            match = re.search(r'<script id="js-initialData"[^>]*>(.*?)</script>', html, re.DOTALL)
            if match:
                json_str = match.group(1)
                data = json.loads(json_str)
                
                # 根据URL类型提取不同的时间
                if "/answer/" in url:
                    # 答案页面：从answers中提取
                    answer_id = self._extract_answer_id(url)
                    if answer_id:
                        answers = data.get("initialState", {}).get("entities", {}).get("answers", {})
                        answer_data = answers.get(answer_id, {})
                        created_time = answer_data.get("createdTime")
                        if created_time:
                            dt = datetime.fromtimestamp(int(created_time))
                            return dt.strftime("%Y-%m-%d")
                
                elif "/question/" in url:
                    # 问题页面：从questions中提取
                    question_id = self._extract_question_id(url)
                    if question_id:
                        questions = data.get("initialState", {}).get("entities", {}).get("questions", {})
                        question_data = questions.get(question_id, {})
                        created = question_data.get("created")
                        if created:
                            dt = datetime.fromtimestamp(int(created))
                            return dt.strftime("%Y-%m-%d")
                
                elif "/zvideo/" in url:
                    # 视频页面：从zvideos中提取
                    video_id = self._extract_zvideo_id(url)
                    if video_id:
                        zvideos = data.get("initialState", {}).get("entities", {}).get("zvideos", {})
                        video_data = zvideos.get(video_id, {})
                        created_at = video_data.get("createdAt")
                        if created_at:
                            dt = datetime.fromtimestamp(int(created_at))
                            return dt.strftime("%Y-%m-%d")
            
        except Exception as e:
            logger.warning("zhihu_date_extract_failed", error=str(e))

        # Fallback: 当前日期
        return datetime.now().strftime("%Y-%m-%d")

    def _extract_answer_id(self, url: str) -> str:
        """从URL提取答案ID"""
        match = re.search(r'/answer/(\d+)', url)
        return match.group(1) if match else ""

    def _extract_question_id(self, url: str) -> str:
        """从URL提取问题ID"""
        match = re.search(r'/question/(\d+)', url)
        return match.group(1) if match else ""

    def _extract_zvideo_id(self, url: str) -> str:
        """从URL提取视频ID"""
        match = re.search(r'/zvideo/(\d+)', url)
        return match.group(1) if match else ""

    async def _determine_article_type(self, page: Page, url: str) -> str:
        """判断文章类型"""
        if "/zvideo/" in url:
            return "视频"
        return "图文"

    async def _take_screenshot(self, page: Page, url: str) -> str:
        """截图"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"zhihu_{url_hash}.png"
        filepath = Path("screenshots") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        await page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)
