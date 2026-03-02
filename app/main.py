import asyncio
import logging
import re
import time

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.services.buddha_bot import ask_buddha
from app.services.content_extractor import extract_content, extract_first_url
from app.services.job_store import JobStore
from app.services.summarizer import summarize_content

load_dotenv()
settings = Settings.from_env()
summary_job_store = JobStore()
buddha_job_store = JobStore()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kakao Multi-Bot Skill Server")

MAX_SIMPLE_TEXT_LEN = 900
MAX_OUTPUTS = 3
RESULT_CMD_PATTERN = re.compile(r"^\s*/?결과\s+([A-Za-z0-9]{6,20})\s*$")
BUDDHA_ROUTE_KEYWORDS = ("부처님", "붓다")


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
    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
        },
    }


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
                {
                    "label": "결과 확인",
                    "action": "message",
                    "messageText": f"{result_cmd} {job_id}",
                }
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
                {
                    "label": "결과 확인",
                    "action": "message",
                    "messageText": f"{result_cmd} {job_id}",
                }
            ],
        },
    }


def _extract_utterance(payload: dict) -> str:
    user_request = payload.get("userRequest", {})
    utterance = user_request.get("utterance")
    if isinstance(utterance, str):
        return utterance
    return ""


def _extract_result_job_id(utterance: str) -> str | None:
    match = RESULT_CMD_PATTERN.match(utterance or "")
    if not match:
        return None
    return match.group(1)


def _extract_url(payload: dict, utterance: str) -> str | None:
    url = extract_first_url(utterance)
    if url:
        return url

    action = payload.get("action", {})
    params = action.get("params", {}) if isinstance(action, dict) else {}
    param_url = params.get("url") if isinstance(params, dict) else None
    if isinstance(param_url, str):
        return extract_first_url(param_url) or param_url.strip()

    return None


def _extract_question(payload: dict, utterance: str) -> str:
    if utterance.strip():
        return utterance.strip()

    action = payload.get("action", {})
    params = action.get("params", {}) if isinstance(action, dict) else {}
    question = params.get("question") if isinstance(params, dict) else None
    if isinstance(question, str):
        return question.strip()
    return ""


def _should_route_to_buddha(utterance: str) -> bool:
    if not utterance:
        return False
    return any(keyword in utterance for keyword in BUDDHA_ROUTE_KEYWORDS)


def _build_summary_help_message() -> str:
    return (
        "사용법\n"
        "1) URL을 보내면 요약을 접수합니다.\n"
        "2) 안내받은 요청 ID로 '/결과 <요청ID>'를 보내면 결과를 확인할 수 있습니다.\n\n"
        "예시\n"
        "- 요약 https://example.com/news\n"
        "- /결과 ABC123XYZ"
    )


def _build_buddha_help_message() -> str:
    return (
        "질문을 보내주세요.\n"
        "답변은 5초 제한 때문에 비동기로 생성됩니다.\n"
        "안내된 요청 ID로 '/결과 <요청ID>'를 보내 확인할 수 있습니다.\n\n"
        "예: 부처님이라면 팀 갈등을 어떻게 보라고 하실까요?"
    )


def _build_result_message(
    job_store: JobStore,
    job_id: str,
    result_cmd: str = "/결과",
) -> str:
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


def _resolve_result_job(job_id: str) -> tuple[str, JobStore] | None:
    summary_job = summary_job_store.get(job_id)
    if summary_job is not None:
        return ("summary", summary_job_store)

    buddha_job = buddha_job_store.get(job_id)
    if buddha_job is not None:
        return ("buddha", buddha_job_store)

    return None


def _build_cross_result_response(job_id: str, result_cmd: str = "/결과") -> dict:
    resolved = _resolve_result_job(job_id)
    if not resolved:
        return kakao_simple_text(
            "요청 ID '{job_id}'를 찾지 못했습니다.\n"
            "ID를 다시 확인해 주세요. (요청은 약 1시간 동안 조회 가능)".format(job_id=job_id)
        )

    _, store = resolved
    job = store.get(job_id)
    if job and job.status in ("queued", "processing"):
        return kakao_job_processing(job_id, result_cmd=result_cmd)

    return kakao_simple_text(_build_result_message(store, job_id, result_cmd=result_cmd))


async def _process_summary_job(job_id: str, url: str) -> None:
    started = time.perf_counter()
    summary_job_store.mark_processing(job_id)
    try:
        extract_started = time.perf_counter()
        content = await asyncio.to_thread(extract_content, url, settings)
        extract_elapsed = time.perf_counter() - extract_started
        logger.info(
            "Summary extract done: id=%s source_type=%s chars=%d elapsed=%.2fs",
            job_id,
            content.source_type,
            len(content.content),
            extract_elapsed,
        )

        summarize_started = time.perf_counter()
        summary = await summarize_content(content, settings)
        summarize_elapsed = time.perf_counter() - summarize_started
        logger.info(
            "Summary llm done: id=%s output_chars=%d elapsed=%.2fs",
            job_id,
            len(summary),
            summarize_elapsed,
        )

        message = f"[요약 완료] {url}\n\n{summary}"
        summary_job_store.mark_done(job_id, message)
        elapsed = time.perf_counter() - started
        logger.info("Summary job done: id=%s, time=%.2fs, summary_len=%d", job_id, elapsed, len(summary))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process summary job. id=%s url=%s", job_id, url)
        summary_job_store.mark_failed(job_id, str(exc))


async def _process_buddha_job(job_id: str, question: str) -> None:
    started = time.perf_counter()
    buddha_job_store.mark_processing(job_id)
    try:
        answer = await ask_buddha(question, settings)
        message = f"[부처님 관점 답변]\n\n{answer}"
        buddha_job_store.mark_done(job_id, message)
        elapsed = time.perf_counter() - started
        logger.info("Buddha job done: id=%s, time=%.2fs, answer_len=%d", job_id, elapsed, len(answer))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process buddha job. id=%s", job_id)
        buddha_job_store.mark_failed(job_id, str(exc))


def _enqueue_buddha_job(payload: dict, utterance: str, background_tasks: BackgroundTasks) -> JSONResponse:
    question = _extract_question(payload, utterance)
    if not question:
        return JSONResponse(kakao_simple_text(_build_buddha_help_message()))

    job = buddha_job_store.create(question)
    background_tasks.add_task(_process_buddha_job, job.job_id, question)
    return JSONResponse(kakao_job_accepted(job.job_id, job_name="답변"))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/kakao/skill")
async def kakao_skill(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    utterance = _extract_utterance(payload)

    result_job_id = _extract_result_job_id(utterance)
    if result_job_id:
        return JSONResponse(_build_cross_result_response(result_job_id))

    if _should_route_to_buddha(utterance):
        return _enqueue_buddha_job(payload, utterance, background_tasks)

    url = _extract_url(payload, utterance)
    if not url:
        return JSONResponse(kakao_simple_text(_build_summary_help_message()))

    job = summary_job_store.create(url)
    background_tasks.add_task(_process_summary_job, job.job_id, url)
    return JSONResponse(kakao_job_accepted(job.job_id, job_name="요약"))


@app.post("/kakao/skill/buddha")
async def kakao_buddha_skill(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    utterance = _extract_utterance(payload)

    result_job_id = _extract_result_job_id(utterance)
    if result_job_id:
        return JSONResponse(_build_cross_result_response(result_job_id))

    return _enqueue_buddha_job(payload, utterance, background_tasks)
