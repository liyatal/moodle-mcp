"""Real-network checks. Skipped unless MOODLE_LIVE=1 (never run in CI by default).

Token-less on purpose: only the public identity endpoint is contacted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_sites.py"


def test_live_preflight_for_tau(m):
    m.ensure_site_identity()  # raises MoodleError on mismatch / unreachable
    assert len(m._preflight_ok) == 1


def test_live_every_site_still_matches_its_host(m):
    spec = importlib.util.spec_from_file_location("check_sites_live", SCRIPT)
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        verdicts = {key: check.check_site(client, url)[0] for key, (_n, url) in m.SITES.items()}
    mismatches = {k: v for k, v in verdicts.items() if v == "MISMATCH"}
    assert mismatches == {}
