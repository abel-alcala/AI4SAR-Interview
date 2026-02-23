from collections.abc import Sequence
from pydantic import BaseModel
from sqlalchemy.sql.sqltypes import DateTime
from typing import Literal, TypedDict
from interview_helper.context_manager.types import (
    AnalysisId,
    ProjectId,
    SessionId,
    TranscriptId,
)
from interview_helper.context_manager.types import UserId
from alembic.config import Config
from alembic import command
from pathlib import Path
import sqlalchemy as sa
from contextlib import contextmanager
from dataclasses import dataclass
import interview_helper.context_manager.models as models
from ulid import ULID


class PersistentDatabase:
    """A persistent database that is saved to local disk"""

    DATABASE_URL = "sqlite+pysqlite:///data/database.sqlite3"

    def __init__(self, engine: sa.Engine | None = None):
        if engine is None:
            engine = sa.create_engine(PersistentDatabase.DATABASE_URL)

        self.engine = engine

    @classmethod
    def new_in_memory(cls):
        """
        A constructor for creating a persistent database in memory for testing
        """
        new_persistent_db = cls(
            engine=sa.create_engine("sqlite+pysqlite:///:memory:", echo=True)
        )

        new_persistent_db._run_migrations_for_testing()

        return new_persistent_db

    @contextmanager
    def begin(self):
        with self.engine.begin() as conn:
            yield conn

    def _run_migrations_for_testing(self):
        """
        We expect for production that the user runs the migration themselves, but for
        unit tests we must invoke it ourselves.
        """
        alembic_dir = Path(__file__).parent.parent.parent.parent / "alembic"

        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(alembic_dir))

        # Dark magic to get the in-memory database to alembic.
        alembic_cfg.attributes["connectable"] = self.engine

        command.upgrade(alembic_cfg, "head")


@dataclass
class UserResult:
    user_id: UserId
    full_name: str
    oidc_id: str


def get_user_by_id(db: PersistentDatabase, user_id: UserId) -> UserResult | None:
    """
    Returns the user given their user_id
    """
    with db.begin() as conn:
        result = (
            conn.execute(
                sa.select(
                    models.User.user_id, models.User.full_name, models.User.oidc_id
                ).where(models.User.user_id == str(user_id))
            )
            .tuples()
            .one_or_none()
        )

        if result is not None:
            user_id_str, full_name, oidc_id = result
            return UserResult(
                user_id=UserId.from_str(user_id_str),
                full_name=full_name,
                oidc_id=oidc_id,
            )

        return None


def get_or_add_user_by_oidc_id(
    db: PersistentDatabase, oidc_id: str, full_name: str | None
) -> UserResult:
    """
    Get or add a user by oidc_id. Uses the existing name if found.
    """
    with db.begin() as conn:
        result = (
            conn.execute(
                sa.select(models.User.user_id, models.User.full_name).where(
                    models.User.oidc_id == oidc_id
                )
            )
            .tuples()
            .one_or_none()
        )

        if result is not None:
            user_id, full_name_result = result

            # If the incoming name differs from what we have stored, update it
            if full_name is not None and full_name_result != full_name:
                update_result = conn.execute(
                    sa.update(models.User)
                    .where(models.User.user_id == user_id)
                    .values(full_name=full_name)
                )
                # Ensure exactly one row was updated
                assert update_result.rowcount == 1, (
                    "Expected exactly one user row to be updated"
                )

                full_name_result = full_name

            return UserResult(
                user_id=UserId.from_str(user_id),
                full_name=full_name_result,
                oidc_id=oidc_id,
            )

        user_id = str(ULID()).lower()
        assert conn.execute(
            sa.insert(models.User),
            {"user_id": user_id, "full_name": full_name, "oidc_id": oidc_id},
        )

        assert full_name is not None, (
            f"Full name must be provided for new user with OIDC ID: {oidc_id}"
        )

        return UserResult(
            user_id=UserId.from_str(user_id),
            full_name=full_name,
            oidc_id=oidc_id,
        )


