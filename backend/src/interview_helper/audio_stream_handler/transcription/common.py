from interview_helper.context_manager.database import (
    add_transcription,
    get_session_sequence_number,
)
from interview_helper.context_manager.messages import (
    TranscriptChunkToSend,
    TranscriptionMessage,
)
from interview_helper.context_manager.session_context_manager import SessionContext
from interview_helper.context_manager.types import TranscriptId


async def accept_transcript(ctx: SessionContext, text: str, speaker: str | None):
    # Send transcription data over websocket

    # Make speaker ID unique per-session
    # Get session number for this project

    ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    if speaker == "Unknown" or speaker == "" or speaker is None:
        speaker = "Unknown"
    else:
        session_sequence_number = get_session_sequence_number(
            ctx.manager.db, ctx.project_id, ctx.session_id
        )

        # Get session sequence letter(s) (more than 26 sessions, makes AA, AB, etc.)
        letters = ""
        n = session_sequence_number - 1  # zero indexed
        while n >= 0:
            letters = ALPHA[n % 26] + letters
            n = n // 26 - 1

        # Decompose session_id
        name = speaker.split("-")[0]
        number = speaker.split("-")[1] if "-" in speaker else ""

        speaker = f"{name}-{letters}{number}" if number else f"{name}_{letters}"
    # Add to DB
    added_transcription_id = TranscriptId.from_str(
        add_transcription(
            ctx.manager.db,
            user_id=ctx.get_user_id(),
            session_id=ctx.session_id,
            project_id=ctx.project_id,
            text=text,
            speaker=speaker,
        )
    )

    # Broadcast to all sessions in this project
    await ctx.manager.broadcast_to_project(
        ctx.project_id,
        TranscriptionMessage(
            type="transcription",
            chunk=TranscriptChunkToSend(
                text=text,
                speaker=speaker,
                transcription_id=str(added_transcription_id),
            ),
        ),
    )

    # Ensure the session is aware of it.
    await ctx.accept_transcript(text, added_transcription_id)
