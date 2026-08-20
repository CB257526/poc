"""MCP服务器 - HTTP模式

基于FastAPI实现的MCP工具服务器
提供工作流相关的工具接口供外部平台调用
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import uvicorn
from workflow.runtime import WorkflowRuntime
from workflow.config import config
from workflow.services import setup_logging, get_logger

# 初始化日志
setup_logging(
    level=config.get("logging.level", "INFO"),
    format_type=config.get("logging.format", "json"),
    output=config.get("logging.output", "both"),
    logs_dir=config.get_logs_dir()
)

logger = get_logger()

# 创建FastAPI应用
app = FastAPI(
    title="约稿费用验收工作流 MCP Server",
    description="提供工作流执行和状态查询的MCP工具",
    version=config.get_workflow_version()
)

# 创建全局运行时实例
runtime = WorkflowRuntime()


# === Pydantic模型定义 ===

class WorkflowStartRequest(BaseModel):
    """启动工作流请求"""
    input_file: str = Field(..., description="输入文件路径（表1）")
    table_dir: Optional[str] = Field(None, description="表格目录，默认使用配置中的路径")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外的元数据")


class WorkflowStartResponse(BaseModel):
    """启动工作流响应"""
    run_id: str
    status: str
    message: str
    state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    """工作流状态响应"""
    run_id: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    node_statuses: Optional[Dict[str, Any]] = None
    issues_summary: Optional[Dict[str, int]] = None


class NodeStatusResponse(BaseModel):
    """节点状态响应"""
    node_id: str
    node_name: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class IssuesResponse(BaseModel):
    """问题列表响应"""
    total: int
    issues: List[Dict[str, Any]]


class ArtifactsResponse(BaseModel):
    """产物列表响应"""
    run_id: str
    artifacts: List[str]


# === MCP工具端点 ===

@app.post("/tools/workflow_start", response_model=WorkflowStartResponse)
async def workflow_start(request: WorkflowStartRequest):
    """
    MCP工具：启动工作流

    启动一个新的工作流运行实例
    """
    try:
        logger.info(
            "mcp_workflow_start_called",
            input_file=request.input_file,
            table_dir=request.table_dir
        )

        result = runtime.start_workflow(
            input_file=request.input_file,
            table_dir=request.table_dir,
            metadata=request.metadata
        )

        if result["status"] == "completed":
            return WorkflowStartResponse(
                run_id=result["run_id"],
                status="completed",
                message="工作流执行完成",
                state=result.get("state")
            )
        else:
            return WorkflowStartResponse(
                run_id=result["run_id"],
                status="failed",
                message="工作流执行失败",
                error=result.get("error")
            )

    except Exception as e:
        logger.error("mcp_workflow_start_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/workflow_status/{run_id}", response_model=WorkflowStatusResponse)
async def workflow_status(run_id: str):
    """
    MCP工具：查询工作流状态

    返回工作流的运行状态和节点状态摘要
    """
    try:
        logger.info("mcp_workflow_status_called", run_id=run_id)

        status = runtime.get_run_status(run_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")

        # 获取节点状态
        node_statuses = runtime.get_node_status(run_id)

        # 获取问题摘要
        issues = runtime.get_issues(run_id)
        issues_summary = None
        if issues:
            issues_summary = {
                "total": len(issues),
                "errors": sum(1 for i in issues if i.get("level") == "error"),
                "warnings": sum(1 for i in issues if i.get("level") == "warning")
            }

        return WorkflowStatusResponse(
            run_id=run_id,
            status=status.get("status"),
            started_at=status.get("started_at"),
            completed_at=status.get("completed_at"),
            error=status.get("error"),
            node_statuses=node_statuses,
            issues_summary=issues_summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("mcp_workflow_status_failed", run_id=run_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/workflow_node_status/{run_id}/{node_id}", response_model=NodeStatusResponse)
async def workflow_node_status(run_id: str, node_id: str):
    """
    MCP工具：查询节点状态

    返回特定节点的详细状态
    """
    try:
        logger.info("mcp_workflow_node_status_called", run_id=run_id, node_id=node_id)

        node_status = runtime.get_node_status(run_id, node_id)

        if not node_status:
            raise HTTPException(status_code=404, detail=f"节点 {node_id} 在运行 {run_id} 中不存在")

        return NodeStatusResponse(**node_status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "mcp_workflow_node_status_failed",
            run_id=run_id,
            node_id=node_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/workflow_get_issues/{run_id}", response_model=IssuesResponse)
async def workflow_get_issues(
    run_id: str,
    level: Optional[str] = None,
    node_id: Optional[str] = None
):
    """
    MCP工具：获取问题列表

    返回工作流执行过程中收集的所有问题
    可以按级别和节点进行过滤
    """
    try:
        logger.info(
            "mcp_workflow_get_issues_called",
            run_id=run_id,
            level=level,
            node_id=node_id
        )

        issues = runtime.get_issues(run_id, level, node_id)

        if issues is None:
            raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")

        return IssuesResponse(
            total=len(issues),
            issues=issues
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("mcp_workflow_get_issues_failed", run_id=run_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/workflow_list_artifacts/{run_id}", response_model=ArtifactsResponse)
async def workflow_list_artifacts(run_id: str):
    """
    MCP工具：列出产物

    返回工作流生成的所有产物文件列表
    """
    try:
        logger.info("mcp_workflow_list_artifacts_called", run_id=run_id)

        artifacts = runtime.list_artifacts(run_id)

        return ArtifactsResponse(
            run_id=run_id,
            artifacts=artifacts
        )

    except Exception as e:
        logger.error("mcp_workflow_list_artifacts_failed", run_id=run_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/workflow_download_artifact/{run_id}/{artifact_name}")
async def workflow_download_artifact(run_id: str, artifact_name: str):
    """
    MCP工具：下载产物

    返回产物文件的路径（实际下载由调用方实现）
    """
    try:
        logger.info(
            "mcp_workflow_download_artifact_called",
            run_id=run_id,
            artifact_name=artifact_name
        )

        artifact_path = runtime.get_artifact(run_id, artifact_name)

        if not artifact_path:
            raise HTTPException(status_code=404, detail=f"产物 {artifact_name} 不存在")

        return {
            "run_id": run_id,
            "artifact_name": artifact_name,
            "path": artifact_path
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "mcp_workflow_download_artifact_failed",
            run_id=run_id,
            artifact_name=artifact_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


# === 健康检查端点 ===

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "workflow_name": config.get_workflow_name(),
        "workflow_version": config.get_workflow_version()
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "约稿费用验收工作流 MCP Server",
        "version": config.get_workflow_version(),
        "endpoints": {
            "workflow_start": "/tools/workflow_start",
            "workflow_status": "/tools/workflow_status/{run_id}",
            "workflow_node_status": "/tools/workflow_node_status/{run_id}/{node_id}",
            "workflow_get_issues": "/tools/workflow_get_issues/{run_id}",
            "workflow_list_artifacts": "/tools/workflow_list_artifacts/{run_id}",
            "workflow_download_artifact": "/tools/workflow_download_artifact/{run_id}/{artifact_name}",
            "health": "/health",
            "docs": "/docs"
        }
    }


def start_server():
    """启动MCP服务器"""
    host = config.get("api.host", "0.0.0.0")
    port = config.get("api.port", 8000)

    logger.info(
        "mcp_server_starting",
        host=host,
        port=port,
        workflow_name=config.get_workflow_name()
    )

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
