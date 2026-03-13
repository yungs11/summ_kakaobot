import html as html_lib
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import ParseError

import httpx
import trafilatura
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi

try:
    from yt_dlp import YoutubeDL
except Exception:  # noqa: BLE001
    YoutubeDL = None  # type: ignore[assignment]

from app.config import Settings
from app.schemas import ExtractedContent

URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
logger = logging.getLogger(__name__)

# 뉴스 도메인 (정확 일치 또는 서브도메인) - 블로그보다 먼저 체크
_NEWS_DOMAINS = {
    "techcrunch.com", "zdnet.com", "wired.com", "theverge.com",
    "reuters.com", "bloomberg.com", "forbes.com", "cnbc.com",
    "venturebeat.com", "arstechnica.com", "engadget.com",
    "chosun.com", "joins.com", "hani.co.kr", "khan.co.kr",
    "yonhapnewstv.co.kr", "yonhap.co.kr", "ytn.co.kr",
    "etnews.com", "zdnet.co.kr", "itworld.co.kr", "aitimes.com",
    "news.naver.com", "news.daum.net",
}
# 뉴스 URL 경로 패턴 (날짜, /news/, /article/ 등)
_NEWS_PATH_RE = re.compile(r"/(?:news|article|story|press|release|[0-9]{4}/[0-9]{2})/", re.IGNORECASE)

# 블로그 플랫폼 도메인 (서브도메인 포함)
_BLOG_DOMAINS = {
    "medium.com", "substack.com", "tistory.com", "velog.io",
    "brunch.co.kr", "blog.naver.com",
    "wordpress.com", "blogspot.com", "ghost.io", "hashnode.dev",
    "dev.to", "notion.so",
}
# 블로그 URL 경로 패턴
_BLOG_PATH_RE = re.compile(r"/(blog|posts?|b|writing)/", re.IGNORECASE)


def _infer_source_type(url: str) -> str:
    """URL 패턴·도메인으로 source_type 추론: news / blog / other"""
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")
    path = parsed.path

    # 뉴스 우선 체크 (news.naver.com 등이 blog.naver.com보다 먼저 매칭되어야 함)
    if any(host == d or host.endswith("." + d) for d in _NEWS_DOMAINS):
        return "news"
    if _NEWS_PATH_RE.search(path):
        return "news"
    if any(host == d or host.endswith("." + d) for d in _BLOG_DOMAINS):
        return "blog"
    if _BLOG_PATH_RE.search(path):
        return "blog"
    return "other"


def extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(').,\"\'')


def _youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        return parsed.path.strip("/") or None

    if "youtube.com" in host:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[-1].split("/")[0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[-1].split("/")[0]
    return None


def _clean_text(text: str, limit: int = 12000) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


def _extract_html_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    return title or "Untitled"


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


def _fetch_html(url: str, settings: Settings) -> tuple[str, str]:
    """(final_url, html) 반환. 403 시 User-Agent 바꿔 재시도."""
    with httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers=_BROWSER_HEADERS,
    ) as client:
        response = client.get(url)

        if response.status_code == 403:
            # Googlebot UA로 재시도 (일부 사이트 허용)
            response = client.get(
                url,
                headers={
                    **_BROWSER_HEADERS,
                    "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
                },
            )

        if response.status_code == 403:
            raise ValueError(
                f"해당 페이지는 외부 접근을 차단하고 있어 내용을 가져올 수 없습니다. (403 Forbidden)\n"
                f"URL: {response.url}"
            )

        response.raise_for_status()
        return str(response.url), response.text


def _extract_from_web(url: str, settings: Settings) -> ExtractedContent:
    final_url, html = _fetch_html(url, settings)

    redirected_video_id = _youtube_video_id(final_url)
    if redirected_video_id:
        logger.info(
            "Redirect resolved to YouTube: original_url=%s final_url=%s video_id=%s",
            url,
            final_url,
            redirected_video_id,
        )
        return _extract_from_youtube(final_url, settings)

    title = _extract_html_title(html)
    content = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    ) or ""

    cleaned = _clean_text(content)
    if not cleaned:
        cleaned = _clean_text(BeautifulSoup(html, "html.parser").get_text(" "))

    return ExtractedContent(
        url=final_url,
        source_type=_infer_source_type(final_url),
        title=title,
        content=cleaned,
    )


