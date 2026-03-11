import { Box } from "@mantine/core";
import { useCallback, useEffect, useRef, useState } from "react";
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
    const DEFAULT_INSIGHTS_WIDTH = 340;
    const MIN_TRANSCRIPT_WIDTH = 420;
    const MIN_INSIGHTS_WIDTH = 260;
    const RESIZE_HANDLE_WIDTH = 10;
    const [insightsWidth, setInsightsWidth] = useState(DEFAULT_INSIGHTS_WIDTH);
    const [isResizing, setIsResizing] = useState(false);
    const resizeHandleRef = useRef<HTMLDivElement | null>(null);
    const dragStateRef = useRef<{
        startX: number;
        startWidth: number;
        containerWidth: number;
    } | null>(null);

    const clampInsightsWidth = useCallback((nextWidth: number) => {
        const storedContainerWidth = dragStateRef.current?.containerWidth;
        const containerWidth =
            storedContainerWidth ??
            resizeHandleRef.current?.parentElement?.clientWidth ??
            0;

        if (containerWidth <= 0) return nextWidth;

        const maxInsightsWidth = Math.max(
            MIN_INSIGHTS_WIDTH,
            containerWidth - MIN_TRANSCRIPT_WIDTH - RESIZE_HANDLE_WIDTH,
        );

        return Math.max(
            MIN_INSIGHTS_WIDTH,
            Math.min(nextWidth, maxInsightsWidth),
        );
    }, []);

    useEffect(() => {
        const handleWindowResize = () => {
            setInsightsWidth((prevWidth) => clampInsightsWidth(prevWidth));
        };

        handleWindowResize();
        window.addEventListener("resize", handleWindowResize);
        return () => window.removeEventListener("resize", handleWindowResize);
    }, [clampInsightsWidth]);

    useEffect(() => {
        if (!isResizing) return;

        const handleMouseMove = (event: MouseEvent) => {
            const dragState = dragStateRef.current;
            if (!dragState) return;

            const deltaX = event.clientX - dragState.startX;
            const nextWidth = dragState.startWidth - deltaX;
            setInsightsWidth(clampInsightsWidth(nextWidth));
        };

        const handleMouseUp = () => {
            dragStateRef.current = null;
            setIsResizing(false);
        };

        const previousUserSelect = document.body.style.userSelect;
        const previousCursor = document.body.style.cursor;

        document.body.style.userSelect = "none";
        document.body.style.cursor = "col-resize";

        window.addEventListener("mousemove", handleMouseMove);
        window.addEventListener("mouseup", handleMouseUp);

        return () => {
            document.body.style.userSelect = previousUserSelect;
            document.body.style.cursor = previousCursor;
            window.removeEventListener("mousemove", handleMouseMove);
            window.removeEventListener("mouseup", handleMouseUp);
        };
    }, [clampInsightsWidth, isResizing]);

    const handleResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();

        const containerWidth =
            resizeHandleRef.current?.parentElement?.clientWidth ?? 0;
        if (containerWidth <= 0) return;

        dragStateRef.current = {
            startX: event.clientX,
            startWidth: insightsWidth,
            containerWidth,
        };
        setIsResizing(true);
    };

    return (
        <Box
            style={{
                flex: 1,
                display: "flex",
                minWidth: 0,
                overflow: "hidden",
            }}
        >
            {/* Transcript area fills the rest */}
            <Box
                style={{
                    position: "relative",
                    flex: 1,
                    minWidth: `${MIN_TRANSCRIPT_WIDTH}px`,
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

            <Box
                ref={resizeHandleRef}
                onMouseDown={handleResizeStart}
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize insights panel"
                style={{
                    position: "relative",
                    flex: `0 0 ${RESIZE_HANDLE_WIDTH}px`,
                    cursor: "col-resize",
                    userSelect: "none",
                }}
            >
                <Box
                    style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
                        left: "50%",
                        transform: "translateX(-50%)",
                        width: 2,
                        borderRadius: 999,
                        backgroundColor: isResizing
                            ? "var(--mantine-color-blue-5)"
                            : "var(--mantine-color-gray-3)",
                    }}
                />
            </Box>

            {/* Insights Panel */}
            <Box
                style={{
                    flex: `0 0 ${insightsWidth}px`,
                    minWidth: `${MIN_INSIGHTS_WIDTH}px`,
                    overflow: "hidden",
                }}
            >
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
        </Box>
    );
}
