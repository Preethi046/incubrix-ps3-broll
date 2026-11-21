import json
from pathlib import Path
import pytest
from broll.errors import ServiceError
from broll.storage import LocalStorage,S3Storage
from broll.security import download

def test_local_roundtrip(settings,tmp_path):
    store=LocalStorage(settings); store.ready()
    source=tmp_path/"source.txt"; source.write_text("owned test content")
    assert store.put(source,"job/file.txt")=="job/file.txt"
    assert (store.root/"job/file.txt").read_text()=="owned test content"
    assert store.link("job/file.txt").endswith("/api/v1/files/job/file.txt")

def test_s3_contract(settings,monkeypatch,tmp_path):
    class FakeS3:
        def __init__(self): self.calls=[]
        def upload_file(self,*args): self.calls.append(args)
        def head_bucket(self,**kwargs): self.calls.append(kwargs)
        def generate_presigned_url(self,*args,**kwargs): return "https://signed.example/object"
    clients=[]
    def factory(*args,**kwargs):
        fake=FakeS3(); clients.append(fake); return fake
    monkeypatch.setattr("boto3.client",factory)
    store=S3Storage(settings); store.ready()
    assert store.put(tmp_path/"source","job/file")=="job/file"
    assert store.link("job/file")=="https://signed.example/object"
    assert clients[0].calls[0]=={"Bucket":settings.s3_bucket}
    assert len(clients[0].calls)==2

@pytest.mark.parametrize("status,data,max_size,code",[(302,b"abc",20,"DOWNLOAD_FAILED"),(200,b"abcdef",3,"FILE_TOO_LARGE"),(200,b"",20,"INVALID_MEDIA")])
def test_download_bounded_no_redirects(settings,tmp_path,monkeypatch,status,data,max_size,code):
    monkeypatch.setattr("broll.security.checked_target",lambda *a:("example.com","93.184.216.34","/a",""))
    class Response:
        def __init__(self): self.status=status; self.data=data
        def read(self,n):
            chunk=self.data[:n]; self.data=self.data[n:]; return chunk
    class Connection:
        def __init__(self,*args): pass
        def request(self,*args,**kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr("broll.security.PinnedHTTPS",Connection)
    settings.max_upload_bytes=max_size
    target=tmp_path/"download.wav"
    with pytest.raises(ServiceError) as exc: download("https://example.com/a",target,settings)
    assert exc.value.code==code
    assert not target.exists()
