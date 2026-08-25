"""一次运行的路径约定。

MCP、CLI、HTTP 后端只要都走这里，就不会把数据库和 Excel 产物写到同一处。
默认仍落在仓库的 runtime/ / output/，但可用环境变量整段挪走。
"""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default.resolve()
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def runtime_dir() -> Path:
    path = _env_path("WORKFLOW_RUNTIME_DIR", project_root() / "runtime")
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_db_path() -> Path:
    return runtime_dir() / "workflow.db"


def output_root() -> Path:
    path = _env_path("WORKFLOW_OUTPUT_DIR", project_root() / "output")
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_output_dir(run_id: str, output_root_dir: str | Path | None = None) -> Path:
    root = Path(output_root_dir).expanduser().resolve() if output_root_dir else output_root()
    path = root / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_table_dir() -> Path:
    return _env_path("WORKFLOW_TABLE_DIR", project_root() / "table")


def default_input_file() -> Path:
    raw = os.getenv("WORKFLOW_INPUT_FILE")
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    return default_table_dir() / "1-链接.xlsx"


def runtime_params(
    *,
    run_id: str,
    input_file: str | Path,
    table_dir: str | Path | None = None,
    output_root_dir: str | Path | None = None,
) -> dict[str, str]:
    """一次运行能自述的全部路径。"""
    input_path = Path(input_file).expanduser().resolve()
    tables = Path(table_dir).expanduser().resolve() if table_dir else default_table_dir()
    out_root = Path(output_root_dir).expanduser().resolve() if output_root_dir else output_root()
    run_out = run_output_dir(run_id, out_root)
    return {
        "run_id": run_id,
        "input_file": str(input_path),
        "table_dir": str(tables),
        "table_1": str(input_path),
        "table_3": str(tables / "3-媒体库.xlsx"),
        "table_4": str(tables / "4-账户信息.xlsx"),
        "table_5": str(tables / "5-费用.xlsx"),
        "output_root": str(out_root),
        "output_dir": str(run_out),
        "runtime_dir": str(runtime_dir()),
        "runtime_db": str(runtime_db_path()),
    }
