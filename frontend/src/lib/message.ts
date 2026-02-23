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
    span: string | null;
    transcript_span_id: string | null;
    is_dismissed: boolean;
    tag: string | null;
    ordinal: number;
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
    | RecordingStateMessage;

export interface Envelope {
    message: Message;
}
