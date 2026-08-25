"""后台启动工作流，供 MCP start_run 使用。"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from workflows.models import WorkflowContext
from workflows.paths import default_table_dir, output_root, runtime_params, run_output_dir
from workflows.runtime.store import get_run_store
from workflows.services import get_logger
from workflows.workflow_run import run_workflow

logger = get_logger()


class WorkflowStartError(ValueError):
    pass


def start_workflow_job(
    input_file: str,
    table_dir: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """校验路径后后台启动一次完整运行，立即返回 run_id。"""
    input_path = Path(input_file).expanduser().resolve()
    if not input_path.is_file():
        raise WorkflowStartError(f"输入文件不存在: {input_path}")
    if input_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise WorkflowStartError(f"输入必须是 Excel 文件: {input_path}")

    table_path = Path(table_dir).expanduser().resolve() if table_dir else default_table_dir()
    if not table_path.is_dir():
        raise WorkflowStartError(f"参考表目录不存在: {table_path}")

    output_root_path = Path(output_dir).expanduser().resolve() if output_dir else output_root()
    output_root_path.mkdir(parents=True, exist_ok=True)

    run_id = f"run_{int(time.time() * 1000)}_{os.getpid()}_{threading.get_ident()}"
    params = runtime_params(
        run_id=run_id,
        input_file=input_path,
        table_dir=table_path,
        output_root_dir=output_root_path,
    )
    run_out = run_output_dir(run_id, output_root_path)
    context = WorkflowContext(
        run_id=run_id,
        run_started_at=datetime.now(),
        input_file=str(input_path),
        table_dir=str(table_path),
        config={
            "output_root": str(output_root_path),
            "output_dir": str(run_out),
            "runtime_dir": params["runtime_dir"],
            "runtime_db": params["runtime_db"],
            "paths": params,
        },
        run_status="running",
    )
    get_run_store().save_run(context)

    def _run() -> None:
        try:
            run_workflow(
                input_file=str(input_path),
                table_dir=str(table_path),
                config={
                    "output_root": str(output_root_path),
                    "output_dir": str(run_out),
                },
                run_id=run_id,
            )
        except Exception:
            logger.error("background_workflow_failed", run_id=run_id, exc_info=True)

    thread = threading.Thread(target=_run, name=f"workflow-{run_id}", daemon=True)
    thread.start()
    return {
        "run_id": run_id,
        "status": "running",
        "input_file": params["input_file"],
        "table_dir": params["table_dir"],
        "output_dir": params["output_dir"],
        "output_root": params["output_root"],
        "runtime_db": params["runtime_db"],
        "paths": params,
        "message": "工作流已在后台启动。用 wait_run 跟踪进度，node_02 爬取可能需要数十秒。",
    }
