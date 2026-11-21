import json
from pathlib import Path
from broll.pipeline import Pipeline
from broll.worker import Worker
from broll.db import JobStore
from broll.models import JobInput
from broll.storage import LocalStorage

# These fakes only test orchestration. They DO NOT create real audio/video or prove media quality.
class FakeNarrator:
    def synthesize(self,text,path,voice): path.write_bytes(b"test-audio"); return path
class FakeTranscriber:
    def transcribe(self,path): return [{"word":"Cloud.","start":0,"end":1},{"word":"Bank.","start":1,"end":2}]
class FakeFootage:
    def choose(self,text,hint,avoid,used,clip_id=None):
        cid=clip_id or text
        assert cid not in used
        return {"id":cid,"path":"test-fixture","source":"test-only","license":"Owned","source_url":"https://example.com","license_url":"https://example.com","attribution":"test","ai_generated":False}
class FakeMedia:
    def __init__(self): self.renders=0
    def audio_duration(self,path): return 2
    def segment(self,clip,duration,ratio,target): self.renders+=1; target.write_bytes(b"test-segment")
    def assemble(self,segments,audio,srt,burn_in,target,duration): target.write_bytes(b"test-video-not-playable")

def test_end_to_end_api_worker_storage_and_swap(client,settings):
    media=FakeMedia()
    pipeline=Pipeline(settings,FakeNarrator(),FakeTranscriber(),FakeFootage(),media,LocalStorage(settings))
    worker=Worker(settings,pipeline)
    response=client.post("/api/v1/broll/jobs",headers={"Idempotency-Key":"e2e"},json={"script":"Cloud. Bank.","aspect_ratios":["16:9","9:16","1:1"]})
    job=response.json()["job_id"]; worker.once()
    status=client.get(f"/api/v1/jobs/{job}").json()
    assert status["status"]=="succeeded",status
    assert set(status["results"])=={"video_16x9.mp4","video_9x16.mp4","video_1x1.mp4","timeline.json","captions.srt","manifest.json"}
    timeline=client.get(status["results"]["timeline.json"]).json()
    assert "path" not in timeline[0]["clip"] and len(timeline)==2
    assert media.renders==6
    swapped=client.post(f"/api/v1/broll/jobs/{job}/scenes/0/swap",headers={"Idempotency-Key":"swap"},json={"clip_id":"replacement"})
    assert swapped.status_code==202
    worker.once()
    assert client.get(swapped.json()["status_url"]).json()["status"]=="succeeded"
    assert media.renders==9  # Only one changed scene, across three ratios.
