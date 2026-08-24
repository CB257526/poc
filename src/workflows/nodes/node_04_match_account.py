"""节点4: 匹配账户信息"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger, ExcelService

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

        account_index = self._build_account_index()

        # 处理每条记录
        for record in context.records:
            metrics.processed_count += 1
            record_id = record.get("id", "unknown")

            try:
                # 节点3未通过的记录不能继续匹配账户。
                if record.get("processable") is False:
                    record["account_match_status"] = "skipped"
                    continue

                # 获取媒体名称用于匹配账户
                media_name = record.get("媒体")

                if not media_name:
                    record["account_match_status"] = "not_found"
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

                candidates = account_index.get(self._normalize_name(media_name), [])
                if len(candidates) > 1:
                    record["account_match_status"] = "duplicate"
                    record["processable"] = False
                    issues.append(Issue(
                        level="error",
                        code="DUPLICATE_ACCOUNT_MEDIA",
                        message=f"账户信息表存在重复媒体，无法自动选择账户: {media_name}",
                        node_id=self.node_id,
                        record_id=record_id,
                        details={"media": media_name, "candidate_count": len(candidates)}
                    ))
                    metrics.error_count += 1
                    continue

                matched = candidates[0] if candidates else None

                if matched:
                    # 填充账户信息（列名对齐「账户信息」表头：户名/开户行信息/银行卡账号）
                    record["收款方"] = (
                        matched.get("收款方")
                        or matched.get("户名")
                        or matched.get("账户名称")
                    )
                    record["开户行"] = (
                        matched.get("开户行")
                        or matched.get("开户行信息（具体到支行）")
                        or matched.get("银行")
                    )
                    record["账号"] = (
                        matched.get("账号")
                        or matched.get("银行卡账号")
                        or matched.get("银行账号")
                    )
                    record["联系方式"] = (
                        matched.get("联系方式") or matched.get("电话")
                    )
                    record["身份证"] = (
                        matched.get("身份证") or matched.get("身份证号")
                    )
                    record["开户行所在城市"] = (
                        matched.get("开户行所在城市")
                        or matched.get("开户城市")
                    )

                    # 只校验付款及约稿输出所需字段是否存在，不重复核验其真实性。
                    missing_fields = []
                    for field_name in (
                        "收款方", "身份证", "账号", "联系方式", "开户行", "开户行所在城市"
                    ):
                        if not record.get(field_name):
                            missing_fields.append(field_name)

                    if missing_fields:
                        record["account_match_status"] = "incomplete"
                        record["processable"] = False
                        issues.append(Issue(
                            level="error",
                            code="MISSING_ACCOUNT_FIELDS",
                            message=f"账户信息不完整，缺少: {', '.join(missing_fields)}",
                            node_id=self.node_id,
                            record_id=record_id,
                            details={"missing_fields": missing_fields}
                        ))
                        metrics.error_count += 1
                    else:
                        record["account_match_status"] = "matched"
                        record["processable"] = True
                        metrics.success_count += 1
                    logger.debug(
                        "account_matched",
                        record_id=record_id,
                        media=media_name,
                        payee=record.get("收款方")
                    )
                else:
                    # 未匹配到账户
                    record["account_match_status"] = "not_found"
                    record["processable"] = False
                    issues.append(Issue(
                        level="error",
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

    def _build_account_index(self) -> Dict[str, List[Dict[str, Any]]]:
        """按标准化媒体名称建立账户索引，并保留重名记录供校验。"""
        account_index: Dict[str, List[Dict[str, Any]]] = {}
        for row in self._account_data or []:
            row_media = (
                row.get("媒体")
                or row.get("媒体名称")
                or row.get("账户关联媒体")
            )
            if not row_media:
                continue
            key = self._normalize_name(row_media)
            account_index.setdefault(key, []).append(row)
        return account_index

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

        candidates = self._build_account_index().get(self._normalize_name(media_name), [])
        return candidates[0] if len(candidates) == 1 else None

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
