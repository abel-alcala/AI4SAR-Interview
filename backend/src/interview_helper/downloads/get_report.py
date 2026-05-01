from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from collections.abc import Sequence
from typing import cast
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.flowables import Flowable

from interview_helper.context_manager.database import (
    AnalysisRow,
    PersistentDatabase,
    TranscriptionWithProjectDetails,
    get_all_ai_analyses,
    get_all_transcriptions_for_project,
)
from interview_helper.context_manager.question_categories import (
    QUESTION_CATEGORY_LABELS,
    QUESTION_CATEGORY_ORDER,
    normalize_question_category_code,
)
from interview_helper.context_manager.types import ProjectId
from interview_helper.downloads.util import extract_timestamp_from_ulid

# Time window for transcript excerpts before answered questions
TRANSCRIPT_EXCERPT_WINDOW = timedelta(minutes=1)
# Time gap threshold for adding visual separators between transcript entries
TRANSCRIPT_ENTRY_GAP_SEPARATOR_THRESHOLD = timedelta(minutes=5)
# If an answered-question event happens after this delay, render a standalone timestamp.
ANSWERED_EVENT_TIMESTAMP_CUTOFF = timedelta(minutes=2)


@dataclass
class ReportQuestionEntry:
    analysis_id: str
    ordinal: int
    text: str
    category_code: str
    span: str | None
    question_anchor: str
    context_anchor: str | None
    answered_at_anchor: str | None
    answered_at_text: str | None
    is_starred: bool
    transcript_excerpt: str | None = None


@dataclass
class ReportTranscriptSection:
    anchor: str
    speaker: str
    text: str
    started_at: datetime
    ended_at: datetime
    chunk_ids: list[str] = field(default_factory=list)
    answered_question_refs: list[tuple[int, str, datetime]] = field(
        default_factory=list
    )


@dataclass
class ReportData:
    project_name: str
    start_time: datetime
    total_duration: timedelta
    answered_by_category: dict[str, list[ReportQuestionEntry]]
    unanswered_by_category: dict[str, list[ReportQuestionEntry]]
    transcript_sections: list[ReportTranscriptSection]


@dataclass
class _TranscriptAnchorIndex:
    sections: list[ReportTranscriptSection]
    chunk_to_section_anchor: dict[str, str]
    section_by_anchor: dict[str, ReportTranscriptSection]


def _format_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_duration_hms(duration: timedelta) -> str:
    total_seconds = int(max(duration.total_seconds(), 0))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _format_excerpt_window(duration: timedelta) -> str:
    total_seconds = int(max(duration.total_seconds(), 0))
    minutes, seconds = divmod(total_seconds, 60)
    if minutes > 0 and seconds == 0:
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds} second" if seconds == 1 else f"{seconds} seconds"


def _format_gap_duration(duration: timedelta) -> str:
    total_seconds = int(max(duration.total_seconds(), 0))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _ordered_category_items(
    grouped: dict[str, list[ReportQuestionEntry]],
) -> list[tuple[str, list[ReportQuestionEntry]]]:
    items: list[tuple[str, list[ReportQuestionEntry]]] = []
    for code in QUESTION_CATEGORY_ORDER:
        rows = grouped.get(code, [])
        if rows:
            items.append((code, rows))
    return items


