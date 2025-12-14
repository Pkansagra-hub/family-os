"""
POC Configuration Settings
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Groq API
    groq_api_key: str
    groq_model: str = "llama-3.1-70b-versatile"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # POC Settings
    thread_id_prefix: str = "t-poc-"
    clarification_limit: int = 2

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
