"""工作流运行时管理器"""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from workflow.models import WorkflowState, NodeStatus
from workflow.services import StorageService, get_logger
from workflow.config import config

logger = get_logger()


class WorkflowRuntime:
    """
    工作流运行时管理器

    职责：
    - 启动工作流
    - 查询工作流状态
    - 查询节点状态
    - 管理检查点
    - 访问产物
    """

    def __init__(self):
        self.storage = StorageService(config.get_artifacts_dir())
        self.active_runs: Dict[str, Dict[str, Any]] = {}

        # 获取检查点数据库路径
        checkpoint_db = config.get_checkpoint_db()

        # 创建检查点保存器上下文管理器
        self._checkpointer_cm = SqliteSaver.from_conn_string(checkpoint_db)
        self._checkpointer = self._checkpointer_cm.__enter__()

        # 创建并编译工作流
        from workflow.graph import create_workflow
        workflow = create_workflow()
        self.runnable = workflow.compile(checkpointer=self._checkpointer)

    def start_workflow(
        self,
        input_file: str,
        table_dir: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        启动工作流

        Args:
            input_file: 输入文件路径（表1）
            table_dir: 表格目录，None表示使用配置中的默认值
            metadata: 额外的元数据

        Returns:
            包含 run_id 和初始状态的字典
        """
        # 生成运行ID
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        # 获取表格目录
        if table_dir is None:
            table_dir = config.get_table_dir()

        # 创建运行目录
        self.storage.create_run_dir(run_id)

        # 构建初始状态
        initial_state: WorkflowState = {
            "run_id": run_id,
            "run_started_at": datetime.now().isoformat(),
            "config": {
                "table_dir": table_dir,
                "workflow_name": config.get_workflow_name(),
                "workflow_version": config.get_workflow_version(),
            },
            "input_file": input_file,
            "table_paths": {},
            "table_metadata": {},
            "records": [],
            "quote_details": None,
            "monthly_summary": None,
            "payment_rows": None,
            "output_files": {},
            "issues": [],
            "node_statuses": {},
            "metrics": {}
        }

        if metadata:
            initial_state["config"]["metadata"] = metadata

        logger.info(
            "workflow_started",
            run_id=run_id,
            input_file=input_file,
            table_dir=table_dir
        )

        # 记录到活跃运行
        self.active_runs[run_id] = {
            "run_id": run_id,
            "status": "running",
            "started_at": initial_state["run_started_at"],
            "input_file": input_file
        }

        # 执行工作流（同步执行）
        try:
            # 使用thread_id来标识这次运行的检查点
            config_dict = {"configurable": {"thread_id": run_id}}

            final_state = self.runnable.invoke(initial_state, config_dict)

            # 更新运行记录
            self.active_runs[run_id]["status"] = "completed"
            self.active_runs[run_id]["completed_at"] = datetime.now().isoformat()

            logger.info(
                "workflow_completed",
                run_id=run_id,
                issues_count=len(final_state.get("issues", []))
            )

            return {
                "run_id": run_id,
                "status": "completed",
                "state": final_state
            }

        except Exception as e:
            # 更新运行记录
            self.active_runs[run_id]["status"] = "failed"
            self.active_runs[run_id]["completed_at"] = datetime.now().isoformat()
            self.active_runs[run_id]["error"] = str(e)

            logger.error(
                "workflow_failed",
                run_id=run_id,
                error=str(e),
                exc_info=True
            )

            return {
                "run_id": run_id,
                "status": "failed",
                "error": str(e)
            }

    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        获取运行状态

        Args:
            run_id: 运行ID

        Returns:
            运行状态字典，如果不存在返回None
        """
        if run_id in self.active_runs:
            return self.active_runs[run_id]

        # 尝试从检查点恢复
        try:
            config_dict = {"configurable": {"thread_id": run_id}}
            state = self.runnable.get_state(config_dict)

            if state:
                return {
                    "run_id": run_id,
                    "status": "completed",  # 从检查点恢复说明已完成
                    "state": state.values
                }
        except Exception as e:
            logger.warning("failed_to_get_state_from_checkpoint", run_id=run_id, error=str(e))

        return None

    def get_node_status(self, run_id: str, node_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取节点状态

        Args:
            run_id: 运行ID
            node_id: 节点ID，None表示返回所有节点状态

        Returns:
            节点状态字典或所有节点状态
        """
        run_status = self.get_run_status(run_id)

        if not run_status or "state" not in run_status:
            return None

        state: WorkflowState = run_status["state"]
        node_statuses = state.get("node_statuses", {})

        if node_id:
            return node_statuses.get(node_id)
        else:
            return node_statuses

    def get_issues(
        self,
        run_id: str,
        level: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取问题列表

        Args:
            run_id: 运行ID
            level: 问题级别过滤 (warning/error)
            node_id: 节点ID过滤

        Returns:
            问题列表
        """
        run_status = self.get_run_status(run_id)

        if not run_status or "state" not in run_status:
            return None

        state: WorkflowState = run_status["state"]
        issues = state.get("issues", [])

        # 应用过滤
        if level:
            issues = [i for i in issues if i.get("level") == level]

        if node_id:
            issues = [i for i in issues if i.get("node_id") == node_id]

        return issues

    def get_artifact(self, run_id: str, artifact_name: str) -> Optional[str]:
        """
        获取产物文件路径

        Args:
            run_id: 运行ID
            artifact_name: 产物名称

        Returns:
            文件路径，如果不存在返回None
        """
        return self.storage.get_artifact_path(run_id, artifact_name)

    def list_artifacts(self, run_id: str) -> List[str]:
        """
        列出运行的所有产物

        Args:
            run_id: 运行ID

        Returns:
            产物文件名列表
        """
        return self.storage.list_artifacts(run_id)

    def get_full_state(self, run_id: str) -> Optional[WorkflowState]:
        """
        获取完整的工作流状态

        Args:
            run_id: 运行ID

        Returns:
            完整状态，如果不存在返回None
        """
        run_status = self.get_run_status(run_id)

        if run_status and "state" in run_status:
            return run_status["state"]

        return None

    def __del__(self):
        """清理资源"""
        if hasattr(self, '_checkpointer_cm'):
            try:
                self._checkpointer_cm.__exit__(None, None, None)
            except Exception:
                pass