def _build_transcript_anchor_index(
    transcript_rows: Sequence[TranscriptionWithProjectDetails],
) -> _TranscriptAnchorIndex:
    sections: list[ReportTranscriptSection] = []
    chunk_to_section_anchor: dict[str, str] = {}

    current_speaker: str | None = None
    current_texts: list[str] = []
    current_chunk_ids: list[str] = []
    current_started_at: datetime | None = None

    def flush_current() -> None:
        nonlocal current_speaker, current_texts, current_chunk_ids, current_started_at

        if (
            current_speaker is None
            or current_started_at is None
            or len(current_chunk_ids) == 0
        ):
            return

        anchor = f"transcript-{len(sections) + 1}"
        ended_at = extract_timestamp_from_ulid(current_chunk_ids[-1])
        section = ReportTranscriptSection(
            anchor=anchor,
            speaker=current_speaker,
            text=" ".join(current_texts).strip(),
            started_at=current_started_at,
            ended_at=ended_at,
            chunk_ids=[*current_chunk_ids],
        )
        sections.append(section)

        for chunk_id in current_chunk_ids:
            chunk_to_section_anchor[chunk_id] = anchor

        current_speaker = None
        current_texts = []
        current_chunk_ids = []
        current_started_at = None

    for row in transcript_rows:
        transcription_id = str(row["transcription_id"])
        speaker = str(row["speaker"] or "Unknown Speaker")
        text = str(row["text_output"] or "").strip()
        timestamp = extract_timestamp_from_ulid(transcription_id)

        if current_speaker is None:
            current_speaker = speaker
            current_started_at = timestamp
            current_chunk_ids = [transcription_id]
            current_texts = [text]
            continue

        if speaker == current_speaker:
            current_chunk_ids.append(transcription_id)
            current_texts.append(text)
            continue

        flush_current()
        current_speaker = speaker
        current_started_at = timestamp
        current_chunk_ids = [transcription_id]
        current_texts = [text]

    flush_current()

    section_by_anchor = {section.anchor: section for section in sections}
    return _TranscriptAnchorIndex(
        sections=sections,
        chunk_to_section_anchor=chunk_to_section_anchor,
        section_by_anchor=section_by_anchor,
    )


def _compute_total_duration(
    transcript_rows: Sequence[TranscriptionWithProjectDetails],
) -> timedelta:
    if not transcript_rows:
        return timedelta(0)

    per_session_bounds: dict[str, tuple[datetime, datetime]] = {}

    for row in transcript_rows:
        session_id = str(row["session_id"])
        timestamp = extract_timestamp_from_ulid(str(row["transcription_id"]))

        previous = per_session_bounds.get(session_id)
        if previous is None:
            per_session_bounds[session_id] = (timestamp, timestamp)
            continue

        min_ts, max_ts = previous
        if timestamp < min_ts:
            min_ts = timestamp
        if timestamp > max_ts:
            max_ts = timestamp
        per_session_bounds[session_id] = (min_ts, max_ts)

    total = timedelta(0)
    for min_ts, max_ts in per_session_bounds.values():
        total += max_ts - min_ts

    return total


def _analysis_context_anchor(
    analysis: AnalysisRow, chunk_to_section_anchor: dict[str, str]
) -> str | None:
    if analysis.transcript_span_id is not None:
        span_anchor = chunk_to_section_anchor.get(str(analysis.transcript_span_id))
        if span_anchor is not None:
            return span_anchor

    start_anchor = chunk_to_section_anchor.get(str(analysis.transcript_context_start))
    if start_anchor is not None:
        return start_anchor

    return chunk_to_section_anchor.get(str(analysis.transcript_context_end))


def _format_excerpt_rows(excerpt_rows: Sequence[tuple[str, str]]) -> str | None:
    if len(excerpt_rows) == 0:
        return None

    grouped_lines: list[str] = []
    current_speaker: str | None = None
    current_texts: list[str] = []

    def flush_current() -> None:
        nonlocal current_speaker, current_texts
        if current_speaker is None or len(current_texts) == 0:
            return
        grouped_lines.append(f"{current_speaker}: {' '.join(current_texts)}")
        current_speaker = None
        current_texts = []

    for speaker, text in excerpt_rows:
        if current_speaker is None:
            current_speaker = speaker
            current_texts = [text]
            continue

        if speaker == current_speaker:
            current_texts.append(text)
            continue

        flush_current()
        current_speaker = speaker
        current_texts = [text]

    flush_current()
    return "\n".join(grouped_lines) if grouped_lines else None


