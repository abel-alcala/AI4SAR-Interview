import pytest
from pydantic import SecretStr, ValidationError

from interview_helper.config import Settings

# pyright: reportUnknownMemberType=none, reportUnknownVariableType=none


def test_cors_origins_list_string_parsing():
    """Test that CORS origins list is passed through unchanged"""

    origin1 = "https://localhost:3000"
    origin2 = "https://localhost:3001"

    # Required since it will turn into a list[str] via validation
    origins_list = f"{origin1},{origin2}"

    settings = Settings(
        CORS_ALLOW_ORIGINS=origins_list,  # pyright: ignore[reportArgumentType]
        OIDC_AUTHORITY="test",
        OIDC_CLIENT_ID="client_id",
        OPENAI_API_ENDPOINT="https://endpoint.com",
        OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
        AZURE_DEPLOYMENT="gpt-5",
        AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
        AZURE_SPEECH_KEY=None,
        AZURE_SPEECH_REGION=None,
        LANGFUSE_SECRET_KEY=None,
        LANGFUSE_PUBLIC_KEY=None,
        LANGFUSE_BASE_URL=None,
    )
    assert settings.cors_allow_origins == [origin1, origin2]


def test_empty_cors_origins_raises_error():
    """Test that empty CORS_ALLOW_ORIGINS raises ValueError"""
    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        _ = Settings(
            CORS_ALLOW_ORIGINS=None,  # pyright: ignore[reportArgumentType]
            OIDC_AUTHORITY="test",
            OIDC_CLIENT_ID="client_id",
            OPENAI_API_ENDPOINT="https://endpoint.com",
            OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
            AZURE_DEPLOYMENT="gpt-5",
            AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
            AZURE_SPEECH_KEY=None,
            AZURE_SPEECH_REGION=None,
            LANGFUSE_SECRET_KEY=None,
            LANGFUSE_PUBLIC_KEY=None,
            LANGFUSE_BASE_URL=None,
        )


def test_split_origins_splits_comma_separated_string():
    """Test that split_origins splits comma-separated string"""

    result = Settings.split_origins("https://localhost:3000,https://example.com")
    assert result == ["https://localhost:3000", "https://example.com"]


def test_split_origins_accepts_list():
    """Test that split_origins passes through list input"""

    origins_list = ["https://localhost:3000", "https://example.com"]
    result = Settings.split_origins(origins_list)
    assert result == origins_list


def test_split_origins_cleans_bracketed_string():
    """Test that split_origins cleans bracketed string"""

    result = Settings.split_origins("[https://localhost:3000,https://example.com]")
    assert result == ["https://localhost:3000", "https://example.com"]


def test_split_origins_removes_empty_strings():
    """Test that split_origins does not include empty strings"""

    result = Settings.split_origins("[https://localhost:3000,https://example.com,]")
    assert result == ["https://localhost:3000", "https://example.com"]


def test_split_origins_empty_string_results_in_empty_list():
    """Test that split_origins returns empty list for empty string"""

    result = Settings.split_origins("")
    assert result == []


def test_settings_immutability():
    """Test that settings can't be modified"""

    instance = Settings(
        SERVER_HOST="0.0.0.0",
        # will be parsed into list[str]
        CORS_ALLOW_ORIGINS="https://localhost:3000,https://localhost:3001",  # pyright: ignore[reportArgumentType]
        OIDC_AUTHORITY="test",
        OIDC_CLIENT_ID="client_id",
        OPENAI_API_ENDPOINT="https://endpoint.com",
        OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
        AZURE_DEPLOYMENT="gpt-5",
        AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
        AZURE_SPEECH_KEY=None,
        AZURE_SPEECH_REGION=None,
        LANGFUSE_SECRET_KEY=None,
        LANGFUSE_PUBLIC_KEY=None,
        LANGFUSE_BASE_URL=None,
    )

    with pytest.raises(ValidationError, match="frozen"):
        instance.cors_allow_origins = []

    with pytest.raises(ValidationError, match="frozen"):
        instance.server_host = "127.0.0.1"


def test_azure_speech_settings():
    instance = Settings(
        SERVER_HOST="0.0.0.0",
        # will be parsed into list[str]
        CORS_ALLOW_ORIGINS="https://localhost:3000,https://localhost:3001",  # pyright: ignore[reportArgumentType]
        OIDC_AUTHORITY="test",
        OIDC_CLIENT_ID="client_id",
        OPENAI_API_ENDPOINT="https://endpoint.com",
        OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
        AZURE_DEPLOYMENT="gpt-5",
        AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
        AZURE_SPEECH_KEY="abc123",  # pyright: ignore[reportArgumentType]
        AZURE_SPEECH_REGION="westus",
        LANGFUSE_SECRET_KEY=None,
        LANGFUSE_PUBLIC_KEY=None,
        LANGFUSE_BASE_URL=None,
    )
    assert instance.azure_speech_key == SecretStr("abc123")
    assert instance.azure_speech_region == "westus"


def test_azure_speech_one_throws_error():
    # (using mocked environment)
    with pytest.raises(ValueError, match="together or not at all"):
        _instance = Settings(
            SERVER_HOST="0.0.0.0",
            # will be parsed into list[str]
            CORS_ALLOW_ORIGINS="https://localhost:3000,https://localhost:3001",  # pyright: ignore[reportArgumentType]
            OIDC_AUTHORITY="test",
            OIDC_CLIENT_ID="client_id",
            OPENAI_API_ENDPOINT="https://endpoint.com",
            OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
            AZURE_DEPLOYMENT="gpt-5",
            AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
            AZURE_SPEECH_KEY="abc123",  # pyright: ignore[reportArgumentType]
            AZURE_SPEECH_REGION=None,
            LANGFUSE_SECRET_KEY=None,
            LANGFUSE_PUBLIC_KEY=None,
            LANGFUSE_BASE_URL=None,
        )
    with pytest.raises(ValueError, match="together or not at all"):
        _instance = Settings(
            SERVER_HOST="0.0.0.0",
            # will be parsed into list[str]
            CORS_ALLOW_ORIGINS="https://localhost:3000,https://localhost:3001",  # pyright: ignore[reportArgumentType]
            OIDC_AUTHORITY="test",
            OIDC_CLIENT_ID="client_id",
            OPENAI_API_ENDPOINT="https://endpoint.com",
            OPENAI_API_KEY=SecretStr("sample_openai_api_key"),
            AZURE_DEPLOYMENT="gpt-5",
            AZURE_EVAL_DEPLOYMENT="gpt-4o-mini",
            AZURE_SPEECH_KEY=None,
            AZURE_SPEECH_REGION="westus",
            LANGFUSE_SECRET_KEY=None,
            LANGFUSE_PUBLIC_KEY=None,
            LANGFUSE_BASE_URL=None,
        )
