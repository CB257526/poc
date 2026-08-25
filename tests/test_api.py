from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

import workflows.api as api


def configure_api(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "BASE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(api, "TABLE_DIR", Path("table").resolve())
    api.BASE_DIR.mkdir(parents=True, exist_ok=True)
    api._tasks.clear()
    return TestClient(api.app)


def test_validate_real_link_table_is_ready(tmp_path, monkeypatch):
    client = configure_api(tmp_path, monkeypatch)
    content = Path("table/1-链接.xlsx").read_bytes()

    response = client.post("/api/v1/tasks/validate", content=content)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert len(payload["records"]) == 6


def test_media_name_correction_changes_task_to_ready(tmp_path, monkeypatch):
    client = configure_api(tmp_path, monkeypatch)
    workbook = load_workbook("table/1-链接.xlsx")
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
