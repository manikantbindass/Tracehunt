import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["critical", "high", "medium", "low"]
Status = Literal["open", "investigating", "resolved"]
Level = Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MonitorCreate(Input):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[\w .:/-]+$")
    url: str = Field(min_length=8, max_length=2048)
    method: Literal["GET", "HEAD"] = "GET"
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)
    latency_threshold_ms: int = Field(default=1000, ge=10, le=60000)
    enabled: bool = True


class MonitorUpdate(Input):
    enabled: bool


class LogCreate(Input):
    service: str = Field(min_length=1, max_length=120, pattern=r"^[\w./-]+$")
    level: Level = "INFO"
    message: str = Field(min_length=1, max_length=10000)
    trace_id: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value):
        value = str(value).upper()
        return "WARN" if value == "WARNING" else value

    @field_validator("metadata")
    @classmethod
    def bound_metadata(cls, value):
        encoded = json.dumps(value, allow_nan=False).encode("utf-8")
        if len(encoded) > 16000:
            raise ValueError("metadata must be at most 16 KB")
        return value


class LogBatch(Input):
    logs: list[LogCreate] = Field(min_length=1, max_length=500)


class IncidentCreate(Input):
    title: str = Field(min_length=3, max_length=240)
    service: str = Field(min_length=1, max_length=120)
    severity: Severity = "medium"
    summary: str = Field(default="", max_length=10000)


class IncidentUpdate(Input):
    status: Status


class DeploymentCreate(Input):
    service: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=120)
    environment: str = Field(default="production", min_length=1, max_length=32)
    status: Literal["success", "failed", "in_progress", "rolled_back"] = "success"
    commit_sha: str | None = Field(default=None, max_length=64, pattern=r"^[a-fA-F0-9]{7,64}$")


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    probable_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    recommended_actions: list[str]
