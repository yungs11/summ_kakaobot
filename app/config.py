import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    rag_service_url: str = ""
    web_app_url: str = ""

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            rag_service_url=os.getenv("RAG_SERVICE_URL", ""),
            web_app_url=os.getenv("WEB_APP_URL", "").strip(),
        )
