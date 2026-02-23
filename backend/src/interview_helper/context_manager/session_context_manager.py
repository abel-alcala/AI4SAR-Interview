from collections.abc import Sequence
from langchain_core.callbacks import BaseCallbackHandler
from interview_helper.context_manager.messages import (
    AIResultMessage,
    WebSocketMessage,
    RecordingStateMessage,
)
from interview_helper.context_manager.resource_keys import WEBSOCKET
from interview_helper.context_manager.types import AIResult, TranscriptId
from interview_helper.context_manager.types import AIJob
from interview_helper.context_manager.TextCoalescer import TextCoalescer
from interview_helper.security.tickets import TicketStore
from typing import Protocol, runtime_checkable
from collections import defaultdict
from dataclasses import dataclass
from ulid import ULID
from typing import cast, TypeVar, Callable
from collections.abc import Awaitable
import anyio
import anyio.abc
import sys

from interview_helper.config import Settings
from interview_helper.context_manager.types import (
    SessionId,
    ProjectId,
    UserId,
    ResourceKey,
    AnalysisId,
)
from interview_helper.audio_stream_handler.types import AudioChunk
from interview_helper.context_manager.database import (
    PersistentDatabase,
    add_ai_analysis,
    get_analyses_by_ids,
    get_all_transcripts_since_last_analysis,
    get_user_by_id,
)
from interview_helper.context_manager.span_locator import find_span_in_transcripts
import logging

T = TypeVar("T", covariant=True)
U = TypeVar("U", covariant=True)

type AsyncAudioConsumer = Callable[["SessionContext", "AudioChunk"], Awaitable[None]]
type AsyncAudioConsumerFinalize = Callable[["SessionContext"], Awaitable[None]]


@runtime_checkable
class AIAnalyzer(Protocol):
    def __init__(self, config: Settings, db: PersistentDatabase): ...
    async def analyze(
        self, job: AIJob, callbacks: Sequence[BaseCallbackHandler] | None = None
    ) -> AIResult | None: ...


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionContext:
    manager: "AppContextManager"
    session_id: SessionId
    project_id: ProjectId

    async def register(self, key: ResourceKey[T], value: T) -> None:
        """
        Registers the resource with the store

        Raises:
            Assertion Error: If resource registered before on this session.
        """

        return await self.manager.register(
            session_id=self.session_id, key=key, value=value
        )

    async def get(self, key: ResourceKey[T]) -> T | None:
        """
        Gets the resource associated with the key

        Raises:
            Assertion Error: If resource not registered already.
        """
        return await self.manager.get(session_id=self.session_id, key=key)

    async def get_or_wait(self, key: ResourceKey[T]):
        return await self.manager.get_or_wait(self.session_id, key)

    async def unregister(self, key: ResourceKey[T]) -> None:
        """
        Unregisters the resource from the store

        Raises:
            Assertion Error: If resource not registered.
        """
        return await self.manager.unregister(session_id=self.session_id, key=key)

    def get_settings(self) -> Settings:
        return self.manager.get_settings()

    def is_active(self) -> bool:
        return self.session_id in self.manager.active_sessions

    async def ingest_audio(self, audio_chunk: AudioChunk):
        await self.manager.ingest_audio(
            session_id=self.session_id,
            project_id=self.project_id,
            audio_chunk=audio_chunk,
        )

    async def teardown(self):
        await self.manager.teardown_session(self.session_id)

    async def accept_transcript(self, new_text: str, transcript_id: TranscriptId):
        await self.manager.accept_transcript(
            self.session_id, text=new_text, transcript_id=transcript_id
        )

    def get_user_id(self):
        return self.manager.session_data[self.session_id].user


# FIXME: Remove global project + user
GLOBAL_PROJECT = ProjectId(ULID(b"0" * 16))