def _precompute_transcript_excerpts_by_asked_at(
    transcript_rows: Sequence[TranscriptionWithProjectDetails],
    analyses: Sequence[AnalysisRow],
) -> dict[str, str | None]:
    asked_events = sorted(
        [
            (analysis.asked_at, analysis.analysis_id)
            for analysis in analyses
            if analysis.asked_at is not None
        ],
        key=lambda item: item[0],
    )
    if len(asked_events) == 0:
        return {}

    excerpts_by_analysis_id: dict[str, str | None] = {}
    window_rows: deque[tuple[datetime, str, str]] = deque()
    transcript_events: list[tuple[datetime, str, str]] = []

    for row in transcript_rows:
        row_timestamp = extract_timestamp_from_ulid(str(row["transcription_id"]))
        speaker = str(row["speaker"] or "Unknown Speaker")
        text = str(row["text_output"] or "").strip()
        if text:
            transcript_events.append((row_timestamp, speaker, text))

    event_index = 0
    event_count = len(transcript_events)

    for asked_at_timestamp, analysis_id in asked_events:
        while (
            event_index < event_count
            and transcript_events[event_index][0] < asked_at_timestamp
        ):
            window_rows.append(transcript_events[event_index])
            event_index += 1

        excerpt_start_time = asked_at_timestamp - TRANSCRIPT_EXCERPT_WINDOW
        while window_rows and window_rows[0][0] < excerpt_start_time:
            _ = window_rows.popleft()

        excerpts_by_analysis_id[analysis_id] = _format_excerpt_rows(
            [(speaker, text) for _, speaker, text in window_rows]
        )

    return excerpts_by_analysis_id


def build_report_data(project_id: str, db: PersistentDatabase) -> ReportData | None:
    typed_project_id = ProjectId.from_str(project_id)

    transcript_rows = get_all_transcriptions_for_project(db, typed_project_id)
    if not transcript_rows:
        return None

    anchor_index = _build_transcript_anchor_index(transcript_rows)
    analyses = get_all_ai_analyses(db, typed_project_id)

    transcript_excerpts_by_analysis_id = _precompute_transcript_excerpts_by_asked_at(
        transcript_rows, analyses
    )

    answered_by_category: dict[str, list[ReportQuestionEntry]] = defaultdict(list)
    unanswered_by_category: dict[str, list[ReportQuestionEntry]] = defaultdict(list)

    for analysis in analyses:
        normalized_category = normalize_question_category_code(analysis.category_code)

        answered_anchor: str | None = None
        answered_at_text: str | None = None
        transcript_excerpt: str | None = None

        if analysis.asked_at is not None:
            assert analysis.asked_at_transcript_id, (
                "asked_at_transcript_id should be set if asked_at is set"
            )
            asked_at_id = analysis.asked_at_transcript_id.lower()
            answered_anchor = anchor_index.chunk_to_section_anchor.get(asked_at_id)
            answered_at_text = _format_utc(analysis.asked_at)
            transcript_excerpt = transcript_excerpts_by_analysis_id.get(
                analysis.analysis_id
            )

        question_anchor = f"question-{analysis.ordinal}"

        entry = ReportQuestionEntry(
            analysis_id=analysis.analysis_id,
            ordinal=analysis.ordinal,
            text=analysis.text,
            category_code=normalized_category,
            span=analysis.span,
            question_anchor=question_anchor,
            context_anchor=_analysis_context_anchor(
                analysis, anchor_index.chunk_to_section_anchor
            ),
            answered_at_anchor=answered_anchor,
            answered_at_text=answered_at_text,
            is_starred=analysis.tag in ("starred", "starred_dismissed"),
            transcript_excerpt=transcript_excerpt,
        )

        if analysis.was_asked is True:
            answered_by_category[normalized_category].append(entry)
            if answered_anchor is not None and analysis.asked_at is not None:
                section = anchor_index.section_by_anchor.get(answered_anchor)
                if section is not None:
                    section.answered_question_refs.append(
                        (entry.ordinal, entry.question_anchor, analysis.asked_at)
                    )
        else:
            unanswered_by_category[normalized_category].append(entry)

    for section in anchor_index.sections:
        section.answered_question_refs.sort(key=lambda item: item[2])

    project_name = str(transcript_rows[0]["project_name"] or "Untitled Project")
    first_timestamp = extract_timestamp_from_ulid(
        str(transcript_rows[0]["transcription_id"])
    )

    return ReportData(
        project_name=project_name,
        start_time=first_timestamp,
        total_duration=_compute_total_duration(transcript_rows),
        answered_by_category=dict(answered_by_category),
        unanswered_by_category=dict(unanswered_by_category),
        transcript_sections=anchor_index.sections,
    )


