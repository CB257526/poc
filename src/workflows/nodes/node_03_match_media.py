"""节点3: 匹配媒体库"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger, ExcelService

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

        # 媒体库没有“平台”字段，业务上以标准化后的媒体名称作为唯一键。
        media_index = self._build_media_index()

        # 处理每条记录
        for record in context.records:
            metrics.processed_count += 1
            record_id = record.get("id", "unknown")

            try:
                # 获取媒体名称
                media_name = record.get("媒体")

                if not media_name:
                    record["media_match_status"] = "pending_confirmation"
                    record["processable"] = False
                    issues.append(Issue(
                        level="error",
                        code="MISSING_MEDIA_NAME",
                        message="记录缺少媒体名称",
                        node_id=self.node_id,
                        record_id=record_id
                    ))
                    metrics.error_count += 1
                    continue

                # 媒体名称在媒体库中必须唯一；重名时禁止静默选择第一条。
                candidates = media_index.get(self._normalize_name(media_name), [])
                if len(candidates) > 1:
                    record["media_match_status"] = "pending_confirmation"
                    record["processable"] = False
                    issues.append(Issue(
                        level="error",
                        code="DUPLICATE_MEDIA_NAME",
                        message=f"媒体库存在重复媒体名称，无法自动匹配: {media_name}",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={"media": media_name, "candidate_count": len(candidates)}
                    ))
                    metrics.error_count += 1
                    continue

                matched = candidates[0] if candidates else None

                if matched:
                    # 填充媒体等级和粉丝数（列名对齐「媒体库」表头：媒体级别/粉丝量）
                    record["媒体等级"] = (
                        matched.get("媒体等级")
                        or matched.get("媒体级别")
                        or matched.get("等级")
                    )
                    record["粉丝量"] = (
                        matched.get("粉丝数")
                        or matched.get("粉丝量")
                        or matched.get("关注数")
                    )

                    # 验证节点3的必填输出字段
                    missing_fields = []
                    if not record.get("媒体等级"):
                        missing_fields.append("媒体等级")
                        issues.append(Issue(
                            level="error",
                            code="MISSING_MEDIA_LEVEL",
                            message=f"未找到媒体等级: {media_name}",
                            node_id=self.node_id,
                            record_id=record_id
                        ))
                    if not record.get("粉丝量"):
                        missing_fields.append("粉丝量")
                        issues.append(Issue(
                            level="error",
                            code="MISSING_FAN_COUNT",
                            message=f"未找到粉丝量: {media_name}",
                            node_id=self.node_id,
                            record_id=record_id
                        ))

                    if missing_fields:
                        record["media_match_status"] = "incomplete"
                        record["processable"] = False
                        metrics.error_count += 1
                    else:
                        record["media_match_status"] = "matched"
                        record["processable"] = True
                        metrics.success_count += 1
                    logger.debug(
                        "media_matched",
                        record_id=record_id,
                        media=media_name,
                        level=record.get("媒体等级")
                    )
                else:
                    # 未匹配到媒体
                    record["media_match_status"] = "pending_confirmation"
                    record["processable"] = False
                    # 节点0已做过媒体库名称校验时不重复展示同一错误；
                    # 单独运行节点3时仍保留自身的防御性校验。
                    already_reported = any(
                        issue.code == "MEDIA_NOT_IN_LIBRARY"
                        and issue.record_id == record_id
                        for issue in context.issues
                    )
                    if not already_reported:
                        issues.append(Issue(
                            level="error",
                            code="MEDIA_NOT_FOUND",
                            message=f"表1媒体名称无法匹配媒体库: {media_name}",
                            node_id=self.node_id,
                            record_id=record_id,
                            details={
                                "input_media_name": media_name,
                                "requires_manual_confirmation": True
                            }
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

    def _build_media_index(self) -> Dict[str, List[Dict[str, Any]]]:
        """按标准化媒体名称建立索引，并保留重名记录供调用方校验。"""
        media_index: Dict[str, List[Dict[str, Any]]] = {}
        for row in self._media_data or []:
            row_media = row.get("媒体") or row.get("媒体名称") or row.get("账号")
            if not row_media:
                continue
            key = self._normalize_name(row_media)
            media_index.setdefault(key, []).append(row)
        return media_index

    def _match_media_info(self, media_name: str) -> Optional[Dict[str, Any]]:
        """
        从媒体库中匹配媒体信息

        Args:
            media_name: 媒体名称
        Returns:
            唯一匹配到的媒体记录；未匹配或存在重名时返回None
        """
        if not self._media_data:
            return None

        candidates = self._build_media_index().get(self._normalize_name(media_name), [])
        return candidates[0] if len(candidates) == 1 else None

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
