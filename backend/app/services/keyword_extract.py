"""기술 설명문 → 특허 검색 키워드.

기술 설명문을 그대로 KIPRIS에 넣으면 안 된다. 실측:
  7자 2,440건 → 27자 318건(가장 정밀) → 86자 8건(과협소) → 251자 20,029건(노이즈 폭증)
길이가 넘어가면 AND가 사실상 OR로 흩어진다. **4~30자 키워드 여러 개**로 쪼개 각각
검색한 뒤 출원인을 합산하는 편이 단일 검색어보다 편향이 적다.

보고서 분석과 달리 이 호출은 입력 수백 자·출력 수십 자라 batch(수 분)를 쓸 이유가 없다.
여기서만 실시간 경로를 쓴다.
"""
import asyncio
import json
import logging
import re
from functools import partial

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash-lite"
MIN_LEN, MAX_LEN = 4, 30

SYSTEM = """당신은 특허 검색 전문가입니다. 주어진 기술 설명을 한국 특허 검색에 쓸
검색어로 바꿉니다.

규칙:
- 검색어는 **4~30자**. 길면 검색이 흩어져 노이즈만 늘어납니다
- 3~5개를 만듭니다. 서로 다른 각도(소재·공정·용도·부품)를 담아 한 쪽에 치우치지 않게 합니다
- 특허 명세서에 실제로 쓰이는 표현을 씁니다. 마케팅 용어나 영어 약어 단독은 피합니다
- **산업 전체를 가리키는 일반어는 피합니다.** "리튬 이차전지", "고체전해질 제조방법"처럼
  넓은 말은 검색 결과가 수만 건이 되고, 그 기술을 하는 곳 대신 그 산업의 큰 회사가
  올라옵니다. 소재명·공정명·구조명처럼 **구체적인 층위**로 씁니다
- 설명에 없는 기술을 지어내지 마세요

JSON만 출력하세요: {"keywords": ["...", "..."]}"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _call(description: str) -> str:
    r = _get_client().models.generate_content(
        model=MODEL,
        contents=f"기술 설명:\n{description}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            max_output_tokens=512,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL),
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {"keywords": {"type": "ARRAY", "items": {"type": "STRING"}}},
                "required": ["keywords"],
            },
        ),
    )
    return r.text or ""


def _clean(keywords: list[str]) -> list[str]:
    """길이 규칙에 맞는 것만 남긴다. 모델이 규칙을 어겨도 검색이 망가지지 않게."""
    out, seen = [], set()
    for k in keywords:
        k = re.sub(r"\s+", " ", str(k)).strip()
        if not (MIN_LEN <= len(k) <= MAX_LEN):
            logger.debug("키워드 길이 규칙 위반, 제외: %r (%d자)", k, len(k))
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


async def extract(description: str) -> list[str]:
    """기술 설명 → 검색 키워드. 실패하면 예외 대신 빈 목록을 주지 않는다(호출부가 알아야 한다)."""
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, partial(_call, description))
    data = json.loads(raw)
    keywords = _clean(data.get("keywords") or [])
    if not keywords:
        raise ValueError(f"쓸 만한 검색어를 만들지 못했습니다. 모델 응답: {raw[:200]}")
    return keywords
