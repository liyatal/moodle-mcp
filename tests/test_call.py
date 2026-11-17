"""call(), the READ_FUNCTIONS allowlist, error mapping, preflight identity, _flatten, fmt_time."""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
import pytest

from support import FAKE_TOKEN, PREFLIGHT_OK, TAU_HOST, TAU_URL, assert_no_token, form

EXPECTED_READ_FUNCTIONS = {
    "core_webservice_get_site_info",
    "core_enrol_get_users_courses",
    "core_course_get_contents",
    "core_calendar_get_action_events_by_timesort",
    "mod_assign_get_assignments",
    "mod_assign_get_submission_status",
    "gradereport_user_get_grade_items",
    "mod_forum_get_forums_by_courses",
    "mod_forum_get_forum_discussions",
    "core_course_get_updates_since",
    "mod_forum_get_discussion_posts",
    "mod_quiz_get_quizzes_by_courses",
    "mod_quiz_get_user_attempts",
    "mod_quiz_get_user_best_grade",
    "tool_mobile_get_public_config",
}


def _req(url: str = TAU_URL) -> httpx.Request:
    return httpx.Request("POST", url)


# ------------------------------------------------------------------------------- allowlist


def test_read_functions_is_exactly_the_contract_list(m):
    assert isinstance(m.READ_FUNCTIONS, frozenset)
    assert set(m.READ_FUNCTIONS) == EXPECTED_READ_FUNCTIONS


@pytest.mark.parametrize(
    "function",
    [
        "mod_assign_save_submission",
        "mod_assign_submit_for_grading",
        "mod_forum_add_discussion_post",
        "core_message_send_instant_messages",
        "core_user_update_user_preferences",
        "tool_mobile_call_external_functions",
        "tool_mobile_get_autologin_key",
        "core_course_get_contents ",
        " core_course_get_contents",
        "core_course_get_contents\n",
        "CORE_COURSE_GET_CONTENTS",
        "core_course_get_contents,mod_assign_save_submission",
        "core_course_get_contents&wsfunction=mod_assign_save_submission",
        "",
        "x",
    ],
)
def test_call_rejects_functions_outside_allowlist_with_zero_http(m, mock, function):
    with pytest.raises(PermissionError):
        m.call(function)
    assert mock.requests == []


def test_call_rejects_non_string_function_without_http(m, mock):
    with pytest.raises((PermissionError, TypeError)):
        m.call(None)
    with pytest.raises((PermissionError, TypeError)):
        m.call(["core_course_get_contents"])
    assert mock.requests == []


@pytest.mark.parametrize("function", sorted(EXPECTED_READ_FUNCTIONS))
def test_every_read_function_is_callable(m, mock, function):
    if function == "tool_mobile_get_public_config":
        # public: answered by the token-less nologin endpoint, never by the REST endpoint
        assert m.call(function)["wwwroot"] == TAU_URL
        assert mock.rest_requests() == []
        assert len(mock.preflight_requests()) == 1
        return
    mock.on(function, {})
    assert m.call(function) == {}
    assert function in mock.functions_called()


@pytest.mark.parametrize("name", ["wstoken", "wsfunction", "moodlewsrestformat"])
def test_call_rejects_reserved_param_names(m, mock, name):
    with pytest.raises(ValueError):
        m.call("core_course_get_contents", **{name: "evil"})
    assert mock.rest_requests() == []


def test_call_param_names_cannot_smuggle_extra_fields(m, mock):
    mock.on("core_course_get_contents", [])
    try:
        m.call("core_course_get_contents", **{"courseid&wstoken=evil": 1})
    except ValueError:
        return  # rejecting such a name outright is fine too
    (request,) = mock.rest_requests()
    fields = form(request)
    assert fields["wstoken"] == FAKE_TOKEN
    assert fields["wsfunction"] == "core_course_get_contents"
    assert "evil" not in fields.values()


# ----------------------------------------------------------------------------- request shape


