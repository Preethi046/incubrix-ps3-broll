import hashlib
import ipaddress
import socket
import time
import ssl
import http.client
from pathlib import Path
from urllib.parse import urlsplit
from .errors import ServiceError

def checked_target(url, allowed_hosts=()):
    try:
        parsed = urlsplit(url)
        host, port = parsed.hostname, parsed.port
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        if port not in (None,443): raise ValueError()
        if allowed_hosts and host.lower() not in {x.lower() for x in allowed_hosts}: raise ValueError()
        answers = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses): raise ValueError()
        return host, addresses[0], parsed.path or "/", parsed.query
    except (ValueError, OSError):
        raise ServiceError("UNSAFE_URL", "Use an allowed public HTTPS URL without credentials or redirects") from None

class PinnedHTTPS(http.client.HTTPSConnection):
    # Pin the validated IP while retaining hostname for TLS SNI/certificate checks.
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address
    def connect(self):
        raw = socket.create_connection((self.address,443),self.timeout)
        self.sock = self._context.wrap_socket(raw,server_hostname=self.host)

def download(url, destination: Path, settings):
    host,address,path,query = checked_target(url,settings.allowed_download_hosts)
    conn = PinnedHTTPS(host,address,settings.http_timeout_seconds)
    size=0
    deadline=time.monotonic()+settings.http_timeout_seconds
    try:
        conn.request("GET",path+("?"+query if query else ""),headers={"User-Agent":"IncuBrix-Broll/0.1"})
        response=conn.getresponse()
        if response.status != 200:
            raise ServiceError("DOWNLOAD_FAILED","Source must return HTTP 200 without redirect",502,response.status>=500)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open("wb") as output:
            while chunk := response.read(65536):
                if time.monotonic()>deadline: raise ServiceError("DOWNLOAD_FAILED","Download exceeded total time limit",504,True)
                size += len(chunk)
                if size>settings.max_upload_bytes: raise ServiceError("FILE_TOO_LARGE","Input exceeds configured size limit",413)
                output.write(chunk)
        if not size: raise ServiceError("INVALID_MEDIA","Empty media file")
    except ServiceError:
        destination.unlink(missing_ok=True)
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise ServiceError("DOWNLOAD_FAILED","Could not download source",502,True) from None
    finally: conn.close()
    return destination

def audio_kind(header: bytes):
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE": return "wav"
    if header.startswith(b"ID3") or (len(header)>1 and header[0] == 255 and header[1]&224 == 224): return "mp3"
    if len(header)>12 and header[4:8] == b"ftyp" and header[8:12] in (b"M4A ",b"isom",b"mp42"): return "m4a"
    raise ServiceError("INVALID_MEDIA","Expected MP3, WAV or M4A audio; extension alone is not trusted",415)
