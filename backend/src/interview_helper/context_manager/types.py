from datetime import datetime, timezone
from typing import (
    TypeVar,
    Generic,
    cast,
    final,
    override,
    runtime_checkable,
    NewType,
    Protocol,
)
from dataclasses import dataclass
from ulid import ULID
#
# Resource Key and Types
#

T = TypeVar("T", covariant=True)


@final
@dataclass(frozen=True)
class ResourceKey(Generic[T]):
    """
    A key to access a resource in the context manager.

    Attributes
    ----------
    name:
        unique resource key
    """

    name: str


#
## New Types
#
@dataclass(frozen=True)
class UserId:
    _user_id: ULID

    @override
    def __str__(self):
        return str(self._user_id).lower()

    @override
    def __hash__(self):
        return hash(self._user_id)

    @classmethod
    def from_str(cls, user_id: str) -> "UserId":
        return cls(_user_id=cast(ULID, ULID.from_str(user_id.upper())))


SessionId = NewType("SessionId", ULID)


@dataclass(frozen=True)
class ProjectId:
    _project_id: ULID

    @override
    def __str__(self):
        return str(self._project_id).lower()

    @classmethod
    def from_str(cls, project_id: str) -> "ProjectId":
        return cls(_project_id=cast(ULID, ULID.from_str(project_id.upper())))


@dataclass(frozen=True)
class AnalysisId:
    _analysis_id: ULID

    @override
    def __str__(self):
        return str(self._analysis_id).lower()

    @classmethod
    def from_str(cls, analysis_id: str) -> "AnalysisId":
        return cls(_analysis_id=cast(ULID, ULID.from_str(analysis_id.upper())))


@dataclass(frozen=True)
class TranscriptId:
    _transcript_id: ULID

    @override
    def __str__(self):
        return str(self._transcript_id).lower()

    @override
    def __hash__(self):
        return hash(self._transcript_id)

    @classmethod
    def from_str(cls, transcript_id: str) -> "TranscriptId":
        return cls(_transcript_id=ULID.from_str(transcript_id.upper()))

    def get_datetime(self):
        return datetime.fromtimestamp(self._transcript_id.timestamp, tz=timezone.utc)


UserIP = NewType("UserIP", str)


@runtime_checkable
class WebSocketProtocol(Protocol):
    async def send_text(self, data: str) -> None: ...
    async def receive_text(self) -> str: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class AIJob:
    project_id: ProjectId


@dataclass(frozen=True)
class AIQuestion:
    question: str
    grounding_span: str
    category_code: str


@dataclass(frozen=True)
class AIResult:
    questions: list[AIQuestion]
    transcript_context_start: TranscriptId
    transcript_context_end: TranscriptId
    summary: str
