from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def identifier() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(8), default="GET")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, default=1000)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    last_latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MonitorCheck(Base):
    __tablename__ = "monitor_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    monitor_id: Mapped[str] = mapped_column(String(36), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    latency: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Log(Base):
    __tablename__ = "logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    service: Mapped[str] = mapped_column(String(120), index=True)
    level: Mapped[str] = mapped_column(String(10), index=True)
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    attributes: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    __table_args__ = (Index("ix_logs_service_level_time", "service", "level", "created_at"),)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    title: Mapped[str] = mapped_column(String(240))
    service: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Timeline(Base):
    __tablename__ = "incident_timeline"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    service: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    action: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    resource: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Event(Base):
    """Transactional outbox. SQL is authoritative; Redis is an optional transport."""

    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class RuleState(Base):
    """A row per fingerprint serializes concurrent incident creation."""

    __tablename__ = "rule_states"
    fingerprint: Mapped[str] = mapped_column(String(200), primary_key=True)
    last_incident_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
