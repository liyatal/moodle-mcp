"""Behaviours added in fix round 1: assignments breaker, JSON download peek, scrub keeping the
key, the 120 s download deadline, and the standalone `moodle_safety` module."""

from __future__ import annotations

import json
import subprocess
import sys
import time as real_time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from support import FAKE_TOKEN, PLUGINFILE, TAU_URL, clean_env, files_under, unwrap

ROOT = Path(__file__).resolve().parents[1]


def _url(name: str = "data.json") -> str:
    return f"{TAU_URL}{PLUGINFILE}123/mod_resource/content/1/{name}"


# ======================================================================== assignments breaker


def _assigns(n: int) -> dict:
    items = [{"id": i, "name": f"HW {i}", "duedate": 0} for i in range(1, n + 1)]
    return {"courses": [{"id": 7, "assignments": items}]}


def _program(mock, outcomes: str):
    """outcomes[i] is for assignment i+1: 'S' = submitted, 'E' = Moodle error, 'H' = HTTP 500."""

    def status(fields):
        kind = outcomes[int(fields["assignid"]) - 1]
        if kind == "S":
            return {"lastattempt": {"submission": {"status": "submitted"}}}
        if kind == "H":
            return httpx.Response(500, text="boom")
        return {
            "exception": "moodle_exception",
            "errorcode": "cannotviewsubmission",
            "message": "x",
        }

    mock.on("mod_assign_get_assignments", _assigns(len(outcomes)))
    mock.on("mod_assign_get_submission_status", status)


def _status_calls(mock) -> int:
    return mock.functions_called().count("mod_assign_get_submission_status")


@pytest.mark.parametrize("kind", ["E", "H"])
def test_breaker_stops_after_three_consecutive_failures(m, mock, kind):
    _program(mock, kind * 10)
    result = m.assignments(7)
    assert len(result) == 10
    assert _status_calls(mock) == 3
    assert all(a["submission_status"] is None for a in result)


def test_success_in_between_resets_the_breaker(m, mock):
    _program(mock, "EESEESEES")
    result = m.assignments(7)
    assert _status_calls(mock) == 9
    assert [a["submission_status"] for a in result] == [None, None, "submitted"] * 3


def test_breaker_trips_after_reset_when_three_fail_again(m, mock):
    _program(mock, "EESEEESS")
    result = m.assignments(7)
    assert _status_calls(mock) == 6  # E E S E E E -> tripped; the last two are not asked
    assert [a["submission_status"] for a in result] == [
        None,
        None,
        "submitted",
        None,
        None,
        None,
        None,
        None,
    ]


def test_isolated_errors_only_affect_their_own_assignment(m, mock):
    _program(mock, "ESSESHS")
    result = m.assignments(7)
    assert _status_calls(mock) == 7
    assert [a["submission_status"] for a in result] == [
        None,
        "submitted",
        "submitted",
        None,
        "submitted",
        None,
        "submitted",
    ]


def test_mixed_error_kinds_count_as_consecutive(m, mock):
    _program(mock, "EHESSS")
    m.assignments(7)
    assert _status_calls(mock) == 3


def test_auth_error_still_propagates_even_inside_an_error_run(m, mock):
    def status(fields):
        if fields["assignid"] == "3":
            return {"exception": "x", "errorcode": "accessexception", "message": "no"}
        return {"exception": "x", "errorcode": "cannotviewsubmission", "message": "no"}

    mock.on("mod_assign_get_assignments", _assigns(5))
    mock.on("mod_assign_get_submission_status", status)
    with pytest.raises(m.MoodleError) as info:
        m.assignments(7)
    assert info.value.errorcode == "accessexception"


# ============================================================================== JSON peek


def _json_ct():
    return {"content-type": "application/json"}


def _chunked(payload: bytes, size: int = 16384):
    def gen():
        for i in range(0, len(payload), size):
            yield payload[i : i + size]

    return gen()


