import asyncio
import logging
import time

from openai import OpenAI

from app.config import Settings

logger = logging.getLogger(__name__)


def _normalize_message_content(raw_content: str | list | None) -> str:
    if isinstance(raw_content, str):
        return raw_content.strip()

    if isinstance(raw_content, list):
        parts: list[str] = []
        for part in raw_content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()

    return ""


async def generate_chat_text(
    *,
    settings: Settings,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    def _call_model() -> str:
        started = time.perf_counter()
        logger.info(
            "LLM request start: model=%s base_url=%s prompt_chars=%d max_tokens=%s",
            model,
            settings.openrouter_base_url,
            len(user_prompt),
            str(max_tokens),
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not response.choices:
            raise ValueError("모델 응답이 비어 있습니다.")

        message = response.choices[0].message
        text = _normalize_message_content(message.content)
        if not text:
            raise ValueError("모델 응답 텍스트를 추출하지 못했습니다.")

        elapsed = time.perf_counter() - started
        logger.info(
            "LLM request done: model=%s elapsed=%.2fs output_chars=%d",
            model,
            elapsed,
            len(text),
        )
        return text

    return await asyncio.to_thread(_call_model)
