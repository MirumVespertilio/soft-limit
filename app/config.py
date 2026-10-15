from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_BOT_TOKEN: str = ""
    ADMIN_TELEGRAM_ID: int = 0
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    SECRET_KEY: str = ""
    CHANNEL_ID: str = ""
    APP_BASE_URL: str = ""


settings = Settings()
