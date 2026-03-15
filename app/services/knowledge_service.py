import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class KnowledgeService:
    """rag-service REST API 클라이언트."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def _enabled(self) -> bool:
        return bool(self.settings.rag_service_url)

    async def summarize(self, *, url: str, user_id: str | None = None) -> dict:
        """URL을 rag-service에 전달해 추출·요약·저장을 위임합니다."""
        if not self._enabled:
            raise RuntimeError("RAG service not configured (RAG_SERVICE_URL unset)")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.settings.rag_service_url}/summarize",
                json={"url": url, "user_id": user_id},
            )
            resp.raise_for_status()
            return resp.json()

    async def search(
        self,
        *,
        query: str,
        limit: int = 5,
        category: str | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        if not self._enabled:
            return []
        payload: dict = {"query": query, "limit": limit}
        if category:
            payload["category"] = category
        if user_id:
            payload["user_id"] = user_id
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{self.settings.rag_service_url}/search", json=payload)
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG search failed: query=%s", query)
            return []

    async def recent_documents(self, limit: int = 5, user_id: str | None = None) -> list[dict]:
        if not self._enabled:
            return []
        try:
            params: dict = {"limit": limit}
            if user_id:
                params["user_id"] = user_id
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.settings.rag_service_url}/documents/recent",
                    params=params,
                )
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG recent_documents failed")
            return []

    async def list_categories(self, user_id: str | None = None) -> list[dict]:
        if not self._enabled:
            return []
        try:
            params: dict = {}
            if user_id:
                params["user_id"] = user_id
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.settings.rag_service_url}/documents/categories", params=params)
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:  # noqa: BLE001
            logger.exception("RAG list_categories failed")
            return []

    async def issue_otp(self, kakao_user_id: str) -> str:
        if not self._enabled:
            raise RuntimeError("RAG service not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.settings.rag_service_url}/auth/issue-otp",
                json={"user_id": kakao_user_id},
            )
            resp.raise_for_status()
            return resp.json()["otp"]

    async def ask(
        self,
        *,
        query: str,
        limit: int = 6,
        category: str | None = None,
        user_id: str | None = None,
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
        if user_id:
            payload["user_id"] = user_id
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
