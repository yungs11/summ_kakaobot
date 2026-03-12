import logging

from app.config import Settings
from app.schemas import ExtractedContent

logger = logging.getLogger(__name__)

# TODO: Neo4j 연동 구현 후 이 스텁을 교체할 것


class KnowledgeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ingest_summary(self, content: ExtractedContent, summary_text: str) -> None:
        # TODO: Neo4j에 Document + Chunk + Tag 노드 저장
        logger.info(
            "Knowledge ingest skipped (Neo4j not yet connected): url=%s",
            content.url,
        )

    async def search(
        self,
        *,
        query: str,
        limit: int = 5,
        category: str | None = None,
    ) -> list[dict]:
        # TODO: Neo4j 벡터 + 풀텍스트 하이브리드 검색
        logger.info("Knowledge search skipped (Neo4j not yet connected): query=%s", query)
        return []

    async def recent_documents(self, limit: int = 5) -> list[dict]:
        # TODO: Neo4j 최근 Document 노드 조회
        logger.info("Knowledge recent_documents skipped (Neo4j not yet connected)")
        return []

    async def list_categories(self) -> list[dict]:
        # TODO: Neo4j Category 집계
        logger.info("Knowledge list_categories skipped (Neo4j not yet connected)")
        return []

    async def ask(
        self,
        *,
        query: str,
        limit: int = 6,
        category: str | None = None,
    ) -> dict:
        # TODO: Neo4j GraphRAG 기반 QA
        logger.info("Knowledge ask skipped (Neo4j not yet connected): query=%s", query)
        return {
            "answer": "지식베이스가 아직 준비 중입니다. (Neo4j 연동 예정)",
            "sources": [],
            "hits": [],
        }
