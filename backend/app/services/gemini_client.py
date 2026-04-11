from google import genai

from app.config import settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


MODEL_NAME = "gemini-2.0-flash"


async def generate(system_prompt: str, user_prompt: str) -> str:
    """Gemini API 호출. system + user 프롬프트를 받아 응답 텍스트를 반환."""
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )
    return response.text or ""
