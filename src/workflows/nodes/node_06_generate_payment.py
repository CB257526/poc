"""节点6: 生成付款表"""

from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict
import os

from workflows.nodes.base import BaseNode
from workflows.models import WorkflowContext, NodeOutput, NodeMetrics, Issue
from workflows.services import get_logger, ExcelService

logger = get_logger()


class Node06GeneratePayment(BaseNode):
    """
    生成付款表节点

    职责：
    1. 按月度、按收款方汇总费用
    2. 生成月度汇总表
    3. 生成付款Excel文件
    4. 保存输出文件路径
    """

    def __init__(self):
        super().__init__("node_06", "生成付款表")

    def process(self, context: WorkflowContext) -> NodeOutput:
        """处理付款表生成"""
        start_time = datetime.now()
        metrics = NodeMetrics()
        issues = []

        # 检查是否有约稿明细数据
        if not context.quote_details or not context.quote_details.get("details"):
            issue = Issue(
                level="critical",
                code="NO_QUOTE_DETAILS",
                message="没有约稿明细数据，无法生成付款表",
                node_id=self.node_id
            )
            issues.append(issue)
            return NodeOutput.create_failure(metrics=metrics, issues=issues)

        quote_details = context.quote_details["details"]
        metrics.processed_count = len(quote_details)

        try:
            # 1. 生成月度汇总
            monthly_summary = self._generate_monthly_summary(quote_details)
            context.monthly_summary = monthly_summary

            logger.info(
                "monthly_summary_generated",
                months=len(monthly_summary)
            )

            # 2. 生成付款行数据
            payment_rows = self._generate_payment_rows(quote_details)
            context.payment_rows = payment_rows

            logger.info(
                "payment_rows_generated",
                count=len(payment_rows)
            )

            # 3. 写入付款Excel文件
            output_file = self._write_payment_excel(context, quote_details, payment_rows, monthly_summary)
            context.output_files["payment"] = output_file

            logger.info(
                "payment_excel_generated",
                output_file=output_file
            )

            # 4. 写入完善后的约稿资料表
            quote_file = self._write_quote_detail_excel(context, quote_details)
            context.output_files["quote_detail"] = quote_file

            logger.info(
                "quote_detail_excel_generated",
                output_file=quote_file
            )

            metrics.success_count = len(quote_details)

        except Exception as e:
            issue = Issue(
                level="critical",
                code="GENERATION_FAILED",
                message=f"生成付款表失败: {str(e)}",
                node_id=self.node_id
            )
            issues.append(issue)
            metrics.error_count = len(quote_details)
            logger.error(
                "payment_generation_failed",
                error=str(e)
            )
            return NodeOutput.create_failure(metrics=metrics, issues=issues)

        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        metrics.duration_ms = duration

        logger.info(
            "node_completed",
            node_id=self.node_id,
            processed=metrics.processed_count,
            success=metrics.success_count,
            output_file=context.output_files.get("payment"),
            duration_ms=duration
        )

        return NodeOutput.create_success(
            metrics=metrics,
            issues=issues,
            data={
                "monthly_summary": monthly_summary,
                "payment_rows": payment_rows
            }
        )

    def _generate_monthly_summary(self, details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成月度汇总

        Args:
            details: 约稿明细列表

        Returns:
            月度汇总字典 {月份: {媒体数, 文章数, 总费用}}
        """
        monthly_data = defaultdict(lambda: {
            "media_count": set(),
            "article_count": 0,
            "total_fee": 0.0
        })

        for detail in details:
            publish_date = detail.get("发布日期")
            media = detail.get("媒体")
            fee = detail.get("费用", 0)

            # 解析月份
            month = self._extract_month(publish_date)
            if not month:
                continue

            # 累计数据
            monthly_data[month]["media_count"].add(media)
            monthly_data[month]["article_count"] += 1
            monthly_data[month]["total_fee"] += float(fee) if fee else 0.0

        # 转换为最终格式
        summary = {}
        for month, data in monthly_data.items():
            summary[month] = {
                "媒体数": len(data["media_count"]),
                "文章数": data["article_count"],
                "总费用": data["total_fee"]
            }

        return summary

    def _generate_payment_rows(self, details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成付款行数据（按收款方汇总）

        Args:
            details: 约稿明细列表

        Returns:
            付款行列表
        """
        # 按收款方分组
        payee_groups = defaultdict(lambda: {
            "details": [],
            "total_fee": 0.0
        })

        for detail in details:
            payee = detail.get("收款方")
            if not payee:
                continue

            fee = detail.get("费用", 0)
            payee_groups[payee]["details"].append(detail)
            payee_groups[payee]["total_fee"] += float(fee) if fee else 0.0

        # 生成付款行
        payment_rows = []
        for payee, group_data in payee_groups.items():
            # 获取账户信息（从第一条记录）
            first_detail = group_data["details"][0]

            row = {
                "收款方": payee,
                "开户行": first_detail.get("开户行"),
                "账号": first_detail.get("账号"),
                "联系方式": first_detail.get("联系方式"),
                "文章数": len(group_data["details"]),
                "总费用": group_data["total_fee"],
                "备注": f"包含{len(group_data['details'])}篇文章"
            }
            payment_rows.append(row)

        # 按总费用降序排列
        payment_rows.sort(key=lambda x: x["总费用"], reverse=True)

        return payment_rows

    def _write_payment_excel(
        self,
        context: WorkflowContext,
        quote_details: List[Dict[str, Any]],
        payment_rows: List[Dict[str, Any]],
        monthly_summary: Dict[str, Any]
    ) -> str:
        """
        写入付款Excel文件

        Args:
            context: 工作流上下文
            quote_details: 约稿明细
            payment_rows: 付款行数据
            monthly_summary: 月度汇总

        Returns:
            输出文件路径
        """
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"付款表_{timestamp}.xlsx"
        output_path = os.path.join("./output", output_filename)

        # 确保输出目录存在
        os.makedirs("./output", exist_ok=True)

        # 使用openpyxl创建Excel
        from openpyxl import Workbook

        wb = Workbook()

        # Sheet 1: 付款汇总
        ws_payment = wb.active
        ws_payment.title = "付款汇总"

        payment_headers = ["收款方", "开户行", "账号", "联系方式", "文章数", "总费用", "备注"]
        for col_idx, header in enumerate(payment_headers, start=1):
            ws_payment.cell(row=1, column=col_idx, value=header)

        for row_idx, row_data in enumerate(payment_rows, start=2):
            for col_idx, header in enumerate(payment_headers, start=1):
                self._set_cell_value(ws_payment, row_idx, col_idx, row_data.get(header, ""))

        # Sheet 2: 约稿明细
        ws_details = wb.create_sheet("约稿明细")

        detail_headers = ["媒体", "平台", "标题", "发布日期", "链接", "媒体等级", "文章类型", "费用", "收款方", "截图"]
        for col_idx, header in enumerate(detail_headers, start=1):
            ws_details.cell(row=1, column=col_idx, value=header)

        for row_idx, row_data in enumerate(quote_details, start=2):
            for col_idx, header in enumerate(detail_headers, start=1):
                self._set_cell_value(ws_details, row_idx, col_idx, row_data.get(header, ""))

        # Sheet 3: 月度汇总
        ws_monthly = wb.create_sheet("月度汇总")

        monthly_headers = ["月份", "媒体数", "文章数", "总费用"]
        for col_idx, header in enumerate(monthly_headers, start=1):
            ws_monthly.cell(row=1, column=col_idx, value=header)

        for row_idx, (month, data) in enumerate(sorted(monthly_summary.items()), start=2):
            ws_monthly.cell(row=row_idx, column=1, value=month)
            ws_monthly.cell(row=row_idx, column=2, value=data["媒体数"])
            ws_monthly.cell(row=row_idx, column=3, value=data["文章数"])
            ws_monthly.cell(row=row_idx, column=4, value=data["总费用"])

        # 保存文件
        wb.save(output_path)

        return output_path

    @staticmethod
    def _set_cell_value(ws, row_idx: int, col_idx: int, value: Any) -> None:
        """
        写入单元格值；以 = 开头的字符串（如 WPS 的 =DISPIMG(...) 图片引用）
        强制按文本存储，避免 openpyxl 当作公式导致读回为空。
        """
        cell = ws.cell(row=row_idx, column=col_idx)
        if isinstance(value, str) and value.startswith("="):
            cell.value = value
            cell.data_type = "s"
        else:
            cell.value = value

    @staticmethod
    def _extract_month(date_str: Any) -> str:
        """
        从日期字符串中提取月份

        Args:
            date_str: 日期字符串（如 "2024-08-15" 或 "2024/8/15"）

        Returns:
            月份字符串（如 "2024-08"），失败返回空字符串
        """
        if not date_str:
            return ""

        try:
            # 尝试多种日期格式
            date_str = str(date_str).strip()

            # 处理 datetime 对象
            if isinstance(date_str, datetime):
                return date_str.strftime("%Y-%m")

            # 处理字符串
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m", "%Y/%m"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%Y-%m")
                except ValueError:
                    continue

            # 如果上述都失败，尝试提取前7个字符（YYYY-MM）
            if len(date_str) >= 7 and date_str[4] in ['-', '/']:
                return date_str[:7]

        except Exception:
            pass

        return ""

    def _write_quote_detail_excel(
        self,
        context: WorkflowContext,
        quote_details: List[Dict[str, Any]]
    ) -> str:
        """
        写入完善后的约稿资料Excel文件（模拟填写2-约稿资料表）

        Args:
            context: 工作流上下文
            quote_details: 约稿明细数据

        Returns:
            输出文件路径
        """
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"2-约稿资料_完善版_{timestamp}.xlsx"
        output_path = os.path.join("./output", output_filename)

        # 确保输出目录存在
        os.makedirs("./output", exist_ok=True)

        # 使用openpyxl创建Excel
        from openpyxl import Workbook

        wb = Workbook()

        # Sheet: 约稿
        ws = wb.active
        ws.title = "约稿"

        # 表头（对应2-约稿资料.xlsx的结构）
        headers = [
            "媒体名称", "媒体级别", "粉丝量", "发布形式", "约稿类型",
            "平台", "标题", "发布链接", "作品截图", "发布日期",
            "约稿数量", "户名", "身份证", "账号", "电话"
        ]

        for col_idx, header in enumerate(headers, start=1):
            ws.cell(row=1, column=col_idx, value=header)

        # 填充数据
        for row_idx, detail in enumerate(quote_details, start=2):
            # 从各节点汇总的数据中提取
            ws.cell(row=row_idx, column=1, value=detail.get("媒体"))  # 媒体名称
            ws.cell(row=row_idx, column=2, value=detail.get("媒体等级"))  # 媒体级别
            ws.cell(row=row_idx, column=3, value=detail.get("粉丝量"))  # 粉丝量
            ws.cell(row=row_idx, column=4, value=detail.get("发布形式", "原创"))  # 发布形式
            ws.cell(row=row_idx, column=5, value=detail.get("文章类型"))  # 约稿类型
            ws.cell(row=row_idx, column=6, value=detail.get("平台"))  # 平台
            ws.cell(row=row_idx, column=7, value=detail.get("标题"))  # 标题
            ws.cell(row=row_idx, column=8, value=detail.get("链接"))  # 发布链接
            self._set_cell_value(ws, row_idx, 9, detail.get("截图", ""))  # 作品截图
            ws.cell(row=row_idx, column=10, value=detail.get("发布日期"))  # 发布日期
            ws.cell(row=row_idx, column=11, value=1)  # 约稿数量（默认1）
            ws.cell(row=row_idx, column=12, value=detail.get("收款方"))  # 户名
            ws.cell(row=row_idx, column=13, value=detail.get("身份证"))  # 身份证
            ws.cell(row=row_idx, column=14, value=detail.get("账号"))  # 账号
            ws.cell(row=row_idx, column=15, value=detail.get("联系方式"))  # 电话

        # 保存文件
        wb.save(output_path)

        return output_path