def test_call_posts_token_in_body_only(m, mock):
    mock.on("core_course_get_contents", [])
    assert m.call("core_course_get_contents", courseid=7) == []
    (request,) = mock.rest_requests()
    assert request.method == "POST"
    assert str(request.url) == f"{TAU_URL}/webservice/rest/server.php"
    assert request.url.query == b""
    fields = form(request)
    assert fields == {
        "wstoken": FAKE_TOKEN,
        "wsfunction": "core_course_get_contents",
        "moodlewsrestformat": "json",
        "courseid": "7",
    }
    for r in mock.requests:
        assert FAKE_TOKEN not in str(r.url)
        assert all(FAKE_TOKEN not in v for v in r.headers.values())
    for r in mock.preflight_requests():
        assert FAKE_TOKEN.encode() not in r.content


def test_call_flattens_nested_params(m, mock):
    mock.on("core_course_get_contents", [])
    m.call(
        "core_course_get_contents",
        courseid=3,
        options=[{"name": "excludemodules", "value": True}, {"name": "x", "value": None}],
        ids=[5, 6],
    )
    (fields,) = mock.forms_for("core_course_get_contents")
    assert fields["ids[0]"] == "5"
    assert fields["ids[1]"] == "6"
    assert fields["options[0][name]"] == "excludemodules"
    assert fields["options[0][value]"] == "1"
    assert fields["options[1][name]"] == "x"
    assert "options[1][value]" not in fields


def test_call_uses_base_path_prefix(m, mock, monkeypatch):
    monkeypatch.setenv("MOODLE_SITE", "bgu")
    mock.preflight = [{"error": False, "data": {"wwwroot": "https://moodle.bgu.ac.il/moodle"}}]
    mock.on("core_course_get_contents", [])
    m.call("core_course_get_contents", courseid=1)
    (request,) = mock.rest_requests()
    assert str(request.url) == "https://moodle.bgu.ac.il/moodle/webservice/rest/server.php"


def test_call_returns_list_and_dict_payloads_untouched(m, mock):
    mock.on("core_course_get_contents", [{"id": 1}])
    mock.on("mod_assign_get_assignments", {"courses": [], "warnings": []})
    assert m.call("core_course_get_contents") == [{"id": 1}]
    assert m.call("mod_assign_get_assignments") == {"courses": [], "warnings": []}


# --------------------------------------------------------------------------- error mapping

FRIENDLY_CODES = [
    "invalidtoken",
    "accessexception",
    "passwordisexpired",
    "wsaccessusersuspended",
    "sitemaintenance",
]


def _exception_payload(code: str, message: str = "raw moodle message") -> dict:
    return {"exception": "moodle_exception", "errorcode": code, "message": message}


def _error_payload(code: str, message: str = "raw moodle message") -> dict:
    return {"error": message, "errorcode": code}


@pytest.mark.parametrize("shape", [_exception_payload, _error_payload], ids=["exception", "error"])
@pytest.mark.parametrize("code", [*FRIENDLY_CODES, "somethingweird"])
def test_moodle_error_dicts_become_moodle_error(m, mock, shape, code):
    mock.on("core_course_get_contents", shape(code))
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    err = info.value
    assert isinstance(err, RuntimeError)
    assert err.errorcode == code
    assert str(err).strip()
    assert FAKE_TOKEN not in str(err)
    if code == "somethingweird":
        assert "raw moodle message" in str(err)


def test_friendly_codes_have_distinct_specific_messages(m, mock):
    messages = set()
    for code in FRIENDLY_CODES:
        mock.on("core_course_get_contents", _exception_payload(code))
        with pytest.raises(m.MoodleError) as info:
            m.call("core_course_get_contents", courseid=1)
        messages.add(str(info.value))
    assert len(messages) == len(FRIENDLY_CODES)


def test_moodle_error_default_errorcode_is_none(m):
    assert m.MoodleError("boom").errorcode is None


