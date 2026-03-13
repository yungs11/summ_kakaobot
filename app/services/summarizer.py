from app.config import Settings
from app.schemas import ExtractedContent
from app.services.openrouter_client import generate_chat_text

_VALID_CATEGORIES = {"AI/LLM", "Infra", "DB", "Product", "Business", "Financial", "Other"}

_CLASSIFY_SYSTEM = "You are a content classifier. Reply with exactly one category label, nothing else."

_CLASSIFY_USER = """\
Classify the following content into one of these categories:
AI/LLM, Infra, DB, Product, Business, Financial, Other

- AI/LLM: AI, LLM, machine learning, deep learning, neural network, ChatGPT, Claude, Gemini, etc.
- Infra: cloud, DevOps, Kubernetes, Docker, CI/CD, networking, server, infrastructure
- DB: database, SQL, NoSQL, vector DB, Neo4j, PostgreSQL, Redis, data storage
- Product: product launch, feature release, UX/UI, SaaS, app, platform
- Business: startup, funding, M&A, strategy, market, partnership, hiring
- Financial: stock, crypto, finance, investment, earnings, IPO, economy
- Other: anything that doesn't fit above

Title: {title}

Summary:
{summary}

Reply with only the category name."""


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
    return summary


async def classify_category(title: str, summary: str, settings: Settings) -> str:
    prompt = _CLASSIFY_USER.replace("{title}", title).replace("{summary}", summary[:800])
    result = await generate_chat_text(
        settings=settings,
        model=settings.openrouter_summary_model,
        system_prompt=_CLASSIFY_SYSTEM,
        user_prompt=prompt,
        temperature=0.0,
    )
    category = result.strip().strip("\"'")
    return category if category in _VALID_CATEGORIES else "Other"
