from sqlalchemy.orm._orm_constructors import relationship
from sqlalchemy.sql.schema import ForeignKey
import sqlalchemy as sa
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)
from sqlalchemy import DateTime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__: str = "users"
    user_id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    full_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    oidc_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    updated_at: Mapped[DateTime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Transcription(Base):
    __tablename__: str = "transcriptions"

    transcription_id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("project.project_id"), nullable=False
    )

    user_id: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("users.user_id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(sa.String(26), nullable=False)

    text_output: Mapped[str] = mapped_column(sa.Text, nullable=True)
    speaker: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    user: Mapped["User"] = relationship(backref="transcriptions")


class AIAnalysis(Base):
    __tablename__: str = "ai_analyses"

    analysis_id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("project.project_id"), nullable=False
    )

    text: Mapped[str] = mapped_column(sa.Text, nullable=False)

    span: Mapped[str] = mapped_column(sa.Text, nullable=True)

    transcript_span_id: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("transcriptions.transcription_id"), nullable=True
    )

    transcript_context_start: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("transcriptions.transcription_id"), nullable=False
    )
    transcript_context_end: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("transcriptions.transcription_id"), nullable=False
    )

    summary: Mapped[str] = mapped_column(sa.Text, nullable=False)

    tag: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)

    time_tag_changed: Mapped[DateTime | None] = mapped_column(
        sa.DateTime, nullable=True
    )


class Project(Base):
    __tablename__: str = "project"

    project_id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)

    name: Mapped[str] = mapped_column(sa.Text, nullable=True)

    creator_user_id: Mapped[str] = mapped_column(
        sa.String(26), ForeignKey("users.user_id"), nullable=False
    )

    created_at: Mapped[DateTime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.func.now()
    )

    updated_at: Mapped[DateTime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
