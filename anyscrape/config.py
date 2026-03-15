from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class Settings:
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    max_search_results: int = 5
    max_crawl_concurrency: int = 3
    headless_default: bool = True
    # Webshare proxy rotation (set API key OR direct proxy credentials)
    webshare_api_key: str = ""
    webshare_proxy_host: str = ""
    webshare_proxy_port: str = ""
    webshare_proxy_username: str = ""
    webshare_proxy_password: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Please export it before running AnyScrape."
            )
        model = os.getenv("ANYSCRAPE_MODEL", "gpt-4o-mini")
        max_results = int(os.getenv("ANYSCRAPE_MAX_RESULTS", "5"))
        concurrency = int(os.getenv("ANYSCRAPE_MAX_CRAWL_CONCURRENCY", "3"))
        headless_default = os.getenv("ANYSCRAPE_HEADLESS_DEFAULT", "true").lower() != "false"
        return cls(
            openai_api_key=api_key,
            openai_model=model,
            max_search_results=max_results,
            max_crawl_concurrency=concurrency,
            headless_default=headless_default,
            webshare_api_key=os.getenv("WEBSHARE_API_KEY", ""),
            webshare_proxy_host=os.getenv("WEBSHARE_PROXY_HOST", ""),
            webshare_proxy_port=os.getenv("WEBSHARE_PROXY_PORT", ""),
            webshare_proxy_username=os.getenv("WEBSHARE_PROXY_USERNAME", ""),
            webshare_proxy_password=os.getenv("WEBSHARE_PROXY_PASSWORD", ""),
        )


settings: Optional[Settings] = None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings.from_env()
    return settings


