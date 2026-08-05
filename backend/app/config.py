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
    # Nur für den Demo-Stack (docker-compose.demo.yml): befüllt eine leere DB
    # beim ersten Start mit Testkonten/-buchungen, in Produktion immer aus.
    seed_demo_data: bool = False

    # Optionale Anbindung einer LOKALEN Ollama-Instanz (4.6). Leer = aus, dann
    # existiert die Funktion in der Oberfläche nicht. Es werden ausschließlich
    # Buchungstexte ohne Kontonummern an die eigene Instanz geschickt, und die
    # KI schlägt nur vor – zugeordnet wird erst nach Bestätigung (Prinzip 6:
    # Fachlogik bleibt regelbasiert im Backend, die KI ergänzt sie nur).
    ollama_url: str = ""            # z.B. http://192.168.1.50:11434
    ollama_model: str = "llama3.1"
    ollama_timeout: int = 120

    class Config:
        env_file = ".env"


settings = Settings()
