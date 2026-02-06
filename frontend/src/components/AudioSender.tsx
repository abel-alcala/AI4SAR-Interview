import {
    ActionIcon,
    Affix,
    Alert,
    Badge,
    Box,
    Button,
    Center,
    Group,
    Loader,
    Paper,
    ScrollArea,
    Stack,
    Tabs,
    Text,
    Title,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import {
    IconAlertTriangle,
    IconBulb,
    IconMicrophone,
    IconX,
    IconAlertCircle,
} from "@tabler/icons-react";
import { createWebRTCClient } from "../lib/webrtc";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "../lib/useWebsocket";
import {
    MessageType,
    type AIResultMessage,
    type TranscriptionMessage,
    type CatchupMessage,
    type ProjectMetadataMessage,
    type AnalysisRow,
    type DismissAIAnalysis,
} from "../lib/message";

// Optional: a tiny Insights panel component so we keep the page clean
function InsightsPanel({
    insights,
    onDismiss,
}: {
    insights: AnalysisRow[];
    onDismiss: (analysisId: string) => void;
}) {
    const activeInsights = insights.filter((a) => !a.is_dismissed);
    const dismissedInsights = insights.filter((a) => a.is_dismissed);

    const renderInsight = (
        analysis: AnalysisRow,
        showDismissButton: boolean,
    ) => (
        <Group
            key={analysis.analysis_id}
            gap="xs"
            align="flex-start"
            style={{ paddingRight: 8 }}
        >
            <IconAlertTriangle size={14} style={{ marginTop: 2 }} />
            <Stack gap={4} style={{ flex: 1 }}>
                <Text size="sm">{analysis.text}</Text>
                {analysis.span && (
                    <Text size="xs" c="dimmed" fs="italic">
                        "{analysis.span}"
                    </Text>
                )}
            </Stack>
            {showDismissButton && (
                <ActionIcon
                    size="sm"
                    variant="subtle"
                    color="gray"
                    onClick={() => onDismiss(analysis.analysis_id)}
                    aria-label="Dismiss insight"
                >
                    <IconX size={14} />
                </ActionIcon>
            )}
        </Group>
    );

    return (
        <Paper
            shadow="md"
            radius="lg"
            p="md"
            withBorder
            style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                maxHeight: "calc(100%)",
            }}
        >
            <Group gap="xs" align="center" mb="sm">
                <IconBulb size={18} />
                <Title order={5}>Questions</Title>
            </Group>

            <Tabs
                defaultValue="active"
                style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                    minHeight: 0,
                }}
            >
                <Tabs.List>
                    <Tabs.Tab value="active">Active</Tabs.Tab>
                    <Tabs.Tab value="dismissed">Dismissed</Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel
                    value="active"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Stack gap="xs">
                            {activeInsights.length === 0 ? (
                                <Text c="dimmed" size="sm">
                                    No active questions yet. They'll show up
                                    here in real time.
                                </Text>
                            ) : (
                                activeInsights
                                    .reverse()
                                    .map((analysis) =>
                                        renderInsight(analysis, true),
                                    )
                            )}
                        </Stack>
                    </ScrollArea>
                </Tabs.Panel>

                <Tabs.Panel
                    value="dismissed"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Stack gap="xs">
                            {dismissedInsights.length === 0 ? (
                                <Text c="dimmed" size="sm">
                                    No dismissed questions.
                                </Text>
                            ) : (
                                dismissedInsights
                                    .reverse()
                                    .map((analysis) =>
                                        renderInsight(analysis, false),
                                    )
                            )}
                        </Stack>
                    </ScrollArea>
                </Tabs.Panel>
            </Tabs>
        </Paper>
    );
}

interface TranscriptSection {
    speaker: string | null;
    text: string;
}

interface TranscriptChunkWithId {
    transcription_id: string;
    speaker: string | null;
    text: string;
}

