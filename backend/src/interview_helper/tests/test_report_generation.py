from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
import sqlalchemy as sa
from ulid import ULID

from interview_helper.context_manager import models
from interview_helper.context_manager.database import (
    PersistentDatabase,
    add_ai_analysis,
    create_new_project,
    create_session,
    get_or_add_user_by_oidc_id,
    mark_ai_analysis_asked,
)
from interview_helper.context_manager.types import (
    ProjectId,
    SessionId,
    TranscriptId,
    UserId,
)
from interview_helper.downloads.get_report import build_report_data, generate_report_pdf


pytestmark = pytest.mark.anyio


def _ulid_at(ts: datetime) -> str:
    ulid_value = cast(ULID, ULID.from_datetime(ts))
    return str(ulid_value).lower()


def _insert_transcription(
    db: PersistentDatabase,
    *,
    transcription_id: str,
    project_id: ProjectId,
    user_id: UserId,
    session_id: SessionId,
    speaker: str,
    text: str,
) -> None:
    with db.begin() as conn:
        _ = conn.execute(
            sa.insert(models.Transcription),
            {
                "transcription_id": transcription_id,
                "project_id": str(project_id),
                "user_id": str(user_id),
                "session_id": str(session_id),
                "speaker": speaker,
                "text_output": text,
            },
        )


def test_build_report_data_groups_questions_and_creates_bidirectional_anchors():
    db = PersistentDatabase.new_in_memory()
    user = get_or_add_user_by_oidc_id(db, "oidc-report-user", "Report User")

    project = create_new_project(db, user.user_id, "Mission Report")
    project_id = ProjectId.from_str(project["id"])

    session_1 = SessionId(ULID())
    session_2 = SessionId(ULID())
    create_session(db, session_1, project_id, user.user_id)
    create_session(db, session_2, project_id, user.user_id)

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=120)
    t2 = t0 + timedelta(seconds=600)

    transcript_1 = _ulid_at(t0)
    transcript_2 = _ulid_at(t1)
    transcript_3 = _ulid_at(t2)

    _insert_transcription(
        db,
        transcription_id=transcript_1,
        project_id=project_id,
        user_id=user.user_id,
        session_id=session_1,
        speaker="Speaker-A",
        text="We last saw him near the trailhead.",
    )
    _insert_transcription(
        db,
        transcription_id=transcript_2,
        project_id=project_id,
        user_id=user.user_id,
        session_id=session_1,
        speaker="Speaker-A",
        text="He was carrying a blue jacket.",
    )
    _insert_transcription(
        db,
        transcription_id=transcript_3,
        project_id=project_id,
        user_id=user.user_id,
        session_id=session_2,
        speaker="Speaker-B",
        text="He usually checks in every night.",
    )

    answered_analysis_id = add_ai_analysis(
        db=db,
        project_id=project_id,
        text="What route did he usually take from the trailhead?",
        category_code="B",
        span="last saw him near the trailhead",
        transcript_span_id=TranscriptId.from_str(transcript_1),
        transcript_context_start=TranscriptId.from_str(transcript_1),
        transcript_context_end=TranscriptId.from_str(transcript_2),
        summary="Summary",
    )

    unanswered_analysis_id = add_ai_analysis(
        db=db,
        project_id=project_id,
        text="What medication does he take?",
        category_code="C",
        span="",
        transcript_span_id=TranscriptId.from_str(transcript_2),
        transcript_context_start=TranscriptId.from_str(transcript_2),
        transcript_context_end=TranscriptId.from_str(transcript_2),
        summary="Summary",
    )
    _ = unanswered_analysis_id

    _ = mark_ai_analysis_asked(
        db,
        analysis_id=str(answered_analysis_id),
        asked_at_transcript_id=transcript_3,
    )
    explicit_asked_at = t1 + timedelta(seconds=30)
    with db.begin() as conn:
        _ = conn.execute(
            sa.update(models.AIAnalysis)
            .where(models.AIAnalysis.analysis_id == str(answered_analysis_id))
            .values(asked_at=explicit_asked_at)
        )

    report = build_report_data(project["id"], db)
    assert report is not None

    assert report.project_name == "Mission Report"
    assert report.start_time == t0
    assert report.total_duration == timedelta(seconds=120)

    answered = report.answered_by_category.get("B", [])
    unanswered = report.unanswered_by_category.get("C", [])

    assert len(answered) == 1
    assert len(unanswered) == 1

    answered_entry = answered[0]
    assert answered_entry.context_anchor == "transcript-1"
    assert answered_entry.answered_at_anchor == "transcript-2"
    assert answered_entry.answered_at_text == "2026-01-01 10:02:30 UTC"
    assert answered_entry.transcript_excerpt is not None
    assert (
        "Speaker-A: He was carrying a blue jacket." in answered_entry.transcript_excerpt
    )

    transcript_section = report.transcript_sections[1]
    assert len(transcript_section.answered_question_refs) == 1
    _, question_anchor, question_datetime = transcript_section.answered_question_refs[0]
    assert question_anchor == answered_entry.question_anchor
    assert question_datetime == explicit_asked_at


def test_generate_report_pdf_returns_pdf_bytes():
    db = PersistentDatabase.new_in_memory()
    user = get_or_add_user_by_oidc_id(db, "oidc-pdf-user", "PDF User")

    project = create_new_project(db, user.user_id, "PDF Project")
    project_id = ProjectId.from_str(project["id"])

    session = SessionId(ULID())
    create_session(db, session, project_id, user.user_id)

    transcript_id = _ulid_at(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    _insert_transcription(
        db,
        transcription_id=transcript_id,
        project_id=project_id,
        user_id=user.user_id,
        session_id=session,
        speaker="Speaker-A",
        text="Sample text",
    )

    pdf_bytes = generate_report_pdf(project["id"], db)
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF")
