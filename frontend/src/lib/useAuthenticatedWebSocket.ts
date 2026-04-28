/**
 * WebSocket hook with ticket-based authentication support for the Interview Helper app.
 *
 * This hook implements a secure two-step authentication process:
 * 1. First, it requests an authentication ticket from the backend using the user's JWT token
 * 2. Then, it uses the ticket to establish the WebSocket connection
 *
 * This approach provides enhanced security by ensuring tickets are single-use and time-limited.
 */

import { useEffect, useState, useRef } from "react";
import type { Envelope, Message } from "./message";
import { useAuth } from "react-oidc-context";

type MessageType = Message["type"];
type MessageMap = { [K in MessageType]: Extract<Message, { type: K }> };

export function useAuthenticatedWebSocket(projectId?: string) {
    const [connectionStatus, setConnectionStatus] = useState<
        "disconnected" | "connecting" | "connected"
    >("disconnected");
    const connectionStatusRef = useRef<
        "disconnected" | "connecting" | "connected"
    >("disconnected");

    // Keep ref in sync with state
    // This is for our functions that we define and that are captured.
    // While also causing re-renders on change for parent components
    useEffect(() => {
        connectionStatusRef.current = connectionStatus;
    }, [connectionStatus]);

    const auth = useAuth();
    const [error, setError] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    // Handlers for specific message types
    const messageHandlersRef = useRef<{
        [K in MessageType]?: (msg: Message) => void;
    }>({});

    // Register a handler for a specific message type
    function registerMessageHandler<K extends MessageType>(
        type: K,
        handler: (msg: MessageMap[K]) => void,
    ) {
        // Store as (msg: Message) => void, but allow type narrowing at registration
        const wrappedHandler = handler as (msg: Message) => void;
        if (!messageHandlersRef.current[type]) {
            messageHandlersRef.current[type] = wrappedHandler;
        } else {
            throw Error(
                `Trying to re-register message type ${type} in Websocket`,
            );
        }
    }

    function deregisterMessageHandler<K extends MessageType>(type: K) {
        messageHandlersRef.current[type] = undefined;
    }

    const connect = async () => {
        if (!auth.isAuthenticated || !auth.user?.id_token) {
            setError("User not authenticated");
            return;
        }

        try {
            setConnectionStatus("connecting");
            setError(null);

            // Get backend URL from environment
            const backendUrl = import.meta.env.VITE_BACKEND_URL || "/api";
            // For relative URLs, construct WebSocket URL from current location
            const wsUrl = backendUrl.startsWith("/")
                ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${backendUrl}`
                : backendUrl.replace("http", "ws");

            // Step 1: Request an authentication ticket from the backend
            const ticketResponse = await fetch(`${backendUrl}/auth/ticket`, {
                method: "GET",
                headers: {
                    Authorization: `Bearer ${auth.user.id_token}`,
                    "Content-Type": "application/json",
                },
            });

            if (!ticketResponse.ok) {
                if (ticketResponse.status === 429) {
                    throw new Error(
                        "Rate limit exceeded. Too many connection attempts. Please wait a moment and try again.",
                    );
                }
                throw new Error(
                    `Failed to obtain authentication ticket: ${ticketResponse.status}`,
                );
            }

            const ticketData = await ticketResponse.json();
            const ticketId = ticketData.ticket_id;

            console.log("Obtained authentication ticket:", ticketId);

            // Step 2: Create WebSocket connection with the ticket and projectId
            const wsParams = new URLSearchParams({ ticket_id: ticketId });
            if (projectId) {
                wsParams.append("project_id", projectId);
            }
            const ws = new WebSocket(`${wsUrl}/ws?${wsParams.toString()}`);

            ws.onopen = () => {
                console.log(
                    "WebSocket connected with ticket-based authentication",
                );
                setConnectionStatus("connected");
            };

            ws.onmessage = (event) => {
                try {
                    const envelope = JSON.parse(event.data) as Envelope;
                    if (!envelope?.message?.type) {
                        console.error("Invalid WebSocket message:", envelope);
                        setError(
                            "Received invalid message format from server!",
                        );
                        return;
                    }
                    const message = envelope.message;

                    // Call registered handlers for this type
                    const handler =
                        messageHandlersRef.current[message.type as MessageType];
                    if (handler) {
                        handler(message);
                    }
                } catch (e) {
                    console.error("Failed to parse WebSocket message:", e);
                }
            };

            ws.onclose = (event) => {
                console.log(
                    "WebSocket disconnected:",
                    event.code,
                    event.reason,
                );
                setConnectionStatus("disconnected");

                if (event.code === 1008) {
                    setError(
                        "Authentication failed - ticket invalid or expired",
                    );
                } else if (event.code !== 1000) {
                    setError(
                        `Connection closed: ${event.reason || "Unknown error"}`,
                    );
                }
            };

            ws.onerror = (event) => {
                console.error("WebSocket error:", event);
                setError("WebSocket connection error");
                setConnectionStatus("disconnected");
            };

            wsRef.current = ws;
        } catch (err) {
            console.error("Failed to connect to WebSocket:", err);
            const errorMessage =
                err instanceof Error ? err.message : "Unknown error";
            setError(`Failed to connect: ${errorMessage}`);
            setConnectionStatus("disconnected");
        }
    };

    const disconnect = () => {
        if (wsRef.current) {
            wsRef.current.close(1000, "User disconnected");
            wsRef.current = null;
        }
    };

    const sendMessage = (message: Message) => {
        if (wsRef.current && connectionStatusRef.current === "connected") {
            const envelope = { message } as Envelope;
            wsRef.current.send(JSON.stringify(envelope));
            return true;
        }
        return false;
    };

    // Connect on mount, disconnect on unmount
    // Only connect if projectId is provided
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (auth.isLoading) {
            return; // Wait until we loaded auth
        }
        if (!projectId) {
            return; // Don't connect without a projectId
        }
        connect();
        return () => {
            disconnect();
        };
    }, [auth.isLoading, projectId]);

    return {
        connectionStatus,
        error,
        connect,
        disconnect,
        sendMessage,
        isConnected: connectionStatus === "connected",
        registerMessageHandler,
        deregisterMessageHandler,
    };
}
