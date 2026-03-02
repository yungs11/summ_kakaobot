from app.config import Settings
from app.services.openrouter_client import generate_chat_text


def _build_prompt(question: str, template: str) -> str:
    return template.replace("{question}", question.strip())


async def ask_buddha(question: str, settings: Settings) -> str:
    prompt = _build_prompt(question, settings.buddha_user_prompt_template)
    answer = await generate_chat_text(
        settings=settings,
        model=settings.openrouter_buddha_model,
        system_prompt=settings.buddha_system_prompt,
        user_prompt=prompt,
        temperature=0.4,
        max_tokens=700,
    )
    return answer[:1200]