def _parse_vtt(raw: str) -> str:
    lines = raw.splitlines()
    parts: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        upper = s.upper()
        if upper.startswith("WEBVTT") or upper.startswith("NOTE"):
            continue
        if upper.startswith("KIND:") or upper.startswith("LANGUAGE:"):
            continue
        if "-->" in s:
            continue
        if s.isdigit():
            continue
        parts.append(s)

    text = " ".join(parts)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(text)


def _parse_xml_caption(raw: str) -> str:
    try:
        root = ET.fromstring(raw)
    except ParseError:
        return ""

    parts: list[str] = []
    for node in root.findall(".//text"):
        item = "".join(node.itertext()).strip()
        if item:
            parts.append(item)

    if not parts:
        return ""
    return html_lib.unescape(" ".join(parts))


def _parse_json3_caption(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    parts: list[str] = []
    events = data.get("events", []) if isinstance(data, dict) else []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        segs = ev.get("segs", [])
        if not isinstance(segs, list):
            continue
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            txt = seg.get("utf8", "")
            if isinstance(txt, str) and txt:
                parts.append(txt.replace("\n", " "))

    if not parts:
        return ""
    return html_lib.unescape(" ".join(parts))


def _decode_subtitle(raw: str, ext: str) -> str:
    ext_norm = (ext or "").lower()

    if ext_norm == "json3":
        parsed = _parse_json3_caption(raw)
        if parsed:
            return parsed

    if ext_norm in {"srv3", "ttml", "xml"}:
        parsed = _parse_xml_caption(raw)
        if parsed:
            return parsed

    stripped = raw.lstrip()
    if stripped.startswith("{"):
        parsed = _parse_json3_caption(raw)
        if parsed:
            return parsed

    if stripped.startswith("<"):
        parsed = _parse_xml_caption(raw)
        if parsed:
            return parsed

    return _parse_vtt(raw)


def _build_yt_dlp_candidates(info: dict[str, Any]) -> list[dict[str, str]]:
    subtitles = info.get("subtitles") if isinstance(info, dict) else None
    auto = info.get("automatic_captions") if isinstance(info, dict) else None

    source_buckets: list[tuple[str, dict[str, Any]]] = []
    if isinstance(subtitles, dict):
        source_buckets.append(("subtitles", subtitles))
    if isinstance(auto, dict):
        source_buckets.append(("automatic_captions", auto))

    def ordered_lang_keys(bucket: dict[str, Any]) -> list[str]:
        preferred = ["ko", "ko-KR", "en", "en-US"]
        keys = list(bucket.keys())
        out: list[str] = []

        for p in preferred:
            if p in bucket and p not in out:
                out.append(p)

        for k in keys:
            if (k.startswith("ko") or k.startswith("en")) and k not in out:
                out.append(k)

        for k in keys:
            if k not in out:
                out.append(k)
        return out

    ext_rank = {"vtt": 0, "srv3": 1, "json3": 2, "ttml": 3, "xml": 4}
    scored: list[tuple[int, int, int, dict[str, str]]] = []

    for source_idx, (source_name, bucket) in enumerate(source_buckets):
        for lang_idx, lang in enumerate(ordered_lang_keys(bucket)):
            tracks = bucket.get(lang)
            if not isinstance(tracks, list):
                continue
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                track_url = track.get("url")
                if not isinstance(track_url, str) or not track_url:
                    continue
                ext = str(track.get("ext", "")).lower()
                payload = {
                    "source": source_name,
                    "lang": lang,
                    "ext": ext,
                    "url": track_url,
                }
                scored.append((source_idx, lang_idx, ext_rank.get(ext, 9), payload))

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return [item[3] for item in scored]


def _extract_with_yt_dlp(url: str, video_id: str, settings: Settings) -> str:
    if YoutubeDL is None:
        logger.warning("YouTube fallback unavailable: video_id=%s method=yt_dlp reason=module_missing", video_id)
        return ""

    try:
        with YoutubeDL(
            {
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }
        ) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "YouTube fallback failed: video_id=%s method=yt_dlp reason=%s",
            video_id,
            exc.__class__.__name__,
        )
        return ""

    if not isinstance(info, dict):
        logger.warning("YouTube fallback failed: video_id=%s method=yt_dlp reason=invalid_info", video_id)
        return ""

    candidates = _build_yt_dlp_candidates(info)
    logger.info("YouTube yt-dlp candidates: video_id=%s count=%d", video_id, len(candidates))

    with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
        for idx, candidate in enumerate(candidates, start=1):
            source = candidate["source"]
            lang = candidate["lang"]
            ext = candidate["ext"]
            sub_url = candidate["url"]
            try:
                response = client.get(sub_url)
                response.raise_for_status()
                raw = response.text
                parsed = _decode_subtitle(raw, ext)
                cleaned = _clean_text(parsed)
                if cleaned:
                    preview = cleaned[:120].replace("\n", " ")
                    logger.info(
                        "YouTube extraction success: video_id=%s method=yt_dlp source=%s lang=%s ext=%s track_index=%d chars=%d preview=%r",
                        video_id,
                        source,
                        lang,
                        ext,
                        idx,
                        len(cleaned),
                        preview,
                    )
                    return cleaned

                logger.warning(
                    "YouTube yt-dlp track empty: video_id=%s source=%s lang=%s ext=%s track_index=%d",
                    video_id,
                    source,
                    lang,
                    ext,
                    idx,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "YouTube yt-dlp track failed: video_id=%s source=%s lang=%s ext=%s track_index=%d reason=%s",
                    video_id,
                    source,
                    lang,
                    ext,
                    idx,
                    exc.__class__.__name__,
                )

    return ""


