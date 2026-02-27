const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "/api";

export interface ProjectListing {
    id: string;
    name: string;
    creator_name: string;
    creator_user_id: string;
    created_at: string;
}

export interface CurrentUser {
    user_id: string;
    full_name: string;
    oidc_id: string;
}

export interface ProjectInfo extends ProjectListing {
    session_count: number;
}

/**
 * Helper function to make authenticated API calls
 */
async function authenticatedFetch<T>(
    endpoint: string,
    token: string,
    options?: RequestInit,
): Promise<T> {
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
        ...options,
        headers: {
            ...options?.headers,
            Authorization: `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        throw new Error(
            `API request failed: ${response.status} ${response.statusText}`,
        );
    }

    return response.json();
}

/**
 * Get current user information
 */
export async function getCurrentUser(token: string): Promise<CurrentUser> {
    return authenticatedFetch<CurrentUser>("/user/me", token);
}

/**
 * Fetch all projects from the backend
 */
export async function fetchProjects(token: string): Promise<ProjectListing[]> {
    return authenticatedFetch<ProjectListing[]>("/project", token);
}

/**
 * Create a new project
 */
export async function createProject(
    projectName: string,
    token: string,
): Promise<ProjectListing> {
    return authenticatedFetch<ProjectListing>(
        `/project?project_name=${encodeURIComponent(projectName)}`,
        token,
        { method: "POST" },
    );
}

/**
 * Download transcript for a project
 */
export async function downloadTranscript(
    projectId: string,
    token: string,
): Promise<void> {
    const response = await fetch(
        `${BACKEND_URL}/project/${projectId}/download/transcript`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        },
    );

    if (!response.ok) {
        throw new Error(
            `Failed to download transcript: ${response.status} ${response.statusText}`,
        );
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
        response.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "transcript.txt";
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/**
 * Download questions for a project
 */
export async function downloadQuestions(
    projectId: string,
    token: string,
): Promise<void> {
    const response = await fetch(
        `${BACKEND_URL}/project/${projectId}/download/questions`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        },
    );

    if (!response.ok) {
        throw new Error(
            `Failed to download questions: ${response.status} ${response.statusText}`,
        );
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
        response.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "questions.txt";
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/**
 * Download audio for a project
 */
export async function downloadAudio(
    projectId: string,
    token: string,
): Promise<void> {
    const response = await fetch(
        `${BACKEND_URL}/project/${projectId}/download/audio`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        },
    );

    if (!response.ok) {
        throw new Error(
            `Failed to download audio: ${response.status} ${response.statusText}`,
        );
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
        response.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "audio.wav";
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/**
 * Get project info including session count
 */
export async function getProjectInfo(
    projectId: string,
    token: string,
): Promise<ProjectInfo> {
    return authenticatedFetch<ProjectInfo>(`/project/${projectId}/info`, token);
}

/**
 * Delete a project
 */
export async function deleteProject(
    projectId: string,
    confirmedName: string,
    token: string,
): Promise<void> {
    const response = await fetch(
        `${BACKEND_URL}/project/${projectId}?confirmed_name=${encodeURIComponent(confirmedName)}`,
        {
            method: "DELETE",
            headers: {
                Authorization: `Bearer ${token}`,
            },
        },
    );

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
            errorText || `Failed to delete project: ${response.status}`,
        );
    }
}
