import { Box } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
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
    type UpdateAIAnalysisTag,
} from "../lib/message";
import { WebSocketErrorBanner } from "./audio-sender/WebSocketErrorBanner";
import { MobileLayout } from "./audio-sender/MobileLayout";
import { DesktopLayout } from "./audio-sender/DesktopLayout";

interface TranscriptSection {
    speaker: string | null;
    text: string;
    chunks: TranscriptChunkWithId[];
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

    // State for highlighting spans in the transcript
    const [highlightedTranscriptId, setHighlightedTranscriptId] = useState<
        string | null
    >(null);
    const [highlightedSpan, setHighlightedSpan] = useState<string | null>(null);
    const [highlightAnimationKey, setHighlightAnimationKey] = useState(0);

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

    // Handle starring an insight
    const handleStarInsight = useCallback(
        (analysisId: string) => {
            // Update local state immediately
            setInsights((prevState) =>
                prevState.map((insight) =>
                    insight.analysis_id === analysisId
                        ? { ...insight, tag: "starred" }
                        : insight,
                ),
            );

            // Send update tag message to backend
            ws.sendMessage({
                type: MessageType.UPDATE_AI_ANALYSIS_TAG,
                timestamp: new Date().toISOString(),
                analysis_id: analysisId,
                tag: "starred",
            });
        },
        [ws],
    );

    // Handle unstarring an insight
    const handleUnstarInsight = useCallback(
        (analysisId: string) => {
            // Update local state immediately
            setInsights((prevState) =>
                prevState.map((insight) =>
                    insight.analysis_id === analysisId
                        ? { ...insight, tag: null }
                        : insight,
                ),
            );

            // Send update tag message to backend
            ws.sendMessage({
                type: MessageType.UPDATE_AI_ANALYSIS_TAG,
                timestamp: new Date().toISOString(),
                analysis_id: analysisId,
                tag: null,
            });
        },
        [ws],
    );

    // Handle dismissing an insight
    const handleDismissInsight = useCallback(
        (analysisId: string) => {
            // Update local state immediately
            setInsights((prevState) =>
                prevState.map((insight) => {
                    if (insight.analysis_id === analysisId) {
                        // If it's starred, mark as starred_dismissed, otherwise just dismissed
                        const newTag =
                            insight.tag === "starred"
                                ? "starred_dismissed"
                                : "dismissed";
                        return { ...insight, tag: newTag };
                    }
                    return insight;
                }),
            );

            // Send update tag message to backend
            const insight = insights.find((i) => i.analysis_id === analysisId);
            const newTag =
                insight?.tag === "starred" ? "starred_dismissed" : "dismissed";
            ws.sendMessage({
                type: MessageType.UPDATE_AI_ANALYSIS_TAG,
                timestamp: new Date().toISOString(),
                analysis_id: analysisId,
                tag: newTag,
            });
        },
        [ws, insights],
    );

    // Handle undoing a dismiss (restore to active or starred)
    const handleUndoDismiss = useCallback(
        (analysisId: string) => {
            // Update local state immediately
            setInsights((prevState) =>
                prevState.map((insight) => {
                    if (insight.analysis_id === analysisId) {
                        // If it was starred_dismissed, restore to starred, otherwise to active (null)
                        const newTag =
                            insight.tag === "starred_dismissed"
                                ? "starred"
                                : null;
                        return { ...insight, tag: newTag };
                    }
                    return insight;
                }),
            );

            // Send update tag message to backend
            const insight = insights.find((i) => i.analysis_id === analysisId);
            const newTag =
                insight?.tag === "starred_dismissed" ? "starred" : null;
            ws.sendMessage({
                type: MessageType.UPDATE_AI_ANALYSIS_TAG,
                timestamp: new Date().toISOString(),
                analysis_id: analysisId,
                tag: newTag,
            });
        },
        [ws, insights],
    );

    const viewportRef = useRef<HTMLDivElement | null>(null);

    // Refs to store DOM elements for each transcript chunk
    const chunkRefs = useRef<Map<string, HTMLDivElement>>(new Map());

