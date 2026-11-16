"""scripts/check_sites.py: token-less, no import-time side effects, correct verdicts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_sites.py"


@pytest.fixture
def check_sites():
    def boom(*_a, **_k):
        raise AssertionError("check_sites touched the network at import time")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx.Client, "send", boom)
        patch.setattr(httpx, "post", boom)
        spec = importlib.util.spec_from_file_location("check_sites_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def answer(data):
    return lambda request: httpx.Response(200, json=[{"error": False, "data": data}])


def test_import_has_no_side_effects(check_sites):
    assert callable(check_sites.main)
    assert callable(check_sites.check_site)


def test_ok_when_host_matches(check_sites):
    client = client_for(answer({"wwwroot": "https://moodle.tau.ac.il", "httpswwwroot": None}))
    status, _detail = check_sites.check_site(client, "https://moodle.tau.ac.il")
    assert status == "OK"


def test_ok_with_path_prefix_and_uppercase_host(check_sites):
    client = client_for(answer({"wwwroot": "https://MOODLE.BGU.ac.il/moodle"}))
    assert check_sites.check_site(client, "https://moodle.bgu.ac.il/moodle")[0] == "OK"


def test_mismatch_when_site_claims_another_host(check_sites):
    client = client_for(answer({"wwwroot": "https://moodle27.technion.ac.il"}))
    status, detail = check_sites.check_site(client, "https://moodle26.technion.ac.il")
    assert status == "MISMATCH"
    assert "moodle27.technion.ac.il" in detail


def test_request_is_the_tokenless_public_config_post(check_sites):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[{"error": False, "data": {"wwwroot": "https://x.edu"}}])

    check_sites.check_site(client_for(handler), "https://x.edu")
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/lib/ajax/service-nologin.php"
    assert request.url.params["info"] == "tool_mobile_get_public_config"
    assert json.loads(request.content) == [
        {"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}
    ]
    assert b"token" not in request.content.lower()
    assert "token" not in str(request.url).lower()


@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(500, text="boom"),
        lambda: httpx.Response(302, headers={"location": "https://elsewhere.example/"}),
        lambda: httpx.Response(200, text="<html>login</html>"),
        lambda: httpx.Response(200, json=[]),
        lambda: httpx.Response(200, json={"not": "a list"}),
        lambda: httpx.Response(200, json=[{"error": False, "data": {}}]),
        lambda: httpx.ConnectError("no route", request=httpx.Request("POST", "https://x.edu")),
    ],
)
def test_errors_are_reported_not_raised(check_sites, response):
    def handler(_request):
        result = response()
        if isinstance(result, Exception):
            raise result
        return result

    status, _detail = check_sites.check_site(client_for(handler), "https://x.edu")
    assert status == "ERROR"


def test_script_is_not_a_test_module():
    assert not SCRIPT.name.startswith("test_")
