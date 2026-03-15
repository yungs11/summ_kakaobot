import logging
import re
import time

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.services.job_store import JobStore
from app.services.knowledge_service import KnowledgeService

load_dotenv()
settings = Settings.from_env()
knowledge_service = KnowledgeService(settings)
summary_job_store = JobStore()
knowledge_job_store = JobStore()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kakao Summary Bot Skill Server")

MAX_SIMPLE_TEXT_LEN = 900
MAX_OUTPUTS = 3
RESULT_CMD_PATTERN = re.compile(r"^\s*/?결과\s+([A-Za-z0-9]{6,20})\s*$")
KNOWLEDGE_SEARCH_PATTERN = re.compile(r"^\s*지식\s*검색\s+(.+?)\s*$")
KNOWLEDGE_ASK_PATTERN = re.compile(r"^\s*지식\s*질문\s+(.+?)\s*$")
RECENT_DOCS_PATTERN = re.compile(r"^\s*(최근\s*문서|최근문서)\s*$")
CATEGORY_LIST_PATTERN = re.compile(r"^\s*(카테고리\s*목록|카테고리목록)\s*$")
WEB_LOGIN_PATTERN = re.compile(r"^\s*(웹\s*로그인|web\s*login)\s*$", re.IGNORECASE)
WEB_URL_PATTERN = re.compile(r"^\s*(웹\s*주소|웹주소|web\s*url|사이트\s*주소|사이트주소)\s*$", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
KAKAO_FILE_PATTERN = re.compile(r"^\s*\[(PDF converted|File|이미지|사진|동영상)\]", re.IGNORECASE)


def _sanitize_text(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text or "").strip()


def _split_for_kakao(text: str) -> list[str]:
    cleaned = _sanitize_text(text)
    if not cleaned:
        return ["응답 텍스트가 비어 있습니다."]

    chunks: list[str] = []
    rest = cleaned

    while rest and len(chunks) < MAX_OUTPUTS:
        if len(rest) <= MAX_SIMPLE_TEXT_LEN:
            chunks.append(rest)
            rest = ""
            break

        cut = rest.rfind("\n", 0, MAX_SIMPLE_TEXT_LEN)
        if cut < 200:
            cut = rest.rfind(" ", 0, MAX_SIMPLE_TEXT_LEN)
        if cut < 1:
            cut = MAX_SIMPLE_TEXT_LEN

        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()

    if rest and chunks:
        suffix = "\n...(생략)"
        last = chunks[-1]
        keep = max(1, MAX_SIMPLE_TEXT_LEN - len(suffix))
        chunks[-1] = last[:keep].rstrip() + suffix

    return chunks or [cleaned[:MAX_SIMPLE_TEXT_LEN]]


def kakao_simple_text(text: str) -> dict:
    outputs = [{"simpleText": {"text": chunk}} for chunk in _split_for_kakao(text)]
    return {"version": "2.0", "template": {"outputs": outputs}}


def kakao_text_response(text: str, quick_replies: list[dict] | None = None) -> dict:
    response = kakao_simple_text(text)
    if quick_replies:
        response["template"]["quickReplies"] = quick_replies
    return response


def kakao_job_accepted(job_id: str, job_name: str = "요약", result_cmd: str = "/결과") -> dict:
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            f"{job_name} 요청을 접수했습니다.\n"
                            f"요청 ID: {job_id}\n"
                            f"잠시 후 '{result_cmd} {job_id}'를 보내 결과를 확인하세요."
                        ),
                    }
                }
            ],
            "quickReplies": [
                {"label": "결과 확인", "action": "message", "messageText": f"{result_cmd} {job_id}"}
            ],
        },
    }


def kakao_job_processing(job_id: str, result_cmd: str = "/결과") -> dict:
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            f"요청 ID '{job_id}'는 아직 처리 중입니다.\n"
                            f"잠시 후 다시 '{result_cmd} {job_id}'를 보내주세요."
                        ),
                    }
                }
            ],
            "quickReplies": [
                {"label": "결과 확인", "action": "message", "messageText": f"{result_cmd} {job_id}"}
            ],
        },
    }


def _extract_utterance(payload: dict) -> str:
    user_request = payload.get("userRequest", {})
    utterance = user_request.get("utterance")
    if isinstance(utterance, str):
        return utterance
    return ""


