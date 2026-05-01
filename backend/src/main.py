#!/usr/bin/env python3
from contextlib import asynccontextmanager

from anyio.from_thread import BlockingPortal
from interview_helper.downloads.util import sanitize_filename
from interview_helper.ai_analysis.ai_analysis import SimpleAnalyzer
from starlette.websockets import WebSocketDisconnect
from interview_helper.audio_stream_handler.transcription.transcription import (
    azure_transcriber_consumer_pair,
    vosk_transcriber_consumer_pair,
)
from interview_helper.context_manager.messages import (
    MarkAIAnalysisAsked,
    MarkAIAnalysisDismissedNotAsked,
    UpdateAIAnalysisTag,
    StarAIAnalysis,
    UndoAIAnalysisDismissal,
    UnstarAIAnalysis,
    PingMessage,
    CatchupMessage,
    ProjectMetadataMessage,
    TranscriptChunkToSend,
    RecordingStateMessage,
    ErrorMessage,
)
from interview_helper.security.http import (
    verify_jwt_token,
    get_user_info_from_oidc_provider,
    get_oidc_userinfo_endpoint,
    extract_user_info_from_token_claims,
)
from interview_helper.security.tickets import TicketResponse
from typing import Annotated
from fastapi import Request
from interview_helper.audio_stream_handler.audio_utils import (
    async_audio_write_to_disk_consumer_pair,
)
import logging
import httpx
import jwt
import time
from collections import defaultdict

from interview_helper.config import Settings
from interview_helper.context_manager.messages import WebRTCMessage
from interview_helper.context_manager.session_context_manager import AppContextManager
from interview_helper.context_manager.concurrent_websocket import ConcurrentWebSocket
from interview_helper.context_manager.resource_keys import (
    ANYIO_BLOCKING_PORTAL,
    WEBSOCKET,
)
from interview_helper.audio_stream_handler.audio_stream_handler import (
    handle_webrtc_message,
)
from interview_helper.context_manager.database import (
    ProjectListing,
    create_new_project,
    mark_ai_analysis_asked,
    mark_ai_analysis_dismissed_not_asked,
    undo_ai_analysis_dismissal,
    star_ai_analysis,
    unstar_ai_analysis,
    get_all_projects,
    get_or_add_user_by_oidc_id,
    get_project_by_id,
    get_all_transcripts,
    get_all_ai_analyses,
    get_project_session_count,
    delete_project,
    get_project_creator_and_name,
)
from interview_helper.context_manager.types import ProjectId

from fastapi.security import OpenIdConnect
from fastapi import FastAPI, WebSocket, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, RedirectResponse
import uvicorn
from pathlib import Path
import wave
import tempfile
import sqlalchemy as sa
from interview_helper.downloads.get_transcript import generate_transcript
from interview_helper.downloads.get_report import generate_report_pdf, build_report_data, serialize_report_data
from interview_helper.context_manager import models

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("transcription_server.log")],
)

logger = logging.getLogger(__name__)

# Settings gets initialized from environment variables.
settings = Settings()  # pyright: ignore[reportCallIssue]

if settings.azure_speech_key is None:
    transcriber_consumer_pair = vosk_transcriber_consumer_pair
    logger.warning("No Azure Speech key found! Falling back to Vosk for STT.")
else:
    transcriber_consumer_pair = azure_transcriber_consumer_pair
    logger.info("Found azure speech key. Using Azure STT")


session_manager = AppContextManager(
    audio_ingest_consumers=(
        async_audio_write_to_disk_consumer_pair,
        transcriber_consumer_pair,
    ),
    ai_processer=SimpleAnalyzer,
    settings=settings,
)

