from types import SimpleNamespace

from workflows.backend.task_support import preview_validate, quote_summary_from_context, workflow_issues
from workflows.models import WorkflowContext


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


def test_workflow_issues_include_node_id():
    context = WorkflowContext(run_id="run-issues", input_file="input.xlsx")
    context.add_issue(
        level="error",
        code="MEDIA_NOT_FOUND",
        message="媒体库未找到该媒体",
        node_id="node_03",
        record_id="rec_0001",
    )

    items = workflow_issues(context)

    assert items == [
        {
            "record_id": "rec_0001",
            "node_id": "node_03",
            "code": "MEDIA_NOT_FOUND",
            "message": "媒体库未找到该媒体",
            "severity": "error",
        }
    ]


def test_preview_validate_flags_invalid_urls(monkeypatch, tmp_path):
    input_file = tmp_path / "1-链接.xlsx"
    input_file.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "workflows.backend.task_support.load_media_library",
        lambda: ({"oxygen": "Oxygen"}, ["Oxygen"]),
    )
    monkeypatch.setattr(
        "workflows.backend.task_support.ExcelService.read_link_sheet",
        lambda *_args, **_kwargs: [{
            "主题": "主题1",
            "媒体": "Oxygen",
            "row_number": 2,
            "链接": ["https://ww.zhihu.com/zvideo/123"],
        }],
    )

    preview = preview_validate(str(input_file))

    assert preview["status"] == "needs_correction"
    assert preview["records"][0]["match_status"] == "matched"
    assert any(issue["code"] == "INVALID_URL" for issue in preview["issues"])
