from collections.abc import Sequence
from pydantic import BaseModel
from sqlalchemy.sql.sqltypes import DateTime
from typing import TypedDict
from interview_helper.context_manager.types import AnalysisId, ProjectId, SessionId
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
            },
        )

    return transcription_id


def get_all_transcripts(db: PersistentDatabase, project_id: ProjectId) -> list[str]:
    """
    Gets all transcript results, sorted by creation date (ascending)
    """
    with db.begin() as conn:
        rows = (
            conn.execute(
                sa.select(models.Transcription.text_output)
                .where(models.Transcription.project_id == str(project_id))
                .order_by(models.Transcription.created_at.asc())
            )
            .scalars()
            .all()
        )

    return list(rows)


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
    is_dismissed: bool


def get_all_ai_analyses(
    db: PersistentDatabase, project_id: ProjectId
) -> list[AnalysisRow]:
    """
    Gets all AI analysis results for a project, sorted by creation date (ascending)

    Also joins with DismissedAIAnalysis to add
    """
    with db.begin() as conn:
        rows = conn.execute(
            sa.select(
                models.AIAnalysis.analysis_id,
                models.AIAnalysis.text,
                models.AIAnalysis.span,
                sa.case(
                    (models.DismissedAIAnalysis.analysis_id.isnot(None), True),
                    else_=False,
                ).label("is_dismissed"),
            )
            .order_by(models.AIAnalysis.analysis_id.asc())
            .outerjoin(
                models.DismissedAIAnalysis,
                models.AIAnalysis.analysis_id == models.DismissedAIAnalysis.analysis_id,
            )
            .where(models.AIAnalysis.project_id == str(project_id))
        ).all()

    return [
        AnalysisRow(
            analysis_id=row.analysis_id,  # pyright: ignore[reportAny]
            text=row.text,  # pyright: ignore[reportAny]
            span=row.span,  # pyright: ignore[reportAny]
            is_dismissed=row.is_dismissed,  # pyright: ignore[reportAny]
        )
        for row in rows
    ]


def dismiss_ai_analysis(db: PersistentDatabase, analysis_id: str, user_id: UserId):
    """
    A user dismisses an AI analysis
    """
    dismissed_analysis_id = str(ULID()).lower()
    with db.begin() as conn:
        _ = conn.execute(
            sa.insert(models.DismissedAIAnalysis),
            {
                "dismissed_analysis_id": dismissed_analysis_id,
                "user_id": str(user_id),
                "analysis_id": analysis_id,
            },
        )


def add_ai_analysis(
    db: PersistentDatabase, project_id: ProjectId, text: str, span: str | None
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
            },
        )

    return AnalysisId.from_str(analysis_id)


def full_text_search_transcriptions(
    db: PersistentDatabase, project_id: ProjectId, fts5_query: str
) -> list[str]:
    """
    Performs a full-text search on transcriptions, returning a list of tuples
    (transcription_id, text_output) that match the query.
    """
    with db.begin() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT t.transcription_id AS "transcription_id", t.text_output as "text_output"
                FROM transcriptions_fts f
                JOIN transcriptions t
                    ON t.rowid = f.rowid
                WHERE f.text_output MATCH :query 
                      AND t.project_id = :project_id;
                """
            ),
            {"query": fts5_query, "project_id": str(project_id)},
        ).all()

    return [row.text_output for row in rows]  # pyright: ignore[reportAny]


def full_text_search_ai_analysis(
    db: PersistentDatabase, project_id: ProjectId, fts5_query: str
) -> list[str]:
    """
    Performs a full-text search on AI analyses, returning a list of tuples
    (analysis_id, text) that match the query.
    """
    with db.begin() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT t.analysis_id AS "analysis_id", t.text as "text"
                FROM ai_analyses_fts f
                JOIN ai_analyses t
                    ON t.rowid = f.rowid
                WHERE f.text MATCH :query 
                      AND t.project_id = :project_id;
                """
            ),
            {"query": fts5_query, "project_id": str(project_id)},
        ).all()

    return [row.text for row in rows]  # pyright: ignore[reportAny]
