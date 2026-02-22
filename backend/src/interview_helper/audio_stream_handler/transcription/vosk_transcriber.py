from vosk import KaldiRecognizer, Model  # pyright: ignore[reportMissingTypeStubs]

from interview_helper.audio_stream_handler.transcription.common import accept_transcript
from interview_helper.audio_stream_handler.types import AudioChunk
from interview_helper.context_manager.session_context_manager import SessionContext

from interview_helper.context_manager.resource_keys import TRANSCRIBER_SESSION

import numpy as np
import json

# Vosk isn't typed properly
# pyright: reportAny=none,reportUnknownMemberType=none, reportUnknownArgumentType=none


async def vosk_close_transcriber(ctx: SessionContext):
    rec = await ctx.get(TRANSCRIBER_SESSION)

    if rec is not None:
        text = json.loads(rec.FinalResult())["text"]
        if text:
            await accept_transcript(ctx, text, None)
        # Unregister so a new recognizer can be created on reconnection
        await ctx.unregister(TRANSCRIBER_SESSION)


async def vosk_transcribe_audio_consumer(ctx: SessionContext, audio_chunk: AudioChunk):
    # Open the wave file once and keep it open across writes
    # so we can batch writes efficiently and finalize
    # the file size at the end.
    rec = await ctx.get(TRANSCRIBER_SESSION)

    if rec is None:
        model = Model(str(ctx.get_settings().vosk_model_path.absolute()))
        rec = KaldiRecognizer(model, audio_chunk.framerate)
        rec.SetWords(True)
        rec.SetPartialWords(True)
        await ctx.register(TRANSCRIBER_SESSION, rec)

    for chunk in audio_chunk.data:
        # Ensure dtype and contiguity
        buf = (
            chunk.reshape(-1, audio_chunk.number_of_channels)
            .mean(axis=1)
            .astype(np.int16)
            .tobytes()
        )

        if rec.AcceptWaveform(buf):
            # Finalized segment
            text = json.loads(rec.Result())["text"]
            if text:
                await accept_transcript(ctx, text, None)
