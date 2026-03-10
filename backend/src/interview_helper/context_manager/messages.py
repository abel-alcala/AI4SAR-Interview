from datetime import datetime
from typing import Any, Literal, Annotated

from pydantic import BaseModel, Field

from interview_helper.context_manager.database import AnalysisRow


class TranscriptChunkToSend(BaseModel):
    text: str
    speaker: str | None
    transcription_id: str


# WARNING: When adding new message types,
# be sure that type is unique across all message types.


class TranscriptionMessage(BaseModel):
    type: Literal["transcription"] = "transcription"
    timestamp: datetime = Field(default_factory=datetime.now)
    chunk: TranscriptChunkToSend


class AIResultMessage(BaseModel):
    type: Literal["ai_result"] = "ai_result"
    timestamp: datetime = Field(default_factory=datetime.now)
    insights: list[AnalysisRow]


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    timestamp: datetime = Field(default_factory=datetime.now)
    error_code: str
    message: str
    session_id: str | None = None


class WebRTCMessage(BaseModel):
    """
    WebRTC signaling messages. Kept loose because lower layers handle details.
    """

    type: Literal["offer", "answer", "ice_candidate"]
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any]


class PingMessage(BaseModel):
    type: Literal["ping"] | Literal["pong"] = "pong"
    timestamp: datetime = Field(default_factory=datetime.now)


class CatchupMessage(BaseModel):
    type: Literal["catchup"] = "catchup"
    timestamp: datetime = Field(default_factory=datetime.now)
    transcript: list[TranscriptChunkToSend]
    insights: list[AnalysisRow]


class ProjectMetadataMessage(BaseModel):
    type: Literal["project_metadata"] = "project_metadata"
    timestamp: datetime = Field(default_factory=datetime.now)
    project_id: str
    project_name: str


class UpdateAIAnalysisTag(BaseModel):
    type: Literal["update_ai_analysis_tag"] = "update_ai_analysis_tag"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str
    tag: Literal["starred", "dismissed", "starred_dismissed"] | None
    was_asked: bool | None = None
    asked_at_transcript_id: str | None = None


class MarkAIAnalysisAsked(BaseModel):
    type: Literal["mark_ai_analysis_asked"] = "mark_ai_analysis_asked"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str
    asked_at_transcript_id: str


class UndoAIAnalysisDismissal(BaseModel):
    type: Literal["undo_ai_analysis_dismissal"] = "undo_ai_analysis_dismissal"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str


class MarkAIAnalysisDismissedNotAsked(BaseModel):
    type: Literal["mark_ai_analysis_dismissed_not_asked"] = (
        "mark_ai_analysis_dismissed_not_asked"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str


class StarAIAnalysis(BaseModel):
    type: Literal["star_ai_analysis"] = "star_ai_analysis"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str


class UnstarAIAnalysis(BaseModel):
    type: Literal["unstar_ai_analysis"] = "unstar_ai_analysis"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str


class RecordingStateMessage(BaseModel):
    type: Literal["recording_state"] = "recording_state"
    timestamp: datetime = Field(default_factory=datetime.now)
    is_recording: bool
    user_name: str | None = None


WebSocketMessage = (
    ErrorMessage
    | TranscriptionMessage
    | WebRTCMessage
    | PingMessage
    | AIResultMessage
    | CatchupMessage
    | ProjectMetadataMessage
    | MarkAIAnalysisAsked
    | UndoAIAnalysisDismissal
    | MarkAIAnalysisDismissedNotAsked
    | StarAIAnalysis
    | UnstarAIAnalysis
    | UpdateAIAnalysisTag
    | RecordingStateMessage
)


class Envelope(BaseModel):
    message: Annotated[
        WebSocketMessage,
        Field(discriminator="type"),
    ]
