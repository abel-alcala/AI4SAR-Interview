import azure.cognitiveservices.speech as speechsdk  # pyright: ignore[reportMissingTypeStubs]

from interview_helper.audio_stream_handler.transcription.common import accept_transcript
from interview_helper.audio_stream_handler.types import AudioChunk
from interview_helper.context_manager.resource_keys import (
    AZURE_AUDIO_FORMAT,
    AZURE_STREAM,
    AZURE_TRANSCRIBER,
    WEBSOCKET,
    ANYIO_BLOCKING_PORTAL,
)
from interview_helper.context_manager.session_context_manager import SessionContext

import numpy as np
import logging
import anyio.to_thread

logger = logging.getLogger(__name__)

# pyright: reportUnknownVariableType=none


async def setup_and_get_azure_transcriber(
    ctx: SessionContext, first_chunk_rate_hz: int
):
    transcriber = await ctx.get(AZURE_TRANSCRIBER)
    if transcriber is not None:
        return transcriber

    # --- Speech config ---
    speech_key = ctx.get_settings().azure_speech_key
    speech_region = ctx.get_settings().azure_speech_region
    if not speech_key or not speech_region:
        raise RuntimeError("Missing AZURE_SPEECH_KEY / AZURE_SPEECH_REGION in settings")

    speech_config = speechsdk.SpeechConfig(
        subscription=speech_key.get_secret_value(), region=speech_region
    )
    speech_config.speech_recognition_language = "en-US"

    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults, "true"
    )

    # --- Audio format + stream ---
    # Use the input sample rate of your chunks; Azure handles common rates (16k/24k/44.1k/48k).
    fmt = speechsdk.audio.AudioStreamFormat(
        samples_per_second=int(first_chunk_rate_hz), bits_per_sample=16, channels=1
    )
    stream = speechsdk.audio.PushAudioInputStream(fmt)
    audio_input = speechsdk.AudioConfig(stream=stream)

    # --- Transcriber (does diarization) ---
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config, audio_config=audio_input
    )

    # ---- Event handlers ----
    ws = await ctx.get_or_wait(WEBSOCKET)

    # We will need to call accept_transcript from azure's thread.
    # So we use anyio's blocking portal to hop back to our event loop.
    portal = await ctx.get(ANYIO_BLOCKING_PORTAL)
    assert portal is not None, "No ANYIO_BLOCKING_PORTAL in context!"

    def _publish_transcript_part(text: str, speaker_id: str | None):
        try:
            portal.call(accept_transcript, ctx, text, speaker_id, ws)
        except RuntimeError as e:
            # Portal has been closed (connection ended), silently ignore
            if "not running" in str(e).lower():
                logger.debug(f"Portal closed, skipping transcript: {text[:50]}...")
            else:
                logger.error(f"Error sending transcription: {e}")
        except Exception as e:
            logger.error(f"Error sending transcription: {e}")

    def on_transcribed(evt: speechsdk.transcription.ConversationTranscriptionEventArgs):
        print(f"Transcribed: {evt.result.text}")
        if (
            evt.result.reason == speechsdk.ResultReason.RecognizedSpeech
            and evt.result.text
        ):
            print(f"Emitting recognized speech: {evt.result.text}")
            _publish_transcript_part(
                evt.result.text, getattr(evt.result, "speaker_id", None)
            )

    transcriber.transcribed.connect(on_transcribed)  # pyright: ignore[reportUnknownMemberType]

    # Start the pipeline + wait for start in seperate thread to not block event loop
    _ = await anyio.to_thread.run_sync(transcriber.start_transcribing_async().get)

    # Stash for reuse
    await ctx.register(AZURE_TRANSCRIBER, transcriber)
    await ctx.register(AZURE_STREAM, stream)
    await ctx.register(AZURE_AUDIO_FORMAT, fmt)
    return transcriber


async def azure_transcribe_audio_consumer(ctx: SessionContext, audio_chunk: AudioChunk):
    """
    Same signature & behavior as your Vosk consumer:
    - Consumes AudioChunk(data: list[np.ndarray[int16 or float]], framerate: int, number_of_channels: int)
    - Pushes bytes to Azure
    - Emits finalized lines via accept_transcript(ctx, text, ws)
    """
    # Create (or reuse) the Azure transcriber + stream
    _ = await setup_and_get_azure_transcriber(
        ctx, first_chunk_rate_hz=audio_chunk.framerate
    )
    stream = await ctx.get(AZURE_STREAM)
    assert stream, f"stream in {ctx.session_id} is not initialized!"

    # For each ndarray in .data, convert to mono int16 little-endian and push
    for chunk in audio_chunk.data:
        # Ensure contiguous mono int16
        buf = (  # pyright: ignore[reportAny]
            chunk.reshape(-1, audio_chunk.number_of_channels)  # pyright: ignore[reportAny]
            .mean(axis=1)
            .astype(np.int16)
            .tobytes()
        )
        stream.write(buf)  # pyright: ignore[reportAny]


async def azure_transcribe_stop(ctx: SessionContext):
    """
    Call this when you're done with the stream (e.g., end of call/meeting).
    """
    transcriber = await ctx.get(AZURE_TRANSCRIBER)
    stream = await ctx.get(AZURE_STREAM)

    if stream:
        stream.close()
        await ctx.unregister(AZURE_STREAM)

    if transcriber:
        _ = await anyio.to_thread.run_sync(transcriber.stop_transcribing_async().get)
        await ctx.unregister(AZURE_TRANSCRIBER)

    # Also unregister the audio format if it exists
    audio_format = await ctx.get(AZURE_AUDIO_FORMAT)
    if audio_format:
        await ctx.unregister(AZURE_AUDIO_FORMAT)
