from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "billing-service"
    schema_name: str = "billing_svc"
    database_url: str
    document_uri: str = "mongodb://localhost:27017"
    document_db: str = "billing_docs_dev"
    cors_origins: list[str] = ["http://localhost:3000"]
    allow_internal_reset: bool = False

    model_config = {"env_prefix": "BILLING_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
