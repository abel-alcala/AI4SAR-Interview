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
    mark_ai_analysis_asked,
    mark_ai_analysis_dismissed_not_asked,
    star_ai_analysis,
    unstar_ai_analysis,
    undo_ai_analysis_dismissal,
)
from interview_helper.context_manager.types import ProjectId, SessionId, TranscriptId
from datetime import datetime, timezone
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


def test_mark_ai_analysis_actions_update_tag_and_asked_fields():
    db = PersistentDatabase.new_in_memory()
    user = get_or_add_user_by_oidc_id(db, "oidc-asked-at", "Asked At User")

    project = create_new_project(db, user.user_id, "P2")
    project_id = ProjectId.from_str(project["id"])
    session_id = SessionId(ULID())
    create_session(db, session_id, project_id, user.user_id)

    transcript_id = add_transcription(
        db=db,
        user_id=user.user_id,
        session_id=session_id,
        project_id=project_id,
        text="Transcript chunk",
        speaker="Speaker-1",
    )

    analysis_id = add_ai_analysis(
        db=db,
        project_id=project_id,
        text="Question?",
        category_code="P",
        span=None,
        transcript_span_id=TranscriptId.from_str(transcript_id),
        transcript_context_start=TranscriptId.from_str(transcript_id),
        transcript_context_end=TranscriptId.from_str(transcript_id),
        summary="Summary",
    )

    current_datetime = datetime.now(timezone.utc)

    _ = mark_ai_analysis_asked(
        db=db, analysis_id=str(analysis_id), asked_at_transcript_id=transcript_id
    )

    rows = get_all_ai_analyses(db, project_id)
    assert len(rows) == 1
    asked_row = rows[0]
    assert asked_row.was_asked is True
    assert asked_row.asked_at_transcript_id == transcript_id
    assert asked_row.asked_at is not None, "asked_at should be set when marked as asked"
    assert asked_row.asked_at >= current_datetime, (
        "asked_at should be at least the time before the 'mark as asked'"
    )

    _ = undo_ai_analysis_dismissal(db=db, analysis_id=str(analysis_id))
    _ = star_ai_analysis(db=db, analysis_id=str(analysis_id))
    _ = mark_ai_analysis_dismissed_not_asked(db=db, analysis_id=str(analysis_id))
    rows_after_clear = get_all_ai_analyses(db, project_id)
    assert len(rows_after_clear) == 1
    cleared_row = rows_after_clear[0]
    assert cleared_row.tag == "starred_dismissed"
    assert cleared_row.was_asked is False
    assert cleared_row.asked_at_transcript_id is None
    assert cleared_row.asked_at is None

    _ = undo_ai_analysis_dismissal(db=db, analysis_id=str(analysis_id))
    rows_after_undo = get_all_ai_analyses(db, project_id)
    assert len(rows_after_undo) == 1
    undone_row = rows_after_undo[0]
    assert undone_row.tag == "starred"
    assert undone_row.was_asked is None
    assert undone_row.asked_at_transcript_id is None
    assert undone_row.asked_at is None

    _ = unstar_ai_analysis(db=db, analysis_id=str(analysis_id))
    rows_after_unstar = get_all_ai_analyses(db, project_id)
    assert len(rows_after_unstar) == 1
    unstarred_row = rows_after_unstar[0]
    assert unstarred_row.tag is None


def test_mark_ai_analysis_actions_validate_invalid_transitions():
    db = PersistentDatabase.new_in_memory()
    user = get_or_add_user_by_oidc_id(db, "oidc-validate-tags", "Validate User")

    project = create_new_project(db, user.user_id, "P3")
    project_id = ProjectId.from_str(project["id"])
    session_id = SessionId(ULID())
    create_session(db, session_id, project_id, user.user_id)

    transcript_id = add_transcription(
        db=db,
        user_id=user.user_id,
        session_id=session_id,
        project_id=project_id,
        text="Transcript chunk",
        speaker="Speaker-1",
    )

    analysis_id = add_ai_analysis(
        db=db,
        project_id=project_id,
        text="Question?",
        category_code="P",
        span=None,
        transcript_span_id=TranscriptId.from_str(transcript_id),
        transcript_context_start=TranscriptId.from_str(transcript_id),
        transcript_context_end=TranscriptId.from_str(transcript_id),
        summary="Summary",
    )

    with pytest.raises(ValueError):
        _ = unstar_ai_analysis(db=db, analysis_id=str(analysis_id))

    with pytest.raises(ValueError):
        _ = undo_ai_analysis_dismissal(db=db, analysis_id=str(analysis_id))

    _ = mark_ai_analysis_dismissed_not_asked(db=db, analysis_id=str(analysis_id))

    with pytest.raises(ValueError):
        _ = star_ai_analysis(db=db, analysis_id=str(analysis_id))

    with pytest.raises(ValueError):
        _ = mark_ai_analysis_asked(
            db=db,
            analysis_id=str(analysis_id),
            asked_at_transcript_id=transcript_id,
        )
