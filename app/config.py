import os
from dataclasses import dataclass

from app.prompt_defaults import (
    KNOWLEDGE_QA_SYSTEM_PROMPT,
    KNOWLEDGE_QA_USER_PROMPT_TEMPLATE,
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
    openrouter_knowledge_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    http_timeout_seconds: int = 15
    summary_system_prompt: str = SUMMARY_SYSTEM_PROMPT
    summary_user_prompt_template: str = SUMMARY_USER_PROMPT_TEMPLATE
    knowledge_qa_system_prompt: str = KNOWLEDGE_QA_SYSTEM_PROMPT
    knowledge_qa_user_prompt_template: str = KNOWLEDGE_QA_USER_PROMPT_TEMPLATE

    @staticmethod
    def from_env() -> "Settings":
        default_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        return Settings(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_summary_model=os.getenv("OPENROUTER_SUMMARY_MODEL", default_model),
            openrouter_knowledge_model=os.getenv("OPENROUTER_KNOWLEDGE_MODEL", default_model),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            summary_system_prompt=_env_text("SUMMARY_SYSTEM_PROMPT", SUMMARY_SYSTEM_PROMPT),
            summary_user_prompt_template=_env_text(
                "SUMMARY_USER_PROMPT_TEMPLATE",
                SUMMARY_USER_PROMPT_TEMPLATE,
            ),
            knowledge_qa_system_prompt=_env_text(
                "KNOWLEDGE_QA_SYSTEM_PROMPT",
                KNOWLEDGE_QA_SYSTEM_PROMPT,
            ),
            knowledge_qa_user_prompt_template=_env_text(
                "KNOWLEDGE_QA_USER_PROMPT_TEMPLATE",
                KNOWLEDGE_QA_USER_PROMPT_TEMPLATE,
            ),
        )
