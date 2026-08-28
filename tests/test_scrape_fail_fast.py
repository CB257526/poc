from workflows.utils.web_scraper import classify_scrape_failure, looks_like_missing_page


def test_http_404_aborts_immediately():
    assert classify_scrape_failure(404, "https://www.zhihu.com/missing") == "HTTP 404"


def test_http_502_aborts():
    assert classify_scrape_failure(502) == "HTTP 502"


def test_http_403_does_not_abort():
    # 知乎反爬经常 403，真实 Chrome 仍可能渲染出正文
    assert classify_scrape_failure(403) is None


def test_http_200_does_not_abort():
    assert classify_scrape_failure(200, "https://www.zhihu.com/question/1") is None


def test_dns_error_aborts():
    err = "net::ERR_NAME_NOT_RESOLVED at https://this-host-does-not-exist.example/"
    assert classify_scrape_failure(None, "", err) == "网络错误: net::ERR_NAME_NOT_RESOLVED"


def test_connection_refused_aborts():
    err = "net::ERR_CONNECTION_REFUSED at https://127.0.0.1:9/"
    assert classify_scrape_failure(None, "", err) == "网络错误: net::ERR_CONNECTION_REFUSED"


def test_chrome_error_page_aborts():
    assert (
        classify_scrape_failure(None, "chrome-error://chromewebdata/")
        == "网络错误: 浏览器无法打开该地址"
    )


def test_timeout_error_aborts():
    reason = classify_scrape_failure(None, "", "Timeout 15000ms exceeded")
    assert reason is not None
    assert reason.startswith("页面加载超时")


def test_missing_page_title():
    assert looks_like_missing_page("404 Not Found")
    assert looks_like_missing_page("页面不存在")
    assert not looks_like_missing_page("如何找到合适的媒体")
    assert not looks_like_missing_page("")
