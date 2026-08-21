from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "commission-service"
    user: str = "commission_pay"
    password: str = "commission_pay"
    dsn: str = "insurance-oracle:1521/FREEPDB1"

    model_config = {"env_prefix": "COMMISSION_SVC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
