"""Batch API의 순수 함수(JSONL 빌드·결과 파싱·JSON 추출) 검증 — API 호출 없음."""
import json
from types import SimpleNamespace

import pytest
from google.genai.errors import ServerError

from app.services.analysis_service import extract_json
from app.services.gemini_batch import build_jsonl_line, parse_result_line


TYPES = ["subsidiary", "rnd", "national_tech"]


def test_jsonl_line_uses_rest_schema():
    """JSONL은 REST 원형 — systemInstruction은 top-level, thinking은 generationConfig 안."""
    line = build_jsonl_line("42", "시스템 지침", "보고서 본문", 24576, TYPES)
    obj = json.loads(line)

    assert obj["key"] == "42"
    req = obj["request"]
    assert req["systemInstruction"]["parts"][0]["text"] == "시스템 지침"
    assert req["contents"][0]["parts"][0]["text"] == "보고서 본문"
    assert req["generationConfig"]["maxOutputTokens"] == 24576
    assert req["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"


def test_jsonl_line_pins_response_schema():
    """분석 본문에 인용 큰따옴표가 많아 모델이 JSON을 깨뜨린다 — API가 막게 한다."""
    req = json.loads(build_jsonl_line("1", "s", "u", 100, TYPES))["request"]
    gc = req["generationConfig"]
    assert gc["responseMimeType"] == "application/json"
    assert set(gc["responseSchema"]["properties"]) == set(TYPES)
    assert set(gc["responseSchema"]["required"]) == set(TYPES)
    assert gc["responseSchema"]["properties"]["rnd"]["type"] == "STRING"


def test_jsonl_line_schema_follows_requested_types():
    """일부 유형만 재분석할 때는 그 유형만 스키마에 들어가야 한다."""
    req = json.loads(build_jsonl_line("1", "s", "u", 100, ["rnd"]))["request"]
    assert list(req["generationConfig"]["responseSchema"]["properties"]) == ["rnd"]


def test_jsonl_line_keeps_korean_readable():
    """ensure_ascii=False — 한국어가 이스케이프되면 파일 크기가 3배가 된다."""
    assert "종속회사" in build_jsonl_line("1", "종속회사 분석", "본문", 100, TYPES)


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


def _fake_client(monkeypatch, upload):
    """files.upload만 갈아끼운 가짜 클라이언트. sleep도 없앤다."""
    from app.services import gemini_batch as gb

    monkeypatch.setattr(gb, "_get_client", lambda: SimpleNamespace(
        files=SimpleNamespace(upload=upload),
        batches=SimpleNamespace(create=lambda **kw: SimpleNamespace(name="batches/ok")),
    ))
    monkeypatch.setattr(gb.time, "sleep", lambda s: None)
    return gb


def test_upload_retries_on_server_error(monkeypatch):
    """실측으로 502가 났다 — 재시도가 없으면 보고서 여러 건의 분석이 통째로 날아간다."""
    calls = []

    def upload(**kw):
        calls.append(1)
        if len(calls) < 3:
            raise ServerError(502, {"message": "Bad Gateway"})
        return SimpleNamespace(name="files/ok")

    gb = _fake_client(monkeypatch, upload)
    assert gb._submit_sync(["{}"], "테스트") == ("batches/ok", "files/ok")
    assert len(calls) == 3


def test_upload_gives_up_after_max_attempts(monkeypatch):
    """무한 재시도는 큐를 막는다 — 상한을 넘으면 예외를 올려 분석을 failed로 만든다."""
    calls = []

    def upload(**kw):
        calls.append(1)
        raise ServerError(502, {"message": "Bad Gateway"})

    gb = _fake_client(monkeypatch, upload)
    with pytest.raises(ServerError):
        gb._submit_sync(["{}"], "테스트")
    assert len(calls) == gb._UPLOAD_ATTEMPTS
