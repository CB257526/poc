"""HTTP adapter for the quote workflow and React application."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from workflows.models import WorkflowContext
from workflows.nodes.node_00_input import Node00Input
from workflows.workflow_run import run_workflow

BASE_DIR = Path(os.getenv("WORKFLOW_RUNTIME_DIR", "./runtime")).resolve()
TABLE_DIR = Path(os.getenv("WORKFLOW_TABLE_DIR", "./table")).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="约稿平台 API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_tasks: dict[str, dict[str, Any]] = {}
_tokens: dict[str, str] = {}
_lock = threading.Lock()
_USERS = [
    {"id":"u_admin","email":"admin@byd.local","name":"系统管理员","role":"admin","status":"active"},
    {"id":"u_op","email":"operator@byd.local","name":"业务经办","role":"operator","status":"active"},
    {"id":"u_fin","email":"finance@byd.local","name":"财务复核","role":"finance","status":"active"},
    {"id":"u_view","email":"viewer@byd.local","name":"只读访客","role":"viewer","status":"active"},
]
for user in _USERS:
    user.update(created_at="2026-08-01T09:00:00+08:00", last_login_at=None)

def _db() -> Path: return BASE_DIR / "frontend.db"
def _init_db() -> None:
    with sqlite3.connect(_db()) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS batches(task_id TEXT, month TEXT, processed_at TEXT, quote_count INTEGER, total_fee REAL, text_fee REAL, video_fee REAL, PRIMARY KEY(task_id,month));
        CREATE TABLE IF NOT EXISTS details(task_id TEXT, detail_id TEXT, month TEXT, media TEXT, content_type TEXT, fee REAL, PRIMARY KEY(task_id,detail_id));
        CREATE TABLE IF NOT EXISTS exceptions(id TEXT PRIMARY KEY, task_id TEXT, payload TEXT);
        """)

def _user(authorization: str | None) -> dict[str, Any]:
    token = (authorization or "").removeprefix("Bearer ")
    uid = _tokens.get(token)
    user = next((u for u in _USERS if u["id"] == uid), None)
    if not user: raise HTTPException(401, detail="未登录或登录已过期")
    return user

def _require(authorization: str | None, roles: set[str] | None = None) -> dict[str, Any]:
    user = _user(authorization)
    if roles and user["role"] not in roles: raise HTTPException(403, detail="当前角色无权执行该操作")
    return user

def _issue(i: Any) -> dict[str, Any]:
    d=i.model_dump(); d["severity"]=d.pop("level"); return d

def _record(r: dict[str, Any], unmatched: set[str]) -> dict[str, Any]:
    links=r.get("链接") or []; links=links if isinstance(links,list) else [links]
    return {"record_id":r.get("id"),"row_number":r.get("row_number"),"topic":r.get("主题") or "","media_name":r.get("媒体") or "","link_count":len(links),"link_preview":"\n".join(map(str,links[:2])),"match_status":"unmatched" if r.get("id") in unmatched else "matched","suggested_name":""}

class Login(BaseModel): email:str; password:str
class Register(BaseModel): email:str; name:str; password:str
class Correction(BaseModel): media_name_corrections:dict[str,str]=Field(default_factory=dict)
class UserPatch(BaseModel): role:str|None=None; status:str|None=None
class ExceptionPatch(BaseModel): summary_fees:dict[str,float]

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/api/v1/auth/login")
def login(body:Login):
    user=next((u for u in _USERS if u["email"]==body.email),None)
    if not user or body.password!="Passw0rd!": raise HTTPException(401,detail="邮箱或密码不正确")
    if user["status"]!="active": raise HTTPException(403,detail="账号尚未启用")
    token=uuid.uuid4().hex; _tokens[token]=user["id"]; user["last_login_at"]=datetime.now().isoformat()
    return {"user":user,"tokens":{"access_token":token,"refresh_token":uuid.uuid4().hex,"token_type":"bearer","expires_in":7200}}

@app.post("/api/v1/auth/register",status_code=201)
def register(body:Register):
    if any(u["email"]==body.email for u in _USERS): raise HTTPException(409,detail="该邮箱已注册")
    _USERS.append({"id":"u_"+uuid.uuid4().hex[:8],"email":body.email,"name":body.name,"role":"operator","status":"pending","created_at":datetime.now().isoformat(),"last_login_at":None})
    return {"message":"注册成功，请等待管理员审核后再登录"}

