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
    projectName: string | null;
    connectionState: "disconnected" | "connected" | "connecting" | "failed";
    statusText: string;
    statusColor: string;
    highlightedTranscriptId: string | null;
    highlightedSpan: string | null;
    highlightAnimationKey: number;
    viewportRef: React.RefObject<HTMLDivElement | null>;
    isWebSocketConnected: boolean;
    onRegisterChunkRef: (
        transcriptionId: string,
        element: HTMLDivElement,
    ) => void;
    onDismissInsight: (analysisId: string) => void;
    onSpanClick: (transcriptId: string, spanText: string) => void;
    onStartRecording: () => void;
    onStopRecording: () => void;
}

export function DesktopLayout({
    transcript,
    insights,
    projectName,
    connectionState,
    statusText,
    statusColor,
    highlightedTranscriptId,
    highlightedSpan,
    highlightAnimationKey,
    viewportRef,
    isWebSocketConnected,
    onRegisterChunkRef,
    onDismissInsight,
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
                    onStartRecording={onStartRecording}
                    onStopRecording={onStopRecording}
                />
            </Box>

            {/* Insights Panel */}
            <Box style={{ flex: "0 0 340px", overflow: "hidden" }}>
                <InsightsPanel
                    insights={insights}
                    onDismiss={onDismissInsight}
                    onSpanClick={onSpanClick}
                />
            </Box>
        </>
    );
}
