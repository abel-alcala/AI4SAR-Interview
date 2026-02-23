import {
    Badge,
    Box,
    Center,
    Group,
    Loader,
    Paper,
    ScrollArea,
    Stack,
    Text,
    Title,
} from "@mantine/core";
import { TranscriptSection } from "./TranscriptSection";

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

interface TranscriptViewProps {
    transcript: TranscriptSectionType[];
    projectName: string | null;
    isConnected: boolean;
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
    showLiveBadge?: boolean;
    titleOrder?: 4 | 5;
}

export function TranscriptView({
    transcript,
    projectName,
    isConnected,
    statusText,
    statusColor,
    highlightedTranscriptId,
    highlightedSpan,
    highlightAnimationKey,
    viewportRef,
    isWebSocketConnected,
    onRegisterChunkRef,
    showLiveBadge = true,
    titleOrder = 4,
}: TranscriptViewProps) {
    return (
        <Paper withBorder shadow="sm" radius="lg" style={{ height: "100%" }}>
            <Stack gap="xs" style={{ height: "100%" }}>
                <Group justify="space-between" p="md" pb={0}>
                    <Group gap="xs">
                        <Title order={titleOrder}>
                            {projectName != null
                                ? titleOrder === 4
                                    ? `${projectName} - Transcript`
                                    : projectName
                                : titleOrder === 4
                                  ? "Transcript"
                                  : "Interview"}
                        </Title>
                        {showLiveBadge && isConnected && (
                            <Badge color="red">
                                {titleOrder === 4 ? "Live" : "Live"}
                            </Badge>
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
                                {transcript.map((section, index) => (
                                    <TranscriptSection
                                        key={index}
                                        section={section}
                                        highlightedTranscriptId={
                                            highlightedTranscriptId
                                        }
                                        highlightedSpan={highlightedSpan}
                                        highlightAnimationKey={
                                            highlightAnimationKey
                                        }
                                        onRegisterRef={onRegisterChunkRef}
                                    />
                                ))}
                            </Stack>
                        ) : !isWebSocketConnected ? (
                            <Center py="xl">
                                <Stack align="center" gap="md">
                                    <Loader size="lg" />
                                    <Text c="dimmed" size="sm">
                                        Connecting...
                                    </Text>
                                </Stack>
                            </Center>
                        ) : (
                            <Text c="dimmed" ta="center" py="xl">
                                Your transcript will appear here.
                            </Text>
                        )}
                    </Box>
                </ScrollArea>
            </Stack>
        </Paper>
    );
}
