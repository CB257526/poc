"""节点0: 输入验证 - 新版本"""

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, Issue
from workflows.services import ExcelService, get_logger
import os

logger = get_logger()


class Node00Input(BaseNode):
    """
    节点0: 输入验证

    职责：
    1. 验证输入文件存在且可读
    2. 验证参考表格存在
    3. 读取输入文件的记录
    4. 初始化记录结构
    """

    def __init__(self):
        super().__init__("node_00", "输入验证")

    def process(self, context: WorkflowContext) -> NodeOutput:
        """
        执行输入验证

        Args:
            context: 工作流上下文

        Returns:
            NodeOutput，包含验证结果和初始化的记录
        """
        excel = ExcelService()
        issues = []
        processed_count = 0
        success_count = 0

        # === 1. 验证输入文件 ===
        if not os.path.exists(context.input_file):
            issues.append(Issue(
                level="critical",
                code="INPUT_FILE_NOT_FOUND",
                message=f"输入文件不存在: {context.input_file}",
                node_id=self.node_id
            ))
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 2. 验证参考表格 ===
        required_tables = ["3-媒体库", "4-账户信息", "5-费用"]
        for table_name in required_tables:
            try:
                context.get_table_path(table_name)
            except FileNotFoundError as e:
                issues.append(Issue(
                    level="critical",
                    code="REFERENCE_TABLE_NOT_FOUND",
                    message=str(e),
                    node_id=self.node_id,
                    details={"table_name": table_name}
                ))

        # 如果有 critical 错误，提前返回
        if any(i.level == "critical" for i in issues):
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 3. 读取输入文件 ===
        try:
            # 1-链接.xlsx 是无表头的"主题-媒体-链接"分层表，用专用方法解析
            rows = excel.read_link_sheet(context.input_file, sheet_name="Sheet1")
            if not rows:
                issues.append(Issue(
                    level="critical",
                    code="EMPTY_INPUT_FILE",
                    message="输入文件为空",
                    node_id=self.node_id 
                ))
                return self._create_failure_output(
                    processed_count=0,
                    success_count=0,
                    issues=issues
                )

            processed_count = len(rows)

        except Exception as e:
            issues.append(Issue(
                level="critical",
                code="READ_INPUT_FILE_FAILED",
                message=f"读取输入文件失败: {str(e)}",
                node_id=self.node_id
            ))
            return self._create_failure_output(
                processed_count=0,
                success_count=0,
                issues=issues
            )

        # === 4. 初始化记录结构 ===
        records = []

        for idx, row in enumerate(rows):
            record_id = f"rec_{idx + 1:04d}"

            # 验证必需字段（链接为列表，空列表视为缺失）
            if not row.get("链接"):
                issues.append(Issue(
                    level="error",
                    code="MISSING_REQUIRED_FIELD",
                    message="缺少必需字段：链接",
                    node_id=self.node_id,
                    record_id=record_id
                ))
                continue

            # 创建记录（read_link_sheet 已按媒体聚合，每条记录即一个媒体块，
            # 链接为列表，供 Node1 逐条解析并合并主链接+同步链接）
            record = {
                **row,
                "id": record_id,
            }

            records.append(record)
            success_count += 1

        logger.info(
            "input_validation_completed",
            total_rows=processed_count,
            valid_records=success_count,
            issues_count=len(issues)
        )

        # === 5. 返回结果 ===
        return self._create_success_output(
            processed_count=processed_count, #已处理的总记录数
            success_count=success_count, #成功处理的记录数
            data={"records": records}, #读取表内容
            issues=issues #问题列表
        )
