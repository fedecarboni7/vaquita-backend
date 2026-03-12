from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    DATABASE_URL: str = "postgresql+asyncpg://expenses_user:expenses_pass@localhost:5432/expenses_db"

    GOOGLE_CLIENT_ID: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 1440  # 24 hours
    FRONTEND_URL: str = "http://localhost:5173"
    GOOGLE_API_KEY: str = ""
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_PROJECT: str = "expenses tracker app"
    LLM_MODEL: str = "gemini-flash-lite-latest"


settings = Settings()