def add_transcription(
    db: PersistentDatabase,
    user_id: UserId,
    session_id: SessionId,
    project_id: ProjectId,
    text: str,
    speaker: str | None,
) -> str:
    """
    Adds a transcription result, returns the transcription ID
    """
    transcription_id = str(ULID()).lower()
    with db.begin() as conn:
        assert conn.execute(
            sa.insert(models.Transcription),
            {
                "transcription_id": transcription_id,
                "user_id": str(user_id),
                "session_id": str(session_id),
                "project_id": str(project_id),
                "text_output": text,
                "speaker": speaker,
            },
        )

    return transcription_id


class TranscriptChunk(TypedDict):
    transcription_id: TranscriptId
    text_output: str
    speaker: str | None


def get_all_transcripts(
    db: PersistentDatabase, project_id: ProjectId
) -> list[TranscriptChunk]:
    """
    Gets all transcript results, sorted by creation date (ascending)
    """
    with db.begin() as conn:
        db_rows = conn.execute(
            sa.select(
                models.Transcription.text_output,
                models.Transcription.speaker,
                models.Transcription.transcription_id,
            )
            .where(models.Transcription.project_id == str(project_id))
            .order_by(models.Transcription.created_at.asc())
        ).all()

    rows: list[TranscriptChunk] = [
        {
            "transcription_id": transcription_id,
            "text_output": text_output,
            "speaker": speaker,
        }
        for text_output, speaker, transcription_id in db_rows  # pyright: ignore[reportAny]
    ]

    return rows


def get_all_transcripts_since_last_analysis(
    db: PersistentDatabase, project_id: ProjectId
) -> list[TranscriptChunk]:
    """
    Gets all transcript results, not including the last one used in AI analysis,
    sorted by creation date (ascending)
    """
    sql = sa.text("""
        SELECT
            t.text_output,
            t.speaker,
            t.transcription_id
        FROM transcriptions t
        WHERE
            t.project_id = :project_id
            AND (
                -- If there has never been an analysis, include everything
                NOT EXISTS (
                    SELECT 1
                    FROM ai_analyses a
                    WHERE a.project_id = :project_id
                )
                OR t.created_at >
                    (
                        SELECT t2.created_at
                        FROM ai_analyses a2
                        JOIN transcriptions t2
                          ON t2.transcription_id = a2.transcript_context_end
                        WHERE a2.project_id = :project_id
                        ORDER BY a2.analysis_id DESC
                        LIMIT 1
                    )
            )
        ORDER BY t.created_at ASC
    """)

    with db.begin() as conn:
        db_rows = conn.execute(sql, {"project_id": str(project_id)}).all()

    rows: list[TranscriptChunk] = [
        {
            "transcription_id": TranscriptId(transcription_id),  # pyright: ignore[reportAny]
            "text_output": text_output,
            "speaker": speaker,
        }
        for text_output, speaker, transcription_id in db_rows  # pyright: ignore[reportAny]
    ]

    return rows


class ProjectListing(TypedDict):
    id: str
    name: str
    creator_name: str
    created_at: str


def get_all_projects(db: PersistentDatabase) -> Sequence[ProjectListing]:
    """
    Gets all projects with creator name and creation date, sorted by creation date (descending)
    """
    with db.begin() as conn:
        rows: Sequence[tuple[str, str, str, DateTime]] = (
            conn.execute(
                sa.select(
                    models.Project.project_id,
                    models.Project.name,
                    models.User.full_name,
                    models.Project.created_at,
                )
                .join(
                    models.User, models.Project.creator_user_id == models.User.user_id
                )
                .order_by(models.Project.created_at.desc())
            )
            .tuples()
            .all()
        )

    projects: list[ProjectListing] = []
    for project_id, project_name, creator_name, created_at in rows:
        projects.append(
            {
                "id": project_id,
                "name": project_name,
                "creator_name": creator_name,
                "created_at": created_at.isoformat(),  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            }
        )

    return projects


