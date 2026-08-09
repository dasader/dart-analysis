"""Batch API의 순수 함수(JSONL 빌드·결과 파싱·JSON 추출) 검증 — API 호출 없음."""
import json

import pytest

from app.services.analysis_service import extract_json
from app.services.gemini_batch import build_jsonl_line, parse_result_line


def test_jsonl_line_uses_rest_schema():
    """JSONL은 REST 원형 — systemInstruction은 top-level, thinking은 generationConfig 안."""
    line = build_jsonl_line("42", "시스템 지침", "보고서 본문", 24576)
    obj = json.loads(line)

    assert obj["key"] == "42"
    req = obj["request"]
    assert req["systemInstruction"]["parts"][0]["text"] == "시스템 지침"
    assert req["contents"][0]["parts"][0]["text"] == "보고서 본문"
    assert req["generationConfig"]["maxOutputTokens"] == 24576
    assert req["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"


def test_jsonl_line_keeps_korean_readable():
    """ensure_ascii=False — 한국어가 이스케이프되면 파일 크기가 3배가 된다."""
    assert "종속회사" in build_jsonl_line("1", "종속회사 분석", "본문", 100)


def test_parse_success():
    line = json.dumps({
        "key": "7",
        "response": {"candidates": [{
            "content": {"parts": [{"text": '{"subsidiary": "## 요약"}'}]},
            "finishReason": "STOP",
        }]},
    })
    key, text, err = parse_result_line(line)
    assert (key, err) == ("7", None)
    assert text == '{"subsidiary": "## 요약"}'


def test_parse_per_request_error():
    """잡이 SUCCEEDED여도 개별 요청은 실패할 수 있다."""
    line = json.dumps({"key": "7", "error": {"code": 400, "message": "too long"}})
    key, text, err = parse_result_line(line)
    assert key == "7" and text is None
    assert "too long" in err


def test_parse_empty_body_reports_finish_reason():
    """본문이 비면 원인 파악을 위해 finishReason을 메시지에 남긴다."""
    line = json.dumps({
        "key": "7",
        "response": {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
    })
    _, text, err = parse_result_line(line)
    assert text is None and "MAX_TOKENS" in err


def test_parse_no_candidates():
    line = json.dumps({"key": "7", "response": {"promptFeedback": {"blockReason": "SAFETY"}}})
    _, text, err = parse_result_line(line)
    assert text is None and err is not None


def test_extract_json_tolerates_trailing_garbage():
    """모델이 끝에 잉여 문자를 붙이는 경우가 실제로 관측됐다 — json.loads는 여기서 죽는다."""
    raw = '{"subsidiary": "## 요약", "rnd": "## R&D"}"\n'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    assert extract_json(raw) == {"subsidiary": "## 요약", "rnd": "## R&D"}


def test_extract_json_strips_code_fence():
    assert extract_json('```json\n{"a": "b"}\n```') == {"a": "b"}


def test_extract_json_raises_on_garbage():
    """파싱 불가는 예외로 드러나야 한다 — 호출부가 원문 보존으로 폴백한다."""
    with pytest.raises((json.JSONDecodeError, ValueError)):
        extract_json("이건 JSON이 아닙니다")
