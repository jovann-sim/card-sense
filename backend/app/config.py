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

settings = Settings()
