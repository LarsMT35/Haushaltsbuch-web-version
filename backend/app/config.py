"""Zentrale Konfiguration – alles per Umgebungsvariable überschreibbar (Prinzip 1)."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # sqlite als Entwicklungs-Fallback, im Docker-Stack kommt PostgreSQL per env
    database_url: str = "sqlite:///./haushaltsbuch.db"
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    token_expire_minutes: int = 12 * 60
    # Erstanlage des Admin-Kontos beim allerersten Start (keine Selbstregistrierung, 4.1)
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_display_name: str = "Administrator"
    # Referenzwährung für alle Auswertungen (4.3)
    reference_currency: str = "EUR"
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