    // Track previous scroll state to maintain position when new messages arrive
    const previousScrollHeightRef = useRef<number>(0);
    const shouldMaintainScrollRef = useRef<boolean>(false);

    // Stable connection state handler
    const handleConnectionChange = useCallback(
        (state: validConnectionStates) => {
            setConnectionState(state);
        },
        [],
    );

    // Handle clicking on a span to highlight it in the transcript
    const handleSpanClick = useCallback(
        (
            transcriptId: { _transcript_id: string } | string,
            spanText: string,
        ) => {
            // Handle case where transcriptId might be an object with _transcript_id property
            let actualTranscriptId: string;
            if (
                typeof transcriptId === "object" &&
                transcriptId?._transcript_id
            ) {
                actualTranscriptId = transcriptId._transcript_id.toLowerCase();
            } else if (typeof transcriptId === "string") {
                actualTranscriptId = transcriptId.toLowerCase();
            } else {
                console.error("Invalid transcriptId:", transcriptId);
                return;
            }

            setHighlightedTranscriptId(actualTranscriptId);
            setHighlightedSpan(spanText);
            // Trigger animation by updating key
            setHighlightAnimationKey((prev) => prev + 1);

            // Scroll to the transcript chunk
            const element = chunkRefs.current.get(actualTranscriptId);
            const viewport = viewportRef.current;

            if (element && viewport) {
                // Get the positions using getBoundingClientRect for accurate calculation
                const elementRect = element.getBoundingClientRect();
                const viewportRect = viewport.getBoundingClientRect();

                // Calculate position of element relative to viewport
                const relativeTop = elementRect.top - viewportRect.top;

                // Current scroll position
                const currentScroll = viewport.scrollTop;

                // Calculate target scroll position to center the element
                const viewportHeight = viewport.clientHeight;
                const elementHeight = elementRect.height;
                const targetScroll =
                    currentScroll +
                    relativeTop -
                    viewportHeight / 2 +
                    elementHeight / 2;

                viewport.scrollTo({
                    top: targetScroll,
                    behavior: "smooth",
                });

                // Also try direct scrollTop assignment as fallback
                setTimeout(() => {
                    if (viewport.scrollTop === currentScroll) {
                        viewport.scrollTop = targetScroll;
                    }
                }, 100);
            }
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

            // Store scroll state before adding new content
            const viewport = viewportRef.current;
            if (viewport) {
                previousScrollHeightRef.current = viewport.scrollHeight;
                // Only maintain scroll if user is scrolled away from top (top = 0 for reversed list)
                shouldMaintainScrollRef.current = viewport.scrollTop > 50;
            }

            // Add to chunks, keeping them sorted by transcription_id (ULIDs are sortable)
            setTranscriptChunks((prevChunks) => {
                const newChunk = { transcription_id, speaker, text };

                // Fast path: empty list
                if (prevChunks.length === 0) {
                    return [newChunk];
                }

                const lastChunk = prevChunks[prevChunks.length - 1];

                // Common case: IDs arrive in ascending order, so we can just append
                if (
                    lastChunk.transcription_id.localeCompare(
                        transcription_id,
                    ) <= 0
                ) {
                    return [...prevChunks, newChunk];
                }

                // Out-of-order chunk: insert while maintaining sort by transcription_id
                let left = 0;
                let right = prevChunks.length;

                while (left < right) {
                    const mid = (left + right) >> 1;
                    const cmp =
                        prevChunks[mid].transcription_id.localeCompare(
                            transcription_id,
                        );

                    if (cmp <= 0) {
                        left = mid + 1;
                    } else {
                        right = mid;
                    }
                }

                return [
                    ...prevChunks.slice(0, left),
                    newChunk,
                    ...prevChunks.slice(left),
                ];
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
        const sections: (TranscriptSection & {
            chunks: TranscriptChunkWithId[];
        })[] = [];

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
                sections[sections.length - 1].chunks.push(chunk);
            } else {
                // Create a new section for this speaker
                sections.push({
                    speaker,
                    text,
                    chunks: [chunk],
                });
            }
        }

        // Reverse so most recent speaker is at the top
        return sections.reverse();
    }, [transcriptChunks]);

