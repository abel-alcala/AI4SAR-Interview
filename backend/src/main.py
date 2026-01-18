#!/usr/bin/env python3
from contextlib import asynccontextmanager

from anyio.from_thread import BlockingPortal
from interview_helper.ai_analysis.ai_analysis import SimpleAnalyzer
from starlette.websockets import WebSocketDisconnect
from interview_helper.audio_stream_handler.transcription.transcription import (
    azure_transcriber_consumer_pair,
    vosk_transcriber_consumer_pair,
)
from interview_helper.context_manager.messages import (
    DismissAIAnalysis,
    PingMessage,
    CatchupMessage,
    ProjectMetadataMessage,
)
from starlette.responses import RedirectResponse
from interview_helper.security.http import (
    verify_jwt_token,
    get_user_info_from_oidc_provider,
    get_oidc_userinfo_endpoint,
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
    dismiss_ai_analysis,
    get_all_projects,
    get_or_add_user_by_oidc_id,
    get_project_by_id,
    get_all_transcripts,
    get_all_ai_analyses,
)
from interview_helper.context_manager.types import ProjectId

from fastapi.security import OpenIdConnect
from fastapi import FastAPI, WebSocket, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

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
async def lifespan(app: FastAPI):
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
                    transcript_text = " ".join(
                        [transcript["text_output"] for transcript in transcripts]
                    )

                    ai_analyses = get_all_ai_analyses(
                        session_manager.db, project_id_typed
                    )
                    insights = [analysis for analysis in ai_analyses if analysis]

                    catchup_msg = CatchupMessage(
                        transcript=transcript_text,
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

                while True:
                    message = await cws.receive_message()

                    if isinstance(message, WebRTCMessage):
                        await handle_webrtc_message(context, message)
                    elif isinstance(message, PingMessage):
                        await cws.send_message(PingMessage())
                    elif isinstance(message, DismissAIAnalysis):
                        dismiss_ai_analysis(
                            session_manager.db, message.analysis_id, ticket.user_id
                        )
                    # handle other message types...
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {context.session_id}")
    except Exception as e:
        logger.error(
            f"Error in WebSocket handler for session {context.session_id}: {e}"
        )
    finally:
        await context.teardown()
        logger.info(f"Closed session {context.session_id} for user {ticket.user_id}")


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

    user_info = await get_user_info_from_oidc_provider(clean_token, userinfo_endpoint)

    name = f"{user_info.given_name or ''} {user_info.family_name or ''}".strip()
    user_id = get_or_add_user_by_oidc_id(
        session_manager.db, user_claims.sub, name
    ).user_id

    new_project: ProjectListing = create_new_project(
        session_manager.db, user_id, project_name
    )

    return new_project


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
