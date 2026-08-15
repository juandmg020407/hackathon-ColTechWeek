"""Configuración desde entorno. Todo tiene default para que arranque sin .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- externos (opcionales: sin ellos el sistema degrada, no cae) ---
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    azure_tts_voice: str = "es-CO-SalomeNeural"
    anthropic_api_key: str = ""
    firms_map_key: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    # --- gobernanza ---
    # por encima de este gasto, la propuesta necesita visto bueno de un tecnico
    umbral_revision_cop: int = 1_500_000

    # --- red ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- caches, en segundos ---
    ttl_clima: int = 3 * 3600
    ttl_estacional: int = 24 * 3600
    ttl_enso: int = 7 * 24 * 3600
    ttl_incendios: int = 6 * 3600

    @property
    def origenes(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
