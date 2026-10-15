from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    ADMIN_TELEGRAM_ID: int = 0
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    SECRET_KEY: str = ""
    CHANNEL_ID: str = ""
    APP_BASE_URL: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