export function AudioSender() {
    type validConnectionStates =
        | "disconnected"
        | "connected"
        | "connecting"
        | "failed";

    const isMobile = useMediaQuery("(max-width: 48em)"); // Mantine md breakpoint ~768px

    const [connectionState, setConnectionState] =
        useState<validConnectionStates>("disconnected");

    const [transcriptChunks, setTranscriptChunks] = useState<
        TranscriptChunkWithId[]
    >([]);

    // Global Set to track seen transcription IDs for deduplication
    const seenTranscriptionIds = useRef(new Set<string>());

    const [insights, setInsights] = useState<AnalysisRow[]>([]);
    const [projectName, setProjectName] = useState<string | null>(null);
    const [showError, setShowError] = useState(false);

    const ws = useWebSocket();

    // Delay showing errors to prevent flash on page refresh/reconnect
    useEffect(() => {
        if (ws.error) {
            // Wait 2 seconds before showing the error
            const timer = setTimeout(() => {
                setShowError(true);
            }, 500);
            return () => clearTimeout(timer);
        } else {
            // Clear error immediately when it's resolved
            setShowError(false);
        }
    }, [ws.error]);

    // Hold the webrtc client instance
    const webrtcClient = useRef<ReturnType<typeof createWebRTCClient> | null>(
        null,
    );

    // Handle dismissing an insight
    const handleDismissInsight = useCallback(
        (analysisId: string) => {
            // Update local state immediately
            setInsights((prevState) =>
                prevState.map((insight) =>
                    insight.analysis_id === analysisId
                        ? { ...insight, is_dismissed: true }
                        : insight,
                ),
            );

            // Send dismiss message to backend
            ws.sendMessage({
                type: MessageType.DISMISS_AI_ANALYSIS,
                timestamp: new Date().toISOString(),
                analysis_id: analysisId,
            });
        },
        [ws],
    );

    const viewportRef = useRef<HTMLDivElement | null>(null);

    // Stable connection state handler
    const handleConnectionChange = useCallback(
        (state: validConnectionStates) => {
            setConnectionState(state);
        },
        [],
    );

    // Create the webrtc client only once
    useEffect(() => {
        if (!webrtcClient.current) {
            webrtcClient.current = createWebRTCClient({
                sendMessage: ws.sendMessage,
                onConnectionChange: handleConnectionChange,
            });
        }
    }, [ws.sendMessage, handleConnectionChange]);

    // Register WS signaling handlers
    useEffect(() => {
        if (!webrtcClient.current) return;

        const types = [
            MessageType.OFFER,
            MessageType.ICE_CANDIDATE,
            MessageType.ANSWER,
        ] as const;

        for (const type of types) {
            ws.registerMessageHandler(
                type,
                webrtcClient.current.handleWebsocketSignaling,
            );
        }

        return () => {
            for (const type of types) {
                ws.deregisterMessageHandler(type);
            }
        };
    }, [ws]);

    // Register transcript handler
    useEffect(() => {
        const handleTranscription = (message: TranscriptionMessage) => {
            const { transcription_id, speaker, text } = message.chunk;

            // Check global Set for duplicates
            if (seenTranscriptionIds.current.has(transcription_id)) {
                // Duplicate, ignore it
                return;
            }

            // Add to global Set
            seenTranscriptionIds.current.add(transcription_id);

            // Add to chunks and sort by transcription_id (ULIDs are sortable)
            setTranscriptChunks((prevChunks) => {
                const newChunks = [
                    ...prevChunks,
                    { transcription_id, speaker, text },
                ].sort((a, b) =>
                    a.transcription_id.localeCompare(b.transcription_id),
                );

                return newChunks;
            });
        };

        ws.registerMessageHandler("transcription", handleTranscription);

        return () => {
            ws.deregisterMessageHandler("transcription");
        };
    }, [ws]);

    // Register Insight Message
    useEffect(() => {
        const handleAIResults = (message: AIResultMessage) => {
            setInsights((prevState: AnalysisRow[]) => {
                // Use analysis_id as idempotency token - replace any existing analysis with same ID
                const newInsights = [...prevState];

                for (const newAnalysis of message.insights) {
                    const existingIndex = newInsights.findIndex(
                        (a) => a.analysis_id === newAnalysis.analysis_id,
                    );

                    if (existingIndex !== -1) {
                        // Replace existing analysis
                        newInsights[existingIndex] = newAnalysis;
                    } else {
                        // Add new analysis
                        newInsights.push(newAnalysis);
                    }
                }

                return newInsights;
            });
        };

        ws.registerMessageHandler("ai_result", handleAIResults);

        return () => {
            ws.deregisterMessageHandler("ai_result");
        };
    }, [ws]);

    // Register Catchup Message
    useEffect(() => {
        const handleCatchup = (message: CatchupMessage) => {
            // Store chunks with deduplication and sorting
            const chunks: TranscriptChunkWithId[] = message.transcript.map(
                (chunk) => ({
                    transcription_id: chunk.transcription_id,
                    speaker: chunk.speaker,
                    text: chunk.text,
                }),
            );

            seenTranscriptionIds.current.clear();

            // Deduplicate by transcription_id using a Set for O(n) complexity
            const uniqueChunks = chunks.filter((chunk) => {
                if (seenTranscriptionIds.current.has(chunk.transcription_id)) {
                    return false;
                }
                seenTranscriptionIds.current.add(chunk.transcription_id);
                return true;
            });

            // Sort by transcription_id (ULIDs are lexically sortable)
            uniqueChunks.sort((a, b) =>
                a.transcription_id.localeCompare(b.transcription_id),
            );

            setTranscriptChunks(uniqueChunks);
            setInsights(message.insights);
        };

        ws.registerMessageHandler("catchup", handleCatchup);

        return () => {
            ws.deregisterMessageHandler("catchup");
        };
    }, [ws]);

    // Compute transcript sections from chunks for display
    const transcript = useMemo(() => {
        const sections: TranscriptSection[] = [];

        // Chunks are already sorted by transcription_id (ULID)
        for (const chunk of transcriptChunks) {
            const speaker = chunk.speaker;
            const text = chunk.text.trim();

            // If the last section has the same speaker, append to it
            if (
                sections.length > 0 &&
                sections[sections.length - 1].speaker === speaker
            ) {
                sections[sections.length - 1].text += " " + text;
            } else {
                // Create a new section for this speaker
                sections.push({ speaker, text });
            }
        }

        // Reverse so most recent speaker is at the top
        return sections.reverse();
    }, [transcriptChunks]);

    // Register Project Metadata Message
    useEffect(() => {
        const handleProjectMetadata = (message: ProjectMetadataMessage) => {
            setProjectName(message.project_name);
        };

        ws.registerMessageHandler("project_metadata", handleProjectMetadata);

        return () => {
            ws.deregisterMessageHandler("project_metadata");
        };
    }, [ws]);

    useEffect(() => {
        const handleDismissAIAnalysis = (message: DismissAIAnalysis) => {
            // Set insight to dismissed in local state so it disappears
            // from active insights list
            setInsights((prevState) =>
                prevState.map((insight) =>
                    insight.analysis_id === message.analysis_id
                        ? { ...insight, is_dismissed: true }
                        : insight,
                ),
            );
        };

        ws.registerMessageHandler(
            "dismiss_ai_analysis",
            handleDismissAIAnalysis,
        );

        return () => {
            ws.deregisterMessageHandler("dismiss_ai_analysis");
        };
    }, [ws]);

    // (Optional) Example: if later you emit insight messages from the server,
    // register a handler here. For now, this just shows how to wire it up.
    // useEffect(() => {
    //   ws.registerMessageHandler("insight", (m: { text: string }) => {
    //     setInsights((prev) => [m.text, ...prev].slice(0, 20));
    //   });
    //   return () => ws.deregisterMessageHandler("insight");
    // }, [ws]);

    function startSendingAudio() {
        if (webrtcClient.current) {
            webrtcClient.current.startAudioStream();
        }
    }

    function stopSendingAudio() {
        if (webrtcClient.current) {
            webrtcClient.current.stopAudioStream();
        }
    }

    const isConnected = connectionState === "connected";
    const isConnecting = connectionState === "connecting";
    const buttonText = isConnected ? "Stop Recording" : "Start Recording";
    const buttonColor = isConnected ? "red" : "green";
    const buttonVariant = isConnected ? "filled" : "light";
    const statusText = isConnected
        ? "Recording..."
        : isConnecting
          ? "Connecting..."
          : "Ready to Start";
    const statusColor = isConnected ? "red" : isConnecting ? "yellow" : "gray";

    return (
        <Box
            style={{
                height: "calc(100dvh - 60px - 32px)",
                width: "100%",
                display: "flex",
                flexDirection: "column",
            }}
        >
            {/* WebSocket Error Banner - Full Width at Top */}
            {showError && ws.error && (
                <Box px="md" pt="md">
                    <Alert
                        icon={<IconAlertCircle size={16} />}
                        title="Connection Error"
                        color="red"
                        onClose={() => {
                            // Error will be cleared on next connection attempt
                        }}
                        radius="md"
                    >
                        Your connection to the server was lost. Please refresh
                        the page to try reconnecting.
                    </Alert>
                </Box>
            )}

            {/* Main Content Area */}
            <Box
                style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "row",
                    gap: "var(--mantine-spacing-sm)",
                    boxSizing: "border-box",
                    overflow: "hidden",
                }}
            >
                {/* Mobile: Tabs for Transcript and Analysis */}
                {isMobile ? (
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
                                defaultValue="transcript"
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
                                    <Tabs.Tab value="analysis">
                                        Questions
                                    </Tabs.Tab>
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
                                        <Group
                                            justify="space-between"
                                            p="md"
                                            pb={0}
                                        >
                                            <Title order={5}>
                                                {projectName != null
                                                    ? projectName
                                                    : "Interview"}
                                            </Title>
                                            <Text size="sm" c={statusColor}>
                                                {statusText}
                                            </Text>
                                        </Group>

                                        <ScrollArea
                                            type="always"
                                            style={{ flex: 1 }}
                                            viewportRef={viewportRef}
                                            offsetScrollbars
                                        >
                                            <Box p="md" pt={0} pb="120px">
                                                {transcript.length > 0 ? (
                                                    <Stack gap="md">
                                                        {transcript.map(
                                                            (
                                                                section,
                                                                index,
                                                            ) => (
                                                                <Box
                                                                    key={index}
                                                                >
                                                                    <Title
                                                                        order={
                                                                            6
                                                                        }
                                                                        mb="xs"
                                                                    >
                                                                        {section.speaker ??
                                                                            "Unknown Speaker"}
                                                                    </Title>
                                                                    <Text
                                                                        style={{
                                                                            whiteSpace:
                                                                                "pre-wrap",
                                                                            lineHeight: 1.6,
                                                                        }}
                                                                    >
                                                                        {
                                                                            section.text
                                                                        }
                                                                    </Text>
                                                                </Box>
                                                            ),
                                                        )}
                                                    </Stack>
                                                ) : (
                                                    <Text
                                                        c="dimmed"
                                                        ta="center"
                                                        py="xl"
                                                    >
                                                        Your transcript will
                                                        appear here.
                                                    </Text>
                                                )}
                                            </Box>
                                        </ScrollArea>
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
                                    <Box
                                        p="md"
                                        style={{ flex: 1, overflow: "hidden" }}
                                    >
                                        <InsightsPanel
                                            insights={insights}
                                            onDismiss={handleDismissInsight}
                                        />
                                    </Box>
                                </Tabs.Panel>
                            </Tabs>
                        </Paper>

                        {/* Bottom-center recording control (floating) - Mobile */}
                        <Affix position={{ bottom: 24, left: 0, right: 0 }}>
                            <Center>
                                <Paper
                                    shadow="xl"
                                    radius="xl"
                                    p="sm"
                                    withBorder
                                >
                                    <Group gap="md" align="center">
                                        <Button
                                            variant={buttonVariant}
                                            color={buttonColor}
                                            leftSection={
                                                isConnecting ? (
                                                    <Loader
                                                        size="sm"
                                                        color="white"
                                                    />
                                                ) : (
                                                    <IconMicrophone size={18} />
                                                )
                                            }
                                            size="lg"
                                            radius="xl"
                                            loading={isConnecting}
                                            disabled={
                                                ws.connectionStatus !==
                                                    "connected" && !isConnecting
                                            }
                                            onClick={() => {
                                                if (
                                                    connectionState ===
                                                    "disconnected"
                                                ) {
                                                    startSendingAudio();
                                                } else if (
                                                    connectionState ===
                                                    "connected"
                                                ) {
                                                    stopSendingAudio();
                                                }
                                            }}
                                            style={{
                                                minWidth: 200,
                                            }}
                                        >
                                            {buttonText}
                                        </Button>
                                    </Group>
                                </Paper>
                            </Center>
                        </Affix>
                    </Box>
                ) : (
                    <>
                        {/* Desktop: Transcript area fills the rest */}
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
                                style={{ height: "100%" }}
                            >
                                <Stack gap="xs" style={{ height: "100%" }}>
                                    <Group
                                        justify="space-between"
                                        p="md"
                                        pb={0}
                                    >
                                        <Group gap="xs">
                                            <Title order={4}>
                                                {projectName != null
                                                    ? `${projectName} - Transcript`
                                                    : "Transcript"}
                                            </Title>
                                            {isConnected && (
                                                <Badge color="red">Live</Badge>
                                            )}
                                        </Group>
                                        <Text size="sm" c={statusColor}>
                                            {statusText}
                                        </Text>
                                    </Group>

                                    <ScrollArea
                                        type="always"
                                        style={{ flex: 1 }}
                                        viewportRef={viewportRef}
                                        offsetScrollbars
                                    >
                                        <Box p="md" pt={0} pb="120px">
                                            {transcript.length > 0 ? (
                                                <Stack gap="md">
                                                    {transcript.map(
                                                        (section, index) => (
                                                            <Box key={index}>
                                                                <Title
                                                                    order={6}
                                                                    mb="xs"
                                                                >
                                                                    {section.speaker ??
                                                                        "Unknown Speaker"}
                                                                </Title>
                                                                <Text
                                                                    style={{
                                                                        whiteSpace:
                                                                            "pre-wrap",
                                                                        lineHeight: 1.6,
                                                                    }}
                                                                >
                                                                    {
                                                                        section.text
                                                                    }
                                                                </Text>
                                                            </Box>
                                                        ),
                                                    )}
                                                </Stack>
                                            ) : (
                                                <Text
                                                    c="dimmed"
                                                    ta="center"
                                                    py="xl"
                                                >
                                                    Your transcript will appear
                                                    here.
                                                </Text>
                                            )}
                                        </Box>
                                    </ScrollArea>
                                </Stack>
                            </Paper>

                            {/* Bottom-center recording control (floating) - Desktop */}
                            <Affix position={{ bottom: 24, left: 0, right: 0 }}>
                                <Center>
                                    <Paper
                                        shadow="xl"
                                        radius="xl"
                                        p="sm"
                                        withBorder
                                    >
                                        <Group gap="md" align="center">
                                            <Button
                                                variant={buttonVariant}
                                                color={buttonColor}
                                                leftSection={
                                                    isConnecting ? (
                                                        <Loader
                                                            size="sm"
                                                            color="white"
                                                        />
                                                    ) : (
                                                        <IconMicrophone
                                                            size={18}
                                                        />
                                                    )
                                                }
                                                size="xl"
                                                radius="xl"
                                                loading={isConnecting}
                                                disabled={
                                                    ws.connectionStatus !==
                                                        "connected" &&
                                                    !isConnecting
                                                }
                                                onClick={() => {
                                                    if (
                                                        connectionState ===
                                                        "disconnected"
                                                    ) {
                                                        startSendingAudio();
                                                    } else if (
                                                        connectionState ===
                                                        "connected"
                                                    ) {
                                                        stopSendingAudio();
                                                    }
                                                }}
                                                style={{
                                                    minWidth: 260,
                                                }}
                                            >
                                                {buttonText}
                                            </Button>
                                        </Group>
                                    </Paper>
                                </Center>
                            </Affix>
                        </Box>

                        <Box style={{ flex: "0 0 340px", overflow: "hidden" }}>
                            <InsightsPanel
                                insights={insights}
                                onDismiss={handleDismissInsight}
                            />
                        </Box>
                    </>
                )}
            </Box>
        </Box>
    );
}
