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

from google.genai import types

from app.config import gemini

logger = logging.getLogger(__name__)

# 보고서 분석(gemini_batch)과 **다른 모델을 쓴다.** 이쪽은 추출이 아니라 도메인 지식이
# 필요한 과제라 모델을 올린 만큼 결과가 달라진다 — 3.5-flash-lite는 설명문의 말을
# 재배열하는 데 그치는데, 3.7-flash는 `아지로다이트`·`황화리튬 오황화이인`·`크리스퍼 카스`
# 같은 실제 특허 용어를 낸다. 낱말을 하나 더 붙여 맥락을 한정하는 경향이 있어
# 넓은 키워드 문제도 같이 준다(`금속 분리판` 394,910건 → `연료전지 금속 분리판 내식성 코팅`
# 1,222건). 실측 SW 분야에서 DART 매칭 기업이 9곳 → 15곳으로 늘었다.
# 기술당 1회·입력 수백 자라 모델을 올려도 비용은 무시할 수준이다.
# 3.8-flash MEDIUM으로 올렸다. 3.7-flash LOW와 단가가 같고, 6개 기술 × 2~3회 실측에서
# 키워드 정밀도 76.9→79.4%, DART 부적합 기업 3.7→3.2곳(적합 11.7→11.2곳). 차이가 회차 간
# 편차(±10%p) 안이라 "조금 나을 수 있다" 수준이지만 비용이 기술당 $0.003이라 택했다.
# **3.8 LOW는 쓰지 마라** — thinking을 아예 안 쓰고 정밀도가 72.5%로 오히려 떨어졌다.
# 3.8도 MINIMAL은 지원하지 않는다(400)
MODEL = "gemini-3.8-flash"
THINKING_LEVEL = types.ThinkingLevel.MEDIUM
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

def _call(contents: str) -> str:
    r = gemini().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            # thinking 토큰이 이 예산을 함께 쓴다 — 3.8 MEDIUM 실측 출력+thinking 평균 647이라
            # 1,024로는 본문이 빈 채로 돌아올 수 있다
            max_output_tokens=4096,
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


def _parse(raw: str) -> list[str]:
    if not raw.strip():
        # thinking 토큰이 max_output_tokens를 다 쓰면 본문이 빈 채로 온다.
        # 그냥 두면 JSONDecodeError("Expecting value")가 나 원인이 드러나지 않는다
        raise ValueError("모델이 빈 응답을 돌려줬습니다 (thinking 예산 초과 가능 — "
                         "max_output_tokens를 올리거나 thinking_level을 낮추세요)")
    return json.loads(raw).get("keywords") or []


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


# 같은 설명으로 **두 번 뽑아 합친다**(쿼리 앙상블). 한 벌은 알려진 적합 DART 기업의 절반쯤만
# 찾는다 — 6개 기술에서 키워드 세트 11~13벌이 찾은 적합 기업을 합쳐 정답으로 두면 세트 1벌의
# 재현율이 24~53%, 2벌 합이 38~69%였다. 회차마다 다른 각도를 고르기 때문이다.
# 늘어난 키워드는 스캔이 키워드당 1페이지만 받아 상쇄한다(tech_scan.PAGES) — 같은 호출 8회면
# 키워드 8개 × 1페이지가 4개 × 2페이지보다 기업을 더 찾았다(전고체 58 vs 56%, 세포 37 vs 21%)
SAMPLES = 2


async def extract(description: str) -> list[str]:
    """기술 설명 → 검색 키워드. 실패하면 빈 목록 대신 예외를 던진다(호출부가 알아야 한다).
    한 회차가 실패해도 나머지로 간다 — 전부 실패할 때만 예외."""
    raws = await asyncio.gather(*[asyncio.to_thread(_call, f"기술 설명:\n{description}")
                                  for _ in range(SAMPLES)], return_exceptions=True)
    merged, errors = [], []
    for raw in raws:
        try:
            if isinstance(raw, BaseException):
                raise raw
            merged += _parse(raw)
        except Exception as e:
            errors.append(e)
            logger.warning("키워드 도출 1회 실패: %s", e)
    keywords = _clean(merged)
    if not keywords:
        raise ValueError(f"쓸 만한 검색어를 만들지 못했습니다: {errors or raws}")
    return keywords