@pytest.mark.parametrize("shape", [_exception_payload, _error_payload], ids=["exception", "error"])
def test_error_messages_are_scrubbed(m, mock, shape):
    mock.on("core_course_get_contents", shape("odd", f"bad {FAKE_TOKEN} and wstoken=XYZ123456789"))
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    text = f"{info.value} {info.value!r}"
    assert FAKE_TOKEN not in text
    assert "XYZ123456789" not in text


def test_httpx_errors_become_scrubbed_moodle_errors(m, mock):
    leaky = f"{TAU_URL}{'/webservice/rest/server.php'}?wstoken={FAKE_TOKEN}"
    errors = [
        httpx.ConnectError(f"connect failed for {leaky}", request=_req()),
        httpx.ReadTimeout(f"timed out talking to {leaky}", request=_req()),
        httpx.RemoteProtocolError(f"weird {FAKE_TOKEN}", request=_req()),
    ]
    for error in errors:
        mock.on("core_course_get_contents", lambda _form, error=error: error)
        with pytest.raises(m.MoodleError) as info:
            m.call("core_course_get_contents", courseid=1)
        text = f"{info.value} {info.value!r} {info.value.args}"
        assert_no_token(text)
        assert "server.php" not in text


@pytest.mark.parametrize("status", [400, 403, 404, 500, 502, 503])
def test_http_error_status_becomes_moodle_error_without_url(m, mock, status):
    mock.on(
        "core_course_get_contents",
        httpx.Response(status, text=f"error page mentioning wstoken={FAKE_TOKEN}"),
    )
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    text = str(info.value)
    assert FAKE_TOKEN not in text
    assert "server.php" not in text
    assert "://" not in text


def test_non_json_200_becomes_moodle_error(m, mock):
    mock.on("core_course_get_contents", httpx.Response(200, text="<html>Please log in</html>"))
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    assert FAKE_TOKEN not in str(info.value)


def test_redirect_response_is_not_followed(m, mock):
    mock.on(
        "core_course_get_contents",
        httpx.Response(302, headers={"location": "https://evil.example.com/steal"}),
    )
    with pytest.raises(m.MoodleError):
        m.call("core_course_get_contents", courseid=1)
    assert mock.foreign_requests() == []


# ----------------------------------------------------------------------------- preflight


def _preflight(wwwroot=None, httpswwwroot=None, **top):
    data = {}
    if wwwroot is not None:
        data["wwwroot"] = wwwroot
    if httpswwwroot is not None:
        data["httpswwwroot"] = httpswwwroot
    return [{"error": False, "data": data, **top}]


