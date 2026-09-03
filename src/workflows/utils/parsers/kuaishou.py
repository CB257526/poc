"""快手平台解析器"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from playwright.async_api import Page

from .base import BaseParser
from workflows.services import get_logger

logger = get_logger()

_PLACEHOLDER_TITLES = {
    "快手",
    "kuaishou",
    "短视频",
    "短视频-快手",
    "打开快手",
    "打开快手，看更多精彩视频",
}

_CAPTCHA_HINTS = (
    "captcha.zt.kuaishou.com",
    "ANTICRAWL",
    "请完成安全验证",
)


class KuaishouParser(BaseParser):
    """快手短链 / 作品页解析器。

    PC Web（www.kuaishou.com/short-video）对无头 Chrome 会弹滑块，
    抓取侧改用 iPhone 指纹，落到 m.gifshow.com/fw/photo 分享页。
    """

    def __init__(self):
        super().__init__("快手")

    async def parse(self, page: Page, url: str) -> Dict[str, Any]:
        try:
            await page.wait_for_selector(
                ".desc, span.text.txt, span.topic.txt, .video-info-title, .photo-time, video",
                timeout=8000,
                state="visible",
            )
        except Exception:
            pass

        await self._save_html_sample(page)
        html = await page.content()

        title = await self._extract_title(page, html)
        publish_date = await self._extract_date(page, html)
        article_type = await self._detect_type(page, html)
        if self._is_captcha_page(html, page.url):
            logger.warning("kuaishou_captcha_page", url=url, href=page.url)
            screenshot_path = ""
        else:
            screenshot_path = await self._take_screenshot(page, url)

        return {
            "title": title or "未能提取标题",
            "publish_date": publish_date,
            "article_type": article_type,
            "screenshot_path": screenshot_path,
        }

    async def _extract_title(self, page: Page, html: str) -> str:
        caption = self._caption_from_html(html)
        if caption:
            return caption[:200]

        try:
            texts = await page.eval_on_selector_all(
                ".desc, span.text.txt, span.topic.txt",
                "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)",
            )
            for text in texts:
                cleaned = self._clean_title(text)
                if cleaned:
                    return cleaned[:200]
        except Exception:
            pass

        for selector in [".video-info-title", ".caption", "h1"]:
            try:
                text = await page.text_content(selector, timeout=2000)
                cleaned = self._clean_title(text or "")
                if cleaned:
                    return cleaned[:200]
            except Exception:
                continue

        try:
            cleaned = self._clean_title(await page.title())
            if cleaned:
                return cleaned[:200]
        except Exception:
            pass

        return ""

    @staticmethod
    def _clean_title(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"[-_]?快手\s*$", "", text).strip()
        if not cleaned or cleaned.lower() in _PLACEHOLDER_TITLES:
            return ""
        if cleaned.startswith("打开快手"):
            return ""
        return cleaned

    @staticmethod
    def _caption_from_html(html: str) -> str:
        match = re.search(r'"caption"\s*:\s*"((?:\\.|[^"\\])*)"', html)
        if not match:
            return ""
        raw = match.group(1)
        try:
            caption = (
                raw.encode("utf-8")
                .decode("unicode_escape")
                .encode("latin-1")
                .decode("utf-8")
            )
        except UnicodeError:
            caption = raw
        return caption.replace("\\n", " ").strip()

    async def _extract_date(self, page: Page, html: str) -> str:
        match = re.search(
            r'"photo"\s*:\s*\{[^{}]{0,800}"timestamp"\s*:\s*(\d{10,13})',
            html,
        )
        if match:
            parsed = self._from_epoch(match.group(1))
            if parsed:
                return parsed

        today = datetime.now().strftime("%Y-%m-%d")
        candidates = []
        for ts in re.findall(r'"timestamp"\s*:\s*(\d{10,13})', html):
            parsed = self._from_epoch(ts)
            # 页面里还有分享打开时间，只取合理的作品发布时间
            if parsed and parsed <= today:
                candidates.append(parsed)
        if candidates:
            return min(candidates)

        for selector in [".photo-time", "[class*='photo-time']", "time"]:
            try:
                text = await page.text_content(selector, timeout=2000)
                parsed = self._parse_relative_date(text or "")
                if parsed:
                    return parsed
            except Exception:
                continue

        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _parse_relative_date(text: str) -> str:
        """网页端常见「2月前 / 3天前」，没有精确到日的时间戳。"""
        if not text:
            return ""
        text = text.strip()
        now = datetime.now()

        absolute = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
        if absolute:
            year, month, day = absolute.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        if "刚刚" in text:
            return now.strftime("%Y-%m-%d")

        mapping = [
            (r"(\d+)\s*分钟前", lambda n: 0),
            (r"(\d+)\s*小时前", lambda n: 0),
            (r"(\d+)\s*天前", lambda n: n),
            (r"(\d+)\s*周前", lambda n: n * 7),
            (r"(\d+)\s*年前", lambda n: n * 365),
        ]
        for pattern, days_fn in mapping:
            match = re.search(pattern, text)
            if match:
                delta = timedelta(days=days_fn(int(match.group(1))))
                return (now - delta).strftime("%Y-%m-%d")

        match = re.search(r"(\d+)\s*月前", text)
        if match:
            months = int(match.group(1))
            year = now.year
            month = now.month - months
            while month <= 0:
                month += 12
                year -= 1
            day = min(now.day, 28)
            return f"{year}-{month:02d}-{day:02d}"

        return ""

    @staticmethod
    def _from_epoch(value: str) -> str:
        try:
            ts = int(value)
            if ts > 10_000_000_000:
                ts = ts / 1000
            dt = datetime.fromtimestamp(ts)
            if dt.year < 2015:
                return ""
            return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return ""

    async def _detect_type(self, page: Page, html: str) -> str:
        if re.search(r'"mainMvUrls"\s*:\s*\[\s*\{', html):
            return "视频"
        if re.search(r'"photoType"\s*:\s*"[^"]*VIDEO', html, re.I):
            return "视频"
        if "/short-video/" in (page.url or "") or "/fw/photo/" in (page.url or ""):
            return "视频"
        try:
            if await page.query_selector("video"):
                return "视频"
        except Exception:
            pass
        return "图文"

    @staticmethod
    def _is_captcha_page(html: str, href: str = "") -> bool:
        hay = f"{html or ''} {href or ''}"
        return any(hint in hay for hint in _CAPTCHA_HINTS)

    async def _save_html_sample(self, page: Page) -> None:
        filepath = Path("web_data") / "快手.html"
        if filepath.exists():
            return
        try:
            filepath.parent.mkdir(exist_ok=True)
            filepath.write_text(await page.content(), encoding="utf-8")
        except Exception as e:
            logger.warning("kuaishou_html_sample_failed", error=str(e))
