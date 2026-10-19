"""Persisted state. Permissions and transitions live in application services."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


ID = BigInteger().with_variant(Integer, 'sqlite')


class User(Base):
    __tablename__ = 'studio_users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(256), default='')
    username: Mapped[str | None] = mapped_column(String(256))
    language_code: Mapped[str] = mapped_column(String(2), default='ru', server_default='ru')
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preference_version: Mapped[int] = mapped_column(Integer, default=0)
    data_version: Mapped[int] = mapped_column(Integer, default=0)
    last_submission_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = 'studio_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RateLimit(Base):
    __tablename__ = 'studio_rate_limits'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class DeletionConfirmation(Base):
    __tablename__ = 'studio_deletion_confirmations'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), unique=True)
    data_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AttachmentGroup(Base):
    __tablename__ = 'studio_attachment_groups'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), index=True)
    phase: Mapped[str] = mapped_column(String(20), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=0)
    charged_count: Mapped[int] = mapped_column(Integer, default=0)
    charged_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class Draft(Base):
    __tablename__ = 'studio_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), unique=True)
    group_id: Mapped[str] = mapped_column(ForeignKey('studio_attachment_groups.id', ondelete='CASCADE'), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    legacy_step: Mapped[str] = mapped_column(String(32), default='service')
    legacy_return_to_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = 'studio_projects'
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), index=True)
    draft_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    group_id: Mapped[str] = mapped_column(ForeignKey('studio_attachment_groups.id', ondelete='CASCADE'), unique=True)
    service_id: Mapped[str | None] = mapped_column(String(40))
    service_title: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    budget: Mapped[str] = mapped_column(Text, default='')
    deadline: Mapped[str] = mapped_column(Text, default='')
    phone: Mapped[str] = mapped_column(Text, default='')
    legacy_username: Mapped[str | None] = mapped_column(Text)
    workflow: Mapped[str] = mapped_column(String(20), default='studio')
    status: Mapped[str] = mapped_column(String(32), default='new', index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    proposal_version: Mapped[int] = mapped_column(Integer, default=0)
    accepted_proposal_version: Mapped[int | None] = mapped_column(Integer)
    delivery_version: Mapped[int] = mapped_column(Integer, default=0)
    close_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Proposal(Base):
    __tablename__ = 'studio_proposals'
    __table_args__ = (UniqueConstraint('project_id', 'version'),)
    id: Mapped[int] = mapped_column(ID, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('studio_projects.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    terms: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Delivery(Base):
    __tablename__ = 'studio_deliveries'
    __table_args__ = (UniqueConstraint('project_id', 'version'),)
    id: Mapped[int] = mapped_column(ID, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('studio_projects.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = 'studio_events'
    id: Mapped[int] = mapped_column(ID, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('studio_projects.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(48))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Idempotency(Base):
    __tablename__ = 'studio_idempotency'
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id', ondelete='CASCADE'), primary_key=True)
    operation: Mapped[str] = mapped_column(String(120), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey('studio_projects.id', ondelete='CASCADE'), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


class Outbox(Base):
    __tablename__ = 'studio_outbox'
    __table_args__ = (Index('ix_studio_outbox_due', 'state', 'next_attempt_at'),)
    id: Mapped[int] = mapped_column(ID, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey('studio_events.id', ondelete='CASCADE'), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('studio_projects.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    recipient_id: Mapped[int] = mapped_column(BigInteger)
    recipient_role: Mapped[str] = mapped_column(String(16), default='client')
    project_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(36))
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))
    legacy_event_key: Mapped[str | None] = mapped_column(Text, unique=True)
    legacy_metadata: Mapped[dict | None] = mapped_column(JSON)


class Attachment(Base):
    __tablename__ = 'studio_attachments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(ForeignKey('studio_attachment_groups.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    extension: Mapped[str] = mapped_column(String(12))
    declared_bytes: Mapped[int] = mapped_column(BigInteger)
    actual_bytes: Mapped[int | None] = mapped_column(BigInteger)
    detected_type: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default='reserved')
    attempt_id: Mapped[str] = mapped_column(String(36), default=new_id)
    object_key: Mapped[str] = mapped_column(String(150), unique=True)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class FileCleanupJob(Base):
    __tablename__ = 'studio_file_cleanup'
    object_key: Mapped[str] = mapped_column(String(150), primary_key=True)
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey('studio_attachments.id', ondelete='SET NULL'), index=True)
    writer_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(36))


class Heartbeat(Base):
    __tablename__ = 'studio_heartbeats'
    name: Mapped[str] = mapped_column(String(48), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
