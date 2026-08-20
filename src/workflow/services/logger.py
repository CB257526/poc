"""结构化日志服务"""

import structlog
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    output: str = "both",
    logs_dir: str = "./logs"
) -> None:
    """
    配置结构化日志

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        format_type: 格式类型 (json, console)
        output: 输出目标 (console, file, both)
        logs_dir: 日志文件目录
    """
    # 创建日志目录
    Path(logs_dir).mkdir(parents=True, exist_ok=True)

    # 配置处理器
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # 根据格式类型选择渲染器
    if format_type == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # 配置structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准logging
    log_level = getattr(logging, level.upper())

    # 创建日志文件名（包含日期）
    log_file = Path(logs_dir) / f"workflow_{datetime.now().strftime('%Y%m%d')}.log"

    # 根据输出目标配置处理器
    handlers = []

    if output in ["console", "both"]:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        handlers.append(console_handler)

    if output in ["file", "both"]:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # 配置根logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        format="%(message)s"  # structlog会处理格式
    )


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    获取logger实例

    Args:
        name: logger名称

    Returns:
        structlog.BoundLogger实例
    """
    return structlog.get_logger(name)


# 默认配置
setup_logging()
