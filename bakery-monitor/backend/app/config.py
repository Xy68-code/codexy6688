"""应用配置 - 所有配置通过环境变量注入。"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置。"""

    # 数据库
    database_url: str = "postgresql://localhost:5432/bakery_monitor"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # 监控
    default_check_interval_min: int = 30
    max_stores_free_tier: int = 1

    # 邮件通知
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@bakery-monitor.com"

    model_config = {"env_prefix": "BM_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