def _extract_kakao_user_id(payload: dict) -> str | None:
    user_request = payload.get("userRequest", {})
    user = user_request.get("user", {}) if isinstance(user_request, dict) else {}
    uid = user.get("id") if isinstance(user, dict) else None
    return str(uid).strip() if isinstance(uid, str) and uid.strip() else None


def _extract_result_job_id(utterance: str) -> str | None:
    match = RESULT_CMD_PATTERN.match(utterance or "")
    return match.group(1) if match else None


def _extract_url(payload: dict, utterance: str) -> str | None:
    match = URL_PATTERN.search(utterance or "")
    if match:
        return match.group(0).rstrip(').,\"\'')

    action = payload.get("action", {})
    params = action.get("params", {}) if isinstance(action, dict) else {}
    param_url = params.get("url") if isinstance(params, dict) else None
    if isinstance(param_url, str):
        m = URL_PATTERN.search(param_url)
        return m.group(0).rstrip(').,\"\'') if m else param_url.strip()

    return None


def _extract_knowledge_search_query(utterance: str) -> str | None:
    match = KNOWLEDGE_SEARCH_PATTERN.match(utterance or "")
    return match.group(1).strip() if match else None


def _extract_knowledge_ask_query(utterance: str) -> str | None:
    match = KNOWLEDGE_ASK_PATTERN.match(utterance or "")
    return match.group(1).strip() if match else None


def _is_recent_documents_command(utterance: str) -> bool:
    return bool(RECENT_DOCS_PATTERN.match(utterance or ""))


def _is_category_list_command(utterance: str) -> bool:
    return bool(CATEGORY_LIST_PATTERN.match(utterance or ""))


def _build_summary_help_message() -> str:
    return (
        "사용법\n"
        "1) URL을 보내면 요약을 접수합니다.\n"
        "2) 안내받은 요청 ID로 '/결과 <요청ID>'를 보내면 결과를 확인할 수 있습니다.\n\n"
        "예시\n"
        "- 요약 https://example.com/news\n"
        "- /결과 ABC123XYZ\n\n"
        "지식 기능\n"
        "- 지식 검색 <키워드>\n"
        "- 지식 질문 <질문>\n"
        "- 최근 문서\n"
        "- 카테고리 목록\n\n"
        "웹앱\n"
        "- 웹 주소: 웹앱 접속 주소 확인\n"
        "- 웹 로그인: 웹앱 로그인 코드 발급"
    )


def _build_knowledge_help_message() -> str:
    return (
        "지식 기능 사용법\n"
        "- 지식 검색 <키워드>\n"
        "- 지식 질문 <질문>\n"
        "- 최근 문서\n"
        "- 카테고리 목록\n\n"
        "예시\n"
        "- 지식 검색 Places API\n"
        "- 지식 질문 내가 저장한 문서 기준으로 Places API 핵심을 알려줘"
    )


def _build_knowledge_quick_replies() -> list[dict]:
    return [
        {"label": "최근 문서", "action": "message", "messageText": "최근 문서"},
        {"label": "카테고리 목록", "action": "message", "messageText": "카테고리 목록"},
    ]


def _format_knowledge_search_results(query: str, items: list[dict]) -> str:
    unique_items: list[dict] = []
    seen_keys: set[str] = set()
    for item in items:
        key = str(item.get("source_url") or item.get("document_id") or item.get("title") or "")
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        unique_items.append(item)

    if not unique_items:
        return (
            f"'{query}'에 대한 저장 문서를 찾지 못했습니다.\n"
            "다른 키워드로 다시 검색해 주세요."
        )

    lines = [f"[지식 검색] '{query}' 결과 {len(unique_items)}건"]
    for idx, item in enumerate(unique_items[:5], start=1):
        title = str(item.get("title", "")).strip() or "Untitled"
        category = str(item.get("category", "")).strip() or "-"
        source_url = str(item.get("source_url", "")).strip()
        lines.append(f"{idx}. {title}")
        lines.append(f"카테고리: {category}")
        if source_url:
            lines.append(source_url)
        snippet = str(item.get("chunk_text", "")).strip()
        if snippet:
            lines.append(snippet[:180])
        lines.append("")
    return "\n".join(lines).strip()


def _format_recent_documents(items: list[dict]) -> str:
    if not items:
        return "저장된 문서가 없습니다."

    lines = [f"[최근 문서] {len(items)}건"]
    for idx, item in enumerate(items[:5], start=1):
        title = str(item.get("title", "")).strip() or "Untitled"
        category = str(item.get("category", "")).strip() or "-"
        source_type = str(item.get("source_type", "")).strip() or "-"
        source_url = str(item.get("source_url", "")).strip()
        lines.append(f"{idx}. {title}")
        lines.append(f"{category} / {source_type}")
        if source_url:
            lines.append(source_url)
        lines.append("")
    return "\n".join(lines).strip()


