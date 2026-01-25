from pydantic.functional_validators import model_validator
from pydantic_settings.main import SettingsConfigDict
from typing import Annotated
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Server settings
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=3000, alias="SERVER_PORT")

    # CORS settings
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default=[], alias="CORS_ALLOW_ORIGINS"
    )

    # OIDC settings
    oidc_authority: str = Field(alias="OIDC_AUTHORITY")
    oidc_client_id: str = Field(alias="OIDC_CLIENT_ID")
    site_url: str = Field(default="http://localhost:3000", alias="SITE_URL")
    frontend_redirect_uri: str = Field(
        default="http://localhost:5173/auth/callback", alias="FRONTEND_REDIRECT_URI"
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            origins = [origin.strip() for origin in v.strip("[]").split(",")]
            # Remove empty strings
            origins = [origin for origin in origins if origin]
            return origins
        return v

    def model_post_init(self, __context):
        if not self.cors_allow_origins:
            raise ValueError(
                "Missing required environment variable: CORS_ALLOW_ORIGINS"
            )

    # Audio processing settings (these rarely change, so keeping as constants is fine)
    num_channels: int = 1
    sample_width: int = 2
    target_sample_rate: int = 48000
    min_duration: int = 5
    bytes_per_sample: int = 2

    # AI Processing
    process_transcript_every_secs: float = 60.0 * 2  # 2 minutes
    process_transcript_every_word_count: int = 100

    azure_api_endpoint: str = Field(alias="OPENAI_API_ENDPOINT")
    azure_api_key: SecretStr = Field(alias="OPENAI_API_KEY")
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str = Field(alias="AZURE_DEPLOYMENT")

    azure_eval_deployment: str = Field(alias="AZURE_EVAL_DEPLOYMENT")

    # File paths
    vosk_model_path: Path = Field(
        default=Path("vosk_models") / "vosk-model-small-en-us-0.15"
    )
    audio_recordings_dir: str = "audio_recordings"
    transcriptions_dir: str = "transcriptions"

    # STT
    azure_speech_key: SecretStr | None = Field(alias="AZURE_SPEECH_KEY", default=None)
    azure_speech_region: str | None = Field(alias="AZURE_SPEECH_REGION", default=None)

    LANGFUSE_SECRET_KEY: SecretStr | None = Field(alias="LANGFUSE_SECRET_KEY")
    LANGFUSE_PUBLIC_KEY: str | None = Field(alias="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_BASE_URL: str | None = Field(alias="LANGFUSE_BASE_URL")

    @model_validator(mode="after")
    def check_azure_fields_together(self):
        if (self.azure_speech_key is None) != (self.azure_speech_region is None):
            raise ValueError(
                "Both AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set together or not at all."
            )
        return self

    @property
    def min_bytes(self) -> int:
        """Derived setting for minimum bytes"""
        return int(self.target_sample_rate * self.bytes_per_sample * self.min_duration)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", frozen=True
    )
