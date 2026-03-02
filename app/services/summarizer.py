from app.config import Settings
from app.schemas import ExtractedContent
from app.services.openrouter_client import generate_chat_text


def _build_prompt(content: ExtractedContent, template: str) -> str:
    return (
        template.replace("{source_type}", content.source_type)
        .replace("{title}", content.title)
        .replace("{url}", content.url)
        .replace("{content}", content.content)
    )


async def summarize_content(content: ExtractedContent, settings: Settings) -> str:
    prompt = _build_prompt(content, settings.summary_user_prompt_template)
    summary = await generate_chat_text(
        settings=settings,
        model=settings.openrouter_summary_model,
        system_prompt=settings.summary_system_prompt,
        user_prompt=prompt,
        temperature=0.2,
    )
    return summary[:1200]
