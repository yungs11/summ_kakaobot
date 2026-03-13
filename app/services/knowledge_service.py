import logging
from datetime import date

import httpx

from app.config import Settings
from app.schemas import ExtractedContent

logger = logging.getLogger(__name__)


class KnowledgeService:
    """rag-service REST API 클라이언트."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def _enabled(self) -> bool:
        return bool(self.settings.rag_service_url)

    async def ingest_summary(self, content: ExtractedContent, summary_text: str, category: str = "Other") -> None:
        if not self._enabled:
            logger.info("RAG service not configured (RAG_SERVICE_URL unset), skipping ingest")
            return
        payload = {
            "source_url": content.url,
            "source_type": content.source_type,
            "title": content.title or "",
            "category": category,
            "summary_text": summary_text,
            "raw_text": content.content,
            "summary_date": date.today().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.settings.rag_service_url}/ingest", json=payload)
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "RAG ingest done: document_id=%s created=%s url=%s",
                    data.get("document_id"),
                    data.get("created"),
                    content.url,
                )
        except Exception:  # noqa: BLE001
            logger.exception("RAG ingest failed: url=%s", content.url)

    async def search(
        self,
        *,
        query: str,
        limit: int = 5,
        category: str | None = None,
    ) -> list[dict]:
        if not self._enabled:
            return []
        payload: dict = {"query": query, "limit": limit}
        if category:
            payload["category"] = category
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{self.settings.rag_service_url}/search", json=payload)
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG search failed: query=%s", query)
            return []

    async def recent_documents(self, limit: int = 5) -> list[dict]:
        if not self._enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.settings.rag_service_url}/documents/recent",
                    params={"limit": limit},
                )
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG recent_documents failed")
            return []

    async def list_categories(self) -> list[dict]:
        if not self._enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.settings.rag_service_url}/documents/categories")
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG list_categories failed")
            return []

    async def ask(
        self,
        *,
        query: str,
        limit: int = 6,
        category: str | None = None,
    ) -> dict:
        if not self._enabled:
            return {
                "answer": "지식베이스가 아직 준비 중입니다. (RAG_SERVICE_URL 미설정)",
                "sources": [],
                "hits": [],
            }
        payload: dict = {"query": query, "limit": limit}
        if category:
            payload["category"] = category
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.settings.rag_service_url}/ask", json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception:  # noqa: BLE001
            logger.exception("RAG ask failed: query=%s", query)
            return {
                "answer": "RAG 서비스 호출 중 오류가 발생했습니다.",
                "sources": [],
                "hits": [],
            }
