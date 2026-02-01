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
    DISMISS_AI_ANALYSIS: "dismiss_ai_analysis",
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
    is_dismissed: boolean;
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

export interface DismissAIAnalysis {
    type: typeof MessageType.DISMISS_AI_ANALYSIS;
    timestamp: string;
    analysis_id: string;
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
    | DismissAIAnalysis;

export interface Envelope {
    message: Message;
}
