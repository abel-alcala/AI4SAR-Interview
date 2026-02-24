from datetime import datetime

from interview_helper.context_manager.database import (
    PersistentDatabase,
    get_all_transcriptions_for_project,
)
from interview_helper.context_manager.types import ProjectId
from .util import extract_timestamp_from_ulid


def generate_transcript(
    project_id: str,
    db: PersistentDatabase,
) -> str | None:
    """
    Generate a formatted transcript for a given project.

    Args:
        project_id: The project ID to generate transcript for
        db: The persistent database instance

    Returns:
        The formatted transcript as a string
    """

    # Fetch all transcriptions for the project with project details
    rows = get_all_transcriptions_for_project(db, ProjectId.from_str(project_id))

    if not rows:
        return None

    project_name = rows[0]["project_name"]

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

    for row in rows:
        transcription_id = row["transcription_id"]
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
