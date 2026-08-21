"""节点5: 计算费用"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger, ExcelService

logger = get_logger()


class Node05CalculateFee(BaseNode):
    """
    计算费用节点

    职责：
    1. 从费用表中读取费用规则
    2. 根据媒体等级、文章类型计算费用
    3. 生成约稿明细数据
    4. 验证费用计算结果
    """

    def __init__(self):
        super().__init__("node_05", "计算费用")
        self._fee_rules = None

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理费用计算"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        # 加载费用表
        try:
            fee_table_path = context.get_table_path("5-费用")
            self._fee_rules = ExcelService.read_sheet_as_dicts(fee_table_path)
            logger.info(
                "fee_table_loaded",
                path=fee_table_path,
                rows=len(self._fee_rules)
            )
        except Exception as e:
            issue = Issue(
                level="critical",
                code="TABLE_LOAD_FAILED",
                message=f"无法加载费用表: {str(e)}",
                node_id=self.node_id
            )
            issues.append(issue)
            metrics.error_count = len(context.records)
            return NodeOutput.create_failure(metrics=metrics, issues=issues)

        # 准备约稿明细列表
        quote_details = []

        # 处理每条记录
        for record in context.records:
            metrics.processed_count += 1
            record_id = record.get("id", "unknown")

            try:
                # 获取计算费用所需的字段
                media_level = record.get("媒体等级")
                article_type = record.get("文章类型")
                media_name = record.get("媒体")
                title = record.get("标题")

                if not media_level:
                    issues.append(Issue(
                        level="error",
                        code="MISSING_MEDIA_LEVEL",
                        message="缺少媒体等级，无法计算费用",
                        node_id=self.node_id,
                        record_id=record_id
                    ))
                    metrics.error_count += 1
                    continue

                if not article_type:
                    issues.append(Issue(
                        level="warning",
                        code="MISSING_ARTICLE_TYPE",
                        message="缺少文章类型，使用默认费用",
                        node_id=self.node_id,
                        record_id=record_id
                    ))

                # 查找费用规则
                fee = self._calculate_fee(media_level, article_type)

                if fee is not None:
                    record["费用"] = fee

                    # 生成约稿明细行
                    detail_link = record.get("primary_link") or record.get("链接")
                    if isinstance(detail_link, list):
                        detail_link = detail_link[0] if detail_link else None
                    detail_row = {
                        "id": record_id,
                        "媒体": media_name,
                        "平台": record.get("平台"),
                        "标题": title,
                        "发布日期": record.get("发布日期"),
                        "链接": detail_link,
                        "媒体等级": media_level,
                        "文章类型": article_type,
                        "费用": fee,
                        "收款方": record.get("收款方"),
                        "开户行": record.get("开户行"),
                        "账号": record.get("账号"),
                        "联系方式": record.get("联系方式"),
                        "截图": record.get("截图")
                    }
                    quote_details.append(detail_row)

                    metrics.success_count += 1
                    logger.debug(
                        "fee_calculated",
                        record_id=record_id,
                        media=media_name,
                        level=media_level,
                        fee=fee
                    )
                else:
                    # 未找到费用规则
                    issues.append(Issue(
                        level="error",
                        code="FEE_RULE_NOT_FOUND",
                        message=f"未找到费用规则: {media_level} / {article_type}",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={"media_level": media_level, "article_type": article_type}
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

        # 将约稿明细保存到context
        context.quote_details = {
            "details": quote_details,
            "total_count": len(quote_details),
            "total_fee": sum(float(d.get("费用", 0)) for d in quote_details)
        }

        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        metrics.duration_ms = duration

        logger.info(
            "node_completed",
            node_id=self.node_id,
            processed=metrics.processed_count,
            success=metrics.success_count,
            errors=metrics.error_count,
            total_fee=context.quote_details["total_fee"],
            duration_ms=duration
        )

        return NodeOutput.create_success(
            metrics=metrics,
            issues=issues,
            data={"quote_details": context.quote_details}
        )

    def _calculate_fee(self, media_level: str, article_type: Optional[str] = None) -> Optional[float]:
        """
        根据媒体等级和文章类型计算费用

        Args:
            media_level: 媒体等级（如 A+, A, B, C 等）
            article_type: 文章类型（如 原创、转载、视频等）

        Returns:
            费用金额，或None（未找到规则）
        """
        if not self._fee_rules:
            return None

        # 首先尝试精确匹配（媒体等级 + 文章类型）
        if article_type:
            for rule in self._fee_rules:
                rule_level = rule.get("媒体等级") or rule.get("等级")
                rule_type = rule.get("文章类型") or rule.get("类型")
                rule_fee = rule.get("费用") or rule.get("金额")

                if rule_level == media_level and rule_type == article_type:
                    return self._parse_fee(rule_fee)

        # 如果精确匹配失败，只按媒体等级匹配（返回默认费用）
        for rule in self._fee_rules:
            rule_level = rule.get("媒体等级") or rule.get("等级")
            rule_type = rule.get("文章类型") or rule.get("类型")
            rule_fee = rule.get("费用") or rule.get("金额")

            # 匹配等级，且没有指定类型（表示默认）
            if rule_level == media_level and (not rule_type or rule_type == "默认"):
                return self._parse_fee(rule_fee)

        return None

    @staticmethod
    def _parse_fee(fee_value: Any) -> Optional[float]:
        """
        解析费用值

        Args:
            fee_value: 费用值（可能是字符串、数字、None）

        Returns:
            浮点数费用，或None
        """
        if fee_value is None:
            return None

        try:
            # 如果是字符串，移除可能的货币符号和逗号
            if isinstance(fee_value, str):
                fee_value = fee_value.replace("¥", "").replace("￥", "").replace(",", "").strip()

            return float(fee_value)
        except (ValueError, TypeError):
            return None
