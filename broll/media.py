import json
import re
import shutil
import subprocess
from pathlib import Path
from .errors import ServiceError

class MediaTools:
    def __init__(self,settings): self.s=settings
    def run(self,args):
        try:
            return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=self.s.render_timeout_seconds).stdout
        except FileNotFoundError: raise ServiceError("MEDIA_TOOL_MISSING","FFmpeg/ffprobe is not installed or configured",503) from None
        except subprocess.TimeoutExpired: raise ServiceError("RENDER_TIMEOUT","Media operation timed out",504,True) from None
        except subprocess.CalledProcessError: raise ServiceError("INVALID_MEDIA","Media processing failed; no internal paths or provider responses are exposed",422) from None
    def version(self):
        return self.run([self.s.ffmpeg,"-version"]).decode("utf-8",errors="replace").splitlines()[0]
    def probe(self,path):
        return json.loads(self.run([self.s.ffprobe,"-v","error","-show_format","-show_streams","-of","json",str(path)]))
    def audio_duration(self,path):
        data=self.probe(path)
        if not any(s["codec_type"]=="audio" for s in data["streams"]): raise ServiceError("NO_AUDIO","Input has no audio stream",422)
        duration=float(data["format"].get("duration",0))
        if not 0<duration<=self.s.max_audio_seconds: raise ServiceError("AUDIO_DURATION","Audio duration is zero or exceeds configured limit",422)
        return duration
    def size(self,ratio):
        s=self.s
        return {"16:9":(s.landscape_width,s.landscape_height),"9:16":(s.portrait_width,s.portrait_height),"1:1":(s.square_size,s.square_size)}[ratio]
    def segment(self,clip,duration,ratio,target):
        w,h=self.size(ratio)
        # Pad rather than crop: preserves edge subjects, with clearly disclosed letterboxing.
        vf=f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x202020,setsar=1,fps={self.s.output_fps},format=yuv420p"
        self.run([self.s.ffmpeg,"-y","-v","error","-stream_loop","-1","-i",str(clip),"-an","-t",str(duration),"-vf",vf,"-c:v","libx264","-preset","fast",str(target)])
    def assemble(self,segments,audio,srt,burn_in,target,duration):
        listing=target.parent/(target.stem+"-concat.txt")
        listing.write_text("".join("file '"+str(p.resolve()).replace("\\","/").replace("'","'\\''")+"'\n" for p in segments),encoding="utf-8")
        cmd=[self.s.ffmpeg,"-y","-v","error","-f","concat","-safe","0","-i",str(listing),"-i",str(audio),"-map","0:v:0","-map","1:a:0","-t",str(duration)]
        if burn_in:
            escaped=str(srt.resolve()).replace("\\","/").replace(":",r"\:").replace("'",r"\'")
            cmd += ["-vf",f"subtitles=filename='{escaped}'","-c:v","libx264","-preset","fast"]
        else: cmd += ["-c:v","copy"]
        self.run(cmd+["-c:a","aac","-ar","48000","-movflags","+faststart",str(target)])
        info=self.probe(target)
        video=next((s for s in info["streams"] if s["codec_type"]=="video"),{})
        audio_stream=next((s for s in info["streams"] if s["codec_type"]=="audio"),{})
        if audio_stream.get("codec_name")!="aac": raise ServiceError("OUTPUT_VALIDATION_FAILED","Encoded audio is not AAC",500)
        if video.get("r_frame_rate")!=f"{self.s.output_fps}/1": raise ServiceError("OUTPUT_VALIDATION_FAILED","Output frame rate differs from settings",500)
        if video.get("codec_name")!="h264" or video.get("pix_fmt")!="yuv420p": raise ServiceError("OUTPUT_VALIDATION_FAILED","Encoded video failed basic validation",500)
        if abs(float(info["format"]["duration"])-duration)>0.2: raise ServiceError("OUTPUT_VALIDATION_FAILED","Output duration differs from narration",500)

def build_scenes(words,duration,provided=None):
    if not words: raise ServiceError("NO_SPEECH","No timestamped speech detected",422)
    previous=0
    for word in words:
        if not 0<=word["start"]<=word["end"]<=duration+0.1 or word["start"]<previous-0.01:
            raise ServiceError("INVALID_TIMESTAMPS","Transcriber returned invalid word times",502)
        previous=word["end"]
    groups=[]
    if provided:
        from .providers import tokens
        actual=[t for w in words for t in tokens(w["word"])]
        expected=[t for scene in provided for t in tokens(scene["text"])]
        if not expected or any(not tokens(scene["text"]) for scene in provided) or actual!=expected or any(len(tokens(w["word"]))!=1 for w in words):
            raise ServiceError("SCENE_ALIGNMENT_FAILED","Scene-list text differs from recognized narration; safe exact word alignment could not be established",422)
        offset=0
        for scene in provided:
            count=len(tokens(scene["text"]))
            groups.append((words[offset:offset+count],scene["text"],scene.get("visual_hint","")))
            offset+=count
    else:
        group=[]
        for word in words:
            group.append(word)
            if re.search(r"[.!?]$",word["word"]):
                groups.append((group," ".join(w["word"] for w in group),"")); group=[]
        if group: groups.append((group," ".join(w["word"] for w in group),""))
    result=[]
    for i,(group,text,hint) in enumerate(groups):
        start=0 if i==0 else group[0]["start"]
        end=duration if i==len(groups)-1 else groups[i+1][0][0]["start"]
        if end<=start: raise ServiceError("INVALID_TIMESTAMPS","Zero-length scene",422)
        result.append({"scene_id":i,"text":text,"visual_hint":hint,"start":start,"end":end})
    return result

def timestamp(value):
    ms=round(value*1000)
    hours,ms=divmod(ms,3600000); minutes,ms=divmod(ms,60000); seconds,ms=divmod(ms,1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

def write_srt(words,path):
    # Phrase-sized caption groups, never inferred from a word-per-minute estimate.
    groups=[]; current=[]
    for word in words:
        current.append(word)
        if len(current)>=8 or re.search(r"[.!?]$",word["word"]): groups.append(current); current=[]
    if current: groups.append(current)
    path.write_text("\n\n".join(f"{i+1}\n{timestamp(g[0]['start'])} --> {timestamp(g[-1]['end'])}\n"+" ".join(w["word"] for w in g) for i,g in enumerate(groups))+"\n",encoding="utf-8")