# ── 적합 문헌 피드백으로 키워드 확장(Rocchio식 relevance feedback) ──────────────
# 첫 스캔의 결과에서 기술 설명과 가장 가까운 문헌을 골라, 그 제목·초록에 **실제로 나오는
# 용어**로 검색어를 더 만든다. 모델이 모르는 명세서 표현(습식합성법·황화수소 가스·
# 다층전극 막전극접합체)을 얻는다. 6개 기술 실측(키워드 3개 추가, IPC 코어 제한 1페이지):
# 적합 DART 기업 81 → 95곳, 부적합 15 → 25곳(늘어난 부적합은 온보딩 적합도 판정이
# 뒤로 민다 — 앙상블과 합쳐도 P@10 53/60 그대로). 연료전지 +7곳·전고체 +5곳으로 검색이
# 깨끗한 분야에서 강하고, 노이즈가 많은 분야(전력반도체)에서는 거의 이득이 없다.
# 문헌 선택은 라벨 없이 임베딩 유사도로 한다(적합/부적합 구분 AUC 0.79~0.96).
EXPAND_N = 3
EXPAND_DOCS = 30
EMBED_MODEL = "gemini-embedding-001"

EXPAND_PROMPT = """아래는 이 기술 키워드로 검색해 얻은 특허 중 기술 설명과 가장 가까운 문헌들입니다.
기존 검색어가 놓쳤을 **다른 각도**의 검색어 {n}개를 새로 만드세요.
- 반드시 아래 문헌의 제목·초록에 **실제로 나오는 용어**를 쓰세요(명세서 표현 그대로)
- 기존 검색어와 겹치는 말만으로 된 검색어는 만들지 마세요
- 나머지 규칙은 시스템 지시를 따르세요

기술: {name}
설명: {description}
기존 검색어: {keywords}

문헌:
{docs}"""


def _embed(texts: list[str], task: str) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 100):     # 요청당 100건 상한
        r = gemini().models.embed_content(
            model=EMBED_MODEL, contents=texts[i:i + 100],
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=768))
        out += [e.values for e in r.embeddings]
    return out


def _closest(name: str, description: str, items: list[dict], n: int) -> list[dict]:
    docs = _embed([f"{it['title']}\n{it['abstract'][:600]}" for it in items], "RETRIEVAL_DOCUMENT")
    q = _embed([f"{name}: {description}"], "RETRIEVAL_QUERY")[0]
    qn = sum(x * x for x in q) ** .5

    def cos(d):
        return sum(x * y for x, y in zip(d, q)) / ((sum(x * x for x in d) ** .5) * qn or 1)
    ranked = sorted(zip(map(cos, docs), range(len(items))), reverse=True)
    return [items[i] for _, i in ranked[:n]]


def _expand_sync(name: str, description: str, keywords: list[str], items: list[dict]) -> list[str]:
    top = _closest(name, description, items, EXPAND_DOCS)
    prompt = EXPAND_PROMPT.format(
        n=EXPAND_N, name=name, description=description, keywords=", ".join(keywords),
        docs="\n".join(f"- {it['title']} / {it['abstract'][:200]}" for it in top))
    have = set(keywords)
    return [w for w in _clean(_parse(_call(prompt))) if w not in have][:EXPAND_N]


async def expand(name: str, description: str, keywords: list[str], items: list[dict]) -> list[str]:
    """검색 결과 특허(items)에서 새 검색어를 캔다. 기존 키워드와 같은 것은 뺀다."""
    items = [it for it in items if it.get("title")]
    if not items:
        return []
    return await asyncio.to_thread(_expand_sync, name, description, keywords, items)