userinfo_endpoint: str = get_oidc_userinfo_endpoint(
    session_manager.get_settings().oidc_authority
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """background task starts at statrup"""
    await session_manager.start_background_services()
    yield
    await session_manager.stop_background_services()


# Create FastAPI app
app = FastAPI(
    title="Modular WebRTC Transcription Server",
    description="A refactored FastAPI-based WebRTC server with functional, modular architecture",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    # FIXME: This is due to Pyrefly not being able to handle Generic ParamSpec and Protocol.
    # pyrefly: ignore[bad-argument-type]
    CORSMiddleware,
    allow_origins=session_manager.get_settings().cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# OIDC Configuration - configured via environment variables

OIDC_CONFIG_URL = (
    session_manager.get_settings().oidc_authority.rstrip("/")
    + "/.well-known/openid-configuration"
)
CLIENT_ID = session_manager.get_settings().oidc_client_id
SITE_URL = session_manager.get_settings().site_url
REDIRECT_URI = f"{SITE_URL}/auth/callback"
SCOPE = "openid profile email"

FRONTEND_REDIRECT_URI = session_manager.get_settings().frontend_redirect_uri

oidc_config: dict[str, str] = httpx.get(OIDC_CONFIG_URL).raise_for_status().json()

signing_algos: str = oidc_config.get("id_token_signing_alg_values_supported", "")
jwks_client = jwt.PyJWKClient(oidc_config["jwks_uri"])
AUTHORIZATION_ENDPOINT = oidc_config["authorization_endpoint"]
TOKEN_ENDPOINT = oidc_config["token_endpoint"]

oidc_scheme = OpenIdConnect(openIdConnectUrl=OIDC_CONFIG_URL)

# Rate limiting for ticket generation (per user)
ticket_rate_limit: dict[str, list[float]] = defaultdict(list)
TICKET_RATE_LIMIT_PER_MINUTE = 10


@app.get("/")
async def root():
    return "Interview Helper Backend"


active_states: dict[str, tuple[str, str]] = {}


@app.get("/login")
async def login_redirect():
    """
    Frontend calls this endpoint to initiate the login flow.
    """
    state = "some_random_string_from_the_frontend"  # In a real app, generate a secure random string
    active_states[state] = ("valid", "")

    auth_url = (
        f"{AUTHORIZATION_ENDPOINT}?"
        f"response_type=code&"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"scope={SCOPE}&"
        f"state={state}"
    )
    return RedirectResponse(auth_url)


@app.get("/health")
async def health_check():
    """
    Health check endpoint that includes ticket system status.
    """
    return {
        "status": "healthy",
        "service": "Interview Helper Backend",
        "ticket_system": {
            "active_tickets": session_manager.ticket_store.get_active_tickets_count(),
            "default_expiration_seconds": session_manager.ticket_store._default_expiration,
        },
    }


@app.get("/auth/ticket", response_model=TicketResponse)
async def generate_websocket_ticket(
    request: Request, token: Annotated[str, Depends(oidc_scheme)]
):
    """
    Generate an authentication ticket for WebSocket connections.

    This endpoint requires a valid JWT token and returns a single-use ticket
    that can be used to authenticate WebSocket connections. The ticket includes
    the client's IP address for additional security.

    Rate limited to prevent abuse: 10 tickets per minute per user.
    """
    # Verify the JWT token
    clean_token = token.removeprefix("Bearer ")
    user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    # Rate limiting check
    current_time = time.time()
    user_requests = ticket_rate_limit[user_claims.sub]

    # Remove old requests (older than 1 minute)
    user_requests[:] = [
        req_time for req_time in user_requests if current_time - req_time < 60
    ]

    # Check if user exceeded rate limit
    if len(user_requests) >= TICKET_RATE_LIMIT_PER_MINUTE:
        logger.warning(f"Rate limit exceeded for user {user_claims.sub}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many ticket requests. Please wait before requesting another ticket.",
        )

    # Add current request timestamp
    user_requests.append(current_time)

    # Get client IP address
    if not request.client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine client IP address",
        )

    client_ip = request.client.host
    if user_claims.name or user_claims.email:
        user_info = extract_user_info_from_token_claims(user_claims)
    else:
        user_info = await get_user_info_from_oidc_provider(clean_token, userinfo_endpoint)

    name = f"{user_info.given_name or ''} {user_info.family_name or ''}".strip()
    user_id = get_or_add_user_by_oidc_id(
        session_manager.db, user_claims.sub, name
    ).user_id

    # Generate the ticket using the user ID
    ticket = session_manager.ticket_store.generate_ticket(user_id, client_ip)

    logger.info(
        f"Generated WebSocket ticket {ticket.ticket_id} for user {user_claims.sub} from IP {client_ip}"
    )

    return TicketResponse(
        ticket_id=ticket.ticket_id,
        expires_in=int(ticket.expires_at - ticket.created_at),
    )


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, ticket_id: str | None, project_id: str | None = None
):
    """
    WebSocket endpoint with ticket-based authentication.

    Clients should first obtain a ticket from /auth/ticket and then pass it
    as a query parameter: /ws?ticket_id=<ticket_id>&project_id=<project_id>
    """
    # Authenticate the WebSocket connection using ticket
    if not ticket_id:
        await websocket.close(code=1008, reason="Authentication ticket required")
        return

    # Require project_id
    if not project_id:
        await websocket.close(code=1008, reason="Project ID required")
        return
    else:
        project_id_typed = ProjectId.from_str(project_id)

    # Get client IP address
    if not websocket.client:
        await websocket.close(code=1008, reason="Unable to determine client IP")
        return

    client_ip = websocket.client.host

    try:
        # Validate the ticket
        ticket = session_manager.ticket_store.validate_ticket(ticket_id, client_ip)

        if not ticket:
            await websocket.close(
                code=1008, reason="Invalid or expired authentication ticket"
            )
            return

        logger.info(
            f"WebSocket connection authenticated for user: {str(ticket.user_id)[0:6]} using ticket {ticket_id}"
        )

        # Clean up the used ticket
        session_manager.ticket_store.cleanup_ticket(ticket_id)

    except Exception as e:
        logger.warning(f"WebSocket ticket validation failed: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return

    # Validate project exists
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        await websocket.close(code=1008, reason="Project not found")
        return

    await websocket.accept()
    context = await session_manager.new_session(
        user_id=ticket.user_id, project_id=project_id_typed
    )
    print(f"Opened new session {context.session_id} for user {ticket.user_id}")

    cws = ConcurrentWebSocket(already_accepted_ws=websocket)

    try:
        async with cws:
            async with BlockingPortal() as portal:
                try:
                    await context.register(ANYIO_BLOCKING_PORTAL, portal)
                    await context.register(WEBSOCKET, cws)

                    # Send catchup message with current transcript and insights
                    transcripts = get_all_transcripts(
                        session_manager.db, project_id_typed
                    )
                    # Send each transcript entry as a separate string for bottom-to-top display
                    transcript_list = [
                        TranscriptChunkToSend(
                            text=transcript["text_output"],
                            speaker=transcript["speaker"],
                            transcription_id=str(transcript["transcription_id"]),
                        )
                        for transcript in transcripts
                    ]

                    ai_analyses = get_all_ai_analyses(
                        session_manager.db, project_id_typed
                    )
                    insights = [analysis for analysis in ai_analyses if analysis]

                    catchup_msg = CatchupMessage(
                        transcript=transcript_list,
                        insights=insights,
                    )
                    await cws.send_message(catchup_msg)
                except Exception as e:
                    logger.error(
                        f"Error during session setup for session {context.session_id}: {e}"
                    )
                    raise e

                # Send project metadata
                metadata_msg = ProjectMetadataMessage(
                    project_id=project["id"],
                    project_name=project["name"],
                )
                await cws.send_message(metadata_msg)

                # Send current recording state if someone is recording
                recording_state = await session_manager.get_recording_state(
                    project_id_typed
                )
                if recording_state:
                    recording_session_id, recording_user_name = recording_state
                    # Only send if it's not this session recording
                    if recording_session_id != context.session_id:
                        recording_state_msg = RecordingStateMessage(
                            is_recording=True,
                            user_name=recording_user_name,
                        )
                        await cws.send_message(recording_state_msg)

                try:
                    while True:
                        message = await cws.receive_message()

                        if isinstance(message, WebRTCMessage):
                            await handle_webrtc_message(context, message)
                        elif isinstance(message, PingMessage):
                            await cws.send_message(PingMessage())
                        elif isinstance(
                            message,
                            (
                                MarkAIAnalysisAsked,
                                UndoAIAnalysisDismissal,
                                MarkAIAnalysisDismissedNotAsked,
                                StarAIAnalysis,
                                UnstarAIAnalysis,
                            ),
                        ):
                            try:
                                if isinstance(message, MarkAIAnalysisAsked):
                                    update = mark_ai_analysis_asked(
                                        session_manager.db,
                                        message.analysis_id,
                                        message.asked_at_transcript_id,
                                    )
                                elif isinstance(message, UndoAIAnalysisDismissal):
                                    update = undo_ai_analysis_dismissal(
                                        session_manager.db,
                                        message.analysis_id,
                                    )
                                elif isinstance(
                                    message, MarkAIAnalysisDismissedNotAsked
                                ):
                                    update = mark_ai_analysis_dismissed_not_asked(
                                        session_manager.db,
                                        message.analysis_id,
                                    )
                                elif isinstance(message, StarAIAnalysis):
                                    update = star_ai_analysis(
                                        session_manager.db,
                                        message.analysis_id,
                                    )
                                else:
                                    update = unstar_ai_analysis(
                                        session_manager.db,
                                        message.analysis_id,
                                    )

                                update_message = UpdateAIAnalysisTag(
                                    analysis_id=update.analysis_id,
                                    tag=update.tag,
                                    was_asked=update.was_asked,
                                    asked_at_transcript_id=update.asked_at_transcript_id,
                                    time_tag_changed=update.time_tag_changed,
                                    asked_at=update.asked_at,
                                )
                                await session_manager.broadcast_to_project(
                                    context.project_id, update_message
                                )
                            except ValueError as e:
                                logger.warning(
                                    "Rejected invalid AI analysis action for %s: %s",
                                    message.analysis_id,
                                    e,
                                )
                                await cws.send_message(
                                    ErrorMessage(
                                        error_code="invalid_ai_analysis_action",
                                        message=str(e),
                                        session_id=str(context.session_id),
                                    )
                                )
                        # handle other message types...
                except WebSocketDisconnect:
                    logger.info(
                        f"WebSocket disconnected for session {context.session_id}"
                    )
    except Exception as e:
        logger.error(
            f"Error in WebSocket handler for session {context.session_id}: {e}"
        )
    finally:
        await context.teardown()
        logger.info(f"Closed session {context.session_id} for user {ticket.user_id}")


@app.get("/user/me")
async def get_current_user(token: Annotated[str, Depends(oidc_scheme)]):
    """
    Returns the current user's information
    """
    clean_token = token.removeprefix("Bearer ")
    user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    if user_claims.name or user_claims.email:
        user_info = extract_user_info_from_token_claims(user_claims)
    else:
        user_info = await get_user_info_from_oidc_provider(clean_token, userinfo_endpoint)
    name = f"{user_info.given_name or ''} {user_info.family_name or ''}".strip()
    user = get_or_add_user_by_oidc_id(session_manager.db, user_claims.sub, name)

    return {
        "user_id": str(user.user_id),
        "full_name": user.full_name,
        "oidc_id": user.oidc_id,
    }


@app.get("/project")
async def list_all_projects(token: Annotated[str, Depends(oidc_scheme)]):
    """
    Returns all projects with details
    """
    clean_token = token.removeprefix("Bearer ")
    _user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)
    return get_all_projects(session_manager.db)


