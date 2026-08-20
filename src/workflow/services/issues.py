"""问题/错误收集器"""

from typing import List, Dict, Any, Literal, Optional
from workflow.models import Issue
import structlog

logger = structlog.get_logger()


class IssueCollector:
    """统一的错误和问题收集器"""

    def __init__(self):
        self.issues: List[Issue] = []

    def add_issue(
        self,
        level: Literal["warning", "error"],
        code: str,
        message: str,
        node_id: Optional[str] = None,
        record_id: Optional[str] = None,
        field: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        添加一个问题

        Args:
            level: 问题级别 (warning 或 error)
            code: 错误码，建议使用大写下划线命名，如 MEDIA_NOT_FOUND
            message: 人类可读的错误信息
            node_id: 发生问题的节点ID
            record_id: 相关的记录ID
            field: 相关的字段名
            **kwargs: 额外的详细信息
        """
        issue: Issue = {
            "level": level,
            "code": code,
            "message": message,
        }

        if node_id:
            issue["node_id"] = node_id
        if record_id:
            issue["record_id"] = record_id
        if field:
            issue["field"] = field

        # 添加额外信息
        if kwargs:
            issue["details"] = kwargs

        self.issues.append(issue)

        # 记录日志
        logger_method = logger.warning if level == "warning" else logger.error
        logger_method(
            "issue_collected",
            level=level,
            code=code,
            message=message,
            node_id=node_id,
            record_id=record_id,
            field=field
        )

    def add_warning(
        self,
        code: str,
        message: str,
        node_id: Optional[str] = None,
        record_id: Optional[str] = None,
        field: Optional[str] = None,
        **kwargs
    ) -> None:
        """快捷方法：添加警告"""
        self.add_issue("warning", code, message, node_id, record_id, field, **kwargs)

    def add_error(
        self,
        code: str,
        message: str,
        node_id: Optional[str] = None,
        record_id: Optional[str] = None,
        field: Optional[str] = None,
        **kwargs
    ) -> None:
        """快捷方法：添加错误"""
        self.add_issue("error", code, message, node_id, record_id, field, **kwargs)

    def get_issues(self, level: Optional[Literal["warning", "error"]] = None) -> List[Issue]:
        """
        获取问题列表

        Args:
            level: 可选，只返回指定级别的问题

        Returns:
            问题列表
        """
        if level:
            return [issue for issue in self.issues if issue["level"] == level]
        return self.issues

    def has_errors(self) -> bool:
        """是否有error级别的问题"""
        return any(issue["level"] == "error" for issue in self.issues)

    def has_warnings(self) -> bool:
        """是否有warning级别的问题"""
        return any(issue["level"] == "warning" for issue in self.issues)

    def has_issues(self) -> bool:
        """是否有任何问题"""
        return len(self.issues) > 0

    def get_summary(self) -> Dict[str, int]:
        """
        获取问题统计摘要

        Returns:
            包含总数、警告数、错误数的字典
        """
        return {
            "total": len(self.issues),
            "warnings": sum(1 for i in self.issues if i["level"] == "warning"),
            "errors": sum(1 for i in self.issues if i["level"] == "error")
        }

    def get_issues_by_node(self, node_id: str) -> List[Issue]:
        """
        获取特定节点的问题

        Args:
            node_id: 节点ID

        Returns:
            该节点的问题列表
        """
        return [issue for issue in self.issues if issue.get("node_id") == node_id]

    def get_issues_by_record(self, record_id: str) -> List[Issue]:
        """
        获取特定记录的问题

        Args:
            record_id: 记录ID

        Returns:
            该记录的问题列表
        """
        return [issue for issue in self.issues if issue.get("record_id") == record_id]

    def clear(self) -> None:
        """清空所有问题"""
        self.issues.clear()

    def extend(self, issues: List[Issue]) -> None:
        """
        批量添加问题

        Args:
            issues: 问题列表
        """
        self.issues.extend(issues)

    def __len__(self) -> int:
        """返回问题数量"""
        return len(self.issues)

    def __bool__(self) -> bool:
        """是否有问题"""
        return self.has_issues()
