"""VYRO — Posts, Hashtags, Likes, Saves."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, utcnow

VISIBILITY_PUBLIC = "public"
VISIBILITY_FOLLOWERS = "followers"


class Post(Base, UUIDPk, TimestampMixin):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_author_created", "author_id", "created_at"),
        Index("ix_posts_created_desc", "created_at"),
    )

    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    images: Mapped[list] = mapped_column(JSONB, default=list, nullable=False, server_default="[]")

    # repost (this post shares another post)
    repost_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True
    )

    visibility: Mapped[str] = mapped_column(String(20), default=VISIBILITY_PUBLIC, nullable=False)

    # denormalized counters (atomic increments)
    likes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reposts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buffs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buffs_total_zyra: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # original post for repost rows
    repost_of: Mapped["Post | None"] = relationship(remote_side="Post.id", lazy="selectin")


class Hashtag(Base, UUIDPk, TimestampMixin):
    __tablename__ = "hashtags"

    name: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    posts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PostHashtag(Base):
    __tablename__ = "post_hashtags"

    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    hashtag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hashtags.id", ondelete="CASCADE"), primary_key=True
    )


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (Index("ix_likes_post_created", "post_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Save(Base):
    __tablename__ = "saves"
    __table_args__ = (Index("ix_saves_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
