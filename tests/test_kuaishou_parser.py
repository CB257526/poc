from workflows.utils.parsers.kuaishou import KuaishouParser
from workflows.utils.web_scraper import kuaishou_context_options


SAMPLE_HTML = """
<html><head><title>快手</title></head>
<body>
<div class="desc">海边的公路摄影#COS#终末地#崩坏星穹铁道</div>
<script>
window.__DATA__ = {"photo":{"photoId":"3xbi4c2dn9bnsmm","caption":"海边的公路摄影#COS #终末地 #崩坏星穹铁道","timestamp":1770717829558,"photoType":"VIDEO","mainMvUrls":[{"url":"https://example.com/a.mp4"}]}};
</script>
</body></html>
"""

CAPTCHA_HTML = """
<iframe src="https://captcha.zt.kuaishou.com/iframe/index.html?bizName=ANTICRAWL_COMMON"></iframe>
<title>短视频-快手</title>
"""


def test_caption_from_embedded_json():
    parser = KuaishouParser()
    assert parser._caption_from_html(SAMPLE_HTML) == "海边的公路摄影#COS #终末地 #崩坏星穹铁道"


def test_clean_title_drops_placeholders():
    parser = KuaishouParser()
    assert parser._clean_title("短视频-快手") == ""
    assert parser._clean_title("快手") == ""
    assert parser._clean_title("海边的公路摄影-快手") == "海边的公路摄影"


def test_date_prefers_work_timestamp_over_open_time():
    parser = KuaishouParser()
    html = (
        '{"timestamp": 1770717829558}'
        '{"timestamp": 1788418003148}'
    )
    # 作品时间 2026-02-10，打开时间更晚；取较早的作品时间
    import asyncio

    async def _run():
        return await parser._extract_date(None, html)

    date = asyncio.run(_run())
    assert date == "2026-02-10"


def test_detect_type_from_main_mv_urls():
    parser = KuaishouParser()
    import asyncio

    class DummyPage:
        url = "https://m.gifshow.com/fw/photo/3xbi4c2dn9bnsmm"

        async def query_selector(self, _sel):
            return None

    async def _run():
        return await parser._detect_type(DummyPage(), SAMPLE_HTML)

    assert asyncio.run(_run()) == "视频"


def test_captcha_page_detected():
    parser = KuaishouParser()
    assert parser._is_captcha_page(CAPTCHA_HTML, "https://www.kuaishou.com/short-video/x")
    assert not parser._is_captcha_page(SAMPLE_HTML, "https://m.gifshow.com/fw/photo/x")


def test_kuaishou_context_is_mobile():
    class DummyPlaywright:
        devices = {
            "iPhone 13": {
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
                "viewport": {"width": 390, "height": 844},
                "is_mobile": True,
                "has_touch": True,
                "default_browser_type": "webkit",
            }
        }

    opts = kuaishou_context_options(DummyPlaywright())
    assert opts["is_mobile"] is True
    assert "iPhone" in opts["user_agent"]
    assert opts["locale"] == "zh-CN"
    assert "default_browser_type" not in opts
