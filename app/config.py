from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: str = "5432"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "REPOMAN"
    DATABASE_NAME: str = "phone_shop_db"

    # JWT
    SECRET_KEY: str = "supersecretkey_change_this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    ADMIN_SECRET: str

    class Config:
        env_file = ".env"

settings = Settings()
