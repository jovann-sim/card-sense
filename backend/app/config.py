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
