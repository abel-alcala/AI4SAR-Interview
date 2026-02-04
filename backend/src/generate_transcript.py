"""Generate formatted transcript for a project."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import cast, Any
import ulid

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_CENTER
from dateutil.relativedelta import relativedelta

attrs = ["years", "months", "days", "hours", "minutes", "seconds"]


def human_readable(delta: relativedelta) -> list[str]:
    return [
        "%d %s"
        % (getattr(delta, attr), attr if getattr(delta, attr) > 1 else attr[:-1])
        for attr in attrs
        if getattr(delta, attr)
    ]


def extract_timestamp_from_ulid(ulid_str: str) -> datetime:
    """Extract timestamp from a ULID string."""
    ulid_obj: ulid.ULID = ulid.ULID.from_str(ulid_str.upper())  # pyright: ignore[reportAny]
    timestamp_float = ulid_obj.timestamp
    return datetime.fromtimestamp(timestamp_float)


def generate_pdf_transcript(
    transcript_data: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    output_file: str,
) -> None:
    """Generate a pretty PDF transcript."""
    pdf_file = (
        output_file.replace(".txt", ".pdf")
        if output_file.endswith(".txt")
        else f"{output_file}.pdf"
    )
    doc = SimpleDocTemplate(
        pdf_file, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch
    )

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=12,
        alignment=TA_CENTER,
    )

    header_style = ParagraphStyle(
        "CustomHeader",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#666666"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )

    speaker_style = ParagraphStyle(
        "Speaker",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#1976d2"),
        fontName="Helvetica-Bold",
        spaceAfter=4,
        leftIndent=0,
    )

    text_style = ParagraphStyle(
        "TranscriptText",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.black,
        leftIndent=20,
        spaceAfter=12,
        leading=14,
    )

    ai_header_style = ParagraphStyle(
        "AIHeader",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#f57c00"),
        fontName="Helvetica-Bold",
        spaceAfter=4,
        leftIndent=0,
    )

    ai_text_style = ParagraphStyle(
        "AIText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#424242"),
        leftIndent=20,
        rightIndent=20,
        spaceAfter=6,
        leading=12,
    )

    ai_span_style = ParagraphStyle(
        "AISpan",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#616161"),
        fontName="Helvetica-Oblique",
        leftIndent=20,
        rightIndent=20,
        spaceAfter=10,
    )

    # Build story
    story: list[Flowable] = []

    # Title page
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("TRANSCRIPT", title_style))
    story.append(Paragraph(f"{transcript_data['project_name']}", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(f"Project ID: {transcript_data['project_id']}", header_style)
    )
    story.append(
        Paragraph(f"Total Entries: {transcript_data['total_entries']}", header_style)
    )
    story.append(
        Paragraph(f"Total Time: {transcript_data['total_length']}", header_style)
    )
    story.append(Spacer(1, 0.5 * inch))

    # Add a separator line
    line_table = Table([[""]], colWidths=[6.5 * inch])
    line_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor("#1a237e")),
            ]
        )
    )
    story.append(line_table)
    story.append(Spacer(1, 0.3 * inch))

    # Content
    for entry in transcript_data["entries"]:  # pyright: ignore[reportAny]
        if entry["type"] == "speaker":
            # Speaker and timestamp
            speaker_para = Paragraph(
                f"[{entry['timestamp']}] <b>{entry['speaker']}</b>:", speaker_style
            )
            story.append(speaker_para)

            # Text
            text_para = Paragraph(entry["text"], text_style)  # pyright: ignore[reportAny]
            story.append(text_para)

        elif entry["type"] == "ai_analysis":
            # AI Analysis section with light background
            story.append(Spacer(1, 6))

            # AI header
            ai_header = Paragraph("🤖 AI ANALYSIS", ai_header_style)
            story.append(ai_header)

            # Highlighted text
            ai_text = Paragraph(f"<b>{entry['text']}</b>", ai_text_style)
            story.append(ai_text)

            # Span if available
            if entry.get("span"):  # pyright: ignore[reportAny]
                ai_span = Paragraph(f'"{entry["span"]}"', ai_span_style)
                story.append(ai_span)

            story.append(Spacer(1, 6))

    # Build PDF
    doc.build(story)
    print(f"PDF transcript saved to: {pdf_file}")


def generate_transcript(
    project_id: str,
    db_path: str = "data/database.sqlite3",
    output_file: str | None = None,
) -> str:
    """
    Generate a formatted transcript for a given project.

    Args:
        project_id: The project ID to generate transcript for
        db_path: Path to the SQLite database
        output_file: Optional path to save the transcript file

    Returns:
        The formatted transcript as a string
    """

    output_file = output_file or "report"
    output_file = output_file if output_file.endswith(".txt") else f"{output_file}.txt"
    # Connect to the database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch all transcriptions for the project, ordered by transcription_id (ULID)
    # Since ULID is chronologically sortable, sorting by transcription_id gives us time order
    query = """
        SELECT 
            transcription_id,
            speaker,
            text_output,
            created_at,
            session_id,
            user_id
        FROM transcriptions
        WHERE project_id = ?
        ORDER BY transcription_id ASC
    """

    _ = cursor.execute(query, (project_id,))
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return f"No transcriptions found for project: {project_id}"

    # Get project name
    _ = cursor.execute("SELECT name FROM project WHERE project_id = ?", (project_id,))
    project_row = cursor.fetchone()  # pyright: ignore[reportAny]
    project_name: str = (
        cast(str, project_row["name"])
        if project_row and project_row["name"]
        else "Untitled Project"
    )

    # Fetch AI analyses for the project
    ai_analyses_query = """
        SELECT 
            analysis_id,
            text,
            span,
            transcript_context_start,
            transcript_context_end,
            summary
        FROM ai_analyses
        WHERE project_id = ?
        ORDER BY transcript_context_end ASC
    """
    _ = cursor.execute(ai_analyses_query, (project_id,))
    ai_analyses = cursor.fetchall()

    # Build a map of transcription_id -> list of analyses that end at that transcription
    analyses_by_end: dict[str, list[dict[str, str]]] = {}
    for analysis in ai_analyses:  # pyright: ignore[reportAny]
        end_id = cast(str, analysis["transcript_context_end"])
        if end_id not in analyses_by_end:
            analyses_by_end[end_id] = []
        analyses_by_end[end_id].append(
            {
                "analysis_id": cast(str, analysis["analysis_id"]),
                "text": cast(str, analysis["text"]),
                "span": cast(str, analysis["span"]) if analysis["span"] else "",
                "summary": cast(str, analysis["summary"]),
                "start": cast(str, analysis["transcript_context_start"]),
                "end": end_id,
            }
        )

    conn.close()

    # Build the transcript
    transcript_lines: list[str] = []
    transcript_lines.append("=" * 80)
    transcript_lines.append(f"TRANSCRIPT - {project_name}")
    transcript_lines.append(f"Project ID: {project_id}")
    transcript_lines.append(f"Total Entries: {len(rows)}")
    transcript_lines.append("=" * 80)
    transcript_lines.append("")

    # For PDF generation
    transcript_entries: list[dict[str, Any]] = []  # pyright: ignore[reportExplicitAny]

    # Group consecutive utterances by the same speaker
    current_speaker: str | None = None
    current_texts: list[str] = []
    current_timestamp: datetime | None = None

    for row in rows:  # pyright: ignore[reportAny]
        transcription_id = cast(str, row["transcription_id"])
        speaker = row["speaker"] or "Unknown Speaker"
        text = row["text_output"] or ""

        # Extract timestamp from ULID
        timestamp = extract_timestamp_from_ulid(transcription_id)

        # If speaker changed, write out the previous group
        if (
            speaker != current_speaker
            and current_speaker is not None
            and current_timestamp is not None
        ):
            timestamp_str = current_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            combined_text = " ".join(current_texts)
            transcript_lines.append(f"[{timestamp_str}] {current_speaker}:")
            transcript_lines.append(f"  {combined_text}")
            transcript_lines.append("")

            # Add to PDF entries
            transcript_entries.append(
                {
                    "type": "speaker",
                    "timestamp": timestamp_str,
                    "speaker": current_speaker,
                    "text": combined_text,
                }
            )

            current_texts = []
            current_timestamp = None

        # Start or continue current speaker's text
        current_speaker = speaker
        if not current_timestamp:
            current_timestamp = timestamp
        current_texts.append(text)

        # Check if there are any AI analyses that end at this transcription
        if transcription_id in analyses_by_end:
            # First, write out the current speaker group if any
            if current_speaker and current_texts:
                timestamp_str = current_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                combined_text = " ".join(current_texts)
                transcript_lines.append(f"[{timestamp_str}] {current_speaker}:")
                transcript_lines.append(f"  {combined_text}")
                transcript_lines.append("")

                # Add to PDF entries
                transcript_entries.append(
                    {
                        "type": "speaker",
                        "timestamp": timestamp_str,
                        "speaker": current_speaker,
                        "text": combined_text,
                    }
                )

                current_texts = []
                current_timestamp = None

            # Now add the AI analyses
            for analysis in analyses_by_end[transcription_id]:
                start_ts = extract_timestamp_from_ulid(analysis["start"])
                end_ts = extract_timestamp_from_ulid(analysis["end"])
                start_str = start_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                end_str = end_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                transcript_lines.append("[AI]")
                transcript_lines.append(f"  - {analysis['text']}")
                transcript_lines.append(f'    "{analysis["span"]}"\n')

                # Add to PDF entries
                transcript_entries.append(
                    {
                        "type": "ai_analysis",
                        "text": analysis["text"],
                        "span": analysis["span"],
                        "start_time": start_str,
                        "end_time": end_str,
                    }
                )

    # Write out the last group
    if current_speaker and current_texts and current_timestamp is not None:
        timestamp_str = current_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        combined_text = " ".join(current_texts)
        transcript_lines.append(f"[{timestamp_str}] {current_speaker}:")
        transcript_lines.append(f"  {combined_text}")
        transcript_lines.append("")

        # Add to PDF entries
        transcript_entries.append(
            {
                "type": "speaker",
                "timestamp": timestamp_str,
                "speaker": current_speaker,
                "text": combined_text,
            }
        )

    transcript = "\n".join(transcript_lines)

    # Save to file if output path provided
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _ = output_path.write_text(transcript, encoding="utf-8")
        print(f"Transcript saved to: {output_file}")

        total_length_duration = extract_timestamp_from_ulid(
            rows[-1]["transcription_id"]  # pyright: ignore[reportAny]
        ) - extract_timestamp_from_ulid(rows[0]["transcription_id"])  # pyright: ignore[reportAny]
        humanh_readable_length = " ".join(
            human_readable(
                relativedelta(seconds=int(total_length_duration.total_seconds()))
            )
        )

        # Generate PDF
        pdf_data: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
            "project_name": project_name,
            "project_id": project_id,
            "total_entries": len(rows),
            "entries": transcript_entries,
            "total_length": humanh_readable_length,
        }
        generate_pdf_transcript(pdf_data, output_file)

    return transcript


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate transcript for a project")
    _ = parser.add_argument("project_id", help="Project ID to generate transcript for")
    _ = parser.add_argument(
        "--db",
        default="data/database.sqlite3",
        help="Path to SQLite database (default: data/database.sqlite3)",
    )
    _ = parser.add_argument(
        "--output",
        "-o",
        help="Output file path (if not specified, prints to stdout)",
    )

    args = parser.parse_args()

    project_id_arg = cast(str, args.project_id)
    db_arg = cast(str, args.db)
    output_arg = cast(str | None, args.output)
    transcript = generate_transcript(project_id_arg, db_arg, output_arg)

    if not output_arg:
        print(transcript)


if __name__ == "__main__":
    main()
