from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Race Engineer"
    udp_host: str = "0.0.0.0"
    udp_port: int = 20777
    enable_udp_listener: bool = True
    enable_voice: bool = False
    enable_coaching: bool = True
    voice_rate: int = 185
    voice_volume: float = 0.85
    history_limit: int = 600
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
