import io
import time
import json
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from broll.api import create_app
from broll.db import JobStore
from broll.worker import Worker

def post(client,key="one",**body): return client.post("/api/v1/broll/jobs",headers={"Idempotency-Key":key},json=body or {"script":"Cloud computing uses remote servers."})

def test_submit_queued_persistent(client,settings):
    response=post(client)
    assert response.status_code==202
    job=response.json()["job_id"]
    data=client.get(f"/api/v1/jobs/{job}").json()
    assert data["status"]=="queued" and data["progress"]==0
    assert JobStore(settings.database).get(job)["status"]=="queued"

def test_idempotency_same_and_conflict(client):
    first=post(client)
    assert post(client).json()==first.json()
    assert post(client,script="different").status_code==409

def test_concurrent_idempotency(client):
    with ThreadPoolExecutor(max_workers=8) as pool: responses=list(pool.map(lambda _:post(client),range(12)))
    assert all(r.status_code==202 for r in responses)
    assert len({r.json()["job_id"] for r in responses})==1

def test_distinct_jobs(client):
    assert post(client,key="a").json()["job_id"]!=post(client,key="b").json()["job_id"]

def test_required_key(client): assert client.post("/api/v1/broll/jobs",json={"script":"hello"}).status_code==422

def test_validation_never_echoes_input(client):
    response=post(client,script="secret-user-text",audio_url="https://secret.example/token")
    assert response.status_code==422
    assert "secret" not in response.text
    assert response.json()["error"]["code"]=="VALIDATION_ERROR"

def test_empty_script(client): assert post(client,script="  ").status_code==422

def test_duplicate_ratio(client): assert post(client,script="hi",aspect_ratios=["16:9","16:9"]).status_code==422

def test_upload_magic_and_idempotency(client):
    audio=b"RIFF"+b"0"*4+b"WAVE"+b"sample"
    def upload(data): return client.post("/api/v1/uploads",headers={"Idempotency-Key":"up"},files={"file":("../../evil.exe",data)})
    first=upload(audio)
    assert first.status_code==200 and first.json()["upload_id"].endswith(".wav")
    assert upload(audio).json()==first.json()
    assert upload(audio+b"changed").status_code==409
    assert upload(b"<html>not audio</html>").status_code==415

def test_upload_limit(settings):
    settings.max_upload_bytes=4
    with TestClient(create_app(settings)) as c:
        r=c.post("/api/v1/uploads",headers={"Idempotency-Key":"up"},files={"file":("big.wav",b"RIFF0000WAVE")})
        assert r.status_code==413

def test_auth(settings):
    settings.api_token="secret"
    with TestClient(create_app(settings)) as c:
        assert post(c).status_code==401
        assert c.get("/health").status_code==200
        assert c.get("/api/v1/jobs/x",headers={"Authorization":"Bearer secret"}).status_code==404

def test_correlation(client):
    r=client.get("/health",headers={"X-Correlation-Id":"test-id"})
    assert r.headers["X-Correlation-Id"]=="test-id"

def test_health_ready_contract(client):
    assert client.get("/health").status_code==200
    assert client.get("/ready").status_code==200
    schema=client.get("/api/v1/openapi.json").json()
    assert schema["openapi"]=="3.1.0"
    assert "/api/v1/broll/jobs" in schema["paths"]
    assert "Idempotency-Key" in json.dumps(schema).replace("idempotency-key","Idempotency-Key")

def test_unknown_route_is_structured(client): assert client.get("/unknown").json()["error"]["code"]=="HTTP_ERROR"

def test_worker_missing_provider_fails_honestly(client,settings):
    job=post(client).json()["job_id"]
    assert Worker(settings).once()
    status=client.get(f"/api/v1/jobs/{job}").json()
    assert status["status"]=="failed" and status["error"]["code"]=="PROVIDER_NOT_CONFIGURED"
    assert status["results"]=={}

def test_queue_limit(client,settings):
    settings.max_queued_jobs=1
    assert post(client,key="a").status_code==202
    assert post(client,key="b").status_code==429
