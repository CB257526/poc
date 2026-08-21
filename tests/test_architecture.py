"""测试新架构 - 基于 LangChain"""

import pytest
import os
from workflows.models import WorkflowContext, Issue, NodeMetrics, NodeOutput
from workflows.nodes.base import BaseNode, WorkflowTerminated
from workflows.nodes.node_00_input import Node00Input
from workflows.nodes.node_01_fill_basic import Node01FillBasic
from workflows.workflow_run import create_workflow, run_workflow


def test_workflow_context():
    """测试 WorkflowContext 模型"""
    context = WorkflowContext(
        run_id="test_run",
        input_file="/test/input.xlsx",
        table_dir="/test/table"
    )

    assert context.run_id == "test_run"
    assert context.input_file == "/test/input.xlsx"
    assert context.table_dir == "/test/table"
    assert context.records == []
    assert context.issues == []
    assert context.completed_nodes == []


def test_issue_model():
    """测试 Issue 模型"""
    issue = Issue(
        level="error",
        code="TEST_ERROR",
        message="测试错误",
        node_id="node_00",
        record_id="rec_001",
        details={"key": "value"}
    )

    assert issue.level == "error"
    assert issue.code == "TEST_ERROR"
    assert issue.message == "测试错误"
    assert issue.node_id == "node_00"
    assert issue.record_id == "rec_001"
    assert issue.details == {"key": "value"}


def test_node_output():
    """测试 NodeOutput 模型"""
    metrics = NodeMetrics(
        processed_count=10,
        success_count=8,
        error_count=2,
        duration_ms=100.5
    )

    output = NodeOutput.create_success(
        metrics=metrics,
        data={"records": [{"id": "1"}]},
        issues=[]
    )

    assert output.success is True
    assert output.metrics.processed_count == 10
    assert output.data == {"records": [{"id": "1"}]}


def test_context_add_issue():
    """测试上下文添加问题"""
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx"
    )

    context.add_issue(
        level="warning",
        code="TEST_WARNING",
        message="测试警告",
        node_id="node_01"
    )

    assert len(context.issues) == 1
    assert context.issues[0].level == "warning"
    assert context.issues[0].code == "TEST_WARNING"


def test_context_has_critical_errors():
    """测试检测 critical 错误"""
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx"
    )

    # 没有错误
    assert context.has_critical_errors() is False

    # 添加 warning
    context.add_issue(
        level="warning",
        code="TEST",
        message="test",
        node_id="node_01"
    )
    assert context.has_critical_errors() is False

    # 添加 critical
    context.add_issue(
        level="critical",
        code="TEST",
        message="test",
        node_id="node_01"
    )
    assert context.has_critical_errors() is True


def test_context_get_issues_by_level():
    """测试按级别获取问题"""
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx"
    )

    context.add_issue(level="warning", code="W1", message="w1", node_id="n1")
    context.add_issue(level="error", code="E1", message="e1", node_id="n1")
    context.add_issue(level="warning", code="W2", message="w2", node_id="n2")
    context.add_issue(level="critical", code="C1", message="c1", node_id="n2")

    warnings = context.get_issues_by_level("warning")
    errors = context.get_issues_by_level("error")
    criticals = context.get_issues_by_level("critical")

    assert len(warnings) == 2
    assert len(errors) == 1
    assert len(criticals) == 1


def test_base_node_simple():
    """测试节点基类"""

    class TestNode(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            return NodeOutput.create_success(
                metrics=NodeMetrics(processed_count=1, success_count=1),
                data={"records": [{"id": "1"}]}  # 返回 records，不是未知字段
            )

    node = TestNode("test_node", "测试节点")
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx",
        records=[{"id": "1"}]  # 提供初始记录，避免被终止
    )

    result = node.invoke(context)

    assert result.current_node == "test_node"
    assert "test_node" in result.completed_nodes
    assert len(result.issues) == 0
    assert len(result.records) == 1


def test_base_node_with_issues():
    """测试节点返回问题"""

    class TestNode(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            issues = [
                Issue(
                    level="warning",
                    code="TEST",
                    message="test warning",
                    node_id=self.node_id
                )
            ]
            return NodeOutput.create_success(
                metrics=NodeMetrics(processed_count=1, success_count=1),
                issues=issues
            )

    node = TestNode("test_node", "测试节点")
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx",
        records=[{"id": "1"}]  # 有记录，不会终止
    )

    result = node.invoke(context)

    assert len(result.issues) == 1
    assert result.issues[0].level == "warning"


def test_base_node_terminates_on_critical():
    """测试节点遇到 critical 错误时终止"""

    class TestNode(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            issues = [
                Issue(
                    level="critical",
                    code="CRITICAL_ERROR",
                    message="严重错误",
                    node_id=self.node_id
                )
            ]
            return NodeOutput.create_failure(
                metrics=NodeMetrics(processed_count=1, success_count=0, error_count=1),
                issues=issues
            )

    node = TestNode("test_node", "测试节点")
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx",
        records=[{"id": "1"}]
    )

    with pytest.raises(WorkflowTerminated):
        node.invoke(context)

    # 上下文应该包含 critical issue
    assert context.has_critical_errors()


def test_base_node_exception_handling():
    """测试节点异常处理"""

    class FailingNode(BaseNode):
        def process(self, context: WorkflowContext) -> NodeOutput:
            raise ValueError("模拟节点执行失败")

    node = FailingNode("failing_node", "失败节点")
    context = WorkflowContext(
        run_id="test",
        input_file="/test.xlsx"
    )

    with pytest.raises(WorkflowTerminated):
        node.invoke(context)

    # 应该有一个 critical issue
    assert context.has_critical_errors()
    assert any("模拟节点执行失败" in i.message for i in context.issues)


def test_workflow_creation():
    """测试工作流创建"""
    workflow = create_workflow()

    assert workflow is not None
    # RunnableSequence 应该包含多个步骤
    assert hasattr(workflow, 'invoke')


def test_node_00_input_file_not_found():
    """测试节点0：输入文件不存在"""
    node = Node00Input()
    context = WorkflowContext(
        run_id="test",
        input_file="/nonexistent/file.xlsx",
        table_dir="./table"
    )

    with pytest.raises(WorkflowTerminated):
        node.invoke(context)

    assert context.has_critical_errors()
    critical_issues = context.get_issues_by_level("critical")
    assert any("INPUT_FILE_NOT_FOUND" in i.code for i in critical_issues)


def test_node_01_platform_identification():
    """测试节点1：平台识别"""
    from workflows.nodes.node_01_fill_basic import Node01FillBasic

    node = Node01FillBasic()

    # 测试各种平台
    assert node._identify_platform("https://www.zhihu.com/question/123") == "知乎"
    assert node._identify_platform("https://weibo.com/123") == "微博"
    assert node._identify_platform("https://mp.weixin.qq.com/s/abc") == "微信公众号"
    assert node._identify_platform("https://www.bilibili.com/video/BV123") == "B站"
    assert node._identify_platform("https://unknown-domain.com/page") == "unknown"


def test_node_01_url_extraction():
    """测试节点1：URL提取"""
    from workflows.nodes.node_01_fill_basic import Node01FillBasic

    node = Node01FillBasic()

    # 单个URL
    text1 = "知乎: https://www.zhihu.com/question/123"
    urls1 = node._extract_urls_from_text(text1)
    assert len(urls1) == 1
    assert urls1[0][1] == "https://www.zhihu.com/question/123"

    # 多个URL（换行分隔）
    text2 = "https://www.zhihu.com/q/1\nhttps://weibo.com/123"
    urls2 = node._extract_urls_from_text(text2)
    assert len(urls2) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
