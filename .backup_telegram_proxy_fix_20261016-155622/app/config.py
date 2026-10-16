from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    SECRET_KEY: str
    CHANNEL_ID: str = ""
    APP_BASE_URL: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY is required")
        if not self.ADMIN_TELEGRAM_ID:
            raise ValueError("ADMIN_TELEGRAM_ID is required")


settings = Settings()