@app.get("/api/v1/auth/me")
def me(authorization:str|None=Header(None)): return _user(authorization)
@app.post("/api/v1/auth/logout",status_code=204)
def logout(authorization:str|None=Header(None)):
    _tokens.pop((authorization or "").removeprefix("Bearer "),None)
@app.get("/api/v1/users")
def users(authorization:str|None=Header(None)): _require(authorization,{"admin"}); return _USERS
@app.patch("/api/v1/users/{uid}")
def patch_user(uid:str,body:UserPatch,authorization:str|None=Header(None)):
    _require(authorization,{"admin"}); user=next((u for u in _USERS if u["id"]==uid),None)
    if not user: raise HTTPException(404,detail="用户不存在")
    if body.role: user["role"]=body.role
    if body.status: user["status"]=body.status
    return user

def _validate(task_id:str, corrections:dict[str,str]|None=None):
    task=_tasks.get(task_id)
    if not task: raise HTTPException(404,detail="任务不存在")
    ctx=WorkflowContext(run_id="pre_"+task_id,input_file=task["input_file"],table_dir=str(TABLE_DIR),config={"media_name_corrections":corrections or {}})
    out=Node00Input().process(ctx); blocking=[i for i in out.issues if i.level in {"error","critical"}]
    unmatched={i.record_id for i in blocking if i.code=="MEDIA_NOT_IN_LIBRARY"}
    allowed=sorted({n for i in out.issues for n in i.details.get("allowed_media_names",[])})
    task.update(status="needs_correction" if blocking else "ready",corrections=corrections or {},records=out.data.get("records",[]),issues=out.issues,updated_at=datetime.now().isoformat())
    return {"task_id":task_id,"status":task["status"],"records":[_record(r,unmatched) for r in task["records"]],"issues":[_issue(i) for i in out.issues],"allowed_media_names":allowed}

@app.post("/api/v1/tasks/validate")
async def validate(request:Request,authorization:str|None=Header(None)):
    if authorization: _require(authorization,{"admin","operator"})
    content=await request.body()
    if not content: raise HTTPException(400,detail="上传文件为空")
    tid="task_"+uuid.uuid4().hex[:12]; root=BASE_DIR/tid; (root/"uploads").mkdir(parents=True); (root/"outputs").mkdir()
    path=root/"uploads"/"1-链接.xlsx"; path.write_bytes(content); now=datetime.now().isoformat()
    _tasks[tid]={"task_id":tid,"status":"validating","input_file":str(path),"output_dir":str(root/"outputs"),"filename":"1-链接.xlsx","created_at":now,"updated_at":now,"created_by":"u_op","issues":[]}
    return _validate(tid)

@app.post("/api/v1/tasks/{tid}/corrections")
def corrections(tid:str,body:Correction,authorization:str|None=Header(None)):
    if authorization: _require(authorization,{"admin","operator"})
    return _validate(tid,body.media_name_corrections)

def _save_stats(tid:str,ctx:WorkflowContext):
    eligible=[d for d in (ctx.quote_details or {}).get("details",[]) if d.get("eligible_for_monthly_summary") is True]
    _init_db()
    with sqlite3.connect(_db()) as c:
      for month in sorted({str(d.get("发布日期") or "")[:7] for d in eligible if len(str(d.get("发布日期") or ""))>=7}):
        ds=[d for d in eligible if str(d.get("发布日期") or "")[:7]==month]; text=sum(float(d.get("费用") or 0) for d in ds if str(d.get("文章类型")) in {"图文","文章","图文类"}); total=sum(float(d.get("费用") or 0) for d in ds)
        c.execute("INSERT OR REPLACE INTO batches VALUES(?,?,?,?,?,?,?)",(tid,month,datetime.now().isoformat(),len(ds),total,text,total-text))
        for idx,d in enumerate(ds): c.execute("INSERT OR REPLACE INTO details VALUES(?,?,?,?,?,?)",(tid,str(d.get("id") or idx),month,str(d.get("媒体") or ""),str(d.get("文章类型") or ""),float(d.get("费用") or 0)))

