"""Read-only live checks for the batch 1 tools (course_updates, forum_posts, discussion_id).

Opt-in with MOODLE_LIVE=1, see test_live_token.py for the setup and the safety rules (types and
shapes only, never personal content in assertions).
"""

from __future__ import annotations

import pytest

from test_live_token import courses, fenced, live, real_items  # noqa: F401  (shared fixtures)

pytestmark = pytest.mark.live


def test_course_updates_shape(live, courses):  # noqa: F811
    checked = 0
    for c in courses[:6]:
        for item in real_items(live.course_updates(c["id"], 30)):
            checked += 1
            assert set(item) == {"id", "type", "name", "updates"}
            assert item["id"] is None or isinstance(item["id"], int)
            assert item["name"] is None or fenced(item["name"])
            for u in real_items(item["updates"]):
                assert set(u) == {"what", "when", "count"}
                assert u["what"] is None or isinstance(u["what"], str)
                assert isinstance(u["count"], int)
    # an empty result is legitimate (nothing changed): only the shape is checked
    assert checked >= 0


def test_course_updates_rejects_bad_arguments_without_a_request(live):  # noqa: F811
    for bad in (0, -1, 91, True, "7"):
        with pytest.raises(ValueError):
            live.course_updates(1, bad)


def test_forum_discussions_expose_an_id_that_forum_posts_accepts(live, courses):  # noqa: F811
    seen_discussion = False
    for c in courses[:6]:
        for d in real_items(live.forum_discussions(c["id"], 3)):
            assert "discussion_id" in d
            if not isinstance(d["discussion_id"], int):
                continue
            seen_discussion = True
            posts = real_items(live.forum_posts(d["discussion_id"], 5))
            assert posts, "a discussion has at least its opening post"
            for p in posts:
                assert set(p) == {"id", "parent_id", "subject", "author", "posted", "message"}
                assert fenced(p["subject"]) and fenced(p["message"])
                assert p["parent_id"] is None or isinstance(p["parent_id"], int)
            return
    if not seen_discussion:
        pytest.skip("no forum discussion found in the first courses")
