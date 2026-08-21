"""节点4: 匹配账户信息"""

from typing import Dict, Any, Optional
from datetime import datetime

from workflow.nodes.base import BaseNode
from workflow.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflow.services import get_logger, ExcelService

logger = get_logger()


class Node04MatchAccount(BaseNode):
    """
    匹配账户信息节点

    职责：
    1. 从账户信息表中匹配付款信息
    2. 包括：收款方、开户行、账号等
    3. 验证账户信息完整性
    """

    def __init__(self):
        super().__init__("node_04", "匹配账户信息")
        self._account_data = None

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理账户匹配"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        # 加载账户信息表
        try:
            account_table_path = context.get_table_path("4-账户信息")
            self._account_data = ExcelService.read_sheet_as_dicts(account_table_path)
            logger.info(
                "account_table_loaded",
                path=account_table_path,
                rows=len(self._account_data)
            )
        except Exception as e:
            issue = Issue(
                level="critical",
                code="TABLE_LOAD_FAILED",
                message=f"无法加载账户信息表: {str(e)}",
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
                # 获取媒体名称用于匹配账户
                media_name = record.get("媒体")

                if not media_name:
                    issues.append(Issue(
                        level="error",
                        code="MISSING_MEDIA_NAME",
                        message="记录缺少媒体名称",
                        node_id=self.node_id,
                        record_id=record_id
                    ))
                    metrics.error_count += 1
                    continue

                # 从账户信息表中匹配
                matched = self._match_account_info(media_name)

                if matched:
                    # 填充账户信息
                    record["收款方"] = matched.get("收款方") or matched.get("账户名称")
                    record["开户行"] = matched.get("开户行") or matched.get("银行")
                    record["账号"] = matched.get("账号") or matched.get("银行账号")
                    record["联系方式"] = matched.get("联系方式") or matched.get("电话")

                    # 验证必填字段
                    missing_fields = []
                    if not record.get("收款方"):
                        missing_fields.append("收款方")
                    if not record.get("账号"):
                        missing_fields.append("账号")

                    if missing_fields:
                        issues.append(Issue(
                            level="warning",
                            code="MISSING_ACCOUNT_FIELDS",
                            message=f"账户信息不完整，缺少: {', '.join(missing_fields)}",
                            node_id=self.node_id,
                            record_id=record_id,
                            details={"missing_fields": missing_fields}
                        ))

                    metrics.success_count += 1
                    logger.debug(
                        "account_matched",
                        record_id=record_id,
                        media=media_name,
                        payee=record.get("收款方")
                    )
                else:
                    # 未匹配到账户
                    issues.append(Issue(
                        level="warning",
                        code="ACCOUNT_NOT_FOUND",
                        message=f"未在账户信息表中找到: {media_name}",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={"media": media_name}
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

    def _match_account_info(self, media_name: str) -> Optional[Dict[str, Any]]:
        """
        从账户信息表中匹配账户信息

        Args:
            media_name: 媒体名称

        Returns:
            匹配到的账户记录，或None
        """
        if not self._account_data:
            return None

        # 标准化媒体名称
        normalized_name = self._normalize_name(media_name)

        # 尝试匹配
        for row in self._account_data:
            # 尝试多个可能的列名
            row_media = (
                row.get("媒体") or
                row.get("媒体名称") or
                row.get("账户关联媒体") or
                row.get("账号")
            )

            if not row_media:
                continue

            normalized_row_media = self._normalize_name(row_media)

            if normalized_name == normalized_row_media:
                return row

        return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        标准化名称用于比较

        - 移除空格
        - 转换为小写
        """
        if not name:
            return ""

        # 移除空格
        name = name.replace(" ", "").replace("　", "")

        # 转换为小写
        name = name.lower()

        return name
