import json
import hashlib
import shutil
import time
from pathlib import Path
from .errors import ServiceError
from .media import MediaTools, build_scenes, write_srt
from .providers import configured_providers
from .security import download, audio_kind
from .storage import storage_for

class Pipeline:
    def __init__(self,settings,narrator=None,transcriber=None,footage=None,media=None,storage=None):
        self.s=settings
        n,t,f=configured_providers(settings)
        self.narrator,self.transcriber,self.footage=narrator or n,transcriber or t,footage or f
        self.media,self.storage=media or MediaTools(settings),storage or storage_for(settings)
    def run(self,job,progress):
        started=time.monotonic()
        payload=job["payload"]
        attempt_key=hashlib.sha256((job["id"]+":"+job["token"]).encode()).hexdigest()[:32]
        work=self.s.data_dir/"work"/attempt_key
        work.mkdir(parents=True,exist_ok=True)
        request=payload.get("request",payload)
        swap=payload.get("swap")
        warnings=["Catalog retrieval uses tag overlap, not semantic understanding or independent relevance scoring.",
            "Portrait/square outputs preserve full source frame using dark padding, not subject-aware crop.",
            "Automatic black/freeze-frame, sensitive-content and model/human relevance checks are not implemented."]
        if swap:
            source=Path(swap["work_dir"])
            if not source.is_dir(): raise ServiceError("SWAP_SOURCE_MISSING","Original cached media is unavailable",409)
            audio=source/"narration.wav"
            words=json.loads((source/"words.json").read_text())
            timeline=json.loads((source/"timeline.json").read_text())
            duration=self.media.audio_duration(audio)
            shutil.copyfile(audio,work/"narration.wav"); audio=work/"narration.wav"
            warnings.append("Swap reuses unchanged cached normalized segments; all final containers are assembled again.")
        else:
            audio=work/"narration.wav"
            if request.get("audio_url"):
                download(request["audio_url"],audio,self.s)
                with audio.open("rb") as source: audio_kind(source.read(32))
            elif request.get("upload_id"):
                source=self.s.data_dir/"uploads"/request["upload_id"]
                if not source.is_file(): raise ServiceError("UPLOAD_NOT_FOUND","Uploaded audio is missing",404)
                shutil.copyfile(source,audio)
            else:
                text=request.get("script") or " ".join(scene["text"] for scene in request["scenes"])
                self.narrator.synthesize(text,audio,request["voice"])
                warnings.append("Default voice label is mapped to configured TTS voice; requested accent/gender is not independently verified.")
            progress(15)
            duration=self.media.audio_duration(audio)
            words=self.transcriber.transcribe(audio)
            timeline=build_scenes(words,duration,request.get("scenes"))
        progress(30)
        used={scene["clip"]["id"] for scene in timeline if swap and scene["scene_id"]!=swap["scene_id"]} if swap else set()
        for scene in timeline:
            if not swap or scene["scene_id"]==swap["scene_id"]:
                clip=self.footage.choose(scene["text"],scene.get("visual_hint",""),request["avoid"],used,swap["clip_id"] if swap else None)
                used.add(clip["id"])
                scene["clip"]=clip
        progress(40)
        srt=work/"captions.srt"; write_srt(words,srt)
        artifacts={}
        for ratio in request["aspect_ratios"]:
            segments=[]
            for scene in timeline:
                segment=work/f"segment-{ratio.replace(':','x')}-{scene['scene_id']}.mp4"
                old=Path(swap["work_dir"])/segment.name if swap else None
                if swap and scene["scene_id"]!=swap["scene_id"] and old.is_file(): shutil.copyfile(old,segment)
                else:
                    # Quantize absolute boundaries, not each duration independently: avoids accumulated drift.
                    frames=round(scene["end"]*self.s.output_fps)-round(scene["start"]*self.s.output_fps)
                    if frames<1: raise ServiceError("INVALID_TIMESTAMPS","Scene is shorter than one output frame",422)
                    self.media.segment(scene["clip"]["path"],frames/self.s.output_fps,ratio,segment)
                segments.append(segment)
            output=work/f"video_{ratio.replace(':','x')}.mp4"
            self.media.assemble(segments,audio,srt,request["captions"]["burn_in"],output,duration)
            artifacts[output.name]=output
        progress(85)
        # Keep absolute catalog paths in private worker cache only, never public timeline.
        (work/"timeline.json").write_text(json.dumps(timeline,indent=2),encoding="utf-8")
        (work/"words.json").write_text(json.dumps(words),encoding="utf-8")
        public_timeline=[]
        for scene in timeline:
            clip={k:v for k,v in scene["clip"].items() if k!="path"}
            public_timeline.append({**scene,"clip":clip})
        public=work/"public-timeline.json"; public.write_text(json.dumps(public_timeline,indent=2),encoding="utf-8")
        artifacts["timeline.json"]=public
        if request["captions"]["srt"]: artifacts["captions.srt"]=srt
        elapsed=time.monotonic()-started
        manifest={"schema_version":"1.0","job_id":job["id"],"providers":{"tts":self.s.tts_provider,"stt":self.s.stt_provider,"footage":"reviewed-local-catalog","renderer":"ffmpeg"},
            "models":{"tts":self.s.tts_model if self.s.tts_provider!="disabled" else None,"stt":self.s.stt_model if self.s.stt_provider!="disabled" else None},
            "versions":{"service":"0.1.0","ffmpeg":self.media.version() if hasattr(self.media,"version") else "TEST_FAKE"},
            "settings":{"aspect_ratios":request["aspect_ratios"],"fps":self.s.output_fps,"captions":request["captions"],"style":request["style"],"seed":self.s.seed},
            "timings":{"processing_seconds":elapsed,"narration_seconds":duration},"cost_estimate_usd":None,
            "cost_warning":"Provider and compute charges are unmeasured; null does not mean free.","warnings":warnings,
            "rights":[{k:scene["clip"].get(k) for k in ("id","source","source_url","license","license_url","attribution","ai_generated")} for scene in timeline]}
        path=work/"manifest.json"; path.write_text(json.dumps(manifest,indent=2),encoding="utf-8"); artifacts["manifest.json"]=path
        keys={name:self.storage.put(path,f"{attempt_key}/{name}") for name,path in artifacts.items()}
        return {"objects":keys,"work_dir":str(work),"request":request}