@app.post("/project")
async def create_project(
    project_name: str, token: Annotated[str, Depends(oidc_scheme)]
) -> ProjectListing:
    """
    Creates a new project
    """
    clean_token = token.removeprefix("Bearer ")
    user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    if user_claims.name or user_claims.email:
        user_info = extract_user_info_from_token_claims(user_claims)
    else:
        user_info = await get_user_info_from_oidc_provider(clean_token, userinfo_endpoint)

    name = f"{user_info.given_name or ''} {user_info.family_name or ''}".strip()
    user_id = get_or_add_user_by_oidc_id(
        session_manager.db, user_claims.sub, name
    ).user_id

    new_project: ProjectListing = create_new_project(
        session_manager.db, user_id, project_name
    )

    return new_project


@app.delete("/project/{project_id}")
async def delete_project_endpoint(
    project_id: str, confirmed_name: str, token: Annotated[str, Depends(oidc_scheme)]
):
    """
    Deletes a project and all associated data (sessions, transcriptions, audio files, questions).
    Only the project creator can delete the project.
    Requires confirmation by providing the exact project name.
    """
    clean_token = token.removeprefix("Bearer ")
    user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    # Get user info
    if user_claims.name or user_claims.email:
        user_info = extract_user_info_from_token_claims(user_claims)
    else:
        user_info = await get_user_info_from_oidc_provider(clean_token, userinfo_endpoint)
    name = f"{user_info.given_name or ''} {user_info.family_name or ''}".strip()
    user_id = get_or_add_user_by_oidc_id(
        session_manager.db, user_claims.sub, name
    ).user_id

    # Verify project exists and get creator info
    project_id_typed = ProjectId.from_str(project_id)

    project_info = get_project_creator_and_name(session_manager.db, project_id_typed)
    if project_info is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if user is the creator
    if project_info.creator_user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Only the project creator can delete this project"
        )

    # Verify the confirmed name matches
    if confirmed_name != project_info.name:
        raise HTTPException(
            status_code=400, detail="Project name confirmation does not match"
        )

    # Delete the project and all related data
    delete_project(
        session_manager.db,
        project_id_typed,
        session_manager.get_settings().audio_recordings_dir,
    )

    return {"status": "success", "message": "Project deleted successfully"}


