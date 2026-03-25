import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = os.environ.get("DATABASE_URL", os.environ.get("DATABASE_PUBLIC_URL", ""))
    magic_link_secret: str = "dev-secret-change-in-production"
    admin_password: str = "admin"
    portal_base_url: str = "http://localhost:8000"
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@aeristechnicalsolutions.com"
    sp_site_url: str = ""
    sp_client_id: str = ""
    sp_client_secret: str = ""
    upload_dir: str = "uploads"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
