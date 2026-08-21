"""节点3: 匹配媒体库"""

from typing import Dict, Any, Optional
from datetime import datetime

from workflow.nodes.base import BaseNode
from workflow.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflow.services import get_logger, ExcelService

logger = get_logger()


class Node03MatchMedia(BaseNode):
    """
    匹配媒体库节点

    职责：
    1. 从媒体库表中匹配媒体等级
    2. 匹配粉丝数
    3. 验证媒体信息完整性
    """

    def __init__(self):
        super().__init__("node_03", "匹配媒体库")
        self._media_data = None

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理媒体匹配"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        # 加载媒体库表
        try:
            media_table_path = context.get_table_path("3-媒体库")
            self._media_data = ExcelService.read_sheet_as_dicts(media_table_path)
            logger.info(
                "media_table_loaded",
                path=media_table_path,
                rows=len(self._media_data)
            )
        except Exception as e:
            issue = Issue(
                level="critical",
                code="TABLE_LOAD_FAILED",
                message=f"无法加载媒体库表: {str(e)}",
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
                # 获取媒体名称和平台
                media_name = record.get("媒体")
                platform = record.get("平台")

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

                # 从媒体库中匹配
                matched = self._match_media_info(media_name, platform)

                if matched:
                    # 填充媒体等级和粉丝数
                    record["媒体等级"] = matched.get("媒体等级") or matched.get("等级")
                    record["粉丝数"] = matched.get("粉丝数") or matched.get("关注数")

                    # 验证必填字段
                    if not record.get("媒体等级"):
                        issues.append(Issue(
                            level="warning",
                            code="MISSING_MEDIA_LEVEL",
                            message=f"未找到媒体等级: {media_name}",
                            node_id=self.node_id,
                            record_id=record_id
                        ))

                    metrics.success_count += 1
                    logger.debug(
                        "media_matched",
                        record_id=record_id,
                        media=media_name,
                        level=record.get("媒体等级")
                    )
                else:
                    # 未匹配到媒体
                    issues.append(Issue(
                        level="warning",
                        code="MEDIA_NOT_FOUND",
                        message=f"未在媒体库中找到: {media_name} ({platform})",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={"media": media_name, "platform": platform}
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

    def _match_media_info(self, media_name: str, platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        从媒体库中匹配媒体信息

        Args:
            media_name: 媒体名称
            platform: 平台名称（可选，用于提高匹配精度）

        Returns:
            匹配到的媒体记录，或None
        """
        if not self._media_data:
            return None

        # 标准化媒体名称
        normalized_name = self._normalize_name(media_name)

        # 首先尝试精确匹配（媒体名 + 平台）
        if platform:
            for row in self._media_data:
                row_media = row.get("媒体") or row.get("媒体名称") or row.get("账号")
                row_platform = row.get("平台")

                if not row_media:
                    continue

                normalized_row_media = self._normalize_name(row_media)

                # 媒体名和平台都匹配
                if normalized_name == normalized_row_media and row_platform == platform:
                    return row

        # 如果精确匹配失败，只按媒体名匹配
        for row in self._media_data:
            row_media = row.get("媒体") or row.get("媒体名称") or row.get("账号")

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
        - 移除特殊字符
        """
        if not name:
            return ""

        # 移除空格
        name = name.replace(" ", "").replace("　", "")

        # 转换为小写
        name = name.lower()

        return name
