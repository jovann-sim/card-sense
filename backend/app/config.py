from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    demo_mode: bool = True
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    finance_agent_model: str = "gemini-2.5-flash"
    firestore_database: str = "(default)"
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"
    plaid_country_codes: str = "US"
    internal_run_secret: str = "change-me"
    cors_origins: str = "http://localhost:3000"

    # Gemini is switched on by having a project to call it through, not by
    # demo_mode. Storage and language model are unrelated concerns, and coupling
    # them meant you could not read a document without also standing up Plaid.
    gemini_enabled: bool | None = None

    # Terms retrieval
    terms_fetch_timeout: float = 30.0
    terms_max_bytes: int = 15_000_000
    terms_max_chars: int = 200_000
    terms_min_chars: int = 400
    terms_user_agent: str = "CardSense/0.1 (+card terms reader)"

    # Extraction quality gate. Below this the card is excluded rather than guessed.
    extraction_min_confidence: float = 0.35

    # Reading a document twice and merging the passes. Misses between runs are
    # uncorrelated, so a second pass recovers most of them; card intelligence
    # runs weekly per card, so the extra call is cheap. Set to 1 to disable.
    extraction_passes: int = 2

    # Demo-mode persistence, so extracted cards survive a restart without Firestore.
    persist_local_store: bool = True
    local_store_path: str = ".localstore.json"

    @property
    def use_gemini(self) -> bool:
        if self.gemini_enabled is not None:
            return self.gemini_enabled
        return bool(self.google_cloud_project)

    def real_mode_errors(self) -> list[str]:
        if self.demo_mode:
            return []
        required = {
            "GOOGLE_CLOUD_PROJECT": self.google_cloud_project,
            "PLAID_CLIENT_ID": self.plaid_client_id,
            "PLAID_SECRET": self.plaid_secret,
        }
        return [f"{key} is required when DEMO_MODE=false" for key, value in required.items() if not value]


settings = Settings()
