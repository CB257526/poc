"""文件存储服务"""

from pathlib import Path
from typing import Optional
import shutil
from datetime import datetime
import structlog

logger = structlog.get_logger()


class StorageService:
    """文件存储服务，负责管理工作流产物的存储"""

    def __init__(self, base_dir: str = "./artifacts"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_run_dir(self, run_id: str) -> Path:
        """
        为一次运行创建专属目录

        Args:
            run_id: 运行ID

        Returns:
            运行目录路径
        """
        run_dir = self.base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        (run_dir / "screenshots").mkdir(exist_ok=True)
        (run_dir / "outputs").mkdir(exist_ok=True)
        (run_dir / "logs").mkdir(exist_ok=True)

        logger.info("run_directory_created", run_id=run_id, path=str(run_dir))
        return run_dir

    def get_run_dir(self, run_id: str) -> Path:
        """
        获取运行目录

        Args:
            run_id: 运行ID

        Returns:
            运行目录路径
        """
        return self.base_dir / run_id

    def save_artifact(
        self,
        run_id: str,
        artifact_name: str,
        content: str,
        subdir: str = "outputs"
    ) -> str:
        """
        保存产物文件

        Args:
            run_id: 运行ID
            artifact_name: 产物文件名
            content: 文件内容
            subdir: 子目录名

        Returns:
            保存的文件路径
        """
        run_dir = self.get_run_dir(run_id)
        artifact_dir = run_dir / subdir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        file_path = artifact_dir / artifact_name

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(
            "artifact_saved",
            run_id=run_id,
            artifact_name=artifact_name,
            path=str(file_path)
        )

        return str(file_path)

    def copy_file(
        self,
        source_path: str,
        run_id: str,
        dest_name: Optional[str] = None,
        subdir: str = "outputs"
    ) -> str:
        """
        复制文件到运行目录

        Args:
            source_path: 源文件路径
            run_id: 运行ID
            dest_name: 目标文件名，None表示使用原文件名
            subdir: 子目录名

        Returns:
            目标文件路径
        """
        run_dir = self.get_run_dir(run_id)
        artifact_dir = run_dir / subdir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        if dest_name is None:
            dest_name = Path(source_path).name

        dest_path = artifact_dir / dest_name
        shutil.copy2(source_path, dest_path)

        logger.info(
            "file_copied",
            run_id=run_id,
            source=source_path,
            destination=str(dest_path)
        )

        return str(dest_path)

    def get_artifact_path(
        self,
        run_id: str,
        artifact_name: str,
        subdir: str = "outputs"
    ) -> Optional[str]:
        """
        获取产物文件路径

        Args:
            run_id: 运行ID
            artifact_name: 产物文件名
            subdir: 子目录名

        Returns:
            文件路径，如果不存在返回None
        """
        file_path = self.get_run_dir(run_id) / subdir / artifact_name

        if file_path.exists():
            return str(file_path)
        return None

    def list_artifacts(self, run_id: str, subdir: str = "outputs") -> list[str]:
        """
        列出运行的所有产物

        Args:
            run_id: 运行ID
            subdir: 子目录名

        Returns:
            文件名列表
        """
        artifact_dir = self.get_run_dir(run_id) / subdir

        if not artifact_dir.exists():
            return []

        return [f.name for f in artifact_dir.iterdir() if f.is_file()]

    def cleanup_run(self, run_id: str) -> None:
        """
        清理运行目录

        Args:
            run_id: 运行ID
        """
        run_dir = self.get_run_dir(run_id)

        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info("run_directory_cleaned", run_id=run_id)

    def get_run_size(self, run_id: str) -> int:
        """
        获取运行目录的总大小

        Args:
            run_id: 运行ID

        Returns:
            目录大小（字节）
        """
        run_dir = self.get_run_dir(run_id)

        if not run_dir.exists():
            return 0

        total_size = 0
        for file_path in run_dir.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size