class AppContextManager:
    """
    Centrally manages all data for the application per-session, per-project, and per-user.
    """

    @dataclass
    class SessionData:
        project: ProjectId
        user: UserId

    def __init__(
        self,
        audio_ingest_consumers: tuple[
            tuple[AsyncAudioConsumer, AsyncAudioConsumerFinalize], ...
        ],
        ai_processer: type[AIAnalyzer],
        settings: Settings | None = None,
    ):
        # We need to protect against race-conditions since our context might end up in an
        # inconsistent state between threads.
        self.lock = anyio.Lock()

        self.store: dict[tuple[ResourceKey[object], SessionId], object] = {}
        self.store_keys: dict[
            SessionId, list[tuple[ResourceKey[object], SessionId]]
        ] = defaultdict(list)
        self.waiting_events: dict[
            tuple[ResourceKey[object], SessionId], anyio.Event
        ] = defaultdict(anyio.Event)

        self.session_data: dict[SessionId, AppContextManager.SessionData] = {}
        self.active_sessions: set[SessionId] = set()

        self.session_task_group: dict[SessionId, anyio.abc.TaskGroup] = {}

        # Track active audio sessions
        self.active_audio_sessions: set[SessionId] = set()
        self.cleanup_waiting_event: dict[SessionId, anyio.Event] = defaultdict(
            anyio.Event
        )

        self.active_ai_analysis: dict[ProjectId, anyio.Lock] = defaultdict(anyio.Lock)

        # Track which session is recording for each project (session_id, user_name)
        self.recording_state: dict[ProjectId, tuple[SessionId, str]] = {}

        # Static for duration of this context, doesn't require lock.
        self.audio_ingest_consumers = audio_ingest_consumers
        self.settings = settings
        self.ticket_store = TicketStore()

        self.db = PersistentDatabase()

        self.ai_processor: None | AIAnalyzer = (
            ai_processer(settings, self.db) if settings else None
        )

        # Background Serivces (e.g., to fetch AI results)
        self._background_tg: anyio.abc.TaskGroup | None = None

        self._job_send: anyio.abc.ObjectSendStream[AIJob] | None = None
        self._job_recv: anyio.abc.ObjectReceiveStream[AIJob] | None = None
        self._workers_started = False
        self.text_coalescer: dict[SessionId, TextCoalescer] = {}

    async def new_session(
        self, user_id: UserId, project_id: ProjectId
    ) -> SessionContext:
        session_id = SessionId(ULID())

        async with self.lock:
            self.session_data[session_id] = AppContextManager.SessionData(
                project=project_id, user=user_id
            )

            self.session_task_group[
                session_id
            ] = await anyio.create_task_group().__aenter__()

            self.active_sessions.add(session_id)

            if self.ai_processor is not None:
                assert self.settings

                # Setup Infrastructure needed to ping the AI service every once in a while
                coalescer = TextCoalescer(
                    word_threshold=self.settings.process_transcript_every_word_count,
                    seconds=self.settings.process_transcript_every_secs,
                )

                self.text_coalescer[session_id] = coalescer

                async def handler(_transcript_id: TranscriptId) -> None:
                    await self._submit_ai_processing_job(AIJob(project_id=project_id))

                # Run the coalescer in the session’s TaskGroup you already maintain
                tg = self.session_task_group[session_id]
                tg.start_soon(coalescer.run, handler)

        return SessionContext(
            manager=self, session_id=session_id, project_id=project_id
        )

    def get_settings(self) -> Settings:
        # Initing settings causes Env lookups, we make sure that doesn't happen
        assert "pytest" not in sys.modules

        return cast(Settings, self.settings)

    async def register(
        self, session_id: SessionId, key: ResourceKey[T], value: T
    ) -> None:
        """
        Registers the resource with the store

        Raises:
            Assertion Error: If resource registered before on this session.
        """
        k = (key, session_id)

        async with self.lock:
            assert session_id in self.active_sessions, f"{session_id} is not active!"
            assert k not in self.store, (
                f"{key.name} already registered for SessionId({session_id})"
            )

            self.store[k] = value
            self.store_keys[session_id].append(k)

            if k in self.waiting_events:
                self.waiting_events[k].set()

    async def get(self, session_id: SessionId, key: ResourceKey[T]) -> T | None:
        """
        Gets the resource associated with the key

        Raises:
            Assertion Error: If resource not registered already.
        """

        async with self.lock:
            assert session_id in self.active_sessions, f"{session_id} is not active!"

            return cast(T, self.store.get((key, session_id), None))

    async def unregister(self, session_id: SessionId, key: ResourceKey[T]) -> None:
        """
        Unregisters the resource from the store

        Raises:
            Assertion Error: If resource not registered.
        """
        k = (key, session_id)

        async with self.lock:
            assert session_id in self.active_sessions, f"{session_id} is not active!"
            assert k in self.store, (
                f"{key.name} not registered for SessionId({session_id})"
            )

            del self.store[k]
            self.store_keys[session_id].remove(k)

            # Clean up waiting event if it exists
            if k in self.waiting_events:
                del self.waiting_events[k]

    async def get_or_wait(self, session_id: SessionId, key: ResourceKey[T]) -> T:
        async with self.lock:
            assert session_id in self.active_sessions, f"{session_id} is not active!"

            potential_value = cast(T | None, self.store.get((key, session_id), None))

            if potential_value is not None:
                return potential_value

            # Get event
            wait_for_value_event = self.waiting_events[(key, session_id)]

        # Wait for value outside of critical section
        await wait_for_value_event.wait()
        async with self.lock:
            return cast(T, self.store[(key, session_id)])

    async def set_active_audio_session(self, session_id: SessionId):
        # Get session data while holding the lock
        session_data = None
        async with self.lock:
            self.active_audio_sessions.add(session_id)
            session_data = self.session_data.get(session_id)

        # Update recording state outside the lock to avoid deadlock
        if session_data:
            # Get user name
            user = get_user_by_id(self.db, session_data.user)
            user_name = user.full_name if user else "Unknown User"

            # Update recording state
            await self.set_recording_state(
                session_data.project, session_id, user_name, True
            )

    async def clear_active_audio_session(self, session_id: SessionId):
        # Get session data and event while holding the lock
        session_data = None
        event = None

        async with self.lock:
            self.active_audio_sessions.remove(session_id)
            session_data = self.session_data.get(session_id)

            if session_id in self.cleanup_waiting_event:
                event = self.cleanup_waiting_event[session_id]

        # Update recording state outside the lock to avoid deadlock
        if session_data:
            # Get user name
            user = get_user_by_id(self.db, session_data.user)
            user_name = user.full_name if user else "Unknown User"

            # Clear recording state
            await self.set_recording_state(
                session_data.project, session_id, user_name, False
            )

        if event is not None:
            event.set()

    async def teardown_session(self, session_id: SessionId) -> None:
        """Teardown all resources for a websocket session"""

        # Wait for any finishing audio handlers
        event = None
        async with self.lock:
            if session_id in self.active_audio_sessions:
                event = self.cleanup_waiting_event[session_id]

        if event is not None:
            await event.wait()

        # Close the text coalescer if it exists
        if session_id in self.text_coalescer:
            await self.text_coalescer[session_id].close()
            del self.text_coalescer[session_id]

        async with self.lock:
            for k in self.store_keys[session_id]:
                del self.store[k]

                if k in self.waiting_events:
                    # Notify any waiting events that session is done
                    self.waiting_events[k].set()
                    del self.waiting_events[k]

            del self.store_keys[session_id]

            del self.session_data[session_id]

            self.active_sessions.remove(session_id)

            # Remove from active audio sessions and notify
            if session_id in self.active_audio_sessions:
                self.active_audio_sessions.remove(session_id)
                # Optionally notify any listeners here if needed

            task_group = self.session_task_group[session_id]

            del self.session_task_group[session_id]

        _ = await task_group.__aexit__(None, None, None)

    async def ingest_audio(
        self, session_id: SessionId, project_id: ProjectId, audio_chunk: AudioChunk
    ):
        ctx = SessionContext(self, session_id, project_id)
        for consumer, _ in self.audio_ingest_consumers:
            await consumer(ctx, audio_chunk)

    async def accept_transcript(
        self, session_id: SessionId, text: str, transcript_id: TranscriptId
    ):
        async with self.lock:
            assert session_id in self.active_sessions, f"{session_id} is not active!"

            await self.text_coalescer[session_id].push(
                text=text, transcript_id=transcript_id
            )

    async def broadcast_to_project(
        self, project_id: ProjectId, message: WebSocketMessage
    ):
        """
        Broadcast a message to all active sessions in a project
        """
        sessions_to_broadcast: list[SessionId] = []

        async with self.lock:
            for session_id, data in self.session_data.items():
                if data.project == project_id and session_id in self.active_sessions:
                    sessions_to_broadcast.append(session_id)

        # Send outside the lock to avoid blocking
        for session_id in sessions_to_broadcast:
            ws = await self.get(session_id, WEBSOCKET)
            logger.debug(
                f"Broadcasting message to session {session_id} in project {project_id}: {message}"
            )
            if ws:
                try:
                    logger.debug(f"Sending message to session {session_id}: {message}")
                    await ws.send_message(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to session {session_id}: {e}")

    async def set_recording_state(
        self,
        project_id: ProjectId,
        session_id: SessionId,
        user_name: str,
        is_recording: bool,
    ):
        """
        Set the recording state for a project and broadcast to all sessions
        """

        async with self.lock:
            if is_recording:
                self.recording_state[project_id] = (session_id, user_name)
            else:
                # Only clear if this session is the one recording
                if project_id in self.recording_state:
                    current_session_id, _ = self.recording_state[project_id]
                    if current_session_id == session_id:
                        del self.recording_state[project_id]

        # Broadcast the state change to all sessions in this project
        message = RecordingStateMessage(
            is_recording=is_recording,
            user_name=user_name if is_recording else None,
        )
        await self.broadcast_to_project(project_id, message)

    async def get_recording_state(
        self, project_id: ProjectId
    ) -> tuple[SessionId, str] | None:
        """
        Get the current recording state for a project
        """
        async with self.lock:
            return self.recording_state.get(project_id)

    async def _submit_ai_processing_job(self, job: AIJob):
        assert self._workers_started
        assert self._job_send is not None

        await self._job_send.send(job)

    async def start_background_services(self, max_buffer_size=5) -> None:
        """
        Creates a global TaskGroup + job queue + worker pool.
        Call this once on app startup (FastAPI lifespan).
        """
        if self._background_tg is not None:
            return  # already started

        if self.ai_processor is None:
            logger.warning(
                "Tried to start background services, but no ai_processor is set!"
            )
            return  # Nothing to start, we didn't provide a processor

        # Long-lived service TG
        self._background_tg = await anyio.create_task_group().__aenter__()

        job_send, job_recv = anyio.create_memory_object_stream[AIJob](
            max_buffer_size=max_buffer_size
        )
        self._job_send = job_send
        self._job_recv = job_recv

        # Spawn workers inside service TG
        for i in range(4):
            self._background_tg.start_soon(
                self._worker, f"bg-w{i}", self._job_recv.clone()
            )

        self._workers_started = True

        logger.info("AI Workers Started")

    async def _worker(
        self, name: str, recv: anyio.abc.ObjectReceiveStream[AIJob]
    ) -> None:
        async with recv:
            # Jobs are simply to "poke" the AI engine that data is incoming.
            # If it is already running that is fine, there will always be another "poke"
            async for job in recv:
                logger.info(f"Attempting to Run AI Job: {job}")
                try:
                    if self.active_ai_analysis[job.project_id].locked():
                        continue
                    async with self.active_ai_analysis[job.project_id]:
                        assert self.ai_processor, (
                            "Should never happen since we check this is not None when we start background services"
                        )
                        results = await self.ai_processor.analyze(job)
                        if results is None:
                            continue  # No results, likely an error or empty transcript, skip job

                    # Add all analyses to database and collect their IDs
                    analysis_ids: list[AnalysisId] = []
                    transcripts = get_all_transcripts_since_last_analysis(
                        self.db, job.project_id
                    )

                    for result in results.questions:
                        # Try to locate the span in the transcripts
                        transcript_span_id = None
                        if result.grounding_span and transcripts:
                            transcript_span_id = find_span_in_transcripts(
                                result.grounding_span, transcripts
                            )

                        id = add_ai_analysis(
                            self.db,
                            project_id=job.project_id,
                            text=result.question,
                            span=result.grounding_span,
                            transcript_span_id=transcript_span_id,
                            transcript_context_start=results.transcript_context_start,
                            transcript_context_end=results.transcript_context_end,
                            summary=results.summary,
                        )
                        analysis_ids.append(id)

                    # Fetch analyses with computed ordinals
                    analyses = get_analyses_by_ids(
                        self.db, job.project_id, analysis_ids
                    )

                    logger.info(
                        [f"Analysis #{a.ordinal} that says {a.text}" for a in analyses]
                    )

                    sessions: set[SessionId] = set()
                    for session, data in self.session_data.items():
                        logger.info(f"{session} {data}")
                        if data.project == job.project_id:
                            sessions.add(session)

                    logger.info(sessions)
                    # broadcast
                    await self.broadcast_to_project(
                        job.project_id, AIResultMessage(insights=analyses)
                    )

                except Exception:
                    # Never let an exception kill the worker or the service TG
                    import logging

                    logging.getLogger(__name__).exception(
                        "background worker %s failed processing job: %r", name, job
                    )

    async def stop_background_services(self) -> None:
        """
        Gracefully drains and shuts down the background service.
        """
        if self._background_tg is None:
            return

        # Close send end so workers finish when queue drains
        if self._job_send is not None:
            await self._job_send.aclose()

        # Exit task group (this will wait for workers to exit)
        await self._background_tg.__aexit__(None, None, None)

        # Clear handles
        self._background_tg = None
        self._job_send = None
        self._job_recv = None
