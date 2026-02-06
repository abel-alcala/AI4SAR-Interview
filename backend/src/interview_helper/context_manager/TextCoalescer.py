from interview_helper.context_manager.types import TranscriptId
import anyio
from typing import Callable, Awaitable


class TextCoalescer:
    """
    Collects text chunks and calls `handler(batch_text)` every N words or T seconds.
    """

    def __init__(
        self,
        word_threshold: int = 100,
        seconds: float = 10.0,
        max_buffer_size: int = 100,
    ):
        self.word_threshold = word_threshold
        self.seconds = seconds
        self._send, self._recv = anyio.create_memory_object_stream[
            tuple[str, TranscriptId]
        ](max_buffer_size)

    # Producer API – push text as it arrives (ASR)
    async def push(self, text: str, transcript_id: TranscriptId) -> None:
        await self._send.send((text, transcript_id))

    # Optional: call this when you know you're done producing (e.g., session end)
    async def close(self) -> None:
        await self._send.aclose()

    # Consumer – run inside a TaskGroup; calls handler whenever a batch is ready
    async def run(self, handler: Callable[[TranscriptId], Awaitable[None]]) -> None:
        async with self._recv:
            buffer: list[str] = []
            word_count = 0
            last_transcript_id: TranscriptId | None = None

            while True:
                # Wait up to `seconds` for enough words to arrive
                with anyio.move_on_after(self.seconds) as timeout:
                    while word_count < self.word_threshold:
                        try:
                            (
                                text,
                                transcript_id,
                            ) = (
                                await self._recv.receive()
                            )  # cancelled when timeout fires
                            last_transcript_id = transcript_id
                            buffer.append(text)
                            word_count += len(text.split())
                        except anyio.EndOfStream:
                            # Stream closed - normal shutdown
                            # Flush any remaining buffer
                            if buffer and last_transcript_id is not None:
                                await handler(last_transcript_id)
                            return

                # Timeout hit AND no data? keep waiting
                if not buffer:
                    # move_on_after fired, but nothing arrived during the window
                    # or the stream is still open and idle.
                    if timeout.cancelled_caught:
                        continue
                    else:
                        # Stream closed cleanly with nothing buffered: exit.
                        break

                # There will always be at least one transcript that comes in, since the buffer isn't empty
                assert last_transcript_id is not None

                # Flush because we hit threshold or time
                buffer.clear()
                word_count = 0
                await handler(last_transcript_id)

            # Final flush on stream close (if anything remains)
            if buffer and last_transcript_id is not None:
                await handler(last_transcript_id)
