import threading
import time
from .config import Settings
from .db import JobStore
from .errors import ServiceError
from .logs import log_event
from .pipeline import Pipeline

class Worker:
    def __init__(self,settings,pipeline=None):
        self.s=settings; self.store=JobStore(settings.database)
        self.pipeline=pipeline or Pipeline(settings)
    def once(self):
        job=self.store.claim(self.s.lease_seconds,self.s.max_attempts)
        if not job: return False
        stop=threading.Event()
        def heartbeat():
            while not stop.wait(max(0.1,self.s.lease_seconds/3)):
                if not self.store.heartbeat(job["id"],job["token"],self.s.lease_seconds): return
        thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
        log_event("INFO","job_started",job["id"],job["correlation"],attempt=job["attempts"])
        try:
            result=self.pipeline.run(job,lambda p:self.store.progress(job["id"],job["token"],p))
            committed=self.store.finish(job["id"],job["token"],result=result)
            log_event("INFO","job_succeeded" if committed else "lease_lost",job["id"],job["correlation"])
        except Exception as exc:
            err=exc if isinstance(exc,ServiceError) else ServiceError("INTERNAL_ERROR","Unexpected processing failure",500)
            self.store.finish(job["id"],job["token"],error=err.body()["error"])
            log_event("ERROR","job_failed",job["id"],job["correlation"],code=err.code)
        finally: stop.set(); thread.join(timeout=2)
        return True
    def run(self):
        while True:
            if not self.once(): time.sleep(self.s.worker_poll_seconds)
if __name__=="__main__": Worker(Settings()).run()
