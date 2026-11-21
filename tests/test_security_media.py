import json
import pytest
from broll.errors import ServiceError
from broll.security import checked_target,audio_kind
from broll.media import build_scenes,write_srt
from broll.storage import safe_key
from broll.providers import LocalCatalog

@pytest.mark.parametrize("url",["http://example.com/audio.mp3","https://user:pass@example.com/a","https://127.0.0.1/a","https://[::1]/a","https://169.254.169.254/a","file:///etc/passwd","https://example.com:8443/a"])
def test_unsafe_urls(url):
    with pytest.raises(ServiceError): checked_target(url)

def test_dns_rebinding_pin(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",lambda *a,**k:[(2,1,6,"",("93.184.216.34",443))])
    host,ip,path,query=checked_target("https://example.com/a?token=x")
    assert (host,ip,path,query)==("example.com","93.184.216.34","/a","token=x")

def test_mixed_dns_private_rejected(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",lambda *a,**k:[(2,1,6,"",("93.184.216.34",443)),(2,1,6,"",("127.0.0.1",443))])
    with pytest.raises(ServiceError): checked_target("https://example.com/a")

@pytest.mark.parametrize("key",["../secret","job/../../secret","/absolute","a\\b"])
def test_unsafe_object_keys(key):
    with pytest.raises(ServiceError): safe_key(key)

def test_word_timing_coverage_and_captions(tmp_path):
    words=[{"word":"Cloud","start":0.2,"end":0.5},{"word":"servers.","start":0.5,"end":1.4},{"word":"Save.","start":1.8,"end":2.5}]
    scenes=build_scenes(words,3)
    assert scenes[0]["start"]==0 and scenes[-1]["end"]==3
    assert scenes[0]["end"]==scenes[1]["start"]==1.8
    path=tmp_path/"c.srt"; write_srt(words,path)
    assert "00:00:00,200 --> 00:00:01,400" in path.read_text()

def test_scene_list_alignment():
    words=[{"word":"Hello","start":0,"end":1},{"word":"world.","start":1,"end":2}]
    assert build_scenes(words,2,[{"text":"Hello world.","visual_hint":"earth"}])[0]["visual_hint"]=="earth"
    with pytest.raises(ServiceError): build_scenes(words,2,[{"text":"Something else"}])

def test_silent_and_bad_timestamps():
    with pytest.raises(ServiceError): build_scenes([],2)
    with pytest.raises(ServiceError): build_scenes([{"word":"x","start":1,"end":0}],2)

def test_catalog_licensing_no_repeat_and_avoid(tmp_path):
    clip=tmp_path/"clip.mp4"; clip.write_bytes(b"fixture-not-a-video")
    entry={"id":"1","path":str(clip),"source":"owned fixture","source_url":"https://example.com/proof","license":"Owned","license_url":"https://example.com/rights","attribution":"Test","tags":["cloud","servers"],"commercial_use":True,"reviewed_safe":True,"watermarked":False,"ai_generated":False}
    path=tmp_path/"catalog.json"; path.write_text(json.dumps([entry]))
    catalog=LocalCatalog(path)
    assert catalog.choose("cloud","",[],set())["id"]=="1"
    with pytest.raises(ServiceError): catalog.choose("cloud","",[],{"1"})
    with pytest.raises(ServiceError): catalog.choose("cloud","",["servers"],set())
    entry["license"]="CC-BY-NC"; path.write_text(json.dumps([entry]))
    with pytest.raises(ServiceError): catalog.choose("cloud","",[],set())
