from pydantic import BaseModel
from fastapi.exceptions import HTTPException
from fastapi import status
from typing import Any
import jwt
import httpx
import logging

logger = logging.getLogger(__name__)

# pyright: reportAny=none


class TokenError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(
            status_code=code, detail=detail, headers={"WWW-Authenticate": "Bearer"}
        )


class TokenClaims(BaseModel):
    # ---- JWT standard claims ----
    iss: str  # Issuer Identifier (MUST match your IdP's issuer URL)
    sub: str  # Subject Identifier (unique user ID)
    exp: int  # Expiration time (epoch seconds)
    iat: int  # Issued-at time (epoch seconds)

    # ---- Recommended but optional ----
    nbf: int | None = None  # Not-before (epoch seconds)
    jti: str | None = None  # JWT ID (unique identifier for this token)

    # ---- OIDC standard claims ----
    auth_time: int | None = None  # Time of user authentication
    nonce: str | None = None  # Nonce (if supplied in the auth request)
    # ---- Profile/email OIDC scopes ----
    name: str | None = None
    preferred_username: str | None = None
    email: str | None = None
    email_verified: bool | None = None

    # ---- Roles/scopes ----
    scope: str | None = None  # space-delimited list of granted scopes
    roles: list[str] | None = (
        None  # IdP-specific claim (sometimes "roles", "groups", etc.)
    )

    # ---- Allow custom claims ----
    extra: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]


def verify_jwt_token(
    token: str, jwks_client: jwt.PyJWKClient, client_id: str, signing_algos: str
) -> TokenClaims:
    signing_key = jwks_client.get_signing_key_from_jwt(token).key
    payload = jwt.decode(
        token,
        key=signing_key,
        algorithms=signing_algos,
        audience=client_id,
    )

    # We expect a standard JWT payload dict here
    assert isinstance(payload, dict), "Expected JWT payload to be a dictionary"

    # normalize scopes/roles here...
    return TokenClaims(**payload)  # pyright: ignore[reportUnknownArgumentType]


class OIDCUserInfo(BaseModel):
    """Model for OIDC provider user information"""

    sub: str
    username: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    phone_number: str | None = None
    phone_number_verified: bool | None = None
    custom_attributes: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]


def extract_user_info_from_token_claims(claims: TokenClaims) -> OIDCUserInfo:
    """
    Extract user profile info directly from JWT claims instead of calling
    the OIDC userinfo endpoint.
    Since Google ID tokens already contain name/email claims, making a separate
    userinfo call unnecessary and avoiding the access-token-vs-id-token mismatch.
    """
    given_name: str | None = None
    family_name: str | None = None

    if claims.name:
        parts = claims.name.split(" ", 1)
        given_name = parts[0]
        family_name = parts[1] if len(parts) > 1 else None

    return OIDCUserInfo(
        sub=claims.sub,
        email=claims.email,
        name=claims.name,
        given_name=given_name,
        family_name=family_name,
    )


async def get_user_info_from_oidc_provider(
    token: str,
    userinfo_endpoint: str,
) -> OIDCUserInfo:
    """
    Get user information from an OIDC provider using the access token.

    Args:
        token: The access token from the OIDC provider (without 'Bearer ' prefix)
        userinfo_endpoint: The userinfo endpoint URL from the OIDC provider

    Returns:
        OIDCUserInfo: User information from the OIDC provider

    Raises:
        TokenError: If the token is invalid or the request fails
    """
    # Remove 'Bearer ' prefix if present
    clean_token = token.removeprefix("Bearer ")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {clean_token}"},
        )

        # We expect a successful 200 from the OIDC provider for valid tokens
        assert response.status_code == 200, (
            f"Failed to get user info: {response.status_code} {response.text}"
        )

        user_data = response.json()

        # Extract standard claims
        standard_claims = {
            "sub",
            "username",
            "email",
            "email_verified",
            "name",
            "given_name",
            "family_name",
            "picture",
            "phone_number",
            "phone_number_verified",
        }

        # Separate standard claims from custom attributes
        standard_user_data = {
            k: v for k, v in user_data.items() if k in standard_claims
        }
        custom_attributes = {
            k: v for k, v in user_data.items() if k not in standard_claims
        }

        # Add custom attributes to the standard data
        standard_user_data["custom_attributes"] = custom_attributes

        return OIDCUserInfo(**standard_user_data)


def get_oidc_userinfo_endpoint(oidc_authority: str) -> str:
    """
    Get the userinfo endpoint from the OIDC provider's well-known configuration.

    Args:
        oidc_authority: The base URL of the OIDC provider (e.g., https://cognito-idp.us-west-2.amazonaws.com/us-west-2_abc123)

    Returns:
        str: The userinfo endpoint URL

    Raises:
        TokenError: If the request fails or the userinfo_endpoint is not found in the configuration
    """
    # Ensure the authority URL doesn't end with a slash
    oidc_authority = oidc_authority.rstrip("/")

    # Construct the well-known configuration URL
    config_url = f"{oidc_authority}/.well-known/openid-configuration"

    with httpx.Client() as client:
        response = client.get(config_url)

        # We expect a successful 200 from the OIDC provider
        assert response.status_code == 200, (
            f"Failed to get OIDC configuration: {response.status_code} {response.text}"
        )

        config_data = response.json()

        # Extract the userinfo endpoint
        userinfo_endpoint = config_data.get("userinfo_endpoint")

        # userinfo_endpoint must be present for a valid OIDC configuration
        assert userinfo_endpoint, "Userinfo endpoint not found in OIDC configuration"

        logger.info(f"Found userinfo endpoint: {userinfo_endpoint}")
        return userinfo_endpoint
