"""
Moodle MCP server for TAU Moodle (moodle.tau.ac.il).

Token lookup order:
    1. MOODLE_TOKEN environment variable
    2. .token file next to this script   (one line, chmod 600)

Run:  .venv/bin/python moodle_mcp.py     (stdio)
"""

import os
import time
import datetime as dt
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.environ.get("MOODLE_URL", "https://moodle.tau.ac.il").rstrip("/")
TOKEN_FILE = Path(os.environ.get("MOODLE_TOKEN_FILE", Path(__file__).resolve().parent / ".token"))
DOWNLOAD_DIR = Path(os.environ.get("MOODLE_DOWNLOAD_DIR", Path.home() / "Downloads" / "moodle")).resolve()

mcp = FastMCP("moodle")
_client = httpx.Client(timeout=30)
_userid: int | None = None


def token() -> str:
    """Read the token lazily so the server still starts (and explains itself) without one."""
    tok = os.environ.get("MOODLE_TOKEN", "").strip()
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text().strip()
    if not tok:
        raise RuntimeError(f"No Moodle token. Set MOODLE_TOKEN or put the token in {TOKEN_FILE}")
    return tok


def call(function: str, **params):
    """Call a Moodle web service function (REST, JSON)."""
    data = {"wstoken": token(), "wsfunction": function, "moodlewsrestformat": "json"}
    data.update(_flatten(params))
    r = _client.post(f"{BASE}/webservice/rest/server.php", data=data)
    r.raise_for_status()
    out = r.json()
    if isinstance(out, dict) and out.get("exception"):
        raise RuntimeError(f"{out.get('errorcode')}: {out.get('message')}")
    return out


def _flatten(obj, prefix=""):
    """Moodle expects arrays as courseids[0]=1&courseids[1]=2 ..."""
    flat = {}
    items = obj.items() if isinstance(obj, dict) else enumerate(obj)
    for k, v in items:
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, (dict, list, tuple)):
            flat.update(_flatten(v, key))
        elif isinstance(v, bool):
            flat[key] = int(v)
        elif v is not None:
            flat[key] = v
    return flat


def userid() -> int:
    global _userid
    if _userid is None:
        _userid = call("core_webservice_get_site_info")["userid"]
    return _userid


def fmt_time(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M") if ts else None


@mcp.tool()
def list_courses(include_past: bool = False) -> list[dict]:
    """List the courses I'm enrolled in (current by default)."""
    now = time.time()
    courses = call("core_enrol_get_users_courses", userid=userid())
    out = []
    for c in courses:
        ended = bool(c.get("enddate") and c["enddate"] < now)
        if ended and not include_past:
            continue
        out.append({"id": c["id"], "name": c["fullname"], "shortname": c["shortname"],
                    "progress": c.get("progress"), "ended": ended})
    return out


@mcp.tool()
def course_contents(course_id: int) -> list[dict]:
    """Sections, activities and files of a course."""
    sections = call("core_course_get_contents", courseid=course_id)
    out = []
    for s in sections:
        mods = []
        for m in s.get("modules", []):
            mods.append({
                "id": m["id"], "name": m["name"], "type": m["modname"], "url": m.get("url"),
                "files": [{"filename": f["filename"], "fileurl": f["fileurl"],
                           "size": f.get("filesize"), "modified": fmt_time(f.get("timemodified"))}
                          for f in m.get("contents", []) if f.get("type") == "file"],
            })
        out.append({"section": s["name"], "modules": mods})
    return out


@mcp.tool()
def upcoming_deadlines(days: int = 14) -> list[dict]:
    """Upcoming deadlines / action events (assignments, quizzes...) in the next N days."""
    now = int(time.time())
    res = call("core_calendar_get_action_events_by_timesort",
               timesortfrom=now, timesortto=now + days * 86400, limitnum=50)
    return [{"name": e["name"], "course": e.get("course", {}).get("fullname"),
             "due": fmt_time(e["timesort"]), "type": e.get("modulename"), "url": e.get("url")}
            for e in res.get("events", [])]


@mcp.tool()
def assignments(course_id: int) -> list[dict]:
    """Assignments of a course with due dates, my submission status and attached files."""
    res = call("mod_assign_get_assignments", courseids=[course_id])
    out = []
    for c in res.get("courses", []):
        for a in c.get("assignments", []):
            status = None
            try:
                st = call("mod_assign_get_submission_status", assignid=a["id"])
                status = st.get("lastattempt", {}).get("submission", {}).get("status")
            except Exception:
                pass
            out.append({"id": a["id"], "name": a["name"], "due": fmt_time(a.get("duedate")),
                        "cutoff": fmt_time(a.get("cutoffdate")), "submission_status": status,
                        "files": [{"filename": f["filename"], "fileurl": f["fileurl"]}
                                  for f in a.get("introattachments", [])]})
    return out


@mcp.tool()
def grades(course_id: int) -> list[dict]:
    """My grade items in a course."""
    res = call("gradereport_user_get_grade_items", courseid=course_id, userid=userid())
    out = []
    for g in res.get("usergrades", []):
        for item in g.get("gradeitems", []):
            out.append({"item": item.get("itemname") or "Course total",
                        "grade": item.get("gradeformatted"), "range": item.get("rangeformatted"),
                        "percentage": item.get("percentageformatted")})
    return out


@mcp.tool()
def forum_discussions(course_id: int, limit: int = 10) -> list[dict]:
    """Latest discussions in a course's forums (announcements included)."""
    forums = call("mod_forum_get_forums_by_courses", courseids=[course_id])
    out = []
    for f in forums:
        res = call("mod_forum_get_forum_discussions", forumid=f["id"], perpage=limit,
                   sortorder=1)  # newest first
        for d in res.get("discussions", []):
            out.append({"forum": f["name"], "subject": d["subject"], "author": d.get("userfullname"),
                        "posted": fmt_time(d.get("created")), "message": d.get("message", "")[:1500]})
    return out


@mcp.tool()
def download_file(fileurl: str, subfolder: str = "") -> str:
    """Download a course file (fileurl from course_contents / assignments) to the local downloads folder."""
    url, base = urlsplit(fileurl), urlsplit(BASE)
    # Exact scheme+host match: the token is appended to this URL, so it must never leave Moodle.
    if (url.scheme, url.netloc) != (base.scheme, base.netloc):
        raise ValueError("Only Moodle file URLs are allowed")
    target = (DOWNLOAD_DIR / subfolder).resolve()
    if not target.is_relative_to(DOWNLOAD_DIR):
        raise ValueError("subfolder must stay inside the download directory")
    name = Path(unquote(url.path)).name
    if not name:
        raise ValueError("URL has no file name")
    sep = "&" if url.query else "?"
    r = _client.get(f"{fileurl}{sep}token={token()}", follow_redirects=False)
    r.raise_for_status()
    if "application/json" in r.headers.get("content-type", ""):
        raise RuntimeError(f"Moodle refused the download: {r.text[:300]}")
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    path.write_bytes(r.content)
    return str(path)


if __name__ == "__main__":
    mcp.run()
