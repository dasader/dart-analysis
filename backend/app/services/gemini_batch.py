"""Gemini Batch API 연동 — JSONL 빌드·제출·상태조회·결과 파싱.

실시간 API 대비 50% 저렴하고, 실측 turnaround는 8.3분이었다(문서상 SLO 24시간).
보고서 1건이 UTF-8로 ~1.7MB라 inline 방식(총 20MB 제한)은 쓸 수 없어 JSONL 파일 업로드만 쓴다.
"""
import asyncio
import json
import logging
import tempfile
from functools import partial
from pathlib import Path

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash-lite"

# 사업보고서 분석은 추론이 아니라 추출·나열 과제 — thinking을 올려도 품질이 오르지 않고
# 출력 예산만 잠식한다(실측: minimal과 high의 종속회사 표 커버리지 동일, high가 2배 느림).
THINKING_LEVEL = "MINIMAL"

# 폴링을 끝내도 되는 상태들
TERMINAL_STATES = frozenset({
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
})

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def build_jsonl_line(
    key: str, system_prompt: str, user_prompt: str, max_output_tokens: int,
    analysis_types: list[str],
) -> str:
    """batch 요청 1줄을 만든다.

    JSONL은 REST 원형 스키마다 — systemInstruction은 top-level, maxOutputTokens와
    thinkingConfig는 generationConfig 안. (inline 방식의 평면 config와 형태가 다르다.)

    responseSchema를 거는 이유: 분석 본문에 보고서 인용이 많아 큰따옴표가 섞이는데,
    모델이 JSON 문자열 안에서 이스케이프를 놓쳐 응답 전체가 깨지는 일이 잦았다
    (실측 3회 중 2회). 스키마를 걸면 API가 JSON 유효성을 보장한다.
    """
    return json.dumps({
        "key": key,
        "request": {
            "contents": [{"parts": [{"text": user_prompt}], "role": "user"}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": THINKING_LEVEL},
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {t: {"type": "STRING"} for t in analysis_types},
                    "required": list(analysis_types),
                },
            },
        },
    }, ensure_ascii=False)


def parse_result_line(line: str) -> tuple[str, str | None, str | None]:
    """결과 JSONL 1줄을 (key, 본문, 오류메시지)로 푼다.

    잡이 SUCCEEDED여도 개별 요청은 실패할 수 있다 — 그 줄은 response 대신 error를 갖는다.
    """
    obj = json.loads(line)
    key = str(obj.get("key", ""))

    if obj.get("error"):
        return key, None, str(obj["error"])

    response = obj.get("response")
    if not response:
        return key, None, "응답이 비어 있습니다."

    candidates = response.get("candidates") or []
    if not candidates:
        return key, None, f"후보 응답이 없습니다: {response.get('promptFeedback', '')}"

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text:
        return key, None, f"본문이 비어 있습니다 (finishReason={candidates[0].get('finishReason')})"
    return key, text, None


def _submit_sync(lines: list[str], display_name: str) -> tuple[str, str]:
    """JSONL 업로드 + batch 생성 (블로킹 — executor에서 실행)."""
    client = _get_client()

    # File API가 파일 경로를 요구하므로 임시 파일을 경유한다
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        path = f.name
    try:
        uploaded = client.files.upload(
            file=path,
            config=types.UploadFileConfig(display_name=display_name, mime_type="jsonl"),
        )
        job = client.batches.create(
            model=MODEL_NAME, src=uploaded.name, config={"display_name": display_name}
        )
        return job.name, uploaded.name
    finally:
        Path(path).unlink(missing_ok=True)


async def submit(lines: list[str], display_name: str) -> tuple[str, str]:
    """batch 작업을 제출하고 (job_name, file_name)을 반환."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_submit_sync, lines, display_name))


def _get_sync(job_name: str) -> dict:
    job = _get_client().batches.get(name=job_name)
    stats = getattr(job, "batch_stats", None)
    return {
        "state": job.state.name,
        "error": str(job.error) if getattr(job, "error", None) else None,
        "result_file": getattr(getattr(job, "dest", None), "file_name", None),
        "request_count": getattr(stats, "request_count", None),
        "success_count": getattr(stats, "successful_request_count", None),
        "failed_count": getattr(stats, "failed_request_count", None),
    }


async def get_status(job_name: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_get_sync, job_name))


def _download_sync(file_name: str) -> list[str]:
    content = _get_client().files.download(file=file_name)
    return [l for l in content.decode("utf-8").splitlines() if l.strip()]


async def download_results(file_name: str) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_download_sync, file_name))


async def cancel(job_name: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _get_client().batches.cancel(name=job_name))
