"""测试无头 Chrome 抓知乎 - 可独立运行"""
import asyncio, sys, json
sys.path.insert(0, "src")
from workflows.utils.web_scraper import scrape_publications

records = [
    {"id": "1", "primary_link": "https://www.zhihu.com/question/1997735046166099243/answer/1997772213143766041", "primary_platform": "知乎"},
    {"id": "2", "primary_link": "https://www.zhihu.com/zvideo/1997648866380632485", "primary_platform": "知乎"},
]

async def main():
    results = await scrape_publications(records)
    for r in results:
        print(json.dumps({
            "id": r["id"],
            "title": (r.get("scraped_title") or "")[:60],
            "date": r.get("scraped_publish_date"),
            "type": r.get("scraped_article_type"),
            "error": r.get("scrape_error"),
        }, ensure_ascii=False))

asyncio.run(main())
