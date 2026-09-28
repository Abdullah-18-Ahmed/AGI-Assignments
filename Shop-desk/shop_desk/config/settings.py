from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str
    catalogue_path: str = "./shop_desk/catalogue/catalogue.json"
    catalogue_version: str = "1.0.0"
    low_stock_threshold: int = 5
    tax_rate: float = 0.0
    shipping_flat: int = 0
    default_page_size: int = 20
    max_history_turns: int = 5
    fast_model: str = "openai/gpt-4o-mini"
    reasoning_model: str = "openai/gpt-4o"
    trace_log_path: str = "./logs/traces.jsonl"
    shop_open_hour: int = 9
    shop_close_hour: int = 18


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()