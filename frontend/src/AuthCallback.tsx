import { useEffect } from "react";
import { useAuth } from "react-oidc-context";

export default function AuthCallback() {
    const auth = useAuth();

    useEffect(() => {
        if (auth.isAuthenticated) {
            // Restore original URL params if launched from IntelliSAR
            const returnTo =
                (auth.user?.state as { returnTo?: string } | null)?.returnTo ??
                "";
            window.location.href = `/${returnTo}`;
        }
    }, [auth.isAuthenticated, auth.user?.state]);

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
                    onClick={() => (window.location.href = "/")}
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
                    Return to Home
                </button>
            </div>
        );
    }

    return (
        <div
            style={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                height: "100vh",
            }}
        >
            Processing authentication...
        </div>
    );
}