    // Maintain scroll position when new content is added at the top
    useEffect(() => {
        const viewport = viewportRef.current;
        if (!viewport || !shouldMaintainScrollRef.current) {
            return;
        }

        // Wait for DOM to update
        requestAnimationFrame(() => {
            const newScrollHeight = viewport.scrollHeight;
            const heightDifference =
                newScrollHeight - previousScrollHeightRef.current;

            if (heightDifference > 0) {
                // New content was added, adjust scroll to maintain position
                viewport.scrollTop += heightDifference;
            }

            // Reset flag
            shouldMaintainScrollRef.current = false;
        });
    }, [transcript]);

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
        const handleUpdateAIAnalysisTag = (message: UpdateAIAnalysisTag) => {
            // Update insight tag in local state
            setInsights((prevState) =>
                prevState.map((insight) =>
                    insight.analysis_id === message.analysis_id
                        ? { ...insight, tag: message.tag }
                        : insight,
                ),
            );
        };

        ws.registerMessageHandler(
            "update_ai_analysis_tag",
            handleUpdateAIAnalysisTag,
        );

        return () => {
            ws.deregisterMessageHandler("update_ai_analysis_tag");
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
    const statusText = isConnected
        ? "Recording..."
        : connectionState === "connecting"
          ? "Connecting..."
          : "Ready to Start";
    const statusColor = isConnected
        ? "red"
        : connectionState === "connecting"
          ? "yellow"
          : "gray";

    // Callback to register chunk refs from child components
    const handleRegisterChunkRef = useCallback(
        (transcriptionId: string, element: HTMLDivElement) => {
            chunkRefs.current.set(transcriptionId, element);
        },
        [],
    );

    return (
        <Box
            style={{
                height: "calc(100dvh - 60px - 32px)",
                width: "100%",
                display: "flex",
                flexDirection: "column",
            }}
        >
            <WebSocketErrorBanner show={showError && !!ws.error} />

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
                {isMobile ? (
                    <MobileLayout
                        transcript={transcript}
                        insights={insights}
                        projectName={projectName}
                        connectionState={connectionState}
                        statusText={statusText}
                        statusColor={statusColor}
                        highlightedTranscriptId={highlightedTranscriptId}
                        highlightedSpan={highlightedSpan}
                        highlightAnimationKey={highlightAnimationKey}
                        viewportRef={viewportRef}
                        isWebSocketConnected={
                            ws.connectionStatus === "connected"
                        }
                        onRegisterChunkRef={handleRegisterChunkRef}
                        onStarInsight={handleStarInsight}
                        onUnstarInsight={handleUnstarInsight}
                        onDismissInsight={handleDismissInsight}
                        onUndoDismiss={handleUndoDismiss}
                        onSpanClick={handleSpanClick}
                        onStartRecording={startSendingAudio}
                        onStopRecording={stopSendingAudio}
                    />
                ) : (
                    <DesktopLayout
                        transcript={transcript}
                        insights={insights}
                        projectName={projectName}
                        connectionState={connectionState}
                        statusText={statusText}
                        statusColor={statusColor}
                        highlightedTranscriptId={highlightedTranscriptId}
                        highlightedSpan={highlightedSpan}
                        highlightAnimationKey={highlightAnimationKey}
                        viewportRef={viewportRef}
                        isWebSocketConnected={
                            ws.connectionStatus === "connected"
                        }
                        onRegisterChunkRef={handleRegisterChunkRef}
                        onStarInsight={handleStarInsight}
                        onUnstarInsight={handleUnstarInsight}
                        onDismissInsight={handleDismissInsight}
                        onUndoDismiss={handleUndoDismiss}
                        onSpanClick={handleSpanClick}
                        onStartRecording={startSendingAudio}
                        onStopRecording={stopSendingAudio}
                    />
                )}
            </Box>
        </Box>
    );
}