def create_new_project(
    db: PersistentDatabase, user_id: UserId, project_name: str
) -> ProjectListing:
    """
    Creates a new project and returns the project ID
    """
    user = get_user_by_id(db, user_id)
    assert user, (
        f"User that doesn't exist (ID: {user_id}) is trying to create project: {project_name}"
    )

    project_id = str(ULID()).lower()
    with db.begin() as conn:
        result = conn.execute(
            sa.insert(models.Project).returning(models.Project.created_at),
            {
                "project_id": project_id,
                "creator_user_id": str(user.user_id),
                "name": project_name,
            },
        )

        created_at = result.scalar_one()

    return {
        "id": project_id,
        "name": project_name,
        "creator_name": user.full_name,
        "created_at": created_at.isoformat(),  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    }


def get_project_by_id(
    db: PersistentDatabase, project_id: ProjectId
) -> ProjectListing | None:
    """
    Gets a single project by ID with creator information
    """
    with db.begin() as conn:
        result = conn.execute(
            sa.select(
                models.Project.project_id,
                models.Project.name,
                models.User.full_name,
                models.Project.created_at,
            )
            .join(models.User, models.Project.creator_user_id == models.User.user_id)
            .where(models.Project.project_id == str(project_id))
        ).one_or_none()

        if result is None:
            return None

        project_id_str, project_name, creator_name, created_at = result.tuple()

        return {
            "id": project_id_str,
            "name": project_name,
            "creator_name": creator_name,
            "created_at": created_at.isoformat(),  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        }


class AnalysisRow(BaseModel):
    analysis_id: str
    text: str
    span: str | None
    transcript_span_id: TranscriptId | None
    tag: Literal["starred", "dismissed", "starred_dismissed"] | None
    transcript_context_start: TranscriptId
    transcript_context_end: TranscriptId
    summary: str
    ordinal: int


def get_all_ai_analyses(
    db: PersistentDatabase, project_id: ProjectId
) -> list[AnalysisRow]:
    """
    Gets all AI analysis results for a project, sorted by creation date (ascending)
    """
    with db.begin() as conn:
        # Subquery to compute row numbers
        subq = (
            sa.select(
                models.AIAnalysis.analysis_id,
                models.AIAnalysis.text,
                models.AIAnalysis.span,
                models.AIAnalysis.transcript_span_id,
                models.AIAnalysis.transcript_context_start,
                models.AIAnalysis.transcript_context_end,
                models.AIAnalysis.summary,
                models.AIAnalysis.tag,
                sa.func.row_number()
                .over(order_by=models.AIAnalysis.analysis_id.asc())
                .label("ordinal"),
            ).where(models.AIAnalysis.project_id == str(project_id))
        ).subquery()

        rows = conn.execute(
            sa.select(
                subq.c.analysis_id,
                subq.c.text,
                subq.c.span,
                subq.c.transcript_span_id,
                subq.c.transcript_context_start,
                subq.c.transcript_context_end,
                subq.c.summary,
                subq.c.tag,
                subq.c.ordinal,
            ).order_by(subq.c.analysis_id.asc())
        ).all()

    return [
        AnalysisRow(
            analysis_id=row.analysis_id,  # pyright: ignore[reportAny]
            text=row.text,  # pyright: ignore[reportAny]
            span=row.span,  # pyright: ignore[reportAny]
            transcript_span_id=TranscriptId.from_str(row.transcript_span_id)  # pyright: ignore[reportAny]
            if row.transcript_span_id  # pyright: ignore[reportAny]
            else None,
            tag=row.tag,  # pyright: ignore[reportAny]
            transcript_context_start=TranscriptId.from_str(
                row.transcript_context_start  # pyright: ignore[reportAny]
            ),
            transcript_context_end=TranscriptId.from_str(row.transcript_context_end),  # pyright: ignore[reportAny]
            summary=row.summary,  # pyright: ignore[reportAny]
            ordinal=row.ordinal,  # pyright: ignore[reportAny]
        )
        for row in rows
    ]


