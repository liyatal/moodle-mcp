"""Spawn the real server over stdio (no network: preflight skipped, no tool is called).

Checks that stdout carries nothing but JSON-RPC and that the advertised tools/instructions
match the contract.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from support import FAKE_TOKEN, clean_env

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    "list_courses",
    "course_contents",
    "upcoming_deadlines",
    "assignments",
    "grades",
    "forum_discussions",
    "course_updates",
    "forum_posts",
    "quizzes",
    "download_file",
}


class Session:
    def __init__(self) -> None:
        env = clean_env(MOODLE_SITE="tau", MOODLE_TOKEN=FAKE_TOKEN, MOODLE_SKIP_PREFLIGHT="1")
        self.proc = subprocess.Popen(  # noqa: S603 - fixed interpreter and repo-local script
            [sys.executable, str(ROOT / "moodle_mcp.py")],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.raw: list[str] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line)

    def send(self, message: dict) -> None:
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, msg_id: int, timeout: float = 60) -> dict:
        while True:
            line = self.lines.get(timeout=timeout)
            self.raw.append(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # kept in `raw`; the purity test inspects it
            if message.get("id") == msg_id:
                return message

    def close(self) -> str:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            self.proc.kill()
        stderr = self.proc.stderr.read() if self.proc.stderr else ""
        self.proc.stdout.close()
        return stderr


@pytest.fixture(scope="module")
def session():
    s = Session()
    try:
        s.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            }
        )
        init = s.wait_for(1)
        s.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        s.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = s.wait_for(2)
        yield {"session": s, "init": init, "tools": tools}
    finally:
        stderr = s.close()
        s.stderr_text = stderr


def test_stdout_is_pure_json_rpc(session):
    s = session["session"]
    assert s.raw, "server wrote nothing"
    for line in s.raw:
        assert isinstance(json.loads(line), dict), line


def test_server_never_writes_the_token_to_stdout(session):
    assert all(FAKE_TOKEN not in line for line in session["session"].raw)


def test_tools_list_has_exactly_the_ten_tools(session):
    names = {t["name"] for t in session["tools"]["result"]["tools"]}
    assert names == TOOLS


def test_initialize_instructions_warn_about_untrusted_content(session):
    text = (session["init"]["result"].get("instructions") or "").lower()
    assert "untrusted_moodle_content" in text
    assert "read-only" in text or "read only" in text
