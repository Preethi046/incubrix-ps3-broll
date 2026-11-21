import json
from datetime import datetime, timezone

def log_event(level, event, job_id=None, correlation_id=None, **fields):
    print(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "level": level, "event": event,
        "job_id": job_id, "correlation_id": correlation_id, **fields}, default=str), flush=True)
