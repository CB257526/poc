"""命令行入口"""

import sys
import argparse
from pathlib import Path
from workflow.runtime import WorkflowRuntime
from workflow.config import config
from workflow.services import setup_logging, get_logger
import json


def main():
    """命令行主入口"""
    parser = argparse.ArgumentParser(
        description="约稿费用验收工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行工作流
  python -m workflow run --input /path/to/1-链接.xlsx

  # 启动MCP服务器
  python -m workflow serve

  # 查询运行状态
  python -m workflow status <run_id>
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # === run 命令 ===
    run_parser = subparsers.add_parser("run", help="运行工作流")
    run_parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="输入文件路径（表1-链接.xlsx）"
    )
    run_parser.add_argument(
        "--table-dir",
        "-t",
        help="表格目录，默认使用配置中的路径"
    )
    run_parser.add_argument(
        "--output",
        "-o",
        choices=["json", "summary"],
        default="summary",
        help="输出格式"
    )

    # === serve 命令 ===
    serve_parser = subparsers.add_parser("serve", help="启动MCP服务器")
    serve_parser.add_argument(
        "--host",
        default=None,
        help="服务器地址"
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="服务器端口"
    )

    # === status 命令 ===
    status_parser = subparsers.add_parser("status", help="查询运行状态")
    status_parser.add_argument("run_id", help="运行ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 初始化日志
    setup_logging(
        level=config.get("logging.level", "INFO"),
        format_type="console" if args.command == "run" else config.get("logging.format", "json"),
        output=config.get("logging.output", "both"),
        logs_dir=config.get_logs_dir()
    )

    logger = get_logger()

    # === 执行命令 ===
    if args.command == "run":
        run_workflow(args, logger)
    elif args.command == "serve":
        serve_mcp(args, logger)
    elif args.command == "status":
        query_status(args, logger)


def run_workflow(args, logger):
    """运行工作流"""
    logger.info("command_run_started", input_file=args.input)

    # 检查输入文件
    if not Path(args.input).exists():
        logger.error("input_file_not_found", path=args.input)
        print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)

    # 创建运行时
    runtime = WorkflowRuntime()

    # 启动工作流
    print(f"🚀 启动工作流...")
    print(f"   输入文件: {args.input}")
    if args.table_dir:
        print(f"   表格目录: {args.table_dir}")

    result = runtime.start_workflow(
        input_file=args.input,
        table_dir=args.table_dir
    )

    # 输出结果
    if args.output == "json":
        # JSON格式输出
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 摘要格式输出
        print_summary(result, runtime)


def print_summary(result, runtime: WorkflowRuntime):
    """打印执行摘要"""
    run_id = result["run_id"]
    status = result["status"]

    print(f"\n{'='*60}")
    print(f"运行ID: {run_id}")
    print(f"状态: {status}")
    print(f"{'='*60}\n")

    if status == "failed":
        print(f"❌ 工作流执行失败")
        print(f"   错误: {result.get('error')}")
        return

    # 获取完整状态
    state = result.get("state")
    if not state:
        return

    # 节点状态
    node_statuses = state.get("node_statuses", {})
    if node_statuses:
        print("📊 节点状态:")
        for node_id, node_status in node_statuses.items():
            status_icon = {
                "completed": "✅",
                "running": "🔄",
                "failed": "❌",
                "pending": "⏳"
            }.get(node_status.get("status"), "❓")

            duration = node_status.get("duration_ms")
            duration_str = f"{duration:.0f}ms" if duration else "-"

            print(f"   {status_icon} {node_status.get('node_name')} ({node_id})")
            print(f"      状态: {node_status.get('status')} | 耗时: {duration_str}")

    print()

    # 问题统计
    issues = state.get("issues", [])
    if issues:
        errors = [i for i in issues if i.get("level") == "error"]
        warnings = [i for i in issues if i.get("level") == "warning"]

        print(f"⚠️  问题汇总: {len(issues)} 个问题")
        if errors:
            print(f"   ❌ 错误: {len(errors)} 个")
            for issue in errors[:3]:  # 只显示前3个
                print(f"      - {issue.get('message')}")
            if len(errors) > 3:
                print(f"      ... 还有 {len(errors) - 3} 个错误")

        if warnings:
            print(f"   ⚠️  警告: {len(warnings)} 个")
            for issue in warnings[:3]:  # 只显示前3个
                print(f"      - {issue.get('message')}")
            if len(warnings) > 3:
                print(f"      ... 还有 {len(warnings) - 3} 个警告")
    else:
        print("✅ 没有问题")

    print()

    # 处理结果
    records = state.get("records", [])
    if records:
        print(f"📄 处理结果:")
        print(f"   共处理 {len(records)} 条记录")

    print(f"\n{'='*60}")
    print(f"✨ 工作流执行完成!")
    print(f"{'='*60}\n")


def serve_mcp(args, logger):
    """启动MCP服务器"""
    from workflow.mcp_server import start_server
    import workflow.mcp_server as mcp_module

    # 覆盖配置
    if args.host:
        config._config["api"]["host"] = args.host
    if args.port:
        config._config["api"]["port"] = args.port

    logger.info("command_serve_started")
    start_server()


def query_status(args, logger):
    """查询运行状态"""
    logger.info("command_status_started", run_id=args.run_id)

    runtime = WorkflowRuntime()
    status = runtime.get_run_status(args.run_id)

    if not status:
        print(f"错误: 运行 {args.run_id} 不存在")
        sys.exit(1)

    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
