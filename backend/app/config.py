"""Application configuration loaded from environment."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://orbitops:orbitops@postgres:5432/orbitops"
    redis_url: str = "redis://redis:6379/0"

    app_name: str = "OrbitOps API"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = ""

    database_retry_attempts: int = 20
    database_retry_delay_seconds: float = 0.5
    database_connection_timeout_seconds: int = 5

    redis_retry_attempts: int = 20
    redis_retry_delay_seconds: float = 0.5
    redis_connect_timeout_seconds: int = 5

    # Crusoe settings are optional by design; app must start without an API key.
    crusoe_api_key: str | None = None
    crusoe_base_url: str = "https://api.inference.crusoecloud.com/v1/"
    crusoe_model: str = "moonshotai/Kimi-K2.6"
    crusoe_multimodal_model: str = "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"
    crusoe_enabled: bool = False

    world_state_seed_version: int = 1
    websocket_heartbeat_seconds: float = 5.0
    local_gpu_telemetry_enabled: bool = False
    local_gpu_node_id: str = "node-local"
    local_gpu_asset_id: str = "gpu-local-0"

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
