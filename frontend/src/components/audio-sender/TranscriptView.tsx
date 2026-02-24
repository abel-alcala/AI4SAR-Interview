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
    Menu,
    ActionIcon,
} from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { useAuth } from "react-oidc-context";
import {
    downloadTranscript,
    downloadQuestions,
    downloadAudio,
} from "../../lib/api";
import { useState } from "react";
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
    projectId?: string;
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
    projectId,
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
    const auth = useAuth();
    const [downloading, setDownloading] = useState<string | null>(null);

    const handleDownloadTranscript = async () => {
        if (!projectId || !auth.user?.access_token) return;
        try {
            setDownloading("transcript");
            await downloadTranscript(projectId, auth.user.access_token);
        } catch (error) {
            console.error("Failed to download transcript:", error);
        } finally {
            setDownloading(null);
        }
    };

    const handleDownloadQuestions = async () => {
        if (!projectId || !auth.user?.access_token) return;
        try {
            setDownloading("questions");
            await downloadQuestions(projectId, auth.user.access_token);
        } catch (error) {
            console.error("Failed to download questions:", error);
        } finally {
            setDownloading(null);
        }
    };

    const handleDownloadAudio = async () => {
        if (!projectId || !auth.user?.access_token) return;
        try {
            setDownloading("audio");
            await downloadAudio(projectId, auth.user.access_token);
        } catch (error) {
            console.error("Failed to download audio:", error);
        } finally {
            setDownloading(null);
        }
    };

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
                    <Group gap="xs">
                        <Text size="sm" c={statusColor}>
                            {statusText}
                        </Text>
                        {projectId && (
                            <Menu shadow="md" width={200}>
                                <Menu.Target>
                                    <ActionIcon
                                        variant="subtle"
                                        color="gray"
                                        size="lg"
                                        loading={downloading !== null}
                                        aria-label="Open Download Options"
                                    >
                                        <IconDownload size={18} />
                                    </ActionIcon>
                                </Menu.Target>

                                <Menu.Dropdown>
                                    <Menu.Label>Downloads</Menu.Label>
                                    <Menu.Item
                                        leftSection={<IconDownload size={14} />}
                                        onClick={handleDownloadAudio}
                                        disabled={downloading !== null}
                                    >
                                        Download Audio
                                    </Menu.Item>
                                    <Menu.Item
                                        leftSection={<IconDownload size={14} />}
                                        onClick={handleDownloadTranscript}
                                        disabled={downloading !== null}
                                    >
                                        Download Transcript
                                    </Menu.Item>
                                    <Menu.Item
                                        leftSection={<IconDownload size={14} />}
                                        onClick={handleDownloadQuestions}
                                        disabled={downloading !== null}
                                    >
                                        Download Questions
                                    </Menu.Item>
                                </Menu.Dropdown>
                            </Menu>
                        )}
                    </Group>
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
