import "@mantine/core/styles.css";

import { useEffect } from "react";
import { MantineProvider, Container } from "@mantine/core";
import { useAuth } from "react-oidc-context";
import {
    BrowserRouter as Router,
    Routes,
    Route,
    useLocation,
    useParams,
} from "react-router-dom";
import AuthCallback from "./AuthCallback";
import ProjectList from "./components/ProjectList";
import AppLayout from "./AppLayout";
import { AudioSender } from "./components/AudioSender";
import { WebSocketProvider } from "./lib/WebSocketProvider";

function ProjectPage() {
    const { projectId } = useParams<{ projectId: string }>();

    return (
        <WebSocketProvider projectId={projectId}>
            <Container
                fluid
                styles={{
                    root: {
                        paddingInline: 0,
                    },
                }}
            >
                <AudioSender projectId={projectId} />
            </Container>
        </WebSocketProvider>
    );
}

function AppContent() {
    const auth = useAuth();
    const location = useLocation();

    // Auto sign-in when launched from IntelliSAR (URL contains ?incidentId=)
    useEffect(() => {
        if (!auth.isAuthenticated && !auth.isLoading && !auth.activeNavigator) {
            const params = new URLSearchParams(window.location.search);
            if (params.has("incidentId")) {
                const loginHint = params.get("login_hint");

                // Strip login_hint from returnTo so it doesnt appear after login
                const returnParams = new URLSearchParams(window.location.search);
                returnParams.delete("login_hint");
                const returnTo = returnParams.toString()
                    ? `?${returnParams.toString()}`
                    : "";

                auth.signinRedirect({
                    state: { returnTo },
                    extraQueryParams: loginHint
                        ? { login_hint: loginHint }
                        : undefined,
                });
            }
        }
    }, [auth, auth.isAuthenticated, auth.isLoading, auth.activeNavigator]);

    // Handle callback route
    if (location.pathname === "/auth/callback") {
        return <AuthCallback />;
    }

    // Handle loading state
    if (auth.isLoading) {
        return (
            <div
                style={{
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    height: "100vh",
                }}
            >
                Loading...
            </div>
        );
    }

    // Handle authentication errors
    if (auth.error) {
        return (
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                    alignItems: "center",
                    height: "100vh",
                    gap: "1rem",
                }}
            >
                <h2>Authentication Error</h2>
                <p>Error: {auth.error.message}</p>
                <button
                    onClick={() => auth.signinRedirect()}
                    style={{
                        padding: "12px 24px",
                        fontSize: "16px",
                        color: "#fff",
                        backgroundColor: "#007bff",
                        border: "none",
                        borderRadius: "5px",
                        cursor: "pointer",
                    }}
                >
                    Try Again
                </button>
            </div>
        );
    }

    // If user is authenticated, show the main app with routing
    if (auth.isAuthenticated) {
        return (
            <AppLayout user={auth.user} onSignOut={() => auth.removeUser()}>
                <Routes>
                    <Route path="/" element={<ProjectList />} />
                    <Route
                        path="/project/:projectId"
                        element={<ProjectPage />}
                    />
                </Routes>
            </AppLayout>
        );
    }

    // If not authenticated, show login page
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "center",
                height: "100vh",
                gap: "1rem",
            }}
        >
            <h1>Welcome to Interview Helper</h1>
            <p>Please sign in with your account to continue.</p>
            <button
                onClick={() => auth.signinRedirect()}
                style={{
                    padding: "12px 24px",
                    fontSize: "16px",
                    color: "#fff",
                    backgroundColor: "#4285f4",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                    transition: "background-color 0.3s ease",
                }}
                onMouseEnter={(e) =>
                    (e.currentTarget.style.backgroundColor = "#357ae8")
                }
                onMouseLeave={(e) =>
                    (e.currentTarget.style.backgroundColor = "#4285f4")
                }
            >
                Sign in with Identity Provider
            </button>
        </div>
    );
}

function App() {
    return (
        <MantineProvider>
            <Router>
                <Routes>
                    <Route path="/*" element={<AppContent />} />
                </Routes>
            </Router>
        </MantineProvider>
    );
}

export default App;