def serialize_report_data(
    report_data: ReportData,
    project_id: str,
    incident_id: str,
    exported_at: datetime,
) -> dict[str, object]:
    """Serialize ReportData to a JSON-safe dict for Firestore / AI model consumption."""

    def _iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()

    def _serialize_question(entry: ReportQuestionEntry) -> dict[str, object]:
        q: dict[str, object] = {
            "ordinal": entry.ordinal,
            "category_code": entry.category_code,
            "category_label": QUESTION_CATEGORY_LABELS.get(entry.category_code, "Unknown"),
            "text": entry.text,
            "context_span": entry.span,
            "is_starred": entry.is_starred,
        }
        if entry.answered_at_text is not None:
            q["answered_at"] = entry.answered_at_text
        if entry.transcript_excerpt is not None:
            q["transcript_excerpt"] = entry.transcript_excerpt
        return q

    answered: list[dict[str, object]] = []
    for code in QUESTION_CATEGORY_ORDER:
        for entry in report_data.answered_by_category.get(code, []):
            answered.append(_serialize_question(entry))

    unanswered: list[dict[str, object]] = []
    for code in QUESTION_CATEGORY_ORDER:
        for entry in report_data.unanswered_by_category.get(code, []):
            unanswered.append(_serialize_question(entry))

    transcript = [
        {
            "speaker": section.speaker,
            "text": section.text,
            "started_at": _iso(section.started_at),
            "ended_at": _iso(section.ended_at),
        }
        for section in report_data.transcript_sections
    ]

    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "project_name": report_data.project_name,
        "incident_id": incident_id,
        "exported_at": _iso(exported_at),
        "interview": {
            "start_time": _iso(report_data.start_time),
            "total_duration_seconds": int(report_data.total_duration.total_seconds()),
        },
        "transcript": transcript,
        "questions": {
            "answered": answered,
            "unanswered": unanswered,
        },
    }


def _render_question_sections(
    story: list[Flowable],
    title: str,
    grouped_questions: dict[str, list[ReportQuestionEntry]],
    normal_style: ParagraphStyle,
    heading_style: ParagraphStyle,
    category_style: ParagraphStyle,
    question_style: ParagraphStyle,
    excerpt_style: ParagraphStyle,
) -> None:
    story.append(Paragraph(escape(title), heading_style))
    story.append(Spacer(1, 0.15 * inch))

    ordered_groups = _ordered_category_items(grouped_questions)
    if len(ordered_groups) == 0:
        story.append(Paragraph("No questions available.", normal_style))
        return

    for category_code, entries in ordered_groups:
        category_label = QUESTION_CATEGORY_LABELS.get(category_code, "Unknown")
        story.append(
            Paragraph(
                f'<font color="#2E5090"><b>{escape(category_code)}.</b> {escape(category_label)}</font>',
                category_style,
            )
        )
        story.append(Spacer(1, 0.12 * inch))

        for entry in entries:
            star_icon = (
                '<font color="#c98a00"><b>&#9733;</b></font>'
                if entry.is_starred
                else ""
            )
            question_label = (
                f"Q{entry.ordinal}. {star_icon}"
                if entry.is_starred
                else f"Q{entry.ordinal}."
            )
            story.append(
                Paragraph(
                    f'<a name="{entry.question_anchor}"/><font color="#1a472a"><b>{question_label}</b></font> {escape(entry.text)}',
                    question_style,
                )
            )

            if entry.span:
                escaped_span = escape(entry.span)
                if entry.context_anchor:
                    story.append(
                        Paragraph(
                            f'<font color="#555555"><i>Context:</i></font> <a href="#{entry.context_anchor}" color="blue"><u>"{escaped_span}"</u></a>',
                            question_style,
                        )
                    )
                else:
                    story.append(
                        Paragraph(
                            f'<font color="#555555"><i>Context:</i> "{escaped_span}"</font>',
                            question_style,
                        )
                    )

            if entry.answered_at_text is not None:
                if entry.answered_at_anchor:
                    story.append(
                        Paragraph(
                            f'<font color="#555555"><i>Answered At:</i></font> <a href="#{entry.answered_at_anchor}" color="blue"><u>{escape(entry.answered_at_text)}</u></a>',
                            question_style,
                        )
                    )
                else:
                    story.append(
                        Paragraph(
                            f'<font color="#555555"><i>Answered At:</i> {escape(entry.answered_at_text)}</font>',
                            question_style,
                        )
                    )

            if entry.transcript_excerpt:
                formatted_excerpt = (
                    '<font color="#555555"><b>[ . . . ]</b></font><br/>'
                    + escape(entry.transcript_excerpt).replace("\n", "<br/>")
                )
                excerpt_label = (
                    f'<a href="#{entry.answered_at_anchor}" color="#666666"><u>Transcript Excerpt (Last {_format_excerpt_window(TRANSCRIPT_EXCERPT_WINDOW)})</u></a>'
                    if entry.answered_at_anchor
                    else f"Transcript Excerpt (Last {_format_excerpt_window(TRANSCRIPT_EXCERPT_WINDOW)})"
                )
                story.append(
                    Paragraph(
                        f'<font color="#666666"><i>{excerpt_label}:</i></font><br/>{formatted_excerpt}',
                        excerpt_style,
                    )
                )

            story.append(Spacer(1, 0.12 * inch))

        story.append(Spacer(1, 0.08 * inch))


