from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SceneInput(StrictModel):
    text: str = Field(min_length=1, max_length=3000)
    visual_hint: str = Field(default="", max_length=1000)
    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError("Text cannot be blank")
        return value.strip()

class Captions(StrictModel):
    burn_in: bool = True
    srt: bool = True

class JobInput(StrictModel):
    audio_url: str | None = Field(default=None, max_length=2048)
    upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}\.(mp3|wav|m4a)$")
    script: str | None = Field(default=None, min_length=1, max_length=30000)
    scenes: list[SceneInput] | None = Field(default=None, min_length=1, max_length=150)
    voice: str = Field(default="en-IN-female", max_length=100)
    aspect_ratios: list[Literal["16:9", "9:16", "1:1"]] = Field(default_factory=lambda: ["16:9"], min_length=1, max_length=3)
    style: str = Field(default="bright, modern, real-world footage", max_length=1000)
    avoid: list[str] = Field(default_factory=list, max_length=50)
    captions: Captions = Field(default_factory=Captions)
    @model_validator(mode="after")
    def one_input(self):
        if sum(x is not None for x in [self.audio_url, self.upload_id, self.script, self.scenes]) != 1:
            raise ValueError("Supply exactly one of audio_url, upload_id, script, scenes")
        if self.script is not None and not self.script.strip(): raise ValueError("Script cannot be blank")
        if len(set(self.aspect_ratios)) != len(self.aspect_ratios): raise ValueError("Duplicate aspect ratios")
        return self

class SwapInput(StrictModel):
    clip_id: str = Field(min_length=1, max_length=200)

class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    details: dict
class ErrorResponse(BaseModel):
    error: ErrorDetail
class Accepted(BaseModel):
    job_id: str
    status_url: str
class UploadResult(BaseModel):
    upload_id: str
    bytes: int
class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: int = Field(ge=0, le=100)
    results: dict[str, str]
    error: ErrorDetail | None
    attempts: int
