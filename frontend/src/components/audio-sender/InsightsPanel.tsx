import {
    ActionIcon,
    Badge,
    Box,
    Divider,
    Group,
    Paper,
    ScrollArea,
    Stack,
    Tabs,
    Text,
    Title,
    Tooltip,
} from "@mantine/core";
import {
    IconArrowBackUp,
    IconBulb,
    IconCheck,
    IconStar,
    IconStarFilled,
    IconX,
} from "@tabler/icons-react";
import { Fragment } from "react";
import type { AnalysisRow } from "../../lib/message";

interface InsightsPanelProps {
    insights: AnalysisRow[];
    onStar: (analysisId: string) => void;
    onUnstar: (analysisId: string) => void;
    onDismissAsAnswered: (analysisId: string) => void;
    onDismissNotAnswered: (analysisId: string) => void;
    onUndoDismiss: (analysisId: string) => void;
    onSpanClick?: (transcriptId: string, spanText: string) => void;
}

export function InsightsPanel({
    insights,
    onStar,
    onUnstar,
    onDismissAsAnswered,
    onDismissNotAnswered,
    onUndoDismiss,
    onSpanClick,
}: InsightsPanelProps) {
    const activeInsights = insights.filter(
        (a) =>
            a.tag !== "starred" &&
            a.tag !== "dismissed" &&
            a.tag !== "starred_dismissed",
    );
    const starredInsights = insights
        .filter((a) => a.tag === "starred")
        .sort((a, b) => {
            // Sort by time_tag_changed, oldest first (newest at bottom)
            const timeA = a.time_tag_changed
                ? new Date(a.time_tag_changed).getTime()
                : 0;
            const timeB = b.time_tag_changed
                ? new Date(b.time_tag_changed).getTime()
                : 0;
            return timeA - timeB;
        });
    const dismissedInsights = insights
        .filter((a) => a.tag === "dismissed" || a.tag === "starred_dismissed")
        .sort((a, b) => {
            // Sort by time_tag_changed, oldest first
            const timeA = a.time_tag_changed
                ? new Date(a.time_tag_changed).getTime()
                : 0;
            const timeB = b.time_tag_changed
                ? new Date(b.time_tag_changed).getTime()
                : 0;
            return timeA - timeB;
        });

    const renderActiveInsight = (analysis: AnalysisRow) => (
        <Group key={analysis.analysis_id} gap="xs" align="flex-start">
            <Stack gap={4} style={{ flex: 1 }}>
                <Text size="sm">
                    <Text component="span" size="xs" c="dimmed" fw={600}>
                        Q{analysis.ordinal}{" "}
                    </Text>
                    {analysis.text}
                </Text>
                {analysis.span && (
                    <Text
                        size="xs"
                        c="dimmed"
                        fs="italic"
                        style={{
                            cursor:
                                analysis.transcript_span_id && onSpanClick
                                    ? "pointer"
                                    : "default",
                            textDecoration:
                                analysis.transcript_span_id && onSpanClick
                                    ? "underline"
                                    : "none",
                        }}
                        onClick={() => {
                            if (
                                analysis.transcript_span_id &&
                                onSpanClick &&
                                analysis.span
                            ) {
                                onSpanClick(
                                    analysis.transcript_span_id,
                                    analysis.span,
                                );
                            }
                        }}
                    >
                        "{analysis.span}"
                    </Text>
                )}
            </Stack>
            <Group gap={4}>
                <Tooltip label="Star this question">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="yellow"
                        onClick={() => onStar(analysis.analysis_id)}
                        aria-label="Star question"
                    >
                        <IconStar size={14} />
                    </ActionIcon>
                </Tooltip>
                <Tooltip label="Mark as answered">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="green"
                        onClick={() =>
                            onDismissAsAnswered(analysis.analysis_id)
                        }
                        aria-label="Mark as answered"
                    >
                        <IconCheck size={14} />
                    </ActionIcon>
                </Tooltip>
                <Tooltip label="Dismiss (not answered)">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="gray"
                        onClick={() =>
                            onDismissNotAnswered(analysis.analysis_id)
                        }
                        aria-label="Dismiss question"
                    >
                        <IconX size={14} />
                    </ActionIcon>
                </Tooltip>
            </Group>
        </Group>
    );

    const renderStarredInsight = (analysis: AnalysisRow) => (
        <Group key={analysis.analysis_id} gap="xs" align="flex-start">
            <Stack gap={4} style={{ flex: 1 }}>
                <Text size="sm">
                    <Text component="span" size="xs" c="dimmed" fw={600}>
                        Q{analysis.ordinal}{" "}
                    </Text>
                    {analysis.text}
                </Text>
                {analysis.span && (
                    <Text
                        size="xs"
                        c="dimmed"
                        fs="italic"
                        style={{
                            cursor:
                                analysis.transcript_span_id && onSpanClick
                                    ? "pointer"
                                    : "default",
                            textDecoration:
                                analysis.transcript_span_id && onSpanClick
                                    ? "underline"
                                    : "none",
                        }}
                        onClick={() => {
                            if (
                                analysis.transcript_span_id &&
                                onSpanClick &&
                                analysis.span
                            ) {
                                onSpanClick(
                                    analysis.transcript_span_id,
                                    analysis.span,
                                );
                            }
                        }}
                    >
                        "{analysis.span}"
                    </Text>
                )}
            </Stack>
            <Group gap={4}>
                <Tooltip label="Remove star">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="yellow"
                        onClick={() => onUnstar(analysis.analysis_id)}
                        aria-label="Unstar question"
                    >
                        <IconStarFilled size={14} />
                    </ActionIcon>
                </Tooltip>
                <Tooltip label="Mark as answered">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="green"
                        onClick={() =>
                            onDismissAsAnswered(analysis.analysis_id)
                        }
                        aria-label="Mark as answered"
                    >
                        <IconCheck size={14} />
                    </ActionIcon>
                </Tooltip>
                <Tooltip label="Dismiss (not answered)">
                    <ActionIcon
                        size="sm"
                        variant="subtle"
                        color="gray"
                        onClick={() =>
                            onDismissNotAnswered(analysis.analysis_id)
                        }
                        aria-label="Dismiss question"
                    >
                        <IconX size={14} />
                    </ActionIcon>
                </Tooltip>
            </Group>
        </Group>
    );

    const renderDismissedInsight = (analysis: AnalysisRow) => (
        <Group key={analysis.analysis_id} gap="xs" align="flex-start">
            <Stack gap={4} style={{ flex: 1 }}>
                <Group gap={4}>
                    {analysis.tag === "starred_dismissed" && (
                        <IconStarFilled
                            size={14}
                            color="var(--mantine-color-yellow-6)"
                        />
                    )}
                    {analysis.was_asked && (
                        <Badge size="xs" color="green" variant="light">
                            Asked
                        </Badge>
                    )}
                    {analysis.was_asked === false && (
                        <Badge size="xs" color="gray" variant="light">
                            Not Asked
                        </Badge>
                    )}
                    <Text size="sm" c="dimmed">
                        <Text component="span" size="xs" fw={600}>
                            Q{analysis.ordinal}{" "}
                        </Text>
                        {analysis.text}
                    </Text>
                </Group>
                {analysis.span && (
                    <Text
                        size="xs"
                        c="dimmed"
                        fs="italic"
                        style={{
                            cursor:
                                analysis.transcript_span_id && onSpanClick
                                    ? "pointer"
                                    : "default",
                            textDecoration:
                                analysis.transcript_span_id && onSpanClick
                                    ? "underline"
                                    : "none",
                        }}
                        onClick={() => {
                            if (
                                analysis.transcript_span_id &&
                                onSpanClick &&
                                analysis.span
                            ) {
                                onSpanClick(
                                    analysis.transcript_span_id,
                                    analysis.span,
                                );
                            }
                        }}
                    >
                        "{analysis.span}"
                    </Text>
                )}
            </Stack>
            <Tooltip label="Restore question">
                <ActionIcon
                    size="sm"
                    variant="subtle"
                    color="gray"
                    onClick={() => onUndoDismiss(analysis.analysis_id)}
                    aria-label="Restore question"
                >
                    <IconArrowBackUp size={14} />
                </ActionIcon>
            </Tooltip>
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
                    <Tabs.Tab value="active">
                        <Group gap={4}>
                            Active
                            {activeInsights.length > 0 && (
                                <Badge
                                    size="sm"
                                    circle
                                    style={{ minWidth: 20 }}
                                >
                                    {activeInsights.length}
                                </Badge>
                            )}
                        </Group>
                    </Tabs.Tab>
                    <Tabs.Tab value="starred">
                        <Group gap={4}>
                            <IconStarFilled size={14} />
                            Starred
                            {starredInsights.length > 0 && (
                                <Badge
                                    size="sm"
                                    circle
                                    style={{ minWidth: 20 }}
                                >
                                    {starredInsights.length}
                                </Badge>
                            )}
                        </Group>
                    </Tabs.Tab>
                    <Tabs.Tab value="dismissed">Dismissed</Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel
                    value="active"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Box pb="120px" pr="md">
                            <Stack gap="xs">
                                {activeInsights.length === 0 ? (
                                    <Text c="dimmed" size="sm">
                                        No active questions yet. They'll show up
                                        here in real time.
                                    </Text>
                                ) : (
                                    activeInsights.map((analysis, index) => (
                                        <Fragment key={analysis.analysis_id}>
                                            {renderActiveInsight(analysis)}
                                            {index <
                                                activeInsights.length - 1 && (
                                                <Divider />
                                            )}
                                        </Fragment>
                                    ))
                                )}
                            </Stack>
                        </Box>
                    </ScrollArea>
                </Tabs.Panel>

                <Tabs.Panel
                    value="starred"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Box pb="120px" pr="md">
                            <Stack gap="xs">
                                {starredInsights.length === 0 ? (
                                    <Text c="dimmed" size="sm">
                                        No starred questions.
                                    </Text>
                                ) : (
                                    starredInsights.map((analysis, index) => (
                                        <Fragment key={analysis.analysis_id}>
                                            {renderStarredInsight(analysis)}
                                            {index <
                                                starredInsights.length - 1 && (
                                                <Divider />
                                            )}
                                        </Fragment>
                                    ))
                                )}
                            </Stack>
                        </Box>
                    </ScrollArea>
                </Tabs.Panel>

                <Tabs.Panel
                    value="dismissed"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Box pb="120px" pr="md">
                            <Stack gap="xs">
                                {dismissedInsights.length === 0 ? (
                                    <Text c="dimmed" size="sm">
                                        No dismissed questions.
                                    </Text>
                                ) : (
                                    dismissedInsights
                                        .reverse()
                                        .map((analysis, index) => (
                                            <Fragment
                                                key={analysis.analysis_id}
                                            >
                                                {renderDismissedInsight(
                                                    analysis,
                                                )}
                                                {index <
                                                    dismissedInsights.length -
                                                        1 && <Divider />}
                                            </Fragment>
                                        ))
                                )}
                            </Stack>
                        </Box>
                    </ScrollArea>
                </Tabs.Panel>
            </Tabs>
        </Paper>
    );
}
