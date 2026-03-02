# Kakao Multi-Bot Skill Server (Summary + Buddha)

카카오 오픈빌더 스킬 서버로 붙일 수 있는 FastAPI 샘플입니다.

## 기능
- URL 요약봇: 링크를 보내면 요약 작업 접수 후 `/결과 <요청ID>`로 조회
- OpenRouter 모델 분리: 요약 각각 다른 모델 사용 가능
- 프롬프트 분리: `env` 또는 설정 파일에서 수정 가능

## 엔드포인트
- `POST /kakao/skill` : URL 요약봇
- `GET /health`

## 설치
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
```

## 주요 환경변수
- `OPENROUTER_API_KEY`
- `OPENROUTER_SUMMARY_MODEL` (예: `openai/gpt-4o-mini`)

프롬프트 오버라이드(선택):
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT_TEMPLATE`

기본 프롬프트 파일:
- `app/prompt_defaults.py`

## 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 카카오 오픈빌더 연결
1. 요약봇 스킬 URL: `https://<your-domain>/kakao/skill`
2. 두 스킬 모두 `POST` + `application/json`

## 사용 예시
요약봇:
- `요약 https://example.com/news`
- 응답: `요청 ID: ABC123...`
- 조회: `/결과 ABC123...`

## 참고
- 카카오 스킬 가이드: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/make_skill
