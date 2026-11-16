"""Public API, FastMCP registration, logging hygiene and the no-token-in-errors regression."""

from __future__ import annotations

import asyncio
import inspect
import logging

import httpx
import pytest

from support import FAKE_TOKEN, TAU_URL, assert_no_token

TOOLS = {
    "list_courses",
    "course_contents",
    "upcoming_deadlines",
    "assignments",
    "grades",
    "forum_discussions",
    "course_updates",
    "forum_posts",
    "download_file",
}

PUBLIC_NAMES = [
    "validate_base_url",
    "get_base",
    "token",
    "download_dir",
    "max_download_bytes",
    "scrub",
    "call",
    "READ_FUNCTIONS",
    "ensure_site_identity",
    "userid",
    "fmt_time",
    "clean_text",
    "html_to_text",
    "untrusted",
    "check_download_url",
    "safe_filename",
    "safe_subfolder",
    "download_file",
    "is_write_function",
    "main",
    "SITES",
    "ConfigError",
    "MoodleError",
    "MAX_ITEMS",
    "MAX_TEXT",
    "MAX_POST_TEXT",
    "MAX_NAME",
    "split_multilang_name",
    "MAX_ASSIGN_STATUS_CALLS",
    "MAX_FORUMS",
    *sorted(TOOLS),
]


def test_public_names_exist(m):
    missing = [name for name in PUBLIC_NAMES if not hasattr(m, name)]
    assert missing == []


def test_exception_hierarchy(m):
    assert issubclass(m.ConfigError, ValueError)
    assert issubclass(m.MoodleError, RuntimeError)


def test_tools_are_plain_callables_with_unchanged_signatures(m):
    expected = {
        "list_courses": [("include_past", False)],
        "course_contents": [("course_id", inspect.Parameter.empty)],
        "upcoming_deadlines": [("days", 14)],
        "assignments": [("course_id", inspect.Parameter.empty)],
        "grades": [("course_id", inspect.Parameter.empty)],
        "forum_discussions": [("course_id", inspect.Parameter.empty), ("limit", 10)],
        "course_updates": [("course_id", inspect.Parameter.empty), ("since_days", 7)],
        "forum_posts": [("discussion_id", inspect.Parameter.empty), ("limit", 20)],
        "download_file": [("fileurl", inspect.Parameter.empty), ("subfolder", "")],
    }
    for name, params in expected.items():
        func = getattr(m, name)
        assert callable(func)
        actual = [(p.name, p.default) for p in inspect.signature(func).parameters.values()]
        assert actual == params, name


def test_fastmcp_exposes_exactly_the_nine_read_tools(m):
    tools = asyncio.run(m.mcp.list_tools())
    assert {tool.name for tool in tools} == TOOLS
    assert len(tools) == 9


def test_fastmcp_instructions_state_the_data_vs_instruction_rule(m):
    text = (m.mcp.instructions or "").lower()
    assert "untrusted_moodle_content" in text
    assert "read-only" in text or "read only" in text
    assert "instruction" in text


def test_module_client_is_configured_not_to_follow_redirects(m, mock):
    client = mock.original_client
    assert isinstance(client, httpx.Client)
    assert client.follow_redirects is False
    assert client.timeout.read is not None


@pytest.mark.parametrize("name", ["httpx", "httpcore"])
def test_http_library_loggers_are_quiet(m, name):
    assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


def test_http_requests_are_not_logged_even_with_debug_logging(m, mock, caplog):
    caplog.set_level(logging.DEBUG)
    mock.on("core_course_get_contents", [])
    m.call("core_course_get_contents", courseid=1)
    assert "server.php" not in caplog.text
    assert "service-nologin" not in caplog.text
    assert FAKE_TOKEN not in caplog.text


# ----------------------------------------------------------------- no token in any error, anywhere

LEAKY_URL = f"{TAU_URL}/webservice/rest/server.php?wstoken={FAKE_TOKEN}"


def _request() -> httpx.Request:
    return httpx.Request("POST", TAU_URL)


FAILURES = {
    "connect-error": lambda: httpx.ConnectError(f"failed {LEAKY_URL}", request=_request()),
    "timeout": lambda: httpx.ReadTimeout(f"timeout {LEAKY_URL}", request=_request()),
    "http-500": lambda: httpx.Response(500, text=f"oops {LEAKY_URL}"),
    "http-403": lambda: httpx.Response(403, text=f"forbidden token={FAKE_TOKEN}"),
    "moodle-exception": lambda: httpx.Response(
        200,
        json={
            "exception": "moodle_exception",
            "errorcode": "weird",
            "message": f"bad {FAKE_TOKEN} wstoken={FAKE_TOKEN}",
            "debuginfo": FAKE_TOKEN,
        },
    ),
    "error-shape": lambda: httpx.Response(
        200, json={"error": f"nope token={FAKE_TOKEN}", "errorcode": "weird"}
    ),
    "html-200": lambda: httpx.Response(200, text=f"<html>{FAKE_TOKEN}</html>"),
}

TOOL_CALLS = [
    ("list_courses", ()),
    ("course_contents", (7,)),
    ("upcoming_deadlines", ()),
    ("assignments", (7,)),
    ("grades", (7,)),
    ("forum_discussions", (7,)),
]


def _assert_clean(exc: BaseException) -> None:
    for text in (str(exc), repr(exc), " ".join(map(str, exc.args))):
        assert_no_token(text)


@pytest.mark.parametrize("failure", sorted(FAILURES))
@pytest.mark.parametrize(("tool", "args"), TOOL_CALLS)
def test_no_tool_error_contains_the_token(m, mock, tool, args, failure):
    mock.rest.clear()
    mock.rest_default = lambda _form: FAILURES[failure]()
    raised = None
    try:
        getattr(m, tool)(*args)
    except Exception as exc:  # noqa: BLE001 - the whole point is to inspect any exception
        raised = exc
    assert raised is not None, "a failing Moodle must surface as an exception"
    _assert_clean(raised)


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_no_download_error_contains_the_token(m, mock, failure):
    mock.download = lambda _request: FAILURES[failure]()
    url = f"{TAU_URL}/webservice/pluginfile.php/1/mod_resource/content/1/a.pdf"
    raised = None
    try:
        m.download_file(url)
    except Exception as exc:  # noqa: BLE001
        raised = exc
    # "html-200" is a legitimate (if odd) file body for a download; everything else must fail
    if failure != "html-200":
        assert raised is not None
    if raised is not None:
        _assert_clean(raised)


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_no_preflight_error_contains_the_token(m, mock, failure):
    mock.preflight = lambda _request: FAILURES[failure]()
    raised = None
    try:
        m.ensure_site_identity()
    except Exception as exc:  # noqa: BLE001
        raised = exc
    assert raised is not None
    _assert_clean(raised)
