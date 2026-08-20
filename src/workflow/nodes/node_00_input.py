"""节点0: 输入节点

职责：
1. 验证表1文件存在且可读
2. 扫描表格目录，检查表2-6是否存在
3. 记录所有表格的元信息
4. 生成文件路径映射
"""

from pathlib import Path
from typing import Dict, Any
from workflow.nodes.base import BaseNode
from workflow.models import WorkflowState, NodeOutput
from workflow.services import ExcelService, IssueCollector, get_logger

logger = get_logger()


class Node00Input(BaseNode):
    """输入节点 - 验证输入文件并准备表格路径映射"""

    def __init__(self):
        super().__init__("node_00", "输入节点")

    def execute(self, state: WorkflowState) -> NodeOutput:
        """
        执行输入验证逻辑

        Args:
            state: 工作流状态，应包含 input_file 和 table_dir

        Returns:
            节点输出，包含 table_paths 和 table_metadata
        """
        issue_collector = IssueCollector()
        excel_service = ExcelService()

        # 获取输入文件和表格目录
        input_file = state.get("input_file")
        table_dir = state.get("config", {}).get("table_dir", "./table")

        if not input_file:
            raise ValueError("缺少必需参数: input_file")

        logger.info(
            "input_validation_started",
            input_file=input_file,
            table_dir=table_dir
        )

        # === 1. 验证输入文件（表1）===
        valid, error_msg = excel_service.validate_excel_file(input_file)
        if not valid:
            issue_collector.add_error(
                code="INPUT_FILE_INVALID",
                message=f"输入文件验证失败: {error_msg}",
                node_id=self.node_id
            )
            raise ValueError(f"输入文件无效: {error_msg}")

        # 获取表1的元信息
        try:
            table1_metadata = excel_service.get_metadata(input_file)
        except Exception as e:
            issue_collector.add_error(
                code="INPUT_FILE_READ_FAILED",
                message=f"无法读取输入文件元信息: {str(e)}",
                node_id=self.node_id
            )
            raise

        # === 2. 扫描表格目录 ===
        table_dir_path = Path(table_dir)
        if not table_dir_path.exists():
            raise ValueError(f"表格目录不存在: {table_dir}")

        # 定义所有表格的标准名称
        table_names = {
            "1-链接": "1-链接.xlsx",
            "2-约稿资料": "2-约稿资料.xlsx",
            "3-媒体库": "3-媒体库.xlsx",
            "4-账户信息": "4-账户信息.xlsx",
            "5-费用": "5-费用.xlsx",
            "6-付款": "6-付款.xlsx"
        }

        # 必需的参考表（3、4、5是必需的）
        required_tables = ["3-媒体库", "4-账户信息", "5-费用"]

        table_paths = {}
        table_metadata = {}

        # 表1使用输入文件
        table_paths["1-链接"] = input_file
        table_metadata["1-链接"] = table1_metadata

        # 扫描其他表格
        for logical_name, filename in table_names.items():
            if logical_name == "1-链接":
                continue  # 已处理

            file_path = table_dir_path / filename

            if file_path.exists():
                # 验证文件
                valid, error_msg = excel_service.validate_excel_file(str(file_path))

                if valid:
                    table_paths[logical_name] = str(file_path)
                    try:
                        metadata = excel_service.get_metadata(str(file_path))
                        table_metadata[logical_name] = metadata
                    except Exception as e:
                        issue_collector.add_warning(
                            code="TABLE_METADATA_FAILED",
                            message=f"无法读取 {logical_name} 的元信息: {str(e)}",
                            node_id=self.node_id
                        )
                else:
                    issue_collector.add_warning(
                        code="TABLE_FILE_INVALID",
                        message=f"表格 {logical_name} 文件无效: {error_msg}",
                        node_id=self.node_id,
                        details={"file_path": str(file_path)}
                    )
            else:
                # 文件不存在
                if logical_name in required_tables:
                    # 必需表格缺失是错误
                    issue_collector.add_error(
                        code="REQUIRED_TABLE_MISSING",
                        message=f"必需的参考表缺失: {logical_name}",
                        node_id=self.node_id,
                        details={"expected_path": str(file_path)}
                    )
                else:
                    # 可选表格缺失是警告
                    issue_collector.add_warning(
                        code="OPTIONAL_TABLE_MISSING",
                        message=f"可选表格缺失: {logical_name}",
                        node_id=self.node_id,
                        details={"expected_path": str(file_path)}
                    )

        # === 3. 检查必需表格是否都存在 ===
        missing_required = [name for name in required_tables if name not in table_paths]
        if missing_required:
            raise ValueError(f"缺少必需的参考表: {', '.join(missing_required)}")

        # === 4. 更新状态 ===
        state["table_paths"] = table_paths
        state["table_metadata"] = table_metadata

        # === 5. 生成输出 ===
        metrics = {
            "tables_found": len(table_paths),
            "required_tables_ok": all(name in table_paths for name in required_tables),
            "total_size_bytes": sum(
                meta.get("size_bytes", 0)
                for meta in table_metadata.values()
            )
        }

        logger.info(
            "input_validation_completed",
            tables_found=len(table_paths),
            tables_list=list(table_paths.keys()),
            issues_count=len(issue_collector)
        )

        return self._create_success_output(
            data={
                "table_paths": table_paths,
                "table_metadata": table_metadata
            },
            processed_count=len(table_names),
            success_count=len(table_paths),
            issues=issue_collector.get_issues(),
            metrics=metrics
        )
