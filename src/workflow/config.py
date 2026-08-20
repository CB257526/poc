"""配置管理模块"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """配置管理器，负责加载和访问配置"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, encoding='utf-8') as f:
                return yaml.safe_load(f)
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            "workflow": {
                "name": "quotation-fee-workflow",
                "version": "1.0.0",
                "checkpoint_db": "checkpoints.db"
            },
            "tables": {
                "dir": "./table",
                "required": ["3-媒体库", "4-账户信息", "5-费用"]
            },
            "storage": {
                "artifacts_dir": "./artifacts",
                "logs_dir": "./logs",
                "max_artifact_size_mb": 100
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "output": "both"
            },
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
                "cors_origins": ["*"]
            },
            "llm": {
                "enabled": False
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号分隔的路径

        Args:
            key: 配置键，支持 "workflow.name" 这样的路径
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def get_workflow_name(self) -> str:
        """获取工作流名称"""
        return self.get("workflow.name", "quotation-fee-workflow")

    def get_workflow_version(self) -> str:
        """获取工作流版本"""
        return self.get("workflow.version", "1.0.0")

    def get_checkpoint_db(self) -> str:
        """获取检查点数据库路径"""
        return self.get("workflow.checkpoint_db", "checkpoints.db")

    def get_table_dir(self) -> str:
        """获取表格目录"""
        return self.get("tables.dir", "./table")

    def get_required_tables(self) -> list:
        """获取必需的表格列表"""
        return self.get("tables.required", [])

    def get_artifacts_dir(self) -> str:
        """获取产物目录"""
        return self.get("storage.artifacts_dir", "./artifacts")

    def get_logs_dir(self) -> str:
        """获取日志目录"""
        return self.get("storage.logs_dir", "./logs")

    def is_llm_enabled(self) -> bool:
        """是否启用LLM"""
        return self.get("llm.enabled", False)


# 全局配置实例
config = Config()
