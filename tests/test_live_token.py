"""Read-only checks against a REAL Moodle with a REAL token. Skipped unless MOODLE_LIVE=1.

    MOODLE_LIVE=1 python -m pytest -m live -q

Needs the real token saved as `.token` next to moodle_mcp.py (or MOODLE_LIVE_TOKEN_FILE=<path>);
MOODLE_LIVE_SITE=<key> picks another institution (default: tau).

Safety rules for this file:
* every call goes through the real server code and only reads (the allowlist is asserted);
* the tests never open the token file themselves: they point `MOODLE_TOKEN_FILE` at it and let
  `moodle_mcp` read it, exactly as the server does;
* assertions check TYPES, KEYS and SHAPES, never personal content, and never compare course data
  inside an `assert` expression, so a failing run does not print names, grades or messages;
* downloads go to pytest's tmp dir and only the size / kind of the file is checked.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

FENCE_OPEN = "<untrusted_moodle_content source="
FENCE_CLOSE = "</untrusted_moodle_content>"
MAX_DOWNLOAD_PROBE_BYTES = 2_000_000


@pytest.fixture
def live(m, monkeypatch):
    """`moodle_mcp` pointed at the real token file and the real HTTP client."""
    token_file = Path(
        os.environ.get("MOODLE_LIVE_TOKEN_FILE") or Path(m.__file__).parent / ".token"
    )
    if not token_file.is_file():
        pytest.skip("no real token file (save it as .token or set MOODLE_LIVE_TOKEN_FILE)")
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("MOODLE_SITE", os.environ.get("MOODLE_LIVE_SITE", "tau"))
    return m


def fenced(value) -> bool:
    return isinstance(value, str) and value.startswith(FENCE_OPEN) and value.endswith(FENCE_CLOSE)


_MARKER_KEYS = {"truncated", "next_offset"}


def is_marker(item) -> bool:
    """A truncation marker: {"truncated": ...}, optionally with "next_offset" (paged tools)."""
    return isinstance(item, dict) and "truncated" in item and set(item) <= _MARKER_KEYS


def real_items(items):
    """Drop the {"truncated": ...[, "next_offset": N]} marker, if any."""
    assert isinstance(items, list)
    return [i for i in items if not is_marker(i)]


@pytest.fixture
def courses(live):
    result = real_items(live.list_courses(include_past=True))
    if not result:
        pytest.skip("this account has no courses")
    return result


def test_site_info_and_all_read_functions_exist_on_the_site(live):
    info = live.call("core_webservice_get_site_info")
    assert isinstance(info.get("release"), str)
    names = {f.get("name") for f in info.get("functions", []) if isinstance(f, dict)}
    missing = sorted(live.READ_FUNCTIONS - names - {"tool_mobile_get_public_config"})
    assert missing == [], f"functions the server uses are not available on this site: {missing}"


def test_identity_preflight_passes(live):
    live.ensure_site_identity()
    assert live.get_base() in live._preflight_ok


def test_doctor_reports_no_failure_and_leaks_nothing(live, capsys):
    code = live.main(["--doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.rstrip().splitlines()[-1].endswith("0 fail")
    assert live.token() not in out
    assert "token=" not in out.lower()


def test_allowlist_blocks_writes_on_the_real_site(live):
    with pytest.raises(PermissionError):
        live.call("core_message_send_instant_messages", messages=[])
    with pytest.raises(PermissionError):
        live.call("mod_forum_add_discussion_post", postid=1, subject="x", message="x")


def test_list_courses_shape(live, courses):
    for c in courses:
        assert set(c) == {"id", "name", "shortname", "progress", "ended"}
        assert isinstance(c["id"], int)
        assert fenced(c["name"])
        assert isinstance(c["ended"], bool)


def test_upcoming_deadlines_shape(live):
    items = real_items(live.upcoming_deadlines(30))
    for e in items:
        assert set(e) == {"name", "course", "due", "type", "url"}
        assert fenced(e["name"])
        assert e["due"] is None or isinstance(e["due"], str)


def test_course_tools_shapes_on_the_first_courses(live, courses):
    seen = {"contents": 0, "assignments": 0, "grades": 0, "forums": 0}
    for c in courses[:6]:
        cid = c["id"]
        sections = live.course_contents(cid)
        assert isinstance(sections, list)
        for s in real_items(sections):
            if "modules" not in s:
                continue
            seen["contents"] += 1
            assert fenced(s["section"])
            assert s["section_number"] is None or isinstance(s["section_number"], int)
            assert isinstance(s["modules_total"], int) and isinstance(s["files_total"], int)
            for mod in real_items(s["modules"]):
                assert isinstance(mod["id"], int) or mod["id"] is None
                assert fenced(mod["name"])
                assert isinstance(mod["files_total"], int)
                for f in real_items(mod["files"]):
                    assert fenced(f["filename"])
                    assert f["fileurl"] is None or f["fileurl"].startswith("https://")
        for a in real_items(live.assignments(cid)):
            seen["assignments"] += 1
            assert fenced(a["name"])
            assert a["submission_status"] in (None, "new", "draft", "submitted", "reopened")
        try:
            grade_items = real_items(live.grades(cid))
        except live.MoodleError as e:  # e.g. nopermissiontoviewgrades: fine, must be a clean error
            assert e.errorcode not in live._AUTH_ERRORS
        else:
            for g in grade_items:
                seen["grades"] += 1
                assert set(g) == {"item", "grade", "range", "percentage"}
                assert fenced(g["item"])
        for d in real_items(live.forum_discussions(cid, 3)):
            seen["forums"] += 1
            assert fenced(d["subject"]) and fenced(d["author"]) and fenced(d["message"])
    assert seen["contents"] > 0, "no course returned any section: is the account enrolled?"


def test_download_roundtrip_with_the_token_in_the_post_body(live, courses, dl_dir):
    candidates = []
    for c in courses[:6]:
        for s in real_items(live.course_contents(c["id"])):
            for mod in real_items(s.get("modules", [])):
                for f in real_items(mod["files"]):
                    size = f.get("size")
                    if (
                        f.get("fileurl")
                        and isinstance(size, int)
                        and 0 < size <= MAX_DOWNLOAD_PROBE_BYTES
                    ):
                        candidates.append((size, f["fileurl"]))
    if not candidates:
        pytest.skip("no small downloadable file found in the first courses")
    size, url = min(candidates)
    assert "MOODLE_DOWNLOAD_TOKEN_IN_QUERY" not in os.environ
    saved = Path(live.download_file(url, "live-check"))
    assert saved.is_file() and dl_dir in saved.parents
    data = saved.read_bytes()
    assert len(data) > 0
    assert live.token().encode() not in data
    head = data[:200].lstrip()
    try:  # a Moodle error body would parse as {"error"/"exception": ...}; a real file does not
        parsed = json.loads(data)
    except ValueError:
        parsed = None
    assert not (isinstance(parsed, dict) and ("exception" in parsed or "errorcode" in parsed)), (
        head[:0]
    )


def test_no_tool_output_contains_the_token(live, courses):
    token = live.token()
    blobs = [
        live.list_courses(include_past=True),
        live.upcoming_deadlines(30),
        live.course_contents(courses[0]["id"]),
        live.assignments(courses[0]["id"]),
        live.forum_discussions(courses[0]["id"], 3),
    ]
    text = json.dumps(blobs, ensure_ascii=False)
    assert token not in text
    assert "wstoken" not in text.lower()


def test_course_contents_pages_and_section_filter(live, courses):
    """Shapes only: next_offset continues the listing, section= returns that section only."""
    for c in courses[:6]:
        first = live.course_contents(c["id"])
        sections = [s for s in real_items(first) if "modules" in s]
        if not sections:
            continue
        markers = [i for i in first if is_marker(i)]
        assert len(markers) <= 1
        if markers:
            nxt = markers[0]["next_offset"]
            assert isinstance(nxt, int) and nxt > 0
            assert isinstance(live.course_contents(c["id"], offset=nxt), list)
        number = sections[0]["section_number"]
        if isinstance(number, int):
            only = real_items(live.course_contents(c["id"], section=number))
            assert only and all(s["section_number"] == number for s in only)
        return
    pytest.skip("no course with sections in the first courses")