def _format_category_list(items: list[dict]) -> str:
    if not items:
        return "저장된 카테고리가 없습니다."

    lines = ["[카테고리 목록]"]
    for item in items:
        category = str(item.get("category", "")).strip() or "-"
        count = int(item.get("document_count", 0) or 0)
        lines.append(f"- {category}: {count}건")
    return "\n".join(lines)


def _build_result_message(job_store: JobStore, job_id: str, result_cmd: str = "/결과") -> str:
    job = job_store.get(job_id)
    if not job:
        return (
            f"요청 ID '{job_id}'를 찾지 못했습니다.\n"
            "ID를 다시 확인해 주세요. (요청은 약 1시간 동안 조회 가능)"
        )

    if job.status in ("queued", "processing"):
        return (
            f"요청 ID '{job_id}'는 아직 처리 중입니다.\n"
            f"잠시 후 다시 '{result_cmd} {job_id}'를 보내주세요."
        )

    if job.status == "failed":
        return (
            f"요청 ID '{job_id}' 처리 중 오류가 발생했습니다.\n"
            f"원인: {job.error_text[:180]}"
        )

    return job.result_text


def _build_cross_result_response(job_id: str, result_cmd: str = "/결과") -> dict:
    for store in (summary_job_store, knowledge_job_store):
        job = store.get(job_id)
        if job is None:
            continue
        if job.status in ("queued", "processing"):
            return kakao_job_processing(job_id, result_cmd=result_cmd)
        return kakao_simple_text(_build_result_message(store, job_id, result_cmd=result_cmd))

    return kakao_simple_text(
        f"요청 ID '{job_id}'를 찾지 못했습니다.\n"
        "ID를 다시 확인해 주세요. (요청은 약 1시간 동안 조회 가능)"
    )


async def _process_summary_job(job_id: str, url: str, user_id: str | None = None) -> None:
    started = time.perf_counter()
    summary_job_store.mark_processing(job_id)
    try:
        result = await knowledge_service.summarize(url=url, user_id=user_id)
        if result.get("status") == "ok":
            if result.get("created") is False:
                header = f"[기존 문서] 동일한 URL이 이미 DB에 저장되어 있어 새로 저장되지 않았습니다.\n{url}"
            else:
                header = f"[요약 완료] {url}"
            message = f"{header}\n\n{result['summary']}"
        else:
            message = result.get("message", f"[요약 불가] {url}")
        summary_job_store.mark_done(job_id, message)
        elapsed = time.perf_counter() - started
        logger.info("Summary job done: id=%s time=%.2fs", job_id, elapsed)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process summary job. id=%s url=%s", job_id, url)
        summary_job_store.mark_failed(job_id, str(exc))


async def _process_knowledge_job(job_id: str, query: str, user_id: str | None = None) -> None:
    started = time.perf_counter()
    knowledge_job_store.mark_processing(job_id)
    try:
        result = await knowledge_service.ask(query=query, limit=5, user_id=user_id)
        message_parts = [f"[지식 답변]\n\n{result['answer']}"]
        if result["sources"]:
            message_parts.append("\n출처")
            message_parts.extend(result["sources"])
        message = "\n".join(message_parts)
        knowledge_job_store.mark_done(job_id, message)
        elapsed = time.perf_counter() - started
        logger.info("Knowledge job done: id=%s time=%.2fs", job_id, elapsed)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process knowledge job. id=%s", job_id)
        knowledge_job_store.mark_failed(job_id, str(exc))


def _enqueue_knowledge_job(query: str, background_tasks: BackgroundTasks, user_id: str | None = None) -> JSONResponse:
    if not query:
        return JSONResponse(kakao_text_response(_build_knowledge_help_message(), _build_knowledge_quick_replies()))

    job = knowledge_job_store.create(query)
    background_tasks.add_task(_process_knowledge_job, job.job_id, query, user_id)
    return JSONResponse(kakao_job_accepted(job.job_id, job_name="지식 답변"))