def _extract_from_youtube(url: str, settings: Settings) -> ExtractedContent:
    video_id = _youtube_video_id(url)
    if not video_id:
        raise ValueError("유효한 유튜브 영상 URL이 아닙니다.")

    logger.info("YouTube extraction start: video_id=%s url=%s method=transcript_api", video_id, url)

    transcript = []
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])
        joined = " ".join(item.get("text", "") for item in transcript)
        cleaned = _clean_text(joined)
    except ParseError:
        logger.warning(
            "YouTube extraction failed: video_id=%s method=transcript_api reason=parse_error",
            video_id,
        )
        cleaned = ""
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "YouTube extraction failed: video_id=%s method=transcript_api reason=%s",
            video_id,
            exc.__class__.__name__,
        )
        cleaned = ""

    if cleaned:
        preview = cleaned[:120].replace("\n", " ")
        logger.info(
            "YouTube extraction success: video_id=%s method=transcript_api segments=%d chars=%d preview=%r",
            video_id,
            len(transcript),
            len(cleaned),
            preview,
        )
        return ExtractedContent(
            url=url,
            source_type="youtube",
            title=f"YouTube Video ({video_id})",
            content=cleaned,
        )

    logger.info("YouTube extraction fallback start: video_id=%s method=yt_dlp", video_id)
    cleaned = _extract_with_yt_dlp(url, video_id, settings)
    if cleaned:
        return ExtractedContent(
            url=url,
            source_type="youtube",
            title=f"YouTube Video ({video_id})",
            content=cleaned,
        )

    logger.info("YouTube extraction result: video_id=%s text_available=false", video_id)
    raise ValueError(
        "유튜브 자막 텍스트를 추출하지 못해 요약할 수 없습니다. "
        "비공개·연령 제한·자막 비활성화 영상일 수 있습니다."
    )


def extract_content(url: str, settings: Settings) -> ExtractedContent:
    if _youtube_video_id(url):
        logger.info("Extractor selected: youtube_direct url=%s", url)
        return _extract_from_youtube(url, settings)
    logger.info("Extractor selected: web_or_redirect url=%s", url)
    return _extract_from_web(url, settings)
