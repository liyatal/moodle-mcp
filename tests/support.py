"""Helpers shared by the whole suite (imported as `support`).

Everything here is written against CONTRACT.md, never against the implementation.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl

import httpx

FAKE_TOKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
TAU_HOST = "moodle.tau.ac.il"
TAU_URL = f"https://{TAU_HOST}"
REST_PATH = "/webservice/rest/server.php"
PREFLIGHT_PATH = "/lib/ajax/service-nologin.php"
PLUGINFILE = "/webservice/pluginfile.php/"

PREFLIGHT_OK = [
    {
        "error": False,
        "data": {"wwwroot": TAU_URL, "httpswwwroot": TAU_URL, "sitename": "x"},
    }
]

CLOSE_TAG = "</untrusted_moodle_content"
WRAPPED_RE = re.compile(
    r'^<untrusted_moodle_content source="([^"]+)">(.*)</untrusted_moodle_content>$', re.DOTALL
)

# Every env var the implementation reads; the autouse fixture clears them per test.
ENV_VARS = (
    "MOODLE_SITE",
    "MOODLE_URL",
    "MOODLE_TOKEN",
    "MOODLE_TOKEN_FILE",
    "MOODLE_DOWNLOAD_DIR",
    "MOODLE_MAX_DOWNLOAD_MB",
    "MOODLE_SKIP_PREFLIGHT",
    "MOODLE_DOWNLOAD_TOKEN_IN_QUERY",
)


def form(request: httpx.Request) -> dict[str, str]:
    """Decode an application/x-www-form-urlencoded request body into a dict."""
    return dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))


def unwrap(value: Any) -> tuple[str, str]:
    """Assert `value` is exactly one untrusted wrapper; return (source, inner text)."""
    assert isinstance(value, str), f"expected a wrapped string, got {value!r}"
    match = WRAPPED_RE.match(value)
    assert match, f"not wrapped: {value!r}"
    inner = match.group(2)
    assert CLOSE_TAG not in inner, f"unescaped closing tag inside wrapper: {value!r}"
    return match.group(1), inner


def assert_no_token(text: str) -> None:
    """Fail if `text` contains the token or an un-masked `token=<value>` / `wstoken=<value>`."""
    assert FAKE_TOKEN not in text, "token value leaked"
    assert not re.search(r"token=(?!\*\*\*)[^\s&]", text, re.IGNORECASE), f"token= leaked: {text!r}"


def site_info(userid: int = 42, functions: list[str] | None = None, **extra: Any) -> dict:
    names = functions if functions is not None else ["core_course_get_contents"]
    data = {
        "sitename": "Sensitive University Site Name",
        "username": "jdoe_private",
        "firstname": "Dana",
        "lastname": "Cohen",
        "fullname": "Dana Cohen",
        "userid": userid,
        "release": "4.5.1 (Build: 20240101)",
        "version": "2024100700",
        "functions": [{"name": n, "version": "2024100700"} for n in names],
    }
    data.update(extra)
    return data


def clean_env(**extra: str) -> dict[str, str]:
    """os.environ without any MOODLE_* variable, plus `extra` (for subprocess tests)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOODLE_")}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def default_download(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"%PDF-fake", headers={"content-type": "application/pdf"})


class MoodleMock:
    """A tiny fake Moodle behind httpx.MockTransport.

    Values registered with `on` / `preflight` / `download` may be:
      * a JSON-serialisable object      -> 200 JSON response
      * an httpx.Response               -> returned as is
      * an exception instance           -> raised (simulates network errors)
      * a callable                      -> called (REST: with the decoded form dict;
                                           preflight/download: with the request) and its
                                           return value is interpreted as above
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.rest_calls: list[tuple[str, dict[str, str]]] = []
        self.preflight: Any = PREFLIGHT_OK
        self.rest: dict[str, Any] = {
            "core_webservice_get_site_info": site_info(),
            "tool_mobile_get_public_config": {},
        }
        self.rest_default: Any = None
        self.download: Any = default_download
        self.original_client: httpx.Client | None = None

    def on(self, function: str, value: Any) -> None:
        self.rest[function] = value

    # -- introspection helpers -------------------------------------------------------------
    def functions_called(self) -> list[str]:
        return [fn for fn, _ in self.rest_calls]

    def forms_for(self, function: str) -> list[dict[str, str]]:
        return [f for fn, f in self.rest_calls if fn == function]

    def preflight_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(PREFLIGHT_PATH)]

    def rest_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(REST_PATH)]

    def download_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if PLUGINFILE in r.url.path]

    def foreign_requests(self, host: str = TAU_HOST) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host != host]

    # -- transport -------------------------------------------------------------------------
    @staticmethod
    def _respond(value: Any, arg: Any) -> httpx.Response:
        if callable(value):
            value = value(arg)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json=value)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith(PREFLIGHT_PATH):
            return self._respond(self.preflight, request)
        if path.endswith(REST_PATH):
            fields = form(request)
            function = fields.get("wsfunction", "")
            self.rest_calls.append((function, fields))
            if function in self.rest:
                return self._respond(self.rest[function], fields)
            if self.rest_default is not None:
                return self._respond(self.rest_default, fields)
            body = {
                "exception": "moodle_exception",
                "errorcode": "unmocked",
                "message": f"test mock has no answer for {function}",
            }
            return httpx.Response(200, json=body)
        if PLUGINFILE in path:
            return self._respond(self.download, request)
        return httpx.Response(404, text="not found")


def files_under(directory) -> list:
    """All regular files below `directory` (empty list if it does not exist)."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*") if p.is_file())


Handler = Callable[[httpx.Request], httpx.Response]
