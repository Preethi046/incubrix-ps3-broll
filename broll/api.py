import hashlib
import hmac
import re
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, Header, UploadFile, File, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from starlette.exceptions import HTTPException
from .config import Settings
from .db import JobStore
from .errors import ServiceError
from .logs import log_event
from .models import JobInput, SwapInput, Accepted, JobStatus, ErrorResponse, UploadResult
from .security import checked_target, audio_kind
from .storage import storage_for, safe_key

def create_app(settings=None):
    s=settings or Settings()
    store=JobStore(s.database); storage=storage_for(s)
    errors={code:{"model":ErrorResponse} for code in (400,401,404,409,413,415,422,429,500,503)}
    app=FastAPI(title="IncuBrix B-roll foundation",version="0.1.0",openapi_url="/api/v1/openapi.json",docs_url="/api/v1/docs",redoc_url=None,responses=errors)
    app.state.settings=s; app.state.store=store
    @app.middleware("http")
    async def correlation(request,call_next):
        value=request.headers.get("X-Correlation-Id","")
        correlation=value if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}",value) else str(uuid.uuid4())
        request.state.correlation=correlation
        response=await call_next(request)
        response.headers["X-Correlation-Id"]=correlation
        log_event("INFO","http_request",correlation_id=correlation,method=request.method,path=request.url.path,status=response.status_code)
        return response
    @app.exception_handler(ServiceError)
    async def service_error(request,exc): return JSONResponse(exc.body(),status_code=exc.status)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Never echo supplied audio URLs, keys, scripts, file paths or pydantic input context.
        details={"fields":[".".join(str(p) for p in e["loc"]) for e in exc.errors()]}
        return JSONResponse(ServiceError("VALIDATION_ERROR","Invalid request",422,details=details).body(),status_code=422)
    @app.exception_handler(HTTPException)
    async def http_error(request,exc): return JSONResponse(ServiceError("HTTP_ERROR","Request could not be processed",exc.status_code).body(),status_code=exc.status_code)
    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        log_event("ERROR","request_failed",correlation_id=getattr(request.state,"correlation",None),code="INTERNAL_ERROR")
        return JSONResponse(ServiceError("INTERNAL_ERROR","Unexpected service failure",500).body(),status_code=500)
    def authorized(authorization: str | None=Header(default=None)):
        expected=s.api_token.get_secret_value()
        if expected and not hmac.compare_digest(authorization or "","Bearer "+expected): raise ServiceError("UNAUTHORIZED","Bearer token required",401)
    def idem(idempotency_key: str=Header(min_length=1,max_length=200)):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+",idempotency_key): raise ServiceError("INVALID_IDEMPOTENCY_KEY","Use an opaque ASCII idempotency key")
        return idempotency_key
    def accepted(job_id): return {"job_id":job_id,"status_url":f"/api/v1/jobs/{job_id}"}
    @app.get("/health")
    def health(): return {"status":"ok","service":"broll"}
    @app.get("/ready")
    def ready():
        try:
            with store.connect() as db: db.execute("SELECT 1")
            storage.ready()
        except Exception: raise ServiceError("NOT_READY","Database or storage is unavailable",503,True) from None
        return {"status":"ready","note":"Infrastructure ready; media providers may still require configuration"}
    @app.post("/api/v1/broll/jobs",status_code=202,response_model=Accepted,dependencies=[Depends(authorized)])
    def submit(body: JobInput,request: Request,key: str=Depends(idem)):
        if body.audio_url: checked_target(body.audio_url,s.allowed_download_hosts)
        if body.script and len(body.script)>s.max_script_chars: raise ServiceError("INPUT_LIMIT","Script exceeds configured limit",413)
        if body.scenes and len(body.scenes)>s.max_scenes: raise ServiceError("INPUT_LIMIT","Too many scenes",413)
        job=store.submit(key,body.model_dump(),request.state.correlation,s.max_queued_jobs)
        return accepted(job)
    @app.post("/api/v1/uploads",response_model=UploadResult,dependencies=[Depends(authorized)])
    async def upload(file: UploadFile=File(...),key: str=Depends(idem)):
        target=s.data_dir/"uploads"; target.mkdir(parents=True,exist_ok=True)
        temporary=target/(str(uuid.uuid4())+".part")
        digest=hashlib.sha256(); total=0; head=b""
        try:
            with temporary.open("wb") as output:
                while chunk:=await file.read(65536):
                    total+=len(chunk)
                    if total>s.max_upload_bytes: raise ServiceError("FILE_TOO_LARGE","Input exceeds configured limit",413)
                    if len(head)<32: head=(head+chunk)[:32]
                    output.write(chunk); digest.update(chunk)
            kind=audio_kind(head)
            upload_id=digest.hexdigest()+"."+kind
            result=store.upload("upload:"+key,digest.hexdigest(),{"upload_id":upload_id,"bytes":total})
            temporary.replace(target/upload_id)
            return result
        finally:
            temporary.unlink(missing_ok=True)
            await file.close()
    @app.get("/api/v1/jobs/{job_id}",response_model=JobStatus,dependencies=[Depends(authorized)])
    def status(job_id: str):
        job=store.get(job_id)
        return {"job_id":job_id,"status":job["status"],"progress":job["progress"],"attempts":job["attempts"],"results":{name:storage.link(key) for name,key in job["result"].get("objects",{}).items()},"error":job["error"]}
    @app.post("/api/v1/broll/jobs/{job_id}/scenes/{scene_id}/swap",status_code=202,response_model=Accepted,dependencies=[Depends(authorized)])
    def swap(job_id: str,scene_id: int,body: SwapInput,request: Request,key: str=Depends(idem)):
        import json
        original=store.get(job_id)
        if original["status"]!="succeeded": raise ServiceError("JOB_NOT_COMPLETE","Only completed jobs can be changed",409)
        source=Path(original["result"]["work_dir"])
        scenes=json.loads((source/"timeline.json").read_text())
        if scene_id not in [scene["scene_id"] for scene in scenes]: raise ServiceError("SCENE_NOT_FOUND","Scene does not exist",404)
        payload={"request":original["result"]["request"],"swap":{"scene_id":scene_id,"clip_id":body.clip_id,"work_dir":str(source),"parent_job_id":job_id}}
        return accepted(store.submit(key,payload,request.state.correlation,s.max_queued_jobs))
    @app.get("/api/v1/files/{key:path}",dependencies=[Depends(authorized)])
    def file(key: str):
        if s.storage!="local": raise ServiceError("FILE_NOT_FOUND","Use the storage download link",404)
        root=(s.data_dir/"objects").resolve()
        target=(root/safe_key(key)).resolve()
        if not target.is_relative_to(root) or not target.is_file(): raise ServiceError("FILE_NOT_FOUND","File not found",404)
        return FileResponse(target)
    return app

app=create_app()
