"""add transcript_span_id to ai_analyses

Revision ID: add_transcript_span_id
Revises: 869cfd49ebd5
Create Date: 2026-02-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_transcript_span_id"
down_revision: Union[str, None] = "869cfd49ebd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add transcript_span_id column to ai_analyses table
    # SQLite doesn't support adding foreign keys directly, so we just add the column
    with op.batch_alter_table("ai_analyses") as batch_op:
        batch_op.add_column(
            sa.Column("transcript_span_id", sa.String(26), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_ai_analyses_transcript_span_id",
            "transcriptions",
            ["transcript_span_id"],
            ["transcription_id"],
        )


def downgrade() -> None:
    # Drop foreign key constraint and column
    with op.batch_alter_table("ai_analyses") as batch_op:
        batch_op.drop_constraint(
            "fk_ai_analyses_transcript_span_id", type_="foreignkey"
        )
        batch_op.drop_column("transcript_span_id")