def test_preflight_request_shape(m, mock):
    mock.on("core_course_get_contents", [])
    m.call("core_course_get_contents", courseid=1)
    (pre,) = mock.preflight_requests()
    assert pre.method == "POST"
    assert pre.url.host == TAU_HOST
    assert pre.url.path == "/lib/ajax/service-nologin.php"
    assert pre.url.params["info"] == "tool_mobile_get_public_config"
    assert json.loads(pre.content) == [
        {"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}
    ]
    assert FAKE_TOKEN.encode() not in pre.content
    assert FAKE_TOKEN not in str(pre.url)
    assert all(FAKE_TOKEN not in v for v in pre.headers.values())
    # and the identity check happens before the token is sent anywhere
    assert mock.requests.index(pre) < mock.requests.index(mock.rest_requests()[0])


def test_preflight_runs_once_per_process(m, mock):
    mock.on("core_course_get_contents", [])
    for _ in range(3):
        m.call("core_course_get_contents", courseid=1)
    assert len(mock.preflight_requests()) == 1
    assert len(mock.rest_requests()) == 3
    assert len(m._preflight_ok) == 1


def test_preflight_is_per_base(m, mock, monkeypatch):
    mock.on("core_course_get_contents", [])
    m.call("core_course_get_contents", courseid=1)
    monkeypatch.setenv("MOODLE_URL", "https://moodle.example.edu")
    mock.preflight = _preflight("https://moodle.example.edu")
    m.call("core_course_get_contents", courseid=1)
    assert len(mock.preflight_requests()) == 2


@pytest.mark.parametrize(
    "answer",
    [
        _preflight("https://moodle.tau.ac.il"),
        _preflight(httpswwwroot="https://moodle.tau.ac.il"),
        _preflight("http://moodle.tau.ac.il", "https://moodle.tau.ac.il"),
        _preflight("https://MOODLE.TAU.AC.IL"),
        _preflight("https://moodle.tau.ac.il/"),
        _preflight("https://moodle.tau.ac.il", sitename="x", extra="ignored"),
    ],
    ids=["wwwroot", "httpswwwroot", "http-and-https", "uppercase", "trailing-slash", "extras"],
)
def test_preflight_accepts_matching_host(m, mock, answer):
    mock.preflight = answer
    m.ensure_site_identity()
    assert len(m._preflight_ok) == 1


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(_preflight("https://evil.example.com"), id="other-host"),
        pytest.param(_preflight("https://moodle.tau.ac.il.evil.com"), id="suffix-host"),
        pytest.param(_preflight("https://evil.com/moodle.tau.ac.il"), id="host-in-path"),
        pytest.param(_preflight("https://xmoodle.tau.ac.il"), id="prefix-host"),
        pytest.param(_preflight("https://other.tau.ac.il"), id="sibling-host"),
        pytest.param([{"error": False, "data": {}}], id="no-wwwroot"),
        pytest.param([{"error": False, "data": None}], id="null-data"),
        pytest.param([{"error": False}], id="no-data"),
        pytest.param([{"error": True, "data": {"wwwroot": TAU_URL}}], id="error-flag"),
        pytest.param([{"error": True, "exception": {"message": "nope"}}], id="error-exception"),
        pytest.param([], id="empty-list"),
        pytest.param([None], id="null-item"),
        pytest.param({"wwwroot": TAU_URL}, id="dict-not-list"),
        pytest.param("moodle", id="string"),
        pytest.param(None, id="null"),
        pytest.param(
            [{"error": False, "data": {"wwwroot": 42, "httpswwwroot": ["x"]}}], id="wrong-types"
        ),
    ],
)
def test_preflight_refuses_other_sites_before_sending_token(m, mock, answer):
    mock.preflight = answer
    mock.on("core_course_get_contents", [])
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    assert "Refusing to send your token" in str(info.value)
    assert mock.rest_requests() == []
    assert len(m._preflight_ok) == 0


@pytest.mark.parametrize(
    "make_response",
    [
        lambda: httpx.Response(200, text="<html>not moodle</html>"),
        lambda: httpx.Response(200, content=b""),
        lambda: httpx.Response(404, text="nope"),
        lambda: httpx.Response(500, text="boom"),
        lambda: httpx.Response(302, headers={"location": "https://evil.example.com/"}),
        lambda: httpx.ConnectError("no route", request=_req()),
        lambda: httpx.ReadTimeout("slow", request=_req()),
    ],
    ids=["html", "empty", "404", "500", "redirect", "connect-error", "timeout"],
)
def test_preflight_failures_are_moodle_errors_and_block_the_token(m, mock, make_response):
    mock.preflight = lambda _request: make_response()
    mock.on("core_course_get_contents", [])
    with pytest.raises(m.MoodleError) as info:
        m.call("core_course_get_contents", courseid=1)
    assert FAKE_TOKEN not in str(info.value)
    assert mock.rest_requests() == []
    assert mock.foreign_requests() == []


def test_failed_preflight_is_not_cached(m, mock):
    mock.on("core_course_get_contents", [])
    mock.preflight = _preflight("https://evil.example.com")
    with pytest.raises(m.MoodleError):
        m.call("core_course_get_contents", courseid=1)
    mock.preflight = PREFLIGHT_OK
    assert m.call("core_course_get_contents", courseid=1) == []
    assert len(mock.preflight_requests()) == 2


