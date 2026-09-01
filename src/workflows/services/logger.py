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

    log_level = getattr(logging, level.upper(), logging.INFO)

    # 预处理链（structlog 与 stdlib 外来记录共用）
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if format_type == "json"
        else structlog.dev.ConsoleRenderer()
    )

    # 配置标准 logging 根 logger：console + file 双输出
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    handlers = []

    if output in ("console", "both"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        handlers.append(console_handler)

    if output in ("file", "both"):
        log_file = Path(logs_dir) / f"workflow_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    for handler in handlers:
        root.addHandler(handler)

    # 所有输出（含 uvicorn 等 stdlib 日志）统一走 ProcessorFormatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )
    for handler in handlers:
        handler.setFormatter(formatter)

    # 配置 structlog → stdlib
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
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