# Backwards-compatible name used by the existing API regression test.
def _save_completed_statistics(task_id: str, context: WorkflowContext) -> None:
    _save_stats(task_id, context)

def _execute(tid:str):
    task=_tasks[tid]
    try:
      ctx=run_workflow(task["input_file"],str(TABLE_DIR),{"media_name_corrections":task.get("corrections",{}),"output_dir":task["output_dir"]},run_id=tid)
      task.update(context=ctx,status="completed" if ctx.run_status=="completed" else "failed",issues=ctx.issues,error=ctx.termination_reason,updated_at=datetime.now().isoformat());
      if task["status"]=="completed": _save_stats(tid,ctx)
    except Exception as e: task.update(status="failed",error=str(e),updated_at=datetime.now().isoformat())

@app.post("/api/v1/tasks/{tid}/run",status_code=202)
def run(tid:str,bg:BackgroundTasks,authorization:str|None=Header(None)):
    if authorization: _require(authorization,{"admin","operator"})
    task=_tasks.get(tid)
    if not task: raise HTTPException(404,detail="任务不存在")
    if task["status"]!="ready": raise HTTPException(409,detail="输入预检尚未通过")
    task["status"]="running"; bg.add_task(_execute,tid); return {"task_id":tid,"status":"running"}

def _detail(d):
    return {"media_name":d.get("媒体") or "","platform":d.get("平台") or d.get("platform") or "","content_type":d.get("文章类型") or "","media_level":d.get("媒体等级") or "","followers":str(d.get("粉丝量") or ""),"quote_count":1,"unit_price":float(d.get("基础金额") or d.get("费用") or 0),"amount":float(d.get("费用") or 0),"status":"完成","title":d.get("标题") or "","publish_url":d.get("链接") or d.get("url") or "","publish_date":str(d.get("发布日期") or "")}

def _task_view(task):
    ctx=task.get("context"); ds=[_detail(d) for d in (ctx.quote_details or {}).get("details",[]) if d.get("eligible_for_monthly_summary") is True] if ctx else []
    total=sum(d["amount"] for d in ds); summary={"media_count":len({d["media_name"] for d in ds}),"quote_count":len(ds),"total_fee":total,"text_fee":sum(d["amount"] for d in ds if d["content_type"] in {"图文","文章","图文类"}),"video_fee":sum(d["amount"] for d in ds if d["content_type"] in {"视频","视频类"}),"details":ds} if ctx else None
    files=[{"key":k,"filename":Path(v).name,"ready":Path(v).is_file()} for k,v in (ctx.output_files if ctx else {}).items()]
    completed=ctx.completed_nodes if ctx else (["node_00"] if task["status"] in {"ready","running"} else [])
    return {"task_id":task["task_id"],"status":task["status"],"filename":task["filename"],"created_at":task["created_at"],"updated_at":task["updated_at"],"created_by":task["created_by"],"error":task.get("error"),"progress":{"completed_nodes":completed,"total_nodes":7,"current_node":ctx.current_node if ctx else None},"quote_summary":summary,"files":files,"issues":[_issue(i) for i in task.get("issues",[])]}

@app.get("/api/v1/tasks/latest")
def latest(authorization:str|None=Header(None)):
    if authorization: _user(authorization)
    return _task_view(max(_tasks.values(),key=lambda t:t["created_at"])) if _tasks else None
@app.get("/api/v1/tasks/{tid}")
def task(tid:str,authorization:str|None=Header(None)):
    if authorization: _user(authorization)
    if tid not in _tasks: raise HTTPException(404,detail="任务不存在")
    return _task_view(_tasks[tid])

@app.get("/api/v1/tasks/{tid}/files/archive")
def archive(tid:str,authorization:str|None=Header(None)):
    task=_tasks.get(tid); ctx=task.get("context") if task else None
    if not ctx: raise HTTPException(404,detail="结果文件不存在")
    path=Path(task["output_dir"])/"results.zip"
    with zipfile.ZipFile(path,"w") as z:
      for p in ctx.output_files.values(): z.write(p,Path(p).name)
    return FileResponse(path,filename="约稿费用验收_处理结果.zip")
