from functools import lru_cache

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "Live Race Engineer"

    udp_host: str = "0.0.0.0"
    udp_port: int = 20777
    enable_udp_listener: bool = True

    enable_voice: bool = False
    enable_coaching: bool = True
    enable_recording: bool = True

    voice_rate: int = 185
    voice_volume: float = 0.85

    history_limit: int = 9000
    recording_sample_hz: float = 5.0

    data_dir: str = "data/sessions"

    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000"
    )

    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: int = 45

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin
            in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()