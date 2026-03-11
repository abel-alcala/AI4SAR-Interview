export const MessageType = {
    OFFER: "offer",
    ANSWER: "answer",
    ICE_CANDIDATE: "ice_candidate",
    PING: "ping",
    PONG: "pong",
    TRANSCRIPTION: "transcription",
    AI_RESULT: "ai_result",
    CATCHUP: "catchup",
    PROJECT_METADATA: "project_metadata",
    UPDATE_AI_ANALYSIS_TAG: "update_ai_analysis_tag",
    MARK_AI_ANALYSIS_ASKED: "mark_ai_analysis_asked",
    UNDO_AI_ANALYSIS_DISMISSAL: "undo_ai_analysis_dismissal",
    MARK_AI_ANALYSIS_DISMISSED_NOT_ASKED:
        "mark_ai_analysis_dismissed_not_asked",
    STAR_AI_ANALYSIS: "star_ai_analysis",
    UNSTAR_AI_ANALYSIS: "unstar_ai_analysis",
    RECORDING_STATE: "recording_state",
} as const;

interface OfferMessage {
    type: typeof MessageType.OFFER;
    data: {
        sdp: RTCSessionDescriptionInit;
    };
}

interface AnswerMessage {
    type: typeof MessageType.ANSWER;
    data: {
        sdp: RTCSessionDescriptionInit;
    };
}

interface IceCandidateMessage {
    type: typeof MessageType.ICE_CANDIDATE;
    data: {
        candidate: RTCIceCandidateInit;
    };
}

export interface PingMessage {
    type: typeof MessageType.PING | typeof MessageType.PONG;
    timestamp: string;
}

interface TranscriptChunk {
    text: string;
    speaker: string | null;
    transcription_id: string;
}

export interface TranscriptionMessage {
    type: typeof MessageType.TRANSCRIPTION;
    timestamp: string;
    chunk: TranscriptChunk;
}

export interface AIResultMessage {
    type: typeof MessageType.AI_RESULT;
    timestamp: string;
    insights: AnalysisRow[];
}

export interface AnalysisRow {
    analysis_id: string;
    text: string;
    category_code: string;
    span: string | null;
    transcript_span_id: string | null;
    is_dismissed: boolean;
    tag: string | null;
    ordinal: number;
    was_asked?: boolean | null;
    asked_at_transcript_id?: string | null;
    asked_at?: string | null;
    time_tag_changed?: string | null;
}

export interface CatchupMessage {
    type: typeof MessageType.CATCHUP;
    timestamp: string;
    transcript: TranscriptChunk[];
    insights: AnalysisRow[];
}

export interface ProjectMetadataMessage {
    type: typeof MessageType.PROJECT_METADATA;
    timestamp: string;
    project_id: string;
    project_name: string;
}

export interface UpdateAIAnalysisTag {
    type: typeof MessageType.UPDATE_AI_ANALYSIS_TAG;
    timestamp: string;
    analysis_id: string;
    tag: "starred" | "dismissed" | "starred_dismissed" | null;
    was_asked?: boolean | null;
    asked_at_transcript_id?: string | null;
    asked_at?: string | null;
    time_tag_changed?: string | null;
}

export interface MarkAIAnalysisAsked {
    type: typeof MessageType.MARK_AI_ANALYSIS_ASKED;
    timestamp: string;
    analysis_id: string;
    asked_at_transcript_id: string;
}

export interface UndoAIAnalysisDismissal {
    type: typeof MessageType.UNDO_AI_ANALYSIS_DISMISSAL;
    timestamp: string;
    analysis_id: string;
}

export interface MarkAIAnalysisDismissedNotAsked {
    type: typeof MessageType.MARK_AI_ANALYSIS_DISMISSED_NOT_ASKED;
    timestamp: string;
    analysis_id: string;
}

export interface StarAIAnalysis {
    type: typeof MessageType.STAR_AI_ANALYSIS;
    timestamp: string;
    analysis_id: string;
}

export interface UnstarAIAnalysis {
    type: typeof MessageType.UNSTAR_AI_ANALYSIS;
    timestamp: string;
    analysis_id: string;
}

export interface RecordingStateMessage {
    type: typeof MessageType.RECORDING_STATE;
    timestamp: string;
    is_recording: boolean;
    user_name: string | null;
}

export type SignalingMessage =
    | OfferMessage
    | AnswerMessage
    | IceCandidateMessage;

export type Message =
    | SignalingMessage
    | PingMessage
    | TranscriptionMessage
    | AIResultMessage
    | CatchupMessage
    | ProjectMetadataMessage
    | UpdateAIAnalysisTag
    | MarkAIAnalysisAsked
    | UndoAIAnalysisDismissal
    | MarkAIAnalysisDismissedNotAsked
    | StarAIAnalysis
    | UnstarAIAnalysis
    | RecordingStateMessage;

export interface Envelope {
    message: Message;
}
