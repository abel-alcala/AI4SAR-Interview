from datetime import datetime
import sqlite3
from typing import cast
from .util import extract_timestamp_from_ulid


def generate_transcript(
    project_id: str,
    db_path: str,
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

    conn.close()

    # Build the transcript
    transcript_lines: list[str] = []
    transcript_lines.append("=" * 80)
    transcript_lines.append(f"TRANSCRIPT - {project_name}")
    transcript_lines.append(f"Project ID: {project_id}")
    transcript_lines.append(f"Total Entries: {len(rows)}")
    transcript_lines.append("=" * 80)
    transcript_lines.append("")

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

            current_texts = []
            current_timestamp = None

        # Start or continue current speaker's text
        current_speaker = speaker
        if not current_timestamp:
            current_timestamp = timestamp
        current_texts.append(text)

    # Write out the last group
    if current_speaker and current_texts and current_timestamp is not None:
        timestamp_str = current_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        combined_text = " ".join(current_texts)
        transcript_lines.append(f"[{timestamp_str}] {current_speaker}:")
        transcript_lines.append(f"  {combined_text}")
        transcript_lines.append("")

    transcript = "\n".join(transcript_lines)

    return transcript
