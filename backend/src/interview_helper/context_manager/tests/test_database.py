from ulid import ULID
from interview_helper.context_manager.database import (
    PersistentDatabase,
    add_ai_analysis,
    add_transcription,
    create_new_project,
    create_session,
    get_all_ai_analyses,
    get_or_add_user_by_oidc_id,
    get_user_by_id,
)
from interview_helper.context_manager.types import ProjectId, SessionId, TranscriptId
import sqlalchemy as sa
import pytest

pytestmark = pytest.mark.anyio


def test_database_migrations_succeed():
    engine = PersistentDatabase.new_in_memory().engine
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1")).scalar_one() == 1


def test_ulid_generation():
    """Test that ULIDs are generated server-side when creating users"""
    db = PersistentDatabase.new_in_memory()

    test_user_name = "ULID Test User"
    oidc_id = "test-ulid-oidc-id"

    user = get_or_add_user_by_oidc_id(db, oidc_id, test_user_name)

    # ULID should be 26 characters
    assert len(str(user.user_id)) == 26


def test_user_addition():
    db = PersistentDatabase.new_in_memory()

    test_user_name = "Test User"
    another_test_user_name2 = "Test User 2"
    oidc_id = "test-oidc-id"

    added_user = get_or_add_user_by_oidc_id(db, oidc_id, test_user_name)

    added_user3 = get_or_add_user_by_oidc_id(db, oidc_id, another_test_user_name2)
    added_user2 = get_user_by_id(db, added_user.user_id)

    assert added_user2 is not None

    # Check that all of them are the same user, but the name is updated to the latest
    assert added_user3.full_name == added_user2.full_name == another_test_user_name2
    assert added_user.full_name == test_user_name

    assert added_user.user_id == added_user2.user_id == added_user3.user_id
    assert added_user.oidc_id == added_user2.oidc_id == added_user3.oidc_id


def test_add_ai_analysis_normalizes_invalid_category_code_to_default():
    db = PersistentDatabase.new_in_memory()
    user = get_or_add_user_by_oidc_id(db, "oidc-1", "User One")

    project = create_new_project(db, user.user_id, "P1")
    project_id = ProjectId.from_str(project["id"])
    session_id = SessionId(ULID())
    create_session(db, session_id, project_id, user.user_id)

    transcript_id = TranscriptId.from_str(
        add_transcription(
            db=db,
            user_id=user.user_id,
            session_id=session_id,
            project_id=project_id,
            text="Sample transcript",
            speaker="Speaker-1",
        )
    )

    _ = add_ai_analysis(
        db=db,
        project_id=project_id,
        text="What time did they leave?",
        category_code="INVALID",
        span="they left at sunrise",
        transcript_span_id=transcript_id,
        transcript_context_start=transcript_id,
        transcript_context_end=transcript_id,
        summary="Summary",
    )

    rows = get_all_ai_analyses(db, project_id)
    assert len(rows) == 1
    assert rows[0].category_code == "P"
