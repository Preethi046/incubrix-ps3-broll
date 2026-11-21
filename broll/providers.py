import json
import re
from pathlib import Path
from typing import Protocol
import httpx
from .errors import ServiceError

class Narrator(Protocol):
    def synthesize(self,text: str,path: Path,voice: str) -> Path: ...
class Transcriber(Protocol):
    def transcribe(self,path: Path) -> list[dict]: ...
class Footage(Protocol):
    def choose(self,text: str,hint: str,avoid: list[str],used: set[str],clip_id: str | None=None) -> dict: ...

class DisabledNarrator:
    def synthesize(self,*args): raise ServiceError("PROVIDER_NOT_CONFIGURED","Configure a real narration provider",503)
class DisabledTranscriber:
    def transcribe(self,*args): raise ServiceError("PROVIDER_NOT_CONFIGURED","Configure a real timestamped transcription provider",503)

class OpenAICompatible:
    # Explicit opt-in only; no request is made by default. Calls may incur provider charges.
    def __init__(self,settings): self.settings=settings
    def request(self,route,**kwargs):
        s=self.settings
        if not s.ai_api_key.get_secret_value(): raise ServiceError("PROVIDER_NOT_CONFIGURED","AI API key is missing",503)
        try:
            response=httpx.post(s.ai_base_url.rstrip("/")+route,headers={"Authorization":"Bearer "+s.ai_api_key.get_secret_value()},timeout=s.http_timeout_seconds,**kwargs)
            if response.status_code!=200: raise ServiceError("AI_PROVIDER_FAILED","AI provider rejected request",502,response.status_code>=500 or response.status_code==429)
            return response
        except httpx.HTTPError: raise ServiceError("AI_PROVIDER_FAILED","AI provider unavailable",502,True) from None
    def synthesize(self,text,path,voice):
        if voice != "en-IN-female" and voice != self.settings.tts_voice:
            raise ServiceError("VOICE_UNSUPPORTED","Requested voice is not mapped by the configured provider")
        # The requested default label is an alias, not a verified Indian-accent/female guarantee.
        response=self.request("/audio/speech",json={"model":self.settings.tts_model,"voice":self.settings.tts_voice,"input":text,"response_format":"wav"})
        path.write_bytes(response.content)
        return path
    def transcribe(self,path):
        with path.open("rb") as source:
            response=self.request("/audio/transcriptions",files={"file":(path.name,source)},data={"model":self.settings.stt_model,"response_format":"verbose_json","timestamp_granularities[]":"word"})
        try:
            words=response.json()["words"]
            if not words: raise ValueError()
            return [{"word":str(w["word"]),"start":float(w["start"]),"end":float(w["end"])} for w in words]
        except (ValueError,KeyError,TypeError): raise ServiceError("NO_SPEECH","No usable timestamped speech was returned",422) from None

def tokens(text): return re.findall(r"[^\W_]+",text.casefold(),re.UNICODE)

class LocalCatalog:
    # Deterministic tag-overlap baseline, NOT a semantic or vision-language model.
    def __init__(self,path): self.path=path
    def choose(self,text,hint,avoid,used,clip_id=None):
        try: entries=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError): raise ServiceError("FOOTAGE_UNAVAILABLE","Supply a reviewed, rights-cleared local footage catalog",503) from None
        candidates=[]
        query=set(tokens(hint or text))
        for item in entries:
            required=("id","path","source","source_url","license","license_url","attribution","tags","commercial_use","reviewed_safe")
            if any(key not in item for key in required): continue
            if item["id"] in used or not item["commercial_use"] or not item["reviewed_safe"]: continue
            if item["license"] not in ("CC0-1.0","CC-BY-4.0","Pexels License","Pixabay Content License","Owned"): continue
            if item.get("watermarked",True) or item.get("ai_generated",False): continue
            if not Path(item["path"]).is_file(): continue
            tags=" ".join(item["tags"]).casefold()
            if any(set(tokens(term)) <= set(tokens(tags)) for term in avoid if tokens(term)): continue
            if clip_id and item["id"]!=clip_id: continue
            score=len(query & set(tokens(tags))) / max(1,len(query))
            if score>0 or clip_id:
                candidates.append((score,item))
        if not candidates: raise ServiceError("NO_RELEVANT_FOOTAGE","No unused, reviewed, licensed clip matches catalog tags; no unsafe fallback was substituted",422)
        score,item=max(candidates,key=lambda row:(row[0],row[1]["id"]))
        return {**item,"selection_reason":"Reviewed local catalog; highest deterministic query/tag overlap among unused eligible clips (not semantic scoring)","retrieval_score":score,"relevance_score":None}

def configured_providers(settings):
    adapter=OpenAICompatible(settings)
    narrator=adapter if settings.tts_provider=="openai_compatible" else DisabledNarrator()
    transcriber=adapter if settings.stt_provider=="openai_compatible" else DisabledTranscriber()
    return narrator,transcriber,LocalCatalog(settings.catalog)
