"""节点2: 完善发布信息"""

import re
from typing import Dict, Any, Optional
from datetime import datetime

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger, ExcelService

logger = get_logger()


class Node02FillPublication(BaseNode):
    """
    完善发布信息节点

    职责：
    1. 从约稿资料表中匹配标题、发布日期、文章类型
    2. 提取截图路径
    3. 验证必填字段
    """

    def __init__(self):
        super().__init__("node_02", "完善发布信息")
        self._publication_data = None

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理发布信息"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        # 加载约稿资料表
        try:
            publication_table_path = context.get_table_path("2-约稿资料")
            self._publication_data = ExcelService.read_sheet_as_dicts(publication_table_path)
            logger.info(
                "publication_table_loaded",
                path=publication_table_path,
                rows=len(self._publication_data)
            )
        except Exception as e:
            issue = Issue(
                level="critical",
                code="TABLE_LOAD_FAILED",
                message=f"无法加载约稿资料表: {str(e)}",
                node_id=self.node_id
            )
            issues.append(issue)
            metrics.error_count = len(context.records)
            return NodeOutput.create_failure(metrics=metrics, issues=issues)

        # 处理每条记录
        for record in context.records:
            metrics.processed_count += 1
            record_id = record.get("id", "unknown")

            try:
                # 获取链接用于匹配：优先用 Node1 识别的主链接，回退到链接列表首条
                link = record.get("primary_link") or record.get("链接")
                if isinstance(link, list):
                    link = link[0] if link else None
                if not link:
                    issues.append(Issue(
                        level="error",
                        code="MISSING_LINK",
                        message="记录缺少链接字段",
                        node_id=self.node_id,
                        record_id=record_id
                    ))
                    metrics.error_count += 1
                    continue

                # 从约稿资料表中匹配数据
                matched = self._match_publication_info(link)

                if matched:
                    # 填充发布信息
                    record["标题"] = matched.get("标题")
                    record["发布日期"] = matched.get("发布日期")
                    record["文章类型"] = matched.get("文章类型")
                    record["截图"] = matched.get("截图")

                    # 验证必填字段
                    missing_fields = []
                    if not record.get("标题"):
                        missing_fields.append("标题")
                    if not record.get("发布日期"):
                        missing_fields.append("发布日期")

                    if missing_fields:
                        issues.append(Issue(
                            level="warning",
                            code="MISSING_FIELDS",
                            message=f"缺少字段: {', '.join(missing_fields)}",
                            node_id=self.node_id,
                            record_id=record_id,
                            details={"missing_fields": missing_fields}
                        ))

                    metrics.success_count += 1
                    logger.debug(
                        "publication_info_filled",
                        record_id=record_id,
                        title=record.get("标题")
                    )
                else:
                    # 未匹配到数据
                    issues.append(Issue(
                        level="warning",
                        code="NO_MATCH",
                        message=f"未在约稿资料表中找到匹配: {link[:50]}...",
                        node_id=self.node_id,
                        record_id=record_id
                    ))
                    metrics.error_count += 1

            except Exception as e:
                issues.append(Issue(
                    level="error",
                    code="PROCESSING_ERROR",
                    message=f"处理记录时出错: {str(e)}",
                    node_id=self.node_id,
                    record_id=record_id
                ))
                metrics.error_count += 1
                logger.error(
                    "record_processing_error",
                    record_id=record_id,
                    error=str(e)
                )

        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        metrics.duration_ms = duration

        logger.info(
            "node_completed",
            node_id=self.node_id,
            processed=metrics.processed_count,
            success=metrics.success_count,
            errors=metrics.error_count,
            duration_ms=duration
        )

        return NodeOutput.create_success(
            metrics=metrics,
            issues=issues
        )

    def _match_publication_info(self, link: str) -> Optional[Dict[str, Any]]:
        """
        从约稿资料表中匹配链接对应的发布信息

        Args:
            link: 待匹配的链接

        Returns:
            匹配到的记录，或None
        """
        if not self._publication_data:
            return None

        # 标准化链接（移除协议、查询参数等）
        normalized_link = self._normalize_link(link)

        for row in self._publication_data:
            row_link = row.get("链接") or row.get("发布链接") or row.get("文章链接")
            if not row_link:
                continue

            normalized_row_link = self._normalize_link(row_link)

            # 比较标准化后的链接
            if normalized_link == normalized_row_link:
                return row

        return None

    @staticmethod
    def _normalize_link(link: str) -> str:
        """
        标准化链接用于比较

        - 移除协议（http/https）
        - 移除www前缀
        - 移除尾部斜杠
        - 移除查询参数
        """
        if not link:
            return ""

        # 移除协议
        link = re.sub(r'^https?://', '', link)

        # 移除www
        link = re.sub(r'^www\.', '', link)

        # 移除查询参数
        link = link.split('?')[0]

        # 移除尾部斜杠
        link = link.rstrip('/')

        return link.lower()
