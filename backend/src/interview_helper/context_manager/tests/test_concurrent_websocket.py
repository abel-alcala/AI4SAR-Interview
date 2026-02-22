import pytest
from anyio import wait_all_tasks_blocked

from interview_helper.tests.shared import FakeWebSocket

from interview_helper.context_manager.concurrent_websocket import ConcurrentWebSocket
from interview_helper.context_manager.messages import (
    Envelope,
    TranscriptChunkToSend,
    TranscriptionMessage,
)

pytestmark = pytest.mark.anyio


async def test_send_and_receive_message():
    # Setup
    ws = FakeWebSocket()

    await ws.accept()

    cws = ConcurrentWebSocket(already_accepted_ws=ws)
    async with cws:
        # Try to start it again to show no issues
        await cws.start()

        msg = TranscriptionMessage(
            chunk=TranscriptChunkToSend(
                text="Hello, world!", speaker="Speaker 1", transcription_id="123"
            )
        )
        await cws.send_message(msg)
        await wait_all_tasks_blocked()  # Let writer run

        assert len(ws.sent_messages) == 1
        assert Envelope.model_validate_json(ws.sent_messages[0]).message == msg

        ws.enqueue(Envelope(message=msg).model_dump_json())
        recv_msg = await cws.receive_message()

        assert recv_msg == msg

    await wait_all_tasks_blocked()  # Let writer close

    # Check that closing it again doesn't break anything
    await cws.aclose()