async def _handle_knowledge_command(utterance: str, background_tasks: BackgroundTasks, user_id: str | None = None) -> JSONResponse | None:
    search_query = _extract_knowledge_search_query(utterance)
    if search_query is not None:
        items = await knowledge_service.search(query=search_query, limit=5, user_id=user_id)
        return JSONResponse(
            kakao_text_response(_format_knowledge_search_results(search_query, items), _build_knowledge_quick_replies())
        )

    ask_query = _extract_knowledge_ask_query(utterance)
    if ask_query is not None:
        return _enqueue_knowledge_job(ask_query, background_tasks, user_id=user_id)

    if _is_recent_documents_command(utterance):
        items = await knowledge_service.recent_documents(limit=5, user_id=user_id)
        return JSONResponse(
            kakao_text_response(_format_recent_documents(items), _build_knowledge_quick_replies())
        )

    if _is_category_list_command(utterance):
        items = await knowledge_service.list_categories(user_id=user_id)
        return JSONResponse(
            kakao_text_response(_format_category_list(items), _build_knowledge_quick_replies())
        )

    return None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/knowledge/search")
async def knowledge_search(request: Request):
    payload = await request.json()
    query = str(payload.get("query", "")).strip()
    if not query:
        return JSONResponse({"query": "", "count": 0, "items": []})

    limit = int(payload.get("limit", 5))
    category = payload.get("category")
    category_str = str(category).strip() if isinstance(category, str) and category.strip() else None

    items = await knowledge_service.search(query=query, limit=limit, category=category_str)
    return JSONResponse({"query": query, "count": len(items), "items": items})


@app.post("/knowledge/ask")
async def knowledge_ask(request: Request):
    payload = await request.json()
    query = str(payload.get("query", "")).strip()
    if not query:
        return JSONResponse({"query": "", "answer": "질문을 입력해 주세요.", "sources": [], "hits": []})

    limit = int(payload.get("limit", 6))
    category = payload.get("category")
    category_str = str(category).strip() if isinstance(category, str) and category.strip() else None

    result = await knowledge_service.ask(query=query, limit=limit, category=category_str)
    return JSONResponse({
        "query": query,
        "answer": result["answer"],
        "sources": result["sources"],
        "hits": result["hits"],
    })


@app.post("/kakao/skill")
async def kakao_skill(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    logger.info("KAKAO_PAYLOAD: %s", payload)
    utterance = _extract_utterance(payload)
    kakao_user_id = _extract_kakao_user_id(payload)

    result_job_id = _extract_result_job_id(utterance)
    if result_job_id:
        return JSONResponse(_build_cross_result_response(result_job_id))

    if WEB_URL_PATTERN.match(utterance):
        url = settings.web_app_url
        if url:
            return JSONResponse(kakao_simple_text(f"웹앱 주소\n{url}"))
        return JSONResponse(kakao_simple_text("웹앱 주소가 설정되어 있지 않습니다.\n관리자에게 문의하세요."))

    if WEB_LOGIN_PATTERN.match(utterance):
        if not kakao_user_id:
            return JSONResponse(kakao_simple_text("사용자 ID를 확인할 수 없습니다."))
        try:
            otp = await knowledge_service.issue_otp(kakao_user_id)
            msg = f"웹 로그인 코드: {otp}\n\n5분 내에 웹앱 로그인 페이지에서 입력하세요.\n(1회 사용 후 만료)"
        except Exception:
            logger.exception("OTP 발급 실패")
            msg = "로그인 코드 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
        return JSONResponse(kakao_simple_text(msg))

    if KAKAO_FILE_PATTERN.match(utterance):
        return JSONResponse(kakao_simple_text(
            "카카오톡에서 직접 파일을 공유하면 파일 내용을 가져올 수 없습니다.\n\n"
            "PDF/Word 파일을 요약하려면:\n"
            "1) 파일을 외부에 업로드 후 공개 URL을 전달하세요.\n"
            "   예: Google Drive 공유 링크, GitHub raw 링크\n"
            "2) 또는 웹앱에서 직접 파일을 업로드하세요."
        ))

    knowledge_response = await _handle_knowledge_command(utterance, background_tasks, user_id=kakao_user_id)
    if knowledge_response is not None:
        return knowledge_response

    url = _extract_url(payload, utterance)
    if not url:
        return JSONResponse(kakao_simple_text(_build_summary_help_message()))

    job = summary_job_store.create(url)
    background_tasks.add_task(_process_summary_job, job.job_id, url, kakao_user_id)
    return JSONResponse(kakao_job_accepted(job.job_id, job_name="요약"))
