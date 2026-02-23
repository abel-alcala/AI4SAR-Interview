import { Box, Highlight, Text, Title } from "@mantine/core";
import { useEffect, useRef } from "react";

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

interface TranscriptSectionProps {
    section: TranscriptSectionType;
    highlightedTranscriptId: string | null;
    highlightedSpan: string | null;
    highlightAnimationKey: number;
    onRegisterRef: (transcriptionId: string, element: HTMLDivElement) => void;
}

export function TranscriptSection({
    section,
    highlightedTranscriptId,
    highlightedSpan,
    highlightAnimationKey,
    onRegisterRef,
}: TranscriptSectionProps) {
    const boxRef = useRef<HTMLDivElement>(null);

    // Register the ref with parent component for ALL chunks in this section
    useEffect(() => {
        if (boxRef.current && section.chunks.length > 0) {
            // Register this element for all chunk IDs in this section
            for (const chunk of section.chunks) {
                onRegisterRef(chunk.transcription_id, boxRef.current);
            }
        }
    }, [section.chunks, onRegisterRef]);

    // Check if this section contains the highlighted chunk
    const containsHighlight =
        highlightedTranscriptId &&
        section.chunks.some(
            (c) => c.transcription_id === highlightedTranscriptId,
        );

    return (
        <Box
            ref={boxRef}
            style={{
                backgroundColor: containsHighlight
                    ? "rgba(255, 255, 0, 0.1)"
                    : undefined,
                padding: containsHighlight ? "8px" : undefined,
                borderRadius: containsHighlight ? "4px" : undefined,
                transition: "background-color 0.3s ease",
                animation: containsHighlight
                    ? `${highlightAnimationKey % 2 === 0 ? "highlightPulse" : "highlightPulse-alt"} 0.4s ease-out`
                    : undefined,
            }}
        >
            <Title order={6} mb="xs">
                {section.speaker ?? "Unknown Speaker"}
            </Title>
            {highlightedSpan ? (
                <Highlight
                    highlight={highlightedSpan}
                    style={{
                        whiteSpace: "pre-wrap",
                        lineHeight: 1.6,
                    }}
                >
                    {section.text}
                </Highlight>
            ) : (
                <Text
                    style={{
                        whiteSpace: "pre-wrap",
                        lineHeight: 1.6,
                    }}
                >
                    {section.text}
                </Text>
            )}
        </Box>
    );
}
