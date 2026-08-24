"""命令行入口 - 新版本"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

from workflows.workflow_run import run_workflow
from workflows.services import get_logger

logger = get_logger()


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="约稿费用验收工作流 - 基于 LangChain"
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="运行工作流")
    run_parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="输入文件路径（1-链接.xlsx）"
    )
    run_parser.add_argument(
        "--table-dir",
        "-t",
        default="./table",
        help="参考表格目录（默认: ./table）"
    )
    run_parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json"],
        default="text",
        help="输出格式（默认: text）"
    )

    args = parser.parse_args()

    if args.command == "run":
        run_command(args)
    else:
        parser.print_help()
        sys.exit(1)


def run_command(args):
    """执行 run 命令"""
    input_file = Path(args.input).resolve()
    table_dir = Path(args.table_dir).resolve()

    logger.info(
        "starting_workflow_from_cli",
        input_file=str(input_file),
        table_dir=str(table_dir)
    )

    try:
        # 运行工作流
        context = run_workflow(
            input_file=str(input_file),
            table_dir=str(table_dir)
        )

        # 输出结果
        if args.output == "json":
            print_json_output(context)
        else:
            print_text_output(context)

        # 根据结果设置退出码
        if context.has_critical_errors():
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        logger.error("workflow_failed_in_cli", error=str(e), exc_info=True)
        print(f"❌ 工作流执行失败: {str(e)}", file=sys.stderr)
        sys.exit(1)


def print_text_output(context):
    """打印文本格式输出"""
    print("\n" + "="*60)
    print(f"📊 工作流执行报告")
    print("="*60)

    print(f"\n✅ 运行ID: {context.run_id}")
    print(f"⏱️  开始时间: {context.run_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 完成节点: {len(context.completed_nodes)}/7")
    print(f"   {', '.join(context.completed_nodes)}")

    print(f"\n📊 数据统计:")
    print(f"   - 记录数: {len(context.records)}")

    if context.quote_details:
        print(f"   - 约稿明细: ✅")
    if context.monthly_summary:
        print(f"   - 月度汇总: ✅")
    if context.payment_rows:
        print(f"   - 付款表: ✅ ({len(context.payment_rows)}行)")

    # 问题统计
    print(f"\n⚠️  问题统计:")
    critical_count = len(context.get_issues_by_level("critical"))
    error_count = len(context.get_issues_by_level("error"))
    warning_count = len(context.get_issues_by_level("warning"))

    print(f"   - Critical: {critical_count}")
    print(f"   - Error: {error_count}")
    print(f"   - Warning: {warning_count}")

    # 显示前5个问题
    if context.issues:
        print(f"\n📋 问题详情（前5条）:")
        for i, issue in enumerate(context.issues[:5], 1):
            icon = "🔴" if issue.level == "critical" else "🟠" if issue.level == "error" else "🟡"
            print(f"   {i}. {icon} [{issue.level.upper()}] {issue.message}")
            print(f"      节点: {issue.node_id}, 代码: {issue.code}")

        if len(context.issues) > 5:
            print(f"   ... 还有 {len(context.issues) - 5} 个问题")

    # 产物
    if context.output_files:
        print(f"\n📦 输出文件:")
        for name, path in context.output_files.items():
            print(f"   - {name}: {path}")

    print("\n" + "="*60)

    # 最终状态
    if context.has_critical_errors():
        print("❌ 工作流因严重错误终止")
    elif error_count > 0:
        print("⚠️  工作流完成，但有错误")
    elif warning_count > 0:
        print("✅ 工作流完成，有警告")
    else:
        print("✅ 工作流成功完成")

    print("="*60 + "\n")


def print_json_output(context):
    """打印JSON格式输出"""
    output = {
        "run_id": context.run_id,
        "run_started_at": context.run_started_at.isoformat(),
        "completed_nodes": context.completed_nodes,
        "records_count": len(context.records),
        "issues": [
            {
                "level": issue.level,
                "code": issue.code,
                "message": issue.message,
                "node_id": issue.node_id,
                "record_id": issue.record_id,
                "details": issue.details
            }
            for issue in context.issues
        ],
        "issue_counts": {
            "critical": len(context.get_issues_by_level("critical")),
            "error": len(context.get_issues_by_level("error")),
            "warning": len(context.get_issues_by_level("warning"))
        },
        "output_files": context.output_files,
        "has_critical_errors": context.has_critical_errors()
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
