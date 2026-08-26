from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from workflows.models import WorkflowContext

import workflows.api as api


def configure_api(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "BASE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(api, "TABLE_DIR", Path("table").resolve())
    api.BASE_DIR.mkdir(parents=True, exist_ok=True)
    api._tasks.clear()
    return TestClient(api.app)


def test_validate_real_link_table_is_ready(tmp_path, monkeypatch):
    client = configure_api(tmp_path, monkeypatch)
    content = Path("table_test/1-链接.xlsx").read_bytes()

    response = client.post("/api/v1/tasks/validate", content=content)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert len(payload["records"]) == 6


def test_media_name_correction_changes_task_to_ready(tmp_path, monkeypatch):
    client = configure_api(tmp_path, monkeypatch)
    workbook = load_workbook("table_test/1-链接.xlsx")
    workbook["Sheet1"]["A2"] = "Alex Cu1"
    output = BytesIO()
    workbook.save(output)
    workbook.close()

    first = client.post("/api/v1/tasks/validate", content=output.getvalue()).json()
    assert first["status"] == "needs_correction"
    assert "Alex Cui" in first["allowed_media_names"]

    corrected = client.post(
        f"/api/v1/tasks/{first['task_id']}/corrections",
        json={"media_name_corrections": {"2": "Alex Cui"}},
    ).json()

    assert corrected["status"] == "ready"
    assert not corrected["issues"]


def test_monthly_analytics_persists_only_eligible_details(tmp_path, monkeypatch):
    client = configure_api(tmp_path, monkeypatch)
    context = WorkflowContext(
        run_id="run-stats",
        input_file="input.xlsx",
        quote_details={
            "details": [
                {"id": "1", "媒体": "媒体A", "文章类型": "视频", "发布日期": "2026-08-20", "费用": 2000, "eligible_for_monthly_summary": True},
                {"id": "2", "媒体": "异常媒体", "文章类型": "图文", "发布日期": "2026-08-20", "费用": 99999, "eligible_for_monthly_summary": False},
            ]
        },
    )

    api._save_completed_statistics("task-stats", context)
    payload = client.get("/api/v1/analytics/monthly?month=2026-08").json()

    assert payload["batch_count"] == 1
    assert payload["quote_count"] == 1
    assert payload["total_fee"] == 2000
    assert payload["top_media"] == [{"media": "媒体A", "quote_count": 1, "total_fee": 2000.0}]
