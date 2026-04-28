import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { AppShell, Group, Text, Avatar, Burger, Menu } from "@mantine/core";
import { User } from "oidc-client-ts";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { fetchProjects } from "./lib/api";
import type { ProjectListing } from "./lib/api";

interface AppLayoutProps {
    user?: User | null;
    onSignOut?: () => void;
    children: ReactNode;
}

export default function AppLayout({
    user,
    onSignOut,
    children,
}: AppLayoutProps) {
    const [currentProject, setCurrentProject] = useState<ProjectListing | null>(
        null,
    );
    const { projectId } = useParams<{ projectId: string }>();
    const auth = useAuth();
    const navigate = useNavigate();

    console.log(user?.profile);

    // Extract user information from OIDC user object
    const userName =
        `${user?.profile?.given_name || ""} ${user?.profile?.family_name || ""}`.trim() ||
        user?.profile?.preferred_username ||
        "User";

    // Use first letter of name for avatar if no image
    const avatarText = userName.charAt(0).toUpperCase();

    useEffect(() => {
        const loadProject = async () => {
            if (!projectId) {
                setCurrentProject(null);
                return;
            }

            try {
                const token = auth.user?.id_token;
                if (!token) return;

                const projects = await fetchProjects(token);
                const project = projects.find((p) => p.id === projectId);
                setCurrentProject(project || null);
            } catch (err) {
                console.error("Failed to load project:", err);
            }
        };

        loadProject();
    }, [projectId, auth.user?.id_token]);

    return (
        <AppShell header={{ height: 60 }} padding="md">
            <AppShell.Header px="md">
                <Group h="100%" justify="space-between">
                    <Group
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate("/")}
                    >
                        <Text fw={700} size="lg">
                            Interview Helper
                        </Text>
                        {currentProject && (
                            <Text size="sm" c="dimmed">
                                / {currentProject.name}
                            </Text>
                        )}
                    </Group>
                    <Group visibleFrom="sm" gap="xs">
                        <Text fw={500} size="sm">
                            {userName}
                        </Text>
                        <Avatar
                            alt={userName}
                            radius="xl"
                            size="md"
                            color="blue"
                        >
                            {avatarText}
                        </Avatar>
                    </Group>
                    <Menu width="100%" offset={20}>
                        <Menu.Target>
                            <Burger hiddenFrom="sm" size="sm" />
                        </Menu.Target>
                        <Menu.Dropdown>
                            <Menu.Item>Profile</Menu.Item>
                            <Menu.Item>Settings</Menu.Item>
                            <Menu.Item onClick={onSignOut}>Logout</Menu.Item>
                        </Menu.Dropdown>
                    </Menu>
                </Group>
            </AppShell.Header>

            <AppShell.Main>{children}</AppShell.Main>
        </AppShell>
    );
}
