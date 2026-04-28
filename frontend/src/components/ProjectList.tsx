import { useState, useEffect } from "react";
import {
    Container,
    Card,
    Text,
    Button,
    Group,
    SimpleGrid,
    Modal,
    TextInput,
    Stack,
    Title,
    Loader,
    Center,
    ActionIcon,
    Alert,
    Menu,
} from "@mantine/core";
import { IconTrash, IconDots } from "@tabler/icons-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import {
    fetchProjects,
    createProject,
    getProjectInfo,
    deleteProject,
    getCurrentUser,
} from "../lib/api";
import type { ProjectListing, ProjectInfo, CurrentUser } from "../lib/api";

export default function ProjectList() {
    const [projects, setProjects] = useState<ProjectListing[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchParams] = useSearchParams();

    // Capture incidentId and projectName to restore after login
    const urlIncidentId = searchParams.get("incidentId");
    const prefillName =
        sessionStorage.getItem("intellisar_project_name") ??
        searchParams.get("projectName") ??
        "";

    const [createModalOpen, setCreateModalOpen] = useState(!!prefillName);
    const [newProjectName, setNewProjectName] = useState(prefillName);
    const [creating, setCreating] = useState(false);
    const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);

    // Delete modal state
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [projectToDelete, setProjectToDelete] = useState<ProjectInfo | null>(
        null,
    );
    const [deleteConfirmName, setDeleteConfirmName] = useState("");
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const navigate = useNavigate();
    const auth = useAuth();

    useEffect(() => {
        // Save incidentId to sessionStorage for Task 5's "Save to IntelliSAR" button
        if (urlIncidentId) {
            sessionStorage.setItem("intellisar_incident_id", urlIncidentId);
        }

        // Clean up projectName from sessionStorage so it doesn't auto-open on future visits
        if (prefillName) {
            sessionStorage.removeItem("intellisar_project_name");
        }

        const loadData = async () => {
            try {
                setLoading(true);
                setError(null);
                const token = auth.user?.id_token;
                if (!token) {
                    throw new Error("No id token available");
                }
                // Load both user info and projects
                const [userData, projectsData] = await Promise.all([
                    getCurrentUser(token),
                    fetchProjects(token),
                ]);
                setCurrentUser(userData);
                setProjects(projectsData);
            } catch (err) {
                setError(
                    err instanceof Error ? err.message : "Failed to load data",
                );
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, []);

    const handleCreateProject = async () => {
        if (!newProjectName.trim()) {
            return;
        }

        try {
            setCreating(true);
            const token = auth.user?.id_token;
            if (!token) {
                throw new Error("No id token available");
            }

            const newProject = await createProject(newProjectName, token);
            setProjects([...projects, newProject]);
            setCreateModalOpen(false);
            setNewProjectName("");
            // Navigate to the new project
            navigate(`/project/${newProject.id}`);
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to create project",
            );
        } finally {
            setCreating(false);
        }
    };

    const handleProjectClick = (projectId: string) => {
        navigate(`/project/${projectId}`);
    };

    const handleDeleteClick = async (
        e: React.MouseEvent,
        project: ProjectListing,
    ) => {
        e.stopPropagation(); // Prevent card click

        try {
            const token = auth.user?.id_token;
            if (!token) {
                throw new Error("No id token available");
            }

            // Fetch full project info including session count
            const projectInfo = await getProjectInfo(project.id, token);
            setProjectToDelete(projectInfo);
            setDeleteModalOpen(true);
            setDeleteConfirmName("");
            setDeleteError(null);
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "Failed to load project info",
            );
        }
    };

    const handleDeleteConfirm = async () => {
        if (!projectToDelete) return;

        try {
            setDeleting(true);
            setDeleteError(null);
            const token = auth.user?.id_token;
            if (!token) {
                throw new Error("No id token available");
            }

            await deleteProject(projectToDelete.id, deleteConfirmName, token);

            // Remove project from list
            setProjects((prevProjects) =>
                prevProjects.filter((p) => p.id !== projectToDelete.id),
            );

            // Close modal
            setDeleteModalOpen(false);
            setProjectToDelete(null);
            setDeleteConfirmName("");
        } catch (err) {
            setDeleteError(
                err instanceof Error ? err.message : "Failed to delete project",
            );
        } finally {
            setDeleting(false);
        }
    };

    const isDeleteConfirmValid = deleteConfirmName === projectToDelete?.name;

    if (loading) {
        return (
            <Center style={{ height: "100vh" }}>
                <Loader size="lg" />
            </Center>
        );
    }

    return (
        <Container size="xl" py="xl">
            <Group justify="space-between" mb="xl">
                <Title order={1}>My Projects</Title>
                <Button onClick={() => setCreateModalOpen(true)} size="md">
                    Create Project
                </Button>
            </Group>

            {error && (
                <Text c="red" mb="md">
                    {error}
                </Text>
            )}

            {projects.length === 0 ? (
                <Card shadow="sm" padding="xl" radius="md" withBorder>
                    <Stack align="center" gap="md">
                        <Text size="lg" c="dimmed">
                            No projects yet
                        </Text>
                        <Text size="sm" c="dimmed">
                            Create your first project to get started
                        </Text>
                        <Button onClick={() => setCreateModalOpen(true)}>
                            Create Your First Project
                        </Button>
                    </Stack>
                </Card>
            ) : (
                <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg">
                    {projects.map((project) => {
                        const isOwnProject =
                            currentUser?.user_id === project.creator_user_id;
                        return (
                            <Card
                                key={project.id}
                                shadow="sm"
                                padding="lg"
                                radius="md"
                                withBorder
                                style={{
                                    cursor: "pointer",
                                    position: "relative",
                                }}
                                onClick={() => handleProjectClick(project.id)}
                            >
                                <Stack gap="sm">
                                    <Group
                                        justify="space-between"
                                        align="flex-start"
                                    >
                                        <Text
                                            fw={500}
                                            size="lg"
                                            style={{ flex: 1 }}
                                        >
                                            {project.name}
                                        </Text>
                                        {isOwnProject && (
                                            <Menu
                                                position="bottom-end"
                                                withinPortal
                                            >
                                                <Menu.Target>
                                                    <ActionIcon
                                                        variant="subtle"
                                                        onClick={(e) =>
                                                            e.stopPropagation()
                                                        }
                                                        aria-label="Project options"
                                                    >
                                                        <IconDots size={18} />
                                                    </ActionIcon>
                                                </Menu.Target>
                                                <Menu.Dropdown>
                                                    <Menu.Item
                                                        color="red"
                                                        leftSection={
                                                            <IconTrash
                                                                size={16}
                                                            />
                                                        }
                                                        onClick={(e) =>
                                                            handleDeleteClick(
                                                                e,
                                                                project,
                                                            )
                                                        }
                                                    >
                                                        Delete project
                                                    </Menu.Item>
                                                </Menu.Dropdown>
                                            </Menu>
                                        )}
                                    </Group>
                                    <Text size="xs" c="dimmed">
                                        Created by {project.creator_name}
                                    </Text>
                                    <Text size="xs" c="dimmed">
                                        {new Date(
                                            project.created_at,
                                        ).toLocaleDateString("en-US", {
                                            year: "numeric",
                                            month: "long",
                                            day: "numeric",
                                        })}
                                    </Text>
                                </Stack>
                            </Card>
                        );
                    })}
                </SimpleGrid>
            )}

            <Modal
                opened={createModalOpen}
                onClose={() => {
                    setCreateModalOpen(false);
                    setNewProjectName("");
                }}
                title="Create New Project"
            >
                <Stack>
                    <TextInput
                        label="Project Name"
                        placeholder="Enter project name"
                        value={newProjectName}
                        onChange={(e) =>
                            setNewProjectName(e.currentTarget.value)
                        }
                        onKeyDown={(e) => {
                            if (e.key === "Enter") {
                                handleCreateProject();
                            }
                        }}
                    />
                    <Group justify="flex-end">
                        <Button
                            variant="subtle"
                            onClick={() => {
                                setCreateModalOpen(false);
                                setNewProjectName("");
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={handleCreateProject}
                            loading={creating}
                            disabled={!newProjectName.trim()}
                        >
                            Create
                        </Button>
                    </Group>
                </Stack>
            </Modal>

            <Modal
                opened={deleteModalOpen}
                onClose={() => {
                    setDeleteModalOpen(false);
                    setProjectToDelete(null);
                    setDeleteConfirmName("");
                    setDeleteError(null);
                }}
                title="Delete Project"
            >
                <Stack>
                    {projectToDelete && (
                        <>
                            <Alert color="red" title="Warning">
                                This action cannot be undone. This will
                                permanently delete the project{" "}
                                <strong>{projectToDelete.name}</strong> and all
                                associated data including:
                                <ul style={{ marginTop: "8px" }}>
                                    <li>
                                        {projectToDelete.session_count} session
                                        {projectToDelete.session_count !== 1
                                            ? "s"
                                            : ""}
                                    </li>
                                    <li>All transcriptions</li>
                                    <li>All audio recordings</li>
                                    <li>All AI-generated questions</li>
                                </ul>
                            </Alert>

                            <Text size="sm">
                                Please type{" "}
                                <strong>{projectToDelete.name}</strong> to
                                confirm deletion:
                            </Text>

                            <TextInput
                                placeholder={projectToDelete.name}
                                value={deleteConfirmName}
                                onChange={(e) =>
                                    setDeleteConfirmName(e.currentTarget.value)
                                }
                                error={deleteError}
                            />

                            <Group justify="flex-end">
                                <Button
                                    variant="subtle"
                                    onClick={() => {
                                        setDeleteModalOpen(false);
                                        setProjectToDelete(null);
                                        setDeleteConfirmName("");
                                        setDeleteError(null);
                                    }}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    color="red"
                                    onClick={handleDeleteConfirm}
                                    loading={deleting}
                                    disabled={!isDeleteConfirmValid}
                                >
                                    Delete Project
                                </Button>
                            </Group>
                        </>
                    )}
                </Stack>
            </Modal>
        </Container>
    );
}
