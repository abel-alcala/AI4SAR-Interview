from datetime import datetime
from typing import Any, Literal, Annotated

from pydantic import BaseModel, Field

from interview_helper.context_manager.database import AnalysisRow

# WARNING: When adding new message types,
# be sure that type is unique across all message types.


class TranscriptionMessage(BaseModel):
    type: Literal["transcription"] = "transcription"
    timestamp: datetime = Field(default_factory=datetime.now)
    text: str


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
    transcript: list[str]
    insights: list[AnalysisRow]


class ProjectMetadataMessage(BaseModel):
    type: Literal["project_metadata"] = "project_metadata"
    timestamp: datetime = Field(default_factory=datetime.now)
    project_id: str
    project_name: str


class DismissAIAnalysis(BaseModel):
    type: Literal["dismiss_ai_analysis"] = "dismiss_ai_analysis"
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis_id: str


WebSocketMessage = (
    ErrorMessage
    | TranscriptionMessage
    | WebRTCMessage
    | PingMessage
    | AIResultMessage
    | CatchupMessage
    | ProjectMetadataMessage
    | DismissAIAnalysis
)


class Envelope(BaseModel):
    message: Annotated[
        WebSocketMessage,
        Field(discriminator="type"),
    ]
