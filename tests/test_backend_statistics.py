from types import SimpleNamespace

from workflows.backend.task_support import quote_summary_from_context


def test_unclassified_content_keeps_fee_in_total():
    """网页抓取未返回文章类型时，费用仍入账并进入待分类。"""
    context = SimpleNamespace(
        quote_details={
            "details": [
                {
                    "媒体": "媒体A",
                    "文章类型": "",
                    "费用": 1200,
                    "eligible_for_monthly_summary": True,
                }
            ]
        }
    )

    summary = quote_summary_from_context(context)

    assert summary["quote_count"] == 1
    assert summary["total_fee"] == 1200
    assert summary["text_fee"] == 0
    assert summary["video_fee"] == 0
    assert summary["unclassified_fee"] == 1200


def test_total_fee_contains_all_content_categories():
    context = SimpleNamespace(
        quote_details={
            "details": [
                {"媒体": "媒体A", "文章类型": "图文", "费用": 1000, "eligible_for_monthly_summary": True},
                {"媒体": "媒体B", "文章类型": "视频", "费用": 2000, "eligible_for_monthly_summary": True},
                {"媒体": "媒体C", "文章类型": None, "费用": 3000, "eligible_for_monthly_summary": True},
                {"媒体": "异常媒体", "文章类型": "图文", "费用": 99999, "eligible_for_monthly_summary": False},
            ]
        }
    )

    summary = quote_summary_from_context(context)

    assert summary["quote_count"] == 3
    assert summary["total_fee"] == 6000
    assert summary["text_fee"] == 1000
    assert summary["video_fee"] == 2000
    assert summary["unclassified_fee"] == 3000
    assert summary["total_fee"] == summary["text_fee"] + summary["video_fee"] + summary["unclassified_fee"]
