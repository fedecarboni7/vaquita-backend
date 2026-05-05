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
    DEV_AUTH_MODE: bool = False
    FRONTEND_URL: str = "http://localhost:5173"
    GROQ_API_KEY: str = ""
    ENCRYPTION_KEY: str = ""
    FREE_DAILY_LIMIT: int = 5
    GROQ_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    GOOGLE_DEFAULT_MODEL: str = "gemini-2.5-flash"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_PROJECT: str = "expenses tracker app"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    RECEIPT_DAILY_LIMIT: int = 10


settings = Settings()
