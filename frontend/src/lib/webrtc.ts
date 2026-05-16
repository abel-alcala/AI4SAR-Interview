// Configuration

import type { Envelope, Message, SignalingMessage } from "./message";
import { toWebSocketUrl } from "./url-utils";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "/api";
const BACKEND = BACKEND_URL + "/ws";

export const SIGNALING_SERVER_URL = toWebSocketUrl(BACKEND);

function getIceServers(): RTCIceServer[] {
    const servers: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
    const username = import.meta.env.VITE_METERED_TURN_USERNAME;
    const credential = import.meta.env.VITE_METERED_TURN_CREDENTIAL;
    if (username && credential) {
        servers.push(
            { urls: "stun:stun.relay.metered.ca:80" },
            { urls: "turn:a.relay.metered.ca:80", username, credential },
            { urls: "turn:a.relay.metered.ca:80?transport=tcp", username, credential },
            { urls: "turn:a.relay.metered.ca:443", username, credential },
            { urls: "turns:a.relay.metered.ca:443?transport=tcp", username, credential },
        );
    }
    return servers;
}

/**
 * BadConfiguration error
 *
 * This is when the web admin did not configure
 * the server correctly.
 */
export class BadConfiguration extends Error {
    constructor(message: string) {
        super(message);
        this.name = "BadConfiguration";
    }
}

export function createWebRTCClient({
    onConnectionChange,
    sendMessage,
}: {
    onConnectionChange: (
        state: "connected" | "disconnected" | "failed" | "connecting",
    ) => void;
    sendMessage: (message: Message) => void;
}) {
    onConnectionChange("disconnected");

    let localStream: MediaStream, pc: RTCPeerConnection;

    async function handleWebsocketSignaling(msg: SignalingMessage) {
        if (!pc) {
            return;
        }

        if (msg.type === "answer") {
            await pc.setRemoteDescription(
                new RTCSessionDescription(msg.data.sdp),
            );
        } else if (msg.type === "ice_candidate") {
            await pc.addIceCandidate(new RTCIceCandidate(msg.data.candidate));
        }
    }

    async function startAudioStream() {
        onConnectionChange("connecting");
        console.log("Starting audio stream...");
        try {
            if (pc) {
                pc.close();
            }
            pc = new RTCPeerConnection({ iceServers: getIceServers() });

            pc.onicecandidate = (event) => {
                if (event.candidate) {
                    console.log("Sending ICE candidate:", event.candidate);
                    sendMessage({
                        type: "ice_candidate",
                        data: {
                            candidate: event.candidate,
                        },
                    });
                }
            };

            pc.onconnectionstatechange = () => {
                if (pc.connectionState === "connected") {
                    onConnectionChange("connected");
                } else if (
                    pc.connectionState === "disconnected" ||
                    pc.connectionState === "failed"
                ) {
                    onConnectionChange("disconnected");
                }
            };

            localStream = await setupLocalStream();

            // Add local stream to peer
            console.log("Adding local stream to peer connection");
            localStream.getTracks().forEach((track) => {
                pc.addTrack(track, localStream);
            });

            console.log("Creating offer...");
            await createAndSendOffer(pc, {
                sendMessage,
            });
            console.log("Offer sent, waiting for answer...");
        } catch (e) {
            console.error("Failed to start audio stream:", e);
            onConnectionChange("disconnected");
            throw e;
        }
    }

    async function stopAudioStream() {
        onConnectionChange("disconnected");
        localStream?.getTracks().forEach((track) => track.stop());

        if (pc) {
            pc.close();
        }
    }

    return { startAudioStream, stopAudioStream, handleWebsocketSignaling };
}

/**
 * Initialize WebSocket connection and setup message handler
 * @param onSignal - callback to handle incoming signaling data
 *
 * @returns the WebSocket instance
 */
export function initWebSocket(onSignal: (msg: Message) => void) {
    const ws = new WebSocket(SIGNALING_SERVER_URL);
    ws.onmessage = ({ data }) => {
        const msg = JSON.parse(data) as Envelope;
        onSignal(msg.message);
    };

    return ws;
}

/**
 * Setup local audio stream in preparation for WebRTC
 *
 * Requires a secure context (HTTPS or localhost)
 *
 * @returns Local audio stream
 */
async function setupLocalStream() {
    if (window.isSecureContext === false) {
        throw new BadConfiguration(
            "WebRTC requires a secure context (HTTPS or localhost)",
        );
    }

    // Stream just the audio
    return await navigator.mediaDevices.getUserMedia({
        audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
        },
        video: false,
    });
}
/**
 * Send signaling data over WebSocket
 * @param {Object} message - { sdp } or { candidate }
 */
export function sendMessage(message: Message, ws: WebSocket) {
    const envelope: Envelope = { message };
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(envelope));
    }
}
/**
 * Create and send an offer
 */
export async function createAndSendOffer(
    pc: RTCPeerConnection,
    opts: { sendMessage: (message: Message) => void },
) {
    if (!pc) throw new Error("PeerConnection not initialized");
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    opts.sendMessage({
        type: "offer",
        data: {
            sdp: pc.localDescription as RTCSessionDescriptionInit,
        },
    });
}
