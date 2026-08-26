"""配置：GET /api/v1/config  POST /api/v1/config/files"""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..config_store import CONFIG_KINDS, config_status_payload, save_config_upload
from ..database import get_db
from ..errors import ApiError
from ..models import User

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
def get_config(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return config_status_payload(db)


@router.post("/files")
async def upload_config(
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if kind not in CONFIG_KINDS:
        raise ApiError("非法配置类型", code="VALIDATION_ERROR", status_code=400)
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise ApiError("请上传 .xlsx 文件", code="VALIDATION_ERROR", status_code=400)
    content = await file.read()
    if not content:
        raise ApiError("文件为空", code="VALIDATION_ERROR", status_code=400)
    return save_config_upload(db, kind, content, filename, admin)
