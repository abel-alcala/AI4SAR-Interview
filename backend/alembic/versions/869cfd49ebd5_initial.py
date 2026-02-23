"""initial

Revision ID: 869cfd49ebd5
Revises:
Create Date: 2025-11-16 14:05:56.431341

"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "869cfd49ebd5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    _ = op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("oidc_id", sa.String(length=255), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("full_name"),
        sa.UniqueConstraint("oidc_id"),
    )
    _ = op.create_table(
        "project",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("creator_user_id", sa.String(length=26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["creator_user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )
    _ = op.create_table(
        "transcriptions",
        sa.Column("transcription_id", sa.String(length=26), nullable=False),
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("session_id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("text_output", sa.Text(), nullable=True),
        sa.Column("speaker", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.project_id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("transcription_id"),
    )
    _ = op.create_table(
        "ai_analyses",
        sa.Column("analysis_id", sa.String(length=26), nullable=False),
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("span", sa.Text(), nullable=True),
        sa.Column("transcript_span_id", sa.String(length=26), nullable=True),
        sa.Column("transcript_context_start", sa.String(length=26), nullable=False),
        sa.Column("transcript_context_end", sa.String(length=26), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tag", sa.String(length=50), nullable=True),
        sa.Column("time_tag_changed", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.project_id"],
        ),
        sa.ForeignKeyConstraint(
            ["transcript_span_id"],
            ["transcriptions.transcription_id"],
        ),
        sa.ForeignKeyConstraint(
            ["transcript_context_start"],
            ["transcriptions.transcription_id"],
        ),
        sa.ForeignKeyConstraint(
            ["transcript_context_end"],
            ["transcriptions.transcription_id"],
        ),
        sa.PrimaryKeyConstraint("analysis_id"),
    )

    # ==========================
    # --- FTS5 (SQLite only) ---
    # ==========================

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        print("Can't do FTS5 setup on non-SQLite database.")
        exit(1)

    # Transcriptions FTS
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS transcriptions_fts
        USING fts5(
            transcription_id UNINDEXED,
            project_id UNINDEXED,
            user_id UNINDEXED,
            text_output,
            content=''
        );
        """
    )

    # Backfill (safe even in "initial" migration; table likely empty)
    op.execute(
        """
        INSERT INTO transcriptions_fts(rowid, transcription_id, project_id, user_id, text_output)
        SELECT
            rowid,
            transcription_id,
            project_id,
            user_id,
            COALESCE(text_output, '')
        FROM transcriptions;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS transcriptions_fts_ai
        AFTER INSERT ON transcriptions
        BEGIN
            INSERT INTO transcriptions_fts(rowid, transcription_id, project_id, user_id, text_output)
            VALUES (new.rowid, new.transcription_id, new.project_id, new.user_id, COALESCE(new.text_output, ''));
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS transcriptions_fts_ad
        AFTER DELETE ON transcriptions
        BEGIN
            INSERT INTO transcriptions_fts(transcriptions_fts, rowid, transcription_id, project_id, user_id, text_output)
            VALUES ('delete', old.rowid, old.transcription_id, old.project_id, old.user_id, COALESCE(old.text_output, ''));
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS transcriptions_fts_au
        AFTER UPDATE OF transcription_id, project_id, user_id, text_output ON transcriptions
        BEGIN
            INSERT INTO transcriptions_fts(transcriptions_fts, rowid, transcription_id, project_id, user_id, text_output)
            VALUES ('delete', old.rowid, old.transcription_id, old.project_id, old.user_id, COALESCE(old.text_output, ''));

            INSERT INTO transcriptions_fts(rowid, transcription_id, project_id, user_id, text_output)
            VALUES (new.rowid, new.transcription_id, new.project_id, new.user_id, COALESCE(new.text_output, ''));
        END;
        """
    )

    # AI analyses FTS
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS ai_analyses_fts
        USING fts5(
            analysis_id UNINDEXED,
            project_id UNINDEXED,
            text,
            content=''
        );
        """
    )

    op.execute(
        """
        INSERT INTO ai_analyses_fts(rowid, analysis_id, project_id, text)
        SELECT
            rowid,
            analysis_id,
            project_id,
            COALESCE(text, '')
        FROM ai_analyses;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ai_analyses_fts_ai
        AFTER INSERT ON ai_analyses
        BEGIN
            INSERT INTO ai_analyses_fts(rowid, analysis_id, project_id, text)
            VALUES (new.rowid, new.analysis_id, new.project_id, COALESCE(new.text, ''));
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ai_analyses_fts_ad
        AFTER DELETE ON ai_analyses
        BEGIN
            INSERT INTO ai_analyses_fts(ai_analyses_fts, rowid, analysis_id, project_id, text)
            VALUES ('delete', old.rowid, old.analysis_id, old.project_id, COALESCE(old.text, ''));
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ai_analyses_fts_au
        AFTER UPDATE OF analysis_id, project_id, text ON ai_analyses
        BEGIN
            INSERT INTO ai_analyses_fts(ai_analyses_fts, rowid, analysis_id, project_id, text)
            VALUES ('delete', old.rowid, old.analysis_id, old.project_id, COALESCE(old.text, ''));

            INSERT INTO ai_analyses_fts(rowid, analysis_id, project_id, text)
            VALUES (new.rowid, new.analysis_id, new.project_id, COALESCE(new.text, ''));
        END;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("transcriptions")
    op.drop_table("ai_analyses")
    op.drop_table("project")
    op.drop_table("users")
