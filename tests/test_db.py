import time
from broll.db import JobStore

def test_single_lease_and_recovery(settings):
    db=JobStore(settings.database); jid=db.submit("k",{"script":"test"},"c")
    first=db.claim(-1,2)
    second=db.claim(20,2)
    assert first["id"]==second["id"]==jid and first["token"]!=second["token"]
    assert db.finish(jid,first["token"],result={"bad":True}) is False
    assert db.finish(jid,second["token"],result={"ok":True}) is True
    assert db.claim(20,2) is None

def test_no_concurrent_claim(settings):
    db=JobStore(settings.database); db.submit("k",{},"c")
    assert db.claim(100,2)
    assert db.claim(100,2) is None

def test_max_attempts_fails(settings):
    db=JobStore(settings.database); jid=db.submit("k",{},"c")
    db.claim(-1,1); assert db.claim(20,1) is None
    assert db.get(jid)["status"]=="failed"
    assert db.get(jid)["error"]["code"]=="WORKER_INTERRUPTED"

def test_heartbeat_and_monotonic_progress(settings):
    db=JobStore(settings.database); jid=db.submit("k",{},"c"); job=db.claim(100,2)
    assert db.heartbeat(jid,job["token"],100)
    db.progress(jid,job["token"],80); db.progress(jid,job["token"],20)
    assert db.get(jid)["progress"]==80