def test_small_json_file_without_error_keys_is_saved_intact(m, mock, dl_dir):
    body = json.dumps({"course": "alg", "items": [1, 2, 3], "note": "שלום"}).encode()
    mock.download = lambda _r: httpx.Response(200, content=body, headers=_json_ct())
    path = Path(m.download_file(_url("data.json")))
    assert path.name == "data.json"
    assert path.read_bytes() == body


def test_json_list_file_is_saved_intact(m, mock):
    mock.download = lambda _r: httpx.Response(200, content=b"[1, 2, 3]", headers=_json_ct())
    assert Path(m.download_file(_url())).read_bytes() == b"[1, 2, 3]"


def test_large_chunked_json_file_is_saved_intact(m, mock):
    body = json.dumps({"rows": ["x" * 100] * 3000}).encode()  # ~300 KiB, well over 64 KiB
    assert len(body) > 200_000
    mock.download = lambda _r: httpx.Response(200, content=_chunked(body), headers=_json_ct())
    path = Path(m.download_file(_url("big.json")))
    assert path.read_bytes() == body


def test_json_file_whose_content_merely_mentions_error_is_not_an_error(m, mock):
    body = json.dumps({"results": [{"error": "none"}], "errorcount": 0}).encode()
    mock.download = lambda _r: httpx.Response(200, content=body, headers=_json_ct())
    assert Path(m.download_file(_url())).read_bytes() == body


@pytest.mark.parametrize(
    "payload",
    [
        {"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Invalid token"},
        {"error": "Access control exception", "errorcode": "accessexception"},
        {"error": "something went wrong"},  # only a string `error`, no errorcode
    ],
    ids=["exception-shape", "error-shape", "error-string-only"],
)
def test_moodle_error_json_is_an_error_and_saves_nothing(m, mock, dl_dir, payload):
    mock.download = lambda _r: httpx.Response(200, json=payload, headers=_json_ct())
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url("report.json"))
    text = str(info.value)
    assert FAKE_TOKEN not in text
    assert "token=" not in text.lower()
    assert "://" not in text
    assert files_under(dl_dir) == []


def test_moodle_error_json_arriving_in_small_chunks_is_still_detected(m, mock, dl_dir):
    body = json.dumps({"error": "nope", "errorcode": "accessexception"}).encode()
    mock.download = lambda _r: httpx.Response(
        200, content=_chunked(body, size=5), headers=_json_ct()
    )
    with pytest.raises(m.MoodleError):
        m.download_file(_url())
    assert files_under(dl_dir) == []


def test_size_cap_in_the_json_peek_path_deletes_the_partial_file(m, mock, dl_dir, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "1")
    payload = b'{"rows": "' + b"x" * (4 * 1024 * 1024)  # not valid JSON: treated as a file
    mock.download = lambda _r: httpx.Response(
        200, content=_chunked(payload, size=65536), headers=_json_ct()
    )
    with pytest.raises(m.MoodleError):
        m.download_file(_url("huge.json"))
    assert files_under(dl_dir) == []


def test_size_cap_applies_to_valid_json_files_too(m, mock, dl_dir, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "1")
    payload = json.dumps({"rows": "x" * (3 * 1024 * 1024)}).encode()
    mock.download = lambda _r: httpx.Response(
        200, content=_chunked(payload, size=65536), headers=_json_ct()
    )
    with pytest.raises(m.MoodleError):
        m.download_file(_url("huge.json"))
    assert files_under(dl_dir) == []


# ==================================================================================== scrub


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://x.example/y?token=SECRET123456&a=1", "https://x.example/y?token=***&a=1"),
        ("wstoken=SECRET123456", "wstoken=***"),
        ("boom wstoken=SECRET123456 bam", "boom wstoken=*** bam"),
        ("token=SECRET123456", "token=***"),
    ],
)
def test_scrub_keeps_the_key_and_masks_the_value(m, text, expected):
    assert m.scrub(text) == expected


