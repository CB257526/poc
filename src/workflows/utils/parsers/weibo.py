"""微博平台解析器"""

import re
from datetime import datetime
from typing import Dict, Any
from playwright.async_api import Page

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

        # 标题：从微博正文提取
        title = await self._safe_text(page, '[class*="_wbtext_"]')
        if not title:
            # 降级方案：尝试其他选择器
            title = await self._safe_text(page, '[class*="_ogText_"]')
        if not title:
            title = await self._safe_text(page, 'article [class*="text"]')

        # 清理标题：移除尾部的"微博视频"等后缀
        if title:
            title = title.replace(" ​​​", "").strip()
            # 移除"xxx的微博视频"后缀
            import re
            title = re.sub(r'\s+\S+的微博视频$', '', title)

        # 发布日期：._time_xxx class，格式 "26-1-22 12:33"
        publish_date = await self._extract_date(page)

        # 文章类型：微博图文帖页面也会渲染一个隐藏的 video-js mini-player
        # （空 src、不可见），不能只凭「存在 <video>」判视频。
        # 判定依据：有真实 src 且对用户可见的 video，才算视频帖。
        article_type = await self._detect_type(page)

        # 截图
        screenshot_path = await self._take_screenshot(page, url)

        return {
            "title": title or "未能提取标题",
            "publish_date": publish_date,
            "article_type": article_type,
            "screenshot_path": screenshot_path
        }

    async def _detect_type(self, page: Page) -> str:
        """判断文章类型：视频 vs 图文。

        微博页面里即使图文帖也常含一个隐藏的 video-js mini-player
        （无 src、offsetParent 为空）。因此只把「有真实 src 且可见」的
        video 视为视频帖，避免图文被误判成视频。
        """
        try:
            video_info = await page.evaluate("""() => {
                const vids = [...document.querySelectorAll('video')];
                for (const v of vids) {
                    const src = v.getAttribute('src') || (v.currentSrc || '');
                    if (src && v.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            }""")
            if video_info:
                return "视频"
        except Exception:
            pass

        # 兜底：正文明确出现「微博视频 / 播放视频」文案
        try:
            art = await page.query_selector("article")
            body = art or page
            text = await body.inner_text() if art else await page.evaluate(
                "document.body ? document.body.innerText : ''"
            )
            if text and ("微博视频" in text or "播放视频" in text):
                return "视频"
        except Exception:
            pass

        return "图文"

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