def test_skip_preflight_env_makes_no_identity_request(m, mock, monkeypatch):
    monkeypatch.setenv("MOODLE_SKIP_PREFLIGHT", "1")
    mock.preflight = _preflight("https://evil.example.com")  # would fail if it were asked
    mock.on("core_course_get_contents", [])
    assert m.call("core_course_get_contents", courseid=1) == []
    assert mock.preflight_requests() == []


def test_public_config_call_uses_the_tokenless_endpoint_and_never_sends_the_token(m, mock):
    mock.preflight = _preflight("https://evil.example.com")  # even an impostor gets no token
    assert m.call("tool_mobile_get_public_config") == {"wwwroot": "https://evil.example.com"}
    assert mock.rest_requests() == []
    assert len(mock.preflight_requests()) == 1
    for request in mock.requests:
        assert FAKE_TOKEN.encode() not in request.content
        assert FAKE_TOKEN not in str(request.url)
        assert "token" not in request.url.query.decode().lower().replace("tool_mobile", "")
        assert all(FAKE_TOKEN not in v for v in request.headers.values())
        assert "wstoken" not in request.content.decode()
    assert mock.foreign_requests() == []


def test_public_config_call_with_a_missing_token_still_works(m, mock, monkeypatch):
    monkeypatch.delenv("MOODLE_TOKEN")
    assert m.call("tool_mobile_get_public_config")["wwwroot"] == TAU_URL


def test_ensure_site_identity_returns_nothing_on_success(m, mock):
    assert m.ensure_site_identity() is None
    assert len(mock.preflight_requests()) == 1
    assert mock.rest_requests() == []


# ------------------------------------------------------------------------------- userid()


def test_userid_is_cached(m, mock):
    assert m.userid() == 42
    assert m.userid() == 42
    assert mock.functions_called() == ["core_webservice_get_site_info"]


def test_userid_cache_is_reset_by_the_seam(m, mock):
    assert m.userid() == 42
    m._userid = None
    mock.on("core_webservice_get_site_info", {"userid": 77})
    assert m.userid() == 77


# ------------------------------------------------------------------------------- _flatten


def test_flatten_lists_and_dicts(m):
    assert m._flatten({"courseids": [1, 2]}) == {"courseids[0]": 1, "courseids[1]": 2}
    assert m._flatten({"a": [{"k": "v", "n": [3]}]}) == {"a[0][k]": "v", "a[0][n][0]": 3}
    assert m._flatten({"t": (7, 8)}) == {"t[0]": 7, "t[1]": 8}
    assert m._flatten({"s": "text", "n": 1.5, "z": 0}) == {"s": "text", "n": 1.5, "z": 0}


def test_flatten_bool_to_int_and_none_dropped(m):
    assert m._flatten({"yes": True, "no": False, "none": None}) == {"yes": 1, "no": 0}
    assert m._flatten({"l": [True, None, 2]}) == {"l[0]": 1, "l[2]": 2}


def test_flatten_empty(m):
    assert m._flatten({}) == {}
    assert m._flatten({"a": [], "b": {}}) == {}


# ------------------------------------------------------------------------------- fmt_time


def test_fmt_time_formats_local_time(m):
    ts = 1_700_000_000
    expected = dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    assert m.fmt_time(ts) == expected
    assert re.fullmatch(r"\d\d/\d\d/\d{4} \d\d:\d\d", m.fmt_time(ts))


@pytest.mark.parametrize("value", [None, 0, "", False])
def test_fmt_time_falsy_is_none(m, value):
    assert m.fmt_time(value) is None


@pytest.mark.parametrize(
    "value", [10**12, 10**20, -(10**20), 2**63, float("inf"), float("-inf"), float("nan")]
)
def test_fmt_time_out_of_range_never_raises(m, value):
    assert m.fmt_time(value) is None


def test_fmt_time_small_negative_never_raises(m):
    assert m.fmt_time(-1) is None or isinstance(m.fmt_time(-1), str)
