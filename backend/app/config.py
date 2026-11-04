from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    postgres_password: str = ""
    redis_url: str
    anthropic_api_key: str = ""
    firebase_credentials_path: str
    api_v1_prefix: str = "/api/v1"
    llm_provider: str = "ollama"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_base_url: str = "http://localhost:11434"
    render_server_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()