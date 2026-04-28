import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "normalize.css";
import App from "./App.tsx";
import { AuthProvider } from "react-oidc-context";
import { OIDC_AUTHORITY, OIDC_CLIENT_ID, SITE_URL, OIDC_CLIENT_SECRET } from "./constants.ts";

console.log("OIDC Config:", {
    authority: OIDC_AUTHORITY,
    client_id: OIDC_CLIENT_ID,
    site_url: SITE_URL,
    redirect_uri: `${SITE_URL}/auth/callback`,
});

const oidc_config = {
    authority: OIDC_AUTHORITY,
    client_id: OIDC_CLIENT_ID,
    client_secret: OIDC_CLIENT_SECRET,
    redirect_uri: `${SITE_URL}/auth/callback`,
    response_type: "code",
    scope: "openid profile email",
};

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <AuthProvider {...oidc_config}>
            <App />
        </AuthProvider>
    </StrictMode>,
);
