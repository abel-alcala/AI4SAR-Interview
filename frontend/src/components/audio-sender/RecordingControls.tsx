import { Affix, Button, Center, Group, Loader, Paper } from "@mantine/core";
import { IconMicrophone } from "@tabler/icons-react";

interface RecordingControlsProps {
    connectionState: "disconnected" | "connected" | "connecting" | "failed";
    isWebSocketConnected: boolean;
    onStartRecording: () => void;
    onStopRecording: () => void;
    size?: "lg" | "xl";
    minWidth?: number;
}

export function RecordingControls({
    connectionState,
    isWebSocketConnected,
    onStartRecording,
    onStopRecording,
    size = "xl",
    minWidth = 260,
}: RecordingControlsProps) {
    const isConnected = connectionState === "connected";
    const isConnecting = connectionState === "connecting";
    const buttonText = isConnected ? "Stop Recording" : "Start Recording";
    const buttonColor = isConnected ? "red" : "green";
    const buttonVariant = isConnected ? "filled" : "light";

    return (
        <Affix position={{ bottom: 24, left: 0, right: 0 }}>
            <Center>
                <Paper shadow="xl" radius="xl" p="sm" withBorder>
                    <Group gap="md" align="center">
                        <Button
                            variant={buttonVariant}
                            color={buttonColor}
                            leftSection={
                                isConnecting ? (
                                    <Loader size="sm" color="white" />
                                ) : (
                                    <IconMicrophone size={18} />
                                )
                            }
                            size={size}
                            radius="xl"
                            loading={isConnecting}
                            disabled={!isWebSocketConnected && !isConnecting}
                            onClick={() => {
                                if (connectionState === "disconnected") {
                                    onStartRecording();
                                } else if (connectionState === "connected") {
                                    onStopRecording();
                                }
                            }}
                            style={{
                                minWidth,
                            }}
                        >
                            {buttonText}
                        </Button>
                    </Group>
                </Paper>
            </Center>
        </Affix>
    );
}
