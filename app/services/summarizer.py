from app.config import Settings
from app.schemas import ExtractedContent
from app.services.openrouter_client import generate_chat_text

_FAILURE_KEYWORDS = ("요약불가", "알 수 없", "확인 불가", "접근 불가", "내용을 읽을 수 없", "요약할 수 없")

_URL_ONLY_SYSTEM = "You are a helpful assistant that summarizes web content in Korean."

_URL_ONLY_USER = """\
다음 URL의 페이지 내용을 한국어로 요약해주세요.
직접 접근이 어려운 경우, URL과 제목을 바탕으로 알고 있는 정보를 활용해 요약해주세요.
내용을 전혀 알 수 없으면 '요약불가'라고만 답하세요.

URL: {url}
제목: {title}

3~5문장으로 핵심 내용을 요약해주세요."""

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


def is_failed_summary(text: str) -> bool:
    """LLM이 내용을 요약하지 못했음을 나타내는 응답인지 확인."""
    return any(kw in text for kw in _FAILURE_KEYWORDS)


async def summarize_from_url(url: str, title: str, settings: Settings) -> str:
    """URL만으로 LLM에게 요약을 요청 (콘텐츠 추출 실패 시 폴백)."""
    prompt = _URL_ONLY_USER.replace("{url}", url).replace("{title}", title)
    return await generate_chat_text(
        settings=settings,
        model=settings.openrouter_summary_model,
        system_prompt=_URL_ONLY_SYSTEM,
        user_prompt=prompt,
        temperature=0.2,
    )


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
