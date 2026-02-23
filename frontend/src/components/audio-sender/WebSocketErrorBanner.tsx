import { Alert, Box } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";

interface WebSocketErrorBannerProps {
    show: boolean;
}

export function WebSocketErrorBanner({ show }: WebSocketErrorBannerProps) {
    if (!show) return null;

    return (
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
                Your connection to the server was lost. Please refresh the page
                to try reconnecting.
            </Alert>
        </Box>
    );
}
