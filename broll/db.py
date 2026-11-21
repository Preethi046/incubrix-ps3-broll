import hashlib
import json
import sqlite3
import time
import uuid
from .errors import ServiceError

class JobStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                payload TEXT NOT NULL, correlation TEXT NOT NULL, status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '{}',
                error TEXT, attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL,
                token TEXT, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);
            CREATE TABLE IF NOT EXISTS uploads (idem TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
            """)
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db
    def submit(self, key, payload, correlation, max_queued=100):
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(data.encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM jobs WHERE idem=?", (key,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ServiceError("IDEMPOTENCY_CONFLICT", "Key already used for a different request", 409)
                return previous["id"]
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= max_queued: raise ServiceError("QUEUE_FULL", "Queue is full; retry later", 429, True)
            job_id, now = str(uuid.uuid4()), time.time()
            db.execute("INSERT INTO jobs(id,idem,fingerprint,payload,correlation,status,created,updated) VALUES(?,?,?,?,?,'queued',?,?)",
                (job_id,key,fingerprint,data,correlation,now,now))
            return job_id
    def upload(self, key, fingerprint, result):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM uploads WHERE idem=?",(key,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint: raise ServiceError("IDEMPOTENCY_CONFLICT", "Upload key reused with different bytes",409)
                return json.loads(old["result"])
            db.execute("INSERT INTO uploads VALUES(?,?,?)",(key,fingerprint,json.dumps(result)))
            return result
    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None: raise ServiceError("JOB_NOT_FOUND", "Job not found",404)
        result = dict(row)
        for name in ("payload", "result", "error"):
            result[name] = json.loads(result[name]) if result[name] else None
        return result
    def claim(self, lease_seconds, max_attempts):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE jobs SET status='failed', error=?, updated=? WHERE status='running' AND lease_until<? AND attempts>=?",
                (json.dumps({"code":"WORKER_INTERRUPTED","message":"Worker recovery attempts exhausted","retryable":True,"details":{}}),now,now,max_attempts))
            row = db.execute("SELECT id FROM jobs WHERE status='queued' OR (status='running' AND lease_until<? AND attempts<?) ORDER BY created LIMIT 1",(now,max_attempts)).fetchone()
            if not row: return None
            token = str(uuid.uuid4())
            db.execute("UPDATE jobs SET status='running',token=?,lease_until=?,attempts=attempts+1,updated=? WHERE id=?",(token,now+lease_seconds,now,row["id"]))
        return self.get(row["id"])
    def heartbeat(self, job_id, token, seconds):
        with self.connect() as db:
            cur=db.execute("UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND token=? AND status='running'",(time.time()+seconds,time.time(),job_id,token))
            return cur.rowcount == 1
    def progress(self, job_id, token, progress):
        with self.connect() as db:
            db.execute("UPDATE jobs SET progress=MAX(progress,?),updated=? WHERE id=? AND token=? AND status='running'",(min(99,progress),time.time(),job_id,token))
    def finish(self, job_id, token, result=None, error=None):
        with self.connect() as db:
            cur=db.execute("UPDATE jobs SET status=?,progress=?,result=?,error=?,updated=?,lease_until=NULL WHERE id=? AND token=? AND status='running'",
                ("failed" if error else "succeeded", 100 if not error else 0,json.dumps(result or {}),json.dumps(error) if error else None,time.time(),job_id,token))
            return cur.rowcount == 1