def get_analyses_by_ids(
    db: PersistentDatabase, project_id: ProjectId, analysis_ids: list[AnalysisId]
) -> list[AnalysisRow]:
    """
    Gets specific AI analyses by their IDs with ordinals computed.
    Results are returned in the same order as analysis_ids.
    """
    if not analysis_ids:
        return []

    analysis_id_strs = [str(aid) for aid in analysis_ids]

    with db.begin() as conn:
        # Subquery to compute row numbers for all analyses in the project
        subq = (
            sa.select(
                models.AIAnalysis.analysis_id,
                models.AIAnalysis.text,
                models.AIAnalysis.span,
                models.AIAnalysis.transcript_span_id,
                models.AIAnalysis.transcript_context_start,
                models.AIAnalysis.transcript_context_end,
                models.AIAnalysis.summary,
                models.AIAnalysis.tag,
                sa.func.row_number()
                .over(order_by=models.AIAnalysis.analysis_id.asc())
                .label("ordinal"),
            ).where(models.AIAnalysis.project_id == str(project_id))
        ).subquery()

        rows = conn.execute(
            sa.select(
                subq.c.analysis_id,
                subq.c.text,
                subq.c.span,
                subq.c.transcript_span_id,
                subq.c.transcript_context_start,
                subq.c.transcript_context_end,
                subq.c.summary,
                subq.c.tag,
                subq.c.ordinal,
            )
            .where(subq.c.analysis_id.in_(analysis_id_strs))
            .order_by(subq.c.analysis_id.asc())
        ).all()

    # Create a mapping for easy lookup
    analyses_map = {
        row.analysis_id: AnalysisRow(  # pyright: ignore[reportAny]
            analysis_id=row.analysis_id,  # pyright: ignore[reportAny]
            text=row.text,  # pyright: ignore[reportAny]
            span=row.span,  # pyright: ignore[reportAny]
            tag=row.tag,  # pyright: ignore[reportAny]
            transcript_context_start=TranscriptId.from_str(
                row.transcript_context_start  # pyright: ignore[reportAny]
            ),
            transcript_span_id=TranscriptId.from_str(row.transcript_span_id)  # pyright: ignore[reportAny]
            if row.transcript_span_id  # pyright: ignore[reportAny]
            else None,
            transcript_context_end=TranscriptId.from_str(row.transcript_context_end),  # pyright: ignore[reportAny]
            summary=row.summary,  # pyright: ignore[reportAny]
            ordinal=row.ordinal,  # pyright: ignore[reportAny]
        )
        for row in rows
    }

    # Return in the same order as requested
    return [
        analyses_map[aid_str] for aid_str in analysis_id_strs if aid_str in analyses_map
    ]


def update_ai_analysis_tag(
    db: PersistentDatabase, analysis_id: str, tag: str | None, _user_id: UserId
):
    """
    Update the tag for an AI analysis.

    Args:
        analysis_id: The ID of the analysis to update
        tag: The new tag value ("starred", "dismissed", "starred_dismissed", or None to clear)
        _user_id: User ID (kept for API compatibility, not used as tags are project-wide)
    """
    with db.begin() as conn:
        _ = conn.execute(
            sa.update(models.AIAnalysis)
            .where(models.AIAnalysis.analysis_id == analysis_id)
            .values(tag=tag, time_tag_changed=sa.func.now())
        )


def add_ai_analysis(
    db: PersistentDatabase,
    project_id: ProjectId,
    text: str,
    span: str | None,
    transcript_span_id: TranscriptId | None,
    transcript_context_start: TranscriptId,
    transcript_context_end: TranscriptId,
    summary: str,
) -> AnalysisId:
    """
    Adds a transcription result, returns the analysis ID
    """
    analysis_id = str(ULID()).lower()
    with db.begin() as conn:
        assert conn.execute(
            sa.insert(models.AIAnalysis),
            {
                "analysis_id": analysis_id,
                "project_id": str(project_id),
                "text": text,
                "span": span,
                "transcript_span_id": str(transcript_span_id)
                if transcript_span_id
                else None,
                "transcript_context_start": str(transcript_context_start),
                "transcript_context_end": str(transcript_context_end),
                "summary": summary,
            },
        )

    return AnalysisId.from_str(analysis_id)