@app.get("/project/{project_id}/info")
async def get_project_info(
    project_id: str, token: Annotated[str, Depends(oidc_scheme)]
):
    """
    Gets project information including session count for delete confirmation
    """
    clean_token = token.removeprefix("Bearer ")
    _user_claims = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    session_count = get_project_session_count(session_manager.db, project_id_typed)

    return {**project, "session_count": session_count}


@app.get("/project/{project_id}/download/transcript")
async def download_transcript(
    project_id: str, token: Annotated[str, Depends(oidc_scheme)]
):
    """
    Download the transcript for a project as a text file
    """
    clean_token = token.removeprefix("Bearer ")
    _ = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    # Verify project exists
    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate transcript
    transcript_text = generate_transcript(
        project_id=project_id,
        db=session_manager.db,
    )

    if transcript_text is None:
        raise HTTPException(
            status_code=404, detail="No transcriptions found for this project"
        )

    project_name = project["name"] or "transcript"
    safe_filename = sanitize_filename(project_name, "transcript") + "_transcript.txt"

    return Response(
        content=transcript_text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@app.get("/project/{project_id}/download/questions")
async def download_questions(
    project_id: str, token: Annotated[str, Depends(oidc_scheme)]
):
    """
    Download all AI-generated questions for a project as a text file
    """
    clean_token = token.removeprefix("Bearer ")
    _ = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    # Verify project exists
    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all AI analyses (questions)
    analyses = get_all_ai_analyses(session_manager.db, project_id_typed)

    project_name = project["name"] or "questions"
    safe_filename = sanitize_filename(project_name, "questions") + "_questions.txt"

    if not analyses:
        raise HTTPException(
            status_code=404, detail="No AI-generated questions found for this project"
        )

    # Format questions as text
    transcript_lines: list[str] = []
    transcript_lines.append("=" * 80)
    transcript_lines.append(f"GENERATED QUESTIONS - {project_name}")
    transcript_lines.append(f"Project ID: {project_id}")
    transcript_lines.append(f"Total Questions: {len(analyses)}")
    transcript_lines.append("=" * 80)
    transcript_lines.append("")

    for analysis in analyses:
        transcript_lines.append(f"Question #{analysis.ordinal}:")
        transcript_lines.append(f"\t{analysis.text}")

        if analysis.span:
            transcript_lines.append(f'\tContext: "{analysis.span}"')

        if analysis.tag and "starred" in analysis.tag:
            transcript_lines.append("\tStarred")

        if analysis.was_asked is True:
            assert analysis.asked_at is not None, (
                "asked_at should be set if was_asked is True"
            )
            timestamp = analysis.asked_at.strftime("%Y-%m-%d %H:%M:%S %Z")
            transcript_lines.append(f"\tAsked at {timestamp}")
        elif analysis.was_asked is False:
            transcript_lines.append("\tNot Asked")

        transcript_lines.append("")

    questions_text = "\n".join(transcript_lines)

    return Response(
        content=questions_text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@app.get("/project/{project_id}/download/report")
async def download_report(project_id: str, token: Annotated[str, Depends(oidc_scheme)]):
    """
    Download a unified interview report for a project as a PDF
    """
    clean_token = token.removeprefix("Bearer ")
    _ = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    report_pdf = generate_report_pdf(project_id=project_id, db=session_manager.db)
    if report_pdf is None:
        raise HTTPException(
            status_code=404, detail="No transcriptions found for this project"
        )

    project_name = project["name"] or "report"
    safe_filename = sanitize_filename(project_name, "report") + "_report.pdf"

    return Response(
        content=report_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@app.post("/project/{project_id}/push/firebase")
async def push_to_firebase(
    project_id: str,
    incident_id: str,
    token: Annotated[str, Depends(oidc_scheme)],
):
    """
    Serialize the interview report as structured JSON and write it to Firestore
    under incidents/{incident_id}/ai_interview.
    """
    import json
    import firebase_admin  # pyright: ignore[reportMissingTypeStubs]
    from firebase_admin import credentials, firestore  # pyright: ignore[reportMissingTypeStubs]

    clean_token = token.removeprefix("Bearer ")
    _ = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    if not settings.firebase_service_account_key:
        raise HTTPException(
            status_code=503,
            detail="Firebase export is not configured on this server.",
        )

    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    report_data = build_report_data(project_id=project_id, db=session_manager.db)
    if report_data is None:
        raise HTTPException(
            status_code=404, detail="No transcriptions found for this project"
        )

    payload = serialize_report_data(
        report_data=report_data,
        project_id=project_id,
        incident_id=incident_id,
    )

    try:
        firebase_admin.get_app()
    except ValueError:
        sa_dict = json.loads(settings.firebase_service_account_key)
        cred = credentials.Certificate(sa_dict)
        _ = firebase_admin.initialize_app(cred)

    db_client = firestore.client()
    db_client.collection("incidents").document(incident_id).set(
        {"ai_interview": payload}, merge=True
    )

    logger.info(
        "Pushed interview report for project %s to Firebase incident %s",
        project_id,
        incident_id,
    )

    return {"status": "success", "incident_id": incident_id, "project_id": project_id}


@app.get("/project/{project_id}/download/audio")
async def download_audio(project_id: str, token: Annotated[str, Depends(oidc_scheme)]):
    """
    Download all audio recordings for a project stitched together in chronological order
    """
    clean_token = token.removeprefix("Bearer ")
    _ = verify_jwt_token(clean_token, jwks_client, CLIENT_ID, signing_algos)

    # Verify project exists
    project_id_typed = ProjectId.from_str(project_id)
    project = get_project_by_id(session_manager.db, project_id_typed)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all session IDs for this project from the Session table
    with session_manager.db.begin() as conn:
        session_ids_result = conn.execute(
            sa.select(models.Session.session_id)
            .where(models.Session.project_id == project_id)
            .order_by(models.Session.started_at.asc())
        ).all()
        session_ids: list[str] = [row[0] for row in session_ids_result]

    if not session_ids:
        raise HTTPException(
            status_code=404, detail="No audio recordings found for this project"
        )

    # Find corresponding audio files
    audio_dir = Path(session_manager.get_settings().audio_recordings_dir)
    audio_files: list[Path] = []
    for session_id in session_ids:
        audio_file = audio_dir / f"recording-{session_id}.wav"
        if audio_file.exists():
            audio_files.append(audio_file)

    if not audio_files:
        raise HTTPException(
            status_code=404, detail="No audio files found for this project"
        )

    project_name = project["name"] or "audio"
    safe_filename = sanitize_filename(project_name, "audio") + "_audio.wav"

    # Stitch audio files together in a temporary file to avoid materializing in memory
    temp_file = tempfile.NamedTemporaryFile(mode="w+b", suffix=".wav", delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        # Open first file to get parameters
        with wave.open(str(audio_files[0]), "rb") as first_wave:
            params = first_wave.getparams()

            # Create output wave file in temp file
            with wave.open(str(temp_path), "wb") as output_wave:
                output_wave.setparams(params)

                # Write all audio files
                for audio_file in audio_files:
                    with wave.open(str(audio_file), "rb") as input_wave:
                        output_wave.writeframes(
                            input_wave.readframes(input_wave.getnframes())
                        )

        return FileResponse(
            temp_path,
            media_type="audio/wav",
            filename=safe_filename,
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )
    except Exception as e:
        # Clean up temp file if error occurs before streaming starts
        try:
            temp_path.unlink()
        except Exception:
            pass
        raise e


if __name__ == "__main__":
    try:
        uvicorn.run(
            app,
            host=session_manager.get_settings().server_host,
            port=session_manager.get_settings().server_port,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Server error: {e}")
        exit(1)
