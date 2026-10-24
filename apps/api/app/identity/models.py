"""Identity tables (F1 plan §3). All live in the `docflow` schema (ADR-0007)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ROLES = ("admin", "reviewer")
WORKSPACE_NAME_MAX_LENGTH = 80


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


def _timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """A person, global across workspaces. Linked to the identity provider by `auth_subject`."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # The Supabase JWT `sub`. Our own `id` keeps foreign keys independent of the provider.
    auth_subject: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class Workspace(Base):
    """The tenant root (constitution §4)."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {WORKSPACE_NAME_MAX_LENGTH}", name="name_length"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("docflow.users.id"))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp()


class Membership(Base):
    """A user's role in a workspace. The primary key leads with `workspace_id`."""

    __tablename__ = "memberships"
    __table_args__ = (CheckConstraint("role IN ('admin', 'reviewer')", name="role"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docflow.users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
