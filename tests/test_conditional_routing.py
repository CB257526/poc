"""测试条件路由功能"""

import pytest
from workflow.graph import should_continue
from workflow.models import WorkflowState


def test_should_continue_with_critical_error():
    """测试：有critical错误时应该终止"""
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
        "table_paths": {},
        "table_metadata": {},
        "records": [{"id": "rec_1"}],
        "quote_details": None,
        "monthly_summary": None,
        "payment_rows": None,
        "output_files": {},
        "issues": [
            {
                "level": "critical",
                "message": "严重错误",
                "node_id": "node_00"
            }
        ],
        "node_statuses": {},
        "metrics": {}
    }

    result = should_continue(state)
    assert result == "end", "有critical错误时应该返回'end'"


def test_should_continue_with_no_records():
    """测试：没有记录时应该终止"""
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
        "table_paths": {},
        "table_metadata": {},
        "records": [],  # 空记录列表
        "quote_details": None,
        "monthly_summary": None,
        "payment_rows": None,
        "output_files": {},
        "issues": [],
        "node_statuses": {},
        "metrics": {}
    }

    result = should_continue(state)
    assert result == "end", "没有记录时应该返回'end'"


def test_should_continue_with_warnings_only():
    """测试：只有warning时应该继续"""
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
        "table_paths": {},
        "table_metadata": {},
        "records": [{"id": "rec_1"}],
        "quote_details": None,
        "monthly_summary": None,
        "payment_rows": None,
        "output_files": {},
        "issues": [
            {
                "level": "warning",
                "message": "警告信息",
                "node_id": "node_01"
            }
        ],
        "node_statuses": {},
        "metrics": {}
    }

    result = should_continue(state)
    assert result == "continue", "只有warning时应该返回'continue'"


def test_should_continue_with_valid_state():
    """测试：正常状态应该继续"""
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
        "table_paths": {},
        "table_metadata": {},
        "records": [
            {"id": "rec_1"},
            {"id": "rec_2"}
        ],
        "quote_details": None,
        "monthly_summary": None,
        "payment_rows": None,
        "output_files": {},
        "issues": [],
        "node_statuses": {},
        "metrics": {}
    }

    result = should_continue(state)
    assert result == "continue", "正常状态应该返回'continue'"


def test_should_continue_mixed_issues():
    """测试：有error但没有critical时应该继续"""
    state: WorkflowState = {
        "run_id": "test",
        "run_started_at": "2026-08-20T10:00:00",
        "config": {},
        "input_file": "/test.xlsx",
        "table_paths": {},
        "table_metadata": {},
        "records": [{"id": "rec_1"}],
        "quote_details": None,
        "monthly_summary": None,
        "payment_rows": None,
        "output_files": {},
        "issues": [
            {
                "level": "warning",
                "message": "警告",
                "node_id": "node_01"
            },
            {
                "level": "error",
                "message": "错误",
                "node_id": "node_01"
            }
        ],
        "node_statuses": {},
        "metrics": {}
    }

    result = should_continue(state)
    assert result == "continue", "有error但没有critical时应该继续"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