def generate_report_pdf(project_id: str, db: PersistentDatabase) -> bytes | None:
    report_data = build_report_data(project_id, db)
    if report_data is None:
        return None

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Interview Report - {report_data.project_name}",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = cast(ParagraphStyle, styles["Title"])
    title_style.textColor = colors.HexColor("#1a472a")
    title_style.fontSize = 36
    title_style.leading = 42

    heading_style = cast(ParagraphStyle, styles["Heading2"])
    heading_style.textColor = colors.HexColor("#2E5090")
    heading_style.fontSize = 18
    heading_style.spaceAfter = 6

    normal_style = cast(ParagraphStyle, styles["BodyText"])
    normal_style.fontSize = 11

    # Custom styles for categories and questions
    category_style = ParagraphStyle(
        "CategoryStyle",
        parent=normal_style,
        fontSize=13,
        textColor=colors.HexColor("#2E5090"),
        spaceAfter=8,
        spaceBefore=4,
    )

    question_style = ParagraphStyle(
        "QuestionStyle",
        parent=normal_style,
        fontSize=11,
        leftIndent=20,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=normal_style,
        fontSize=13,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6,
    )
    excerpt_style = ParagraphStyle(
        "ExcerptStyle",
        parent=normal_style,
        fontSize=10,
        leading=12,
        leftIndent=36,
        rightIndent=12,
        textColor=colors.HexColor("#666666"),
        spaceBefore=6,
        spaceAfter=4,
    )
    gap_separator_style = ParagraphStyle(
        "GapSeparatorStyle",
        parent=normal_style,
        fontSize=10,
        textColor=colors.HexColor("#777777"),
        alignment=1,
        spaceBefore=6,
        spaceAfter=6,
    )

    story: list[Flowable] = []

    # Cover page
    story.append(Spacer(1, 1.5 * inch))
    story.append(
        Paragraph('<font color="#1a472a"><b>Interview Report</b></font>', title_style)
    )
    story.append(Spacer(1, 0.1 * inch))
    story.append(
        Paragraph(
            f'<font color="#2E5090" size="24"><b>Project: {escape(report_data.project_name)}</b></font>',
            ParagraphStyle(
                "ProjectTitle",
                parent=title_style,
                fontSize=24,
                textColor=colors.HexColor("#2E5090"),
            ),
        )
    )
    story.append(Spacer(1, 0.5 * inch))
    story.append(
        Paragraph(
            f'<font color="#555555"><b>Interview Start:</b> {_format_utc(report_data.start_time)}</font>',
            subtitle_style,
        )
    )
    story.append(
        Paragraph(
            f'<font color="#555555"><b>Total Interview Length:</b> {_format_duration_hms(report_data.total_duration)}</font>',
            subtitle_style,
        )
    )
    story.append(PageBreak())

    # Answered questions
    _render_question_sections(
        story,
        "Answered AI-Questions (Categorized)",
        report_data.answered_by_category,
        normal_style,
        heading_style,
        category_style,
        question_style,
        excerpt_style,
    )
    story.append(PageBreak())

    # Transcript
    story.append(Paragraph("Transcript", heading_style))
    story.append(Spacer(1, 0.15 * inch))

    previous_ended_at: datetime | None = None
    for section in report_data.transcript_sections:
        if previous_ended_at is not None:
            time_gap = section.started_at - previous_ended_at
            if time_gap > TRANSCRIPT_ENTRY_GAP_SEPARATOR_THRESHOLD:
                story.append(
                    Paragraph(
                        f'<font color="#777777"><i>[ . . . {_format_gap_duration(time_gap)} passed . . . ]</i></font>',
                        gap_separator_style,
                    )
                )
                story.append(Spacer(1, 0.06 * inch))

        speaker = section.speaker if section.speaker else "Unknown Speaker"
        transcript_heading = f"[{_format_utc(section.started_at)}] {speaker}"
        story.append(
            Paragraph(
                f'<a name="{section.anchor}"/><font color="#2E5090"><b>{escape(transcript_heading)}</b></font>',
                normal_style,
            )
        )
        story.append(
            Paragraph(
                escape(section.text if section.text else "(No transcript text)"),
                normal_style,
            )
        )

        if section.answered_question_refs:
            grouped_answered_refs: list[
                tuple[datetime, datetime, list[tuple[int, str]]]
            ] = []
            group_first_at: datetime | None = None
            group_last_at: datetime | None = None
            group_links: list[tuple[int, str]] = []

            for ordinal, question_anchor, answered_at in section.answered_question_refs:
                if group_first_at is None or group_last_at is None:
                    group_first_at = answered_at
                    group_last_at = answered_at
                    group_links = [(ordinal, question_anchor)]
                    continue

                if answered_at - group_last_at <= ANSWERED_EVENT_TIMESTAMP_CUTOFF:
                    group_last_at = answered_at
                    group_links.append((ordinal, question_anchor))
                    continue

                grouped_answered_refs.append(
                    (group_first_at, group_last_at, [*group_links])
                )
                group_first_at = answered_at
                group_last_at = answered_at
                group_links = [(ordinal, question_anchor)]

            if group_first_at is not None and group_last_at is not None:
                grouped_answered_refs.append(
                    (group_first_at, group_last_at, [*group_links])
                )

            last_rendered_timestamp = section.ended_at
            for group_first_at, group_last_at, grouped_links in grouped_answered_refs:
                group_gap = group_first_at - last_rendered_timestamp
                if group_gap > TRANSCRIPT_ENTRY_GAP_SEPARATOR_THRESHOLD:
                    story.append(
                        Paragraph(
                            f'<font color="#777777"><i>[ . . . {_format_gap_duration(group_gap)} passed . . . ]</i></font>',
                            gap_separator_style,
                        )
                    )
                    story.append(Spacer(1, 0.06 * inch))

                if group_gap > ANSWERED_EVENT_TIMESTAMP_CUTOFF:
                    story.append(
                        Paragraph(
                            f'<font color="#2E5090"><b>[{_format_utc(group_first_at)}]</b></font>',
                            normal_style,
                        )
                    )

                grouped_links_text = ", ".join(
                    [
                        f'<a href="#{question_anchor}" color="blue"><u>Q{ordinal}</u></a>'
                        for ordinal, question_anchor in grouped_links
                    ]
                )

                story.append(
                    Paragraph(
                        f'<font color="#555555"><i>Answered Here:</i></font> {grouped_links_text}',
                        normal_style,
                    )
                )
                last_rendered_timestamp = group_last_at

        story.append(Spacer(1, 0.1 * inch))
        previous_ended_at = section.ended_at

    story.append(PageBreak())

    # Unanswered questions
    _render_question_sections(
        story,
        "Unanswered AI-Questions",
        report_data.unanswered_by_category,
        normal_style,
        heading_style,
        category_style,
        question_style,
        excerpt_style,
    )

    document.build(story)
    return buffer.getvalue()
