"""Fixtures implementing the CONTRACT section-9 test seams.

* env is cleaned and pinned (tau, fake token, tmp download dir, token file that does not exist),
  so no test can ever read a real `.token` or a developer's environment;
* module state (`_userid`, `_preflight_ok`) is reset around every test;
* the module's `_client` is swapped for a MockTransport client, so no real network is possible
  (tests marked `live` are the only exception and are skipped unless MOODLE_LIVE=1).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from support import ENV_VARS, FAKE_TOKEN, MoodleMock


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MOODLE_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live network test; set MOODLE_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MOODLE_SITE", "tau")
    monkeypatch.setenv("MOODLE_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(tmp_path / "no-such-token-file"))
    monkeypatch.setenv("MOODLE_DOWNLOAD_DIR", str(tmp_path / "downloads"))


def _reset_state(module) -> None:
    module._userid = None
    preflight_cache = getattr(module, "_preflight_ok", None)
    if preflight_cache is not None:
        preflight_cache.clear()


@pytest.fixture(autouse=True)
def m(_env):
    """The module under test, with process-wide caches reset before and after the test."""
    import moodle_mcp

    _reset_state(moodle_mcp)
    yield moodle_mcp
    _reset_state(moodle_mcp)


@pytest.fixture(autouse=True)
def mock(monkeypatch, request, m):
    """Swap `m._client` for a MockTransport client backed by a fake Moodle."""
    fake = MoodleMock()
    fake.original_client = getattr(m, "_client", None)
    if request.node.get_closest_marker("live"):
        yield fake
        return
    client = httpx.Client(transport=httpx.MockTransport(fake.handler), follow_redirects=False)
    monkeypatch.setattr(m, "_client", client)
    yield fake
    client.close()


@pytest.fixture
def dl_dir() -> Path:
    """The (not yet created) download directory selected through MOODLE_DOWNLOAD_DIR."""
    return Path(os.environ["MOODLE_DOWNLOAD_DIR"])
