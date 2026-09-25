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

# 보고서 분석(gemini_batch)과 **다른 모델을 쓴다.** 이쪽은 추출이 아니라 도메인 지식이
# 필요한 과제라 모델을 올린 만큼 결과가 달라진다 — 3.5-flash-lite는 설명문의 말을
# 재배열하는 데 그치는데, 3.7-flash는 `아지로다이트`·`황화리튬 오황화이인`·`크리스퍼 카스`
# 같은 실제 특허 용어를 낸다. 낱말을 하나 더 붙여 맥락을 한정하는 경향이 있어
# 넓은 키워드 문제도 같이 준다(`금속 분리판` 394,910건 → `연료전지 금속 분리판 내식성 코팅`
# 1,222건). 실측 SW 분야에서 DART 매칭 기업이 9곳 → 15곳으로 늘었다.
# 기술당 1회·입력 수백 자라 모델을 올려도 비용은 무시할 수준이다.
MODEL = "gemini-3.7-flash"
# 3.7-flash는 MINIMAL을 지원하지 않는다(에러를 낸다). LOW가 하한이다
THINKING_LEVEL = types.ThinkingLevel.LOW
MIN_LEN, MAX_LEN = 4, 30

# 뒤쪽 세 규칙(분야 고정어·한 대상·표준 표기)은 6개 기술 × 3회 실측에서 드러난 실패를
# 막는다 — "전력반도체 에피택셜 웨이퍼"가 LED용 실리콘 웨이퍼를, "염기교정 유전자 가위
# 줄기세포"가 식물 육종을, "저백금 촉매 막전극접합체 내구성"이 9건을 가져왔다.
# 효과는 크지 않다: 키워드 정밀도 76.9→77.3%로 그대로이고, DART 매칭 기업 중 적합한 곳이
# 11.7→13.6곳, 부적합이 3.7→3.2곳. 예시는 평가셋 밖 분야로 골랐다(모델이 예시를 흉내낸다)
SYSTEM = """당신은 특허 검색 전문가입니다. 주어진 기술 설명을 한국 특허 검색에 쓸
검색어로 바꿉니다.

**검색기의 동작**: 띄어쓰기는 AND이고, 붙여 쓴 복합어도 형태소로 쪼개져 각각 AND로
걸립니다. "교정제어"는 "교정 AND 제어"로 풀려 CRT 전자빔 회로가 1위로 나옵니다.
따라서 단어 하나하나가 그 분야 특허 명세서에 **그 형태 그대로** 나오는 말이어야 합니다.

규칙:
- 검색어는 **4~30자**. 길면 검색이 흩어져 노이즈만 늘어납니다
- **추상 명사를 넣지 마세요.** "치유·제어·융합·통합·모달리티·차세대·정밀·상용화"처럼
  어느 분야에나 있는 말은 AND의 축을 낭비하고 전혀 다른 분야의 특허를 끌어옵니다.
  기술 설명이 정책 문서 문투여도 그 표현을 옮기지 말고 특허 용어로 번역하세요
  (예: "세포유전자 통합 모달리티" → "키메라 항원 수용체", "유전자 가위 염기 교정")
- 3~5개를 만듭니다. 서로 다른 각도(소재·공정·용도·부품)를 담아 한 쪽에 치우치지 않게 합니다
- 특허 명세서에 실제로 쓰이는 표현을 씁니다. 마케팅 용어나 영어 약어 단독은 피합니다
- **산업 전체를 가리키는 일반어는 피합니다.** "리튬 이차전지", "고체전해질 제조방법"처럼
  넓은 말은 검색 결과가 수만 건이 되고, 그 기술을 하는 곳 대신 그 산업의 큰 회사가
  올라옵니다. 소재명·공정명·구조명처럼 **구체적인 층위**로 씁니다
- **검색어마다 그 분야에서만 쓰이는 말을 하나 넣어 분야를 고정합니다.** "박막 증착 장치",
  "표면 코팅층"처럼 여러 분야에 공통인 공정·소재어만으로 된 검색어는 엉뚱한 산업의
  특허를 끌어옵니다. "유기발광", "치과 임플란트"처럼 분야를 정하는 말을 함께 씁니다
- **한 검색어에 한 가지 대상만 담습니다.** "촉매 담체 분리막 모듈"처럼 서로 다른
  대상 둘을 AND로 묶으면 둘을 스치듯 함께 언급한 특허만 남습니다. 각도가 다르면
  검색어를 나눕니다
- 영어 음역어·신조어보다 명세서에 흔한 한국어 표준 표기를 씁니다. 드문 표기는 결과가 수십 건뿐이고 그 뒤를 무관한 특허가 채웁니다
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
            # thinking 토큰이 이 예산을 함께 쓴다 — 실측 최대 437이라 512로는 본문이
            # 빈 채로 돌아올 수 있다
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
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
    if not raw.strip():
        # thinking 토큰이 max_output_tokens를 다 쓰면 본문이 빈 채로 온다.
        # 그냥 두면 JSONDecodeError("Expecting value")가 나 원인이 드러나지 않는다
        raise ValueError("모델이 빈 응답을 돌려줬습니다 (thinking 예산 초과 가능 — "
                         "max_output_tokens를 올리거나 thinking_level을 낮추세요)")
    data = json.loads(raw)
    keywords = _clean(data.get("keywords") or [])
    if not keywords:
        raise ValueError(f"쓸 만한 검색어를 만들지 못했습니다. 모델 응답: {raw[:200]}")
    return keywords
