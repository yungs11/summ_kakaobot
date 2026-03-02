import os
from dataclasses import dataclass

from app.prompt_defaults import (
    BUDDHA_SYSTEM_PROMPT,
    BUDDHA_USER_PROMPT_TEMPLATE,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_PROMPT_TEMPLATE,
)


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.replace("\\n", "\n")


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_summary_model: str = "openai/gpt-4o-mini"
    openrouter_buddha_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    http_timeout_seconds: int = 15
    summary_system_prompt: str = SUMMARY_SYSTEM_PROMPT
    summary_user_prompt_template: str = SUMMARY_USER_PROMPT_TEMPLATE
    buddha_system_prompt: str = BUDDHA_SYSTEM_PROMPT
    buddha_user_prompt_template: str = BUDDHA_USER_PROMPT_TEMPLATE

    @staticmethod
    def from_env() -> "Settings":
        default_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        return Settings(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_summary_model=os.getenv("OPENROUTER_SUMMARY_MODEL", default_model),
            openrouter_buddha_model=os.getenv("OPENROUTER_BUDDHA_MODEL", default_model),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            summary_system_prompt=_env_text("SUMMARY_SYSTEM_PROMPT", SUMMARY_SYSTEM_PROMPT),
            summary_user_prompt_template=_env_text(
                "SUMMARY_USER_PROMPT_TEMPLATE",
                SUMMARY_USER_PROMPT_TEMPLATE,
            ),
            buddha_system_prompt=_env_text("BUDDHA_SYSTEM_PROMPT", BUDDHA_SYSTEM_PROMPT),
            buddha_user_prompt_template=_env_text(
                "BUDDHA_USER_PROMPT_TEMPLATE",
                BUDDHA_USER_PROMPT_TEMPLATE,
            ),
        )