@app.get("/api/v1/tasks/{tid}/files/{key}")
def file(tid:str,key:str,authorization:str|None=Header(None)):
    task=_tasks.get(tid); ctx=task.get("context") if task else None; path=Path(ctx.output_files.get(key,"")) if ctx else Path()
    if not ctx or not path.is_file(): raise HTTPException(404,detail="结果文件不存在")
    return FileResponse(path,filename=path.name)

@app.get("/api/v1/analytics/monthly")
def monthly(month:str|None=None,authorization:str|None=Header(None)):
    if authorization: _user(authorization)
    month=month or datetime.now().strftime("%Y-%m"); _init_db()
    with sqlite3.connect(_db()) as c:
      c.row_factory=sqlite3.Row; batches=[dict(r) for r in c.execute("SELECT task_id,processed_at,quote_count,total_fee,text_fee,video_fee FROM batches WHERE month=? ORDER BY processed_at",(month,))]; top=[dict(r) for r in c.execute("SELECT media,COUNT(*) quote_count,SUM(fee) total_fee FROM details WHERE month=? GROUP BY media ORDER BY total_fee DESC LIMIT 10",(month,))]
    total=sum(r["total_fee"] for r in batches); return {"month":month,"batch_count":len(batches),"quote_count":sum(r["quote_count"] for r in batches),"total_fee":total,"average_batch_fee":total/len(batches) if batches else 0,"batches":batches,"top_media":top}

_CONFIG={"quote_template":"约稿资料模板","media_library":"媒体库","accounts":"账户信息","fee_rules":"费用规则","payment_template":"付款模板"}
@app.get("/api/v1/config")
def config(authorization:str|None=Header(None)):
    files=[]
    mapping={"media_library":"3-媒体库.xlsx","accounts":"4-账户信息.xlsx","fee_rules":"5-费用.xlsx"}
    for kind,label in _CONFIG.items():
      p=TABLE_DIR/mapping.get(kind,kind+".xlsx"); files.append({"kind":kind,"label":label,"configured":p.is_file(),"filename":p.name if p.is_file() else None,"updated_at":datetime.fromtimestamp(p.stat().st_mtime).isoformat() if p.is_file() else None,"updated_by":"u_admin" if p.is_file() else None})
    return {"files":files,"all_ready":all(x["configured"] for x in files)}
@app.post("/api/v1/config/files")
async def upload_config(kind:str=Form(...),file:UploadFile=File(...),authorization:str|None=Header(None)):
    _require(authorization,{"admin"})
    if kind not in _CONFIG or not file.filename.endswith(".xlsx"): raise HTTPException(400,detail="配置文件必须为 xlsx")
    TABLE_DIR.mkdir(parents=True,exist_ok=True); mapping={"media_library":"3-媒体库.xlsx","accounts":"4-账户信息.xlsx","fee_rules":"5-费用.xlsx"}; target=TABLE_DIR/mapping.get(kind,file.filename)
    with target.open("wb") as out: shutil.copyfileobj(file.file,out)
    return config(authorization)

@app.get("/api/v1/dashboard/overview")
def overview(authorization:str|None=Header(None)):
    latest_task=latest(authorization); s=(latest_task or {}).get("quote_summary") or {}
    return {"latest_task":latest_task,"task_status_label":{"completed":"已完成","running":"处理中","failed":"失败","ready":"待处理","needs_correction":"待修正"}.get((latest_task or {}).get("status"),"待处理"),"media_count":s.get("media_count",0),"quote_count":s.get("quote_count",0),"total_fee":s.get("total_fee",0),"type_distribution":[],"pending_exceptions":0,"config_ready":config(authorization)["all_ready"]}

@app.get("/api/v1/exceptions")
def exceptions(task_id:str|None=None,authorization:str|None=Header(None)): _require(authorization,{"admin","operator"}); return []
@app.patch("/api/v1/exceptions/{exception_id}")
def patch_exception(exception_id:str,body:ExceptionPatch,authorization:str|None=Header(None)):
    _require(authorization,{"admin","operator"})
    raise HTTPException(404,detail="异常不存在")
@app.post("/api/v1/exceptions/reaudit")
def reaudit(authorization:str|None=Header(None)): _require(authorization,{"admin","operator"}); return {"resolved":0,"remaining":0}

def main():
    import uvicorn
    uvicorn.run("workflows.api:app",host="0.0.0.0",port=8000,reload=False)
