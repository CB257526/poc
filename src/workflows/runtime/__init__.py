"""工作流运行时：持久化、查询视图、节点清单。"""

from workflows.runtime.catalog import WORKFLOW_NODES, get_node_catalog
from workflows.runtime.store import RunStore, get_run_store, reset_run_store
from workflows.runtime.views import WorkflowQueryService

__all__ = [
    "WORKFLOW_NODES",
    "get_node_catalog",
    "RunStore",
    "get_run_store",
    "reset_run_store",
    "WorkflowQueryService",
    "start_workflow_job",
    "WorkflowStartError",
]


def __getattr__(name: str):
    if name in {"start_workflow_job", "WorkflowStartError"}:
        from workflows.runtime.jobs import WorkflowStartError, start_workflow_job

        mapping = {
            "start_workflow_job": start_workflow_job,
            "WorkflowStartError": WorkflowStartError,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
