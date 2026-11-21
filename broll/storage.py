from pathlib import Path
import shutil
from .errors import ServiceError

def safe_key(key):
    parts=key.split("/")
    if not parts or any(not x or x in (".","..") or "\\" in x for x in parts):
        raise ServiceError("INVALID_PATH","Invalid object key")
    return key

class LocalStorage:
    def __init__(self,settings):
        self.root=settings.data_dir / "objects"
        self.base=settings.public_base_url.rstrip("/")
    def put(self,path,key):
        target=self.root / safe_key(key)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        return key
    def link(self,key): return self.base+"/api/v1/files/"+safe_key(key)
    def ready(self):
        self.root.mkdir(parents=True,exist_ok=True)
        test=self.root/".ready"
        test.write_text("ok")
        test.unlink()

class S3Storage:
    def __init__(self,settings):
        import boto3
        options=dict(aws_access_key_id=settings.s3_access_key.get_secret_value(),aws_secret_access_key=settings.s3_secret_key.get_secret_value(),region_name=settings.s3_region)
        self.client=boto3.client("s3",endpoint_url=settings.s3_endpoint,**options)
        self.public=boto3.client("s3",endpoint_url=settings.s3_public_endpoint,**options)
        self.bucket,self.expires=settings.s3_bucket,settings.signed_url_seconds
    def put(self,path,key):
        self.client.upload_file(str(path),self.bucket,safe_key(key))
        return key
    def link(self,key):
        return self.public.generate_presigned_url("get_object",Params={"Bucket":self.bucket,"Key":safe_key(key)},ExpiresIn=self.expires)
    def ready(self): self.client.head_bucket(Bucket=self.bucket)

def storage_for(settings):
    if settings.storage=="local": return LocalStorage(settings)
    if settings.storage=="s3": return S3Storage(settings)
    raise ValueError("BROLL_STORAGE must be local or s3")
