import {
    ActionIcon,
    Box,
    Group,
    Paper,
    ScrollArea,
    Stack,
    Tabs,
    Text,
    Title,
} from "@mantine/core";
import { IconAlertTriangle, IconBulb, IconX } from "@tabler/icons-react";
import type { AnalysisRow } from "../../lib/message";

interface InsightsPanelProps {
    insights: AnalysisRow[];
    onDismiss: (analysisId: string) => void;
    onSpanClick?: (transcriptId: string, spanText: string) => void;
}

export function InsightsPanel({
    insights,
    onDismiss,
    onSpanClick,
}: InsightsPanelProps) {
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
                        <Box pb="120px">
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
                        </Box>
                    </ScrollArea>
                </Tabs.Panel>

                <Tabs.Panel
                    value="dismissed"
                    pt="md"
                    style={{ flex: 1, overflow: "hidden" }}
                >
                    <ScrollArea h="100%" type="auto">
                        <Box pb="120px">
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
                        </Box>
                    </ScrollArea>
                </Tabs.Panel>
            </Tabs>
        </Paper>
    );
}