def preprocess_fts5_text(searches: list[str]) -> str:
    """
    Preprocesses text for FTS5 queries by removing punctuation and
    combining multiple phrases with OR for SQLite FTS5.
    """
    cleaned_phrases = [
        "".join(char for char in phrase if char.isalnum() or char.isspace()).strip()
        for phrase in searches
    ]
    # Filter out any phrases that became empty after cleaning
    cleaned_phrases = [phrase for phrase in cleaned_phrases if phrase]
    return " OR ".join(cleaned_phrases)


def full_text_search_transcriptions(
    db: PersistentDatabase, project_id: ProjectId, fts5_query_phrases: list[str]
) -> list[str]:
    """
    Performs a full-text search on transcriptions, returning a list of tuples
    (transcription_id, text_output) that match the query.
    """

    query = preprocess_fts5_text(fts5_query_phrases)

    with db.begin() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT
                    t.transcription_id AS "transcription_id",
                    t.text_output AS "text_output",
                    rank
                FROM transcriptions_fts f
                JOIN transcriptions t
                    ON t.rowid = f.rowid
                WHERE f.text_output MATCH :query
                AND t.project_id = :project_id
                ORDER BY rank ASC;

                """
            ),
            {"query": query, "project_id": str(project_id)},
        ).all()

    return [row.text_output for row in rows]  # pyright: ignore[reportAny]


def full_text_search_ai_analysis(
    db: PersistentDatabase, project_id: ProjectId, fts5_query_phrases: list[str]
) -> list[str]:
    """
    Performs a full-text search on AI analyses, returning a list of tuples
    (analysis_id, text) that match the query.

    FTS5 query:
    1. Search for phrases in fts5_query_phrases (combined with OR)
    2. Do not use any punctuation in the search
    """

    # remove punctuation
    query = preprocess_fts5_text(fts5_query_phrases)

    with db.begin() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT
                    t.analysis_id AS "analysis_id",
                    t.text AS "text",
                    rank
                FROM ai_analyses_fts f
                JOIN ai_analyses t
                    ON t.rowid = f.rowid
                WHERE f.text MATCH :query
                AND t.project_id = :project_id
                ORDER BY rank ASC;
                """
            ),
            {"query": query, "project_id": str(project_id)},
        ).all()

    return [row.text for row in rows]  # pyright: ignore[reportAny]


def get_most_recent_summary(
    db: PersistentDatabase, project_id: ProjectId
) -> str | None:
    """
    Gets the most recent AI analysis summary for a project
    """
    with db.begin() as conn:
        result = conn.execute(
            sa.select(models.AIAnalysis.summary)
            .where(models.AIAnalysis.project_id == str(project_id))
            .order_by(models.AIAnalysis.analysis_id.desc())
            .limit(1)
        ).one_or_none()

        if result is None:
            return None

        return result[0]  # pyright: ignore[reportAny]


def get_session_sequence_number(
    db: PersistentDatabase, project_id: ProjectId, session_id: SessionId
) -> int:
    """
    Gets the session sequence (e.g., 1 for the first, 2 for the second) for a given project and session ID
    """

    with db.begin() as conn:
        result = conn.execute(  # pyright: ignore[reportAny]
            sa.text("""
            WITH sessions_base AS (
                SELECT
                    session_id,
                    MIN(created_at) AS first_created_at
                FROM transcriptions
                WHERE project_id = :project_id
                GROUP BY session_id
            ),
            sessions AS (
                SELECT
                    session_id,
                    ROW_NUMBER() OVER (
                        ORDER BY first_created_at, session_id
                    ) AS session_number
                FROM sessions_base
            ),
            current_session AS (
                SELECT session_number
                FROM sessions
                WHERE session_id = :session_id
            ),
            max_session AS (
                SELECT COALESCE(MAX(session_number), 0) AS max_session_number
                FROM sessions
            )
            SELECT
                COALESCE(
                    (SELECT session_number FROM current_session),
                    (SELECT max_session_number + 1 FROM max_session)
                ) AS session_number;
            """),
            {"project_id": str(project_id), "session_id": str(session_id)},
        ).scalar_one()

        return result  # pyright: ignore[reportAny]