def test_scrub_masks_the_real_token_everywhere(m):
    assert m.scrub(FAKE_TOKEN) == "***"
    assert m.scrub(f"a {FAKE_TOKEN} b") == "a *** b"
    assert m.scrub(f"wstoken={FAKE_TOKEN}") == "wstoken=***"
    assert m.scrub(f"{TAU_URL}/x?token={FAKE_TOKEN}&y=1") == f"{TAU_URL}/x?token=***&y=1"


def test_scrub_is_idempotent(m):
    once = m.scrub(f"token={FAKE_TOKEN} wstoken=OTHER1234567890")
    assert m.scrub(once) == once


# ============================================================================ 120 s deadline


def test_deadline_constant_is_120_seconds(m):
    assert m.DOWNLOAD_DEADLINE_S == 120


def test_download_deadline_aborts_and_deletes_the_partial_file(m, mock, dl_dir, monkeypatch):
    state = {"yielded": 0}

    def body():
        for _ in range(4):
            state["yielded"] += 1
            yield b"x" * 1024

    def fake_monotonic():
        return 0.0 if state["yielded"] < 2 else 10_000.0  # 2nd chunk arrives past the deadline

    monkeypatch.setattr(
        m,
        "time",
        SimpleNamespace(monotonic=fake_monotonic, time=real_time.time, sleep=lambda s: None),
    )
    mock.download = lambda _r: httpx.Response(200, content=body())
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url("slow.pdf"))
    assert "120" in str(info.value) or "took" in str(info.value).lower()
    assert FAKE_TOKEN not in str(info.value)
    assert files_under(dl_dir) == []
    assert state["yielded"] < 4  # stopped reading instead of draining the stream


def test_download_within_the_deadline_is_unaffected(m, mock):
    mock.download = lambda _r: httpx.Response(200, content=b"abc")
    assert Path(m.download_file(_url("ok.bin"))).read_bytes() == b"abc"


# ======================================================================= moodle_safety alone


def _run(code: str):
    return subprocess.run(  # noqa: S603 - fixed interpreter, inline code, no shell
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def test_moodle_safety_imports_alone_silently_without_http_or_server_code():
    code = (
        "import sys, moodle_safety\n"
        "assert 'moodle_mcp' not in sys.modules, 'imported moodle_mcp'\n"
        "assert 'httpx' not in sys.modules, 'imported httpx'\n"
        "assert 'mcp' not in sys.modules, 'imported mcp'\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_moodle_safety_helpers_work_standalone():
    code = (
        "import moodle_safety as s\n"
        "assert s.validate_base_url('https://Moodle.Tau.ac.il/') == 'https://moodle.tau.ac.il'\n"
        "assert s.untrusted('a', 'x') == "
        "'<untrusted_moodle_content source=\"x\">a</untrusted_moodle_content>'\n"
        "assert s.is_write_function('mod_assign_save_submission')\n"
        "assert not s.is_write_function('core_course_get_contents')\n"
        "assert s.safe_filename('G:a.txt') != 'G:a.txt'\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_moodle_mcp_reexports_the_safety_helpers(m):
    import moodle_safety

    for name in (
        "ConfigError",
        "clean_text",
        "html_to_text",
        "untrusted",
        "validate_base_url",
        "check_download_url",
        "safe_filename",
        "safe_subfolder",
        "is_write_function",
        "HIGH_RISK",
        "MAX_ITEMS",
        "MAX_TEXT",
        "MAX_NAME",
        "MAX_ASSIGN_STATUS_CALLS",
        "MAX_FORUMS",
    ):
        assert getattr(m, name) is getattr(moodle_safety, name), name


def test_wrapped_output_still_unwraps_after_the_split(m):
    assert unwrap(m.untrusted("hello", "x")) == ("x", "hello")
