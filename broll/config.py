from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BROLL_", env_file=".env", extra="ignore", validate_assignment=True)
    data_dir: Path = Path("data")
    database: Path = Path("data/jobs.sqlite3")
    max_upload_bytes: int = Field(default=80 * 1024 * 1024, gt=0)
    max_audio_seconds: float = 600
    max_script_chars: int = 30000
    max_scenes: int = 150
    http_timeout_seconds: float = 30
    worker_poll_seconds: float = 0.5
    lease_seconds: int = Field(default=300, ge=3)
    max_attempts: int = Field(default=2, ge=1)
    storage: Literal["local", "s3"] = "local"
    public_base_url: str = "http://localhost:8000"
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_bucket: str = "broll"
    s3_region: str = "us-east-1"
    signed_url_seconds: int = 3600
    api_token: SecretStr = SecretStr("")
    max_queued_jobs: int = 100
    allowed_download_hosts: list[str] = Field(default_factory=list)
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    render_timeout_seconds: int = 1800
    catalog: Path = Path("data/catalog.json")
    tts_provider: Literal["disabled", "openai_compatible"] = "disabled"
    stt_provider: Literal["disabled", "openai_compatible"] = "disabled"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: SecretStr = SecretStr("")
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    stt_model: str = "whisper-1"
    seed: int = 42
    output_fps: int = 30
    landscape_width: int = 1920
    landscape_height: int = 1080
    portrait_width: int = 1080
    portrait_height: int = 1920
    square_size: int = 1080
    # None means unmeasured, never report a fabricated free compute cost.
    compute_usd_per_hour: float | None = None
    tts_usd_per_million_chars: float | None = None
    stt_usd_per_minute: float | None = None
