# Kakao Summary Bot

카카오 오픈빌더 스킬 서버로 붙일 수 있는 FastAPI 서버입니다.

## 기능
- URL 요약봇: 링크를 보내면 요약 작업 접수 후 `/결과 <요청ID>`로 조회
- OpenRouter 모델 분리: 요약/지식QA 각각 다른 모델 사용 가능
- 프롬프트 분리: `env` 또는 `app/prompt_defaults.py`에서 수정 가능
- 지식 기능 (Neo4j 연동 예정):
  - `지식 검색 <키워드>`
  - `지식 질문 <질문>` 후 `/결과 <요청ID>` 조회
  - `최근 문서`
  - `카테고리 목록`

## 엔드포인트
- `POST /kakao/skill` : URL 요약봇
- `POST /knowledge/search` : 저장 지식 검색
- `POST /knowledge/ask` : 저장 지식 기반 RAG 답변
- `GET /health`

## 설치
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## 주요 환경변수
- `OPENROUTER_API_KEY`
- `OPENROUTER_SUMMARY_MODEL` (예: `openai/gpt-4o-mini`)
- `OPENROUTER_KNOWLEDGE_MODEL` (예: `openai/gpt-4o-mini`)

Neo4j 연동 (예정):
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`

프롬프트 오버라이드(선택):
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT_TEMPLATE`
- `KNOWLEDGE_QA_SYSTEM_PROMPT`
- `KNOWLEDGE_QA_USER_PROMPT_TEMPLATE`

## 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 카카오 오픈빌더 연결
1. 요약봇 스킬 URL: `https://<your-domain>/kakao/skill`
2. `POST` + `application/json`

## 카카오 채널 사용 예시
- `요약 https://example.com/news`
- `/결과 ABC123XYZ`
- `지식 검색 LangChain`
- `지식 질문 RAG 구현 방법 알려줘`
- `최근 문서`
- `카테고리 목록`

## 참고
- 카카오 스킬 가이드: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/make_skill
