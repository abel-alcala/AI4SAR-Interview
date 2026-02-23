import { Badge, Box, Group, Paper, Stack, Tabs, Text } from "@mantine/core";
import { useState } from "react";
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

interface MobileLayoutProps {
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
    onStarInsight: (analysisId: string) => void;
    onUnstarInsight: (analysisId: string) => void;
    onDismissInsight: (analysisId: string) => void;
    onUndoDismiss: (analysisId: string) => void;
    onSpanClick: (transcriptId: string, spanText: string) => void;
    onStartRecording: () => void;
    onStopRecording: () => void;
}

export function MobileLayout({
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
    onStarInsight,
    onUnstarInsight,
    onDismissInsight,
    onUndoDismiss,
    onSpanClick,
    onStartRecording,
    onStopRecording,
}: MobileLayoutProps) {
    const isConnected = connectionState === "connected";
    const [activeTab, setActiveTab] = useState<string | null>("transcript");

    const handleSpanClick = (transcriptId: string, spanText: string) => {
        // Switch to transcript tab
        setActiveTab("transcript");
        // Wait for tab to render before scrolling
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                // Call the parent handler which will handle highlighting and scrolling
                onSpanClick(transcriptId, spanText);
            });
        });
    };

    return (
        <Box
            style={{
                position: "relative",
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
            }}
        >
            <Paper
                withBorder
                shadow="sm"
                radius="lg"
                style={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <Tabs
                    value={activeTab}
                    onChange={setActiveTab}
                    style={{
                        height: "100%",
                        display: "flex",
                        flexDirection: "column",
                    }}
                >
                    <Tabs.List>
                        <Tabs.Tab value="transcript">
                            <Group gap="xs">
                                <Text>Transcript</Text>
                                {isConnected && (
                                    <Badge color="red" size="sm">
                                        Live
                                    </Badge>
                                )}
                            </Group>
                        </Tabs.Tab>
                        <Tabs.Tab value="analysis">Questions</Tabs.Tab>
                    </Tabs.List>

                    <Tabs.Panel
                        value="transcript"
                        style={{
                            flex: 1,
                            display: "flex",
                            flexDirection: "column",
                            overflow: "hidden",
                        }}
                    >
                        <Stack gap="xs" style={{ height: "100%" }}>
                            <TranscriptView
                                transcript={transcript}
                                projectName={projectName}
                                isConnected={isConnected}
                                statusText={statusText}
                                statusColor={statusColor}
                                highlightedTranscriptId={
                                    highlightedTranscriptId
                                }
                                highlightedSpan={highlightedSpan}
                                highlightAnimationKey={highlightAnimationKey}
                                viewportRef={viewportRef}
                                isWebSocketConnected={isWebSocketConnected}
                                onRegisterChunkRef={onRegisterChunkRef}
                                showLiveBadge={false}
                                titleOrder={5}
                            />
                        </Stack>
                    </Tabs.Panel>

                    <Tabs.Panel
                        value="analysis"
                        style={{
                            flex: 1,
                            display: "flex",
                            flexDirection: "column",
                            overflow: "hidden",
                        }}
                        pt="md"
                    >
                        <Box p="md" style={{ flex: 1, overflow: "hidden" }}>
                            <InsightsPanel
                                insights={insights}
                                onStar={onStarInsight}
                                onUnstar={onUnstarInsight}
                                onDismiss={onDismissInsight}
                                onUndoDismiss={onUndoDismiss}
                                onSpanClick={handleSpanClick}
                            />
                        </Box>
                    </Tabs.Panel>
                </Tabs>
            </Paper>

            <RecordingControls
                connectionState={connectionState}
                isWebSocketConnected={isWebSocketConnected}
                onStartRecording={onStartRecording}
                onStopRecording={onStopRecording}
                size="lg"
                minWidth={200}
            />
        </Box>
    );
}
