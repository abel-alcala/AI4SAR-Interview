import { Box } from "@mantine/core";
import type { AnalysisRow } from "../../lib/message";
import { InsightsPanel } from "./InsightsPanel";
import { RecordingControls } from "./RecordingControls";
import { TranscriptView } from "./TranscriptView";

interface TranscriptChunkWithId {
    transcription_id: string;
    speaker: string | null;
    text: string;
}

interface TranscriptSectionType {
    speaker: string | null;
    text: string;
    chunks: TranscriptChunkWithId[];
}

interface DesktopLayoutProps {
    transcript: TranscriptSectionType[];
    insights: AnalysisRow[];
    projectId?: string;
    projectName: string | null;
    connectionState: "disconnected" | "connected" | "connecting" | "failed";
    statusText: string;
    statusColor: string;
    highlightedTranscriptId: string | null;
    highlightedSpan: string | null;
    highlightAnimationKey: number;
    viewportRef: React.RefObject<HTMLDivElement | null>;
    isWebSocketConnected: boolean;
    isRecordingByOtherUser: boolean;
    recordingUserName: string | null;
    onRegisterChunkRef: (
        transcriptionId: string,
        element: HTMLDivElement,
    ) => void;
    onStarInsight: (analysisId: string) => void;
    onUnstarInsight: (analysisId: string) => void;
    onDismissAsAnswered: (analysisId: string) => void;
    onDismissNotAnswered: (analysisId: string) => void;
    onUndoDismiss: (analysisId: string) => void;
    onSpanClick: (transcriptId: string, spanText: string) => void;
    onStartRecording: () => void;
    onStopRecording: () => void;
}

export function DesktopLayout({
    transcript,
    insights,
    projectId,
    projectName,
    connectionState,
    statusText,
    statusColor,
    highlightedTranscriptId,
    highlightedSpan,
    highlightAnimationKey,
    viewportRef,
    isWebSocketConnected,
    isRecordingByOtherUser,
    recordingUserName,
    onRegisterChunkRef,
    onStarInsight,
    onUnstarInsight,
    onDismissAsAnswered,
    onDismissNotAnswered,
    onUndoDismiss,
    onSpanClick,
    onStartRecording,
    onStopRecording,
}: DesktopLayoutProps) {
    const isConnected = connectionState === "connected";

    return (
        <>
            {/* Transcript area fills the rest */}
            <Box
                style={{
                    position: "relative",
                    flex: 1,
                    minWidth: 0,
                    overflow: "hidden",
                }}
            >
                <TranscriptView
                    transcript={transcript}
                    projectId={projectId}
                    projectName={projectName}
                    isConnected={isConnected}
                    statusText={statusText}
                    statusColor={statusColor}
                    highlightedTranscriptId={highlightedTranscriptId}
                    highlightedSpan={highlightedSpan}
                    highlightAnimationKey={highlightAnimationKey}
                    viewportRef={viewportRef}
                    isWebSocketConnected={isWebSocketConnected}
                    onRegisterChunkRef={onRegisterChunkRef}
                />

                <RecordingControls
                    connectionState={connectionState}
                    isWebSocketConnected={isWebSocketConnected}
                    isRecordingByOtherUser={isRecordingByOtherUser}
                    recordingUserName={recordingUserName}
                    onStartRecording={onStartRecording}
                    onStopRecording={onStopRecording}
                />
            </Box>

            {/* Insights Panel */}
            <Box style={{ flex: "0 0 340px", overflow: "hidden" }}>
                <InsightsPanel
                    insights={insights}
                    onStar={onStarInsight}
                    onUnstar={onUnstarInsight}
                    onDismissAsAnswered={onDismissAsAnswered}
                    onDismissNotAnswered={onDismissNotAnswered}
                    onUndoDismiss={onUndoDismiss}
                    onSpanClick={onSpanClick}
                />
            </Box>
        </>
    );
}
