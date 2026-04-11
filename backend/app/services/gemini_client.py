import asyncio
import logging
import re
from functools import partial

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


MODEL_NAME = "gemini-3-flash-preview"

_MAX_RETRIES = 5


def _call_gemini(system_prompt: str, user_prompt: str, max_output_tokens: int) -> str:
    """동기 Gemini API 호출 — 스레드 풀에서 실행됨."""
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=max_output_tokens,
        ),
    )
    return response.text or ""


async def generate(
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int = 8192,
) -> str:
    """Gemini API 호출. 429 RESOURCE_EXHAUSTED 시 자동 재시도.

    generate_content()는 동기 블로킹 호출이므로 run_in_executor로
    스레드 풀에서 실행해 이벤트 루프를 점유하지 않는다.
    """
    loop = asyncio.get_running_loop()

    for attempt in range(_MAX_RETRIES):
        try:
            return await loop.run_in_executor(
                None,
                partial(_call_gemini, system_prompt, user_prompt, max_output_tokens),
            )

        except Exception as e:
            err = str(e)
            is_rate_limit = "429" in err or "RESOURCE_EXHAUSTED" in err

            if is_rate_limit and attempt < _MAX_RETRIES - 1:
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", err)
                wait = float(match.group(1)) if match else (30 * 2**attempt)
                wait += 2
                logger.warning(
                    "Gemini 429 rate limit (attempt %d/%d). %.0fs 후 재시도...",
                    attempt + 1, _MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue

            raise
