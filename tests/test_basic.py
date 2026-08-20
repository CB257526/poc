"""基础测试 - 验证模块导入和初始化"""

import pytest
from pathlib import Path


def test_imports():
    """测试所有模块是否可以正常导入"""
    # 核心模块
    from workflow import config
    from workflow import models
    from workflow import graph

    # 服务层
    from workflow.services import ExcelService, StorageService, IssueCollector
    from workflow.services import setup_logging, get_logger

    # 节点
    from workflow.nodes import BaseNode, Node00Input, Node01FillBasic

    # 运行时
    from workflow.runtime import WorkflowRuntime

    assert True


def test_config_initialization():
    """测试配置初始化"""
    from workflow.config import config

    # 验证基本配置
    assert config.get_workflow_name() == "quotation-fee-workflow"
    assert config.get_workflow_version() is not None

    # 验证路径配置
    table_dir = config.get_table_dir()
    assert table_dir is not None

    artifacts_dir = config.get_artifacts_dir()
    assert artifacts_dir is not None


def test_models():
    """测试数据模型"""
    from workflow.models import WorkflowState, NodeStatus

    # 创建一个基本的状态对象
    state: WorkflowState = {
        "run_id": "test_run",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/path/to/test.xlsx",
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

    assert state["run_id"] == "test_run"
    assert isinstance(state["records"], list)


def test_graph_creation():
    """测试工作流图创建"""
    from workflow.graph import create_workflow

    workflow = create_workflow()
    assert workflow is not None


def test_services():
    """测试服务层基础功能"""
    from workflow.services import IssueCollector

    collector = IssueCollector()

    # 添加问题
    collector.add_warning(
        code="TEST_WARNING",
        message="测试警告",
        node_id="test_node",
        context={"test": "data"}
    )

    collector.add_error(
        code="TEST_ERROR",
        message="测试错误",
        node_id="test_node"
    )

    # 获取问题
    issues = collector.get_issues()
    assert len(issues) == 2
    assert issues[0]["level"] == "warning"
    assert issues[1]["level"] == "error"


def test_node_base():
    """测试节点基类"""
    from workflow.nodes import BaseNode
    from workflow.models import WorkflowState

    class TestNode(BaseNode):
        def __init__(self):
            super().__init__("test_node", "测试节点")

        def execute(self, state: WorkflowState):
            return self._create_success_output(
                data={"test": "result"},
                processed_count=1,
                success_count=1
            )

    node = TestNode()
    assert node.node_id == "test_node"
    assert node.node_name == "测试节点"

    # 创建测试状态
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
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

    # 执行节点 - __call__返回state而不是NodeOutput
    updated_state = node(state)
    assert updated_state["node_statuses"]["test_node"]["status"] == "completed"
    assert updated_state["node_statuses"]["test_node"]["node_name"] == "测试节点"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
