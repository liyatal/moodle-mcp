"""is_write_function, main(--sites/--doctor/default) and the subprocess-level behaviour."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from support import FAKE_TOKEN, clean_env, site_info

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "moodle_mcp.py"

# ============================================================================ is_write_function

MUST_BE_WRITE = [
    "mod_assign_save_submission",
    "mod_assign_submit_for_grading",
    "mod_forum_add_discussion_post",
    "mod_forum_add_discussion",
    "core_message_send_instant_messages",
    "core_message_delete_message",
    "core_user_update_user_preferences",
    "mod_quiz_save_attempt",
    "mod_quiz_start_attempt",
    "core_calendar_create_calendar_events",
    "tool_mobile_call_external_functions",
    "tool_mobile_get_autologin_key",
    # extra real Moodle names
    "core_user_add_user_device",
    "core_user_remove_user_device",
    "core_message_send_messages_to_conversation",
    "core_message_block_user",
    "core_message_mark_all_notifications_as_read",
    "core_calendar_delete_calendar_events",
    "core_group_add_group_members",
    "core_files_upload",
    "mod_quiz_process_attempt",
    "mod_forum_set_pin_state",
    "mod_forum_toggle_favourite_state",
    "mod_chat_send_chat_message",
    "mod_choice_submit_choice_response",
    "mod_data_add_entry",
    "core_completion_update_activity_completion_status_manually",
    "enrol_manual_enrol_users",
]

MUST_BE_READ = [
    "core_course_get_contents",
    "core_enrol_get_users_courses",
    "mod_forum_get_forum_discussions",
    "gradereport_user_get_grade_items",
    "core_webservice_get_site_info",
    "mod_assign_get_submission_status",
    "core_message_get_conversations",
    # extra real Moodle names
    "core_course_get_courses",
    "core_enrol_get_enrolled_users",
    "core_calendar_get_calendar_events",
    "core_user_get_users_by_field",
    "core_message_get_messages",
    "mod_quiz_get_user_attempts",
    "core_files_get_files",
    "mod_assign_get_assignments",
    "mod_forum_get_forum_access_information",
    "core_grades_get_grades",
    "",
]


@pytest.mark.parametrize("name", MUST_BE_WRITE)
def test_is_write_function_true(m, name):
    assert m.is_write_function(name) is True


@pytest.mark.parametrize("name", MUST_BE_READ)
def test_is_write_function_false(m, name):
    assert m.is_write_function(name) is False


def test_no_allowlisted_function_looks_like_a_write(m):
    for name in m.READ_FUNCTIONS:
        assert m.is_write_function(name) is False, name


def test_high_risk_set_contains_the_known_dangerous_functions(m):
    assert isinstance(m.HIGH_RISK, frozenset)
    for name in (
        "tool_mobile_call_external_functions",
        "tool_mobile_get_autologin_key",
        "core_user_add_user_device",
    ):
        assert name in m.HIGH_RISK
        assert m.is_write_function(name) is True
    assert not (m.HIGH_RISK & m.READ_FUNCTIONS)


# ============================================================================= main --sites


def test_sites_listing_works_with_an_invalid_site(m, monkeypatch, capsys):
    monkeypatch.setenv("MOODLE_SITE", "bogus")
    monkeypatch.delenv("MOODLE_TOKEN")
    assert m.main(["--sites"]) == 0
    out, _err = capsys.readouterr()
    lines = out.splitlines()
    assert len(lines) == len(m.SITES)
    for line, (key, (name, url)) in zip(lines, m.SITES.items(), strict=True):
        assert line == f"{key:11} {name:45} {url}"


# ============================================================================ main --doctor

WRITE_FUNCTIONS = [
    "mod_assign_save_submission",
    "core_message_send_instant_messages",
    "tool_mobile_call_external_functions",
]
READ_FUNCTION_NAMES = ["core_course_get_contents", "core_enrol_get_users_courses"]
SUMMARY_RE = re.compile(r"^doctor: (\d+) ok, (\d+) warn, (\d+) fail$")


def run_doctor(m, capsys):
    rc = m.main(["--doctor"])
    out, err = capsys.readouterr()
    lines = [line for line in out.splitlines() if line.strip()]
    return rc, out, err, lines


def parse_doctor(lines):
    assert lines, "doctor printed nothing"
    for line in lines[:-1]:
        assert line.startswith(("OK:", "WARN:", "FAIL:")), line
    summary = SUMMARY_RE.match(lines[-1])
    assert summary, lines[-1]
    ok, warn, fail = map(int, summary.groups())
    counts = {
        "OK:": sum(line.startswith("OK:") for line in lines),
        "WARN:": sum(line.startswith("WARN:") for line in lines),
        "FAIL:": sum(line.startswith("FAIL:") for line in lines),
    }
    assert (ok, warn, fail) == (counts["OK:"], counts["WARN:"], counts["FAIL:"])
    return ok, warn, fail


def assert_no_private_data(*texts):
    for text in texts:
        assert FAKE_TOKEN not in text
        assert "jdoe_private" not in text
        assert "Dana" not in text
        assert "Cohen" not in text
        assert "987654" not in text
        assert "Sensitive University" not in text


def test_doctor_clean_setup_exits_zero(m, mock, capsys):
    mock.on(
        "core_webservice_get_site_info",
        site_info(userid=987654, functions=READ_FUNCTION_NAMES),
    )
    rc, out, err, lines = run_doctor(m, capsys)
    ok, warn, fail = parse_doctor(lines)
    assert rc == 0
    assert fail == 0
    assert ok >= 3
    assert "moodle.tau.ac.il" in out
    assert "4.5.1" in out  # Moodle release
    assert re.search(r"(?<!\d)2(?!\d)", out)  # number of functions the token holds
    assert "/webservice" not in out
    assert_no_private_data(out, err)


def test_doctor_reports_write_capable_functions_as_warnings(m, mock, capsys):
    mock.on(
        "core_webservice_get_site_info",
        site_info(userid=987654, functions=READ_FUNCTION_NAMES + WRITE_FUNCTIONS),
    )
    rc, out, err, lines = run_doctor(m, capsys)
    _ok, warn, fail = parse_doctor(lines)
    assert rc == 0  # warnings do not fail the run
    assert warn >= 1
    assert fail == 0
    for name in WRITE_FUNCTIONS:
        assert name in out
    for name in READ_FUNCTION_NAMES:
        assert name not in out
    assert_no_private_data(out, err)


def test_doctor_caps_the_write_function_list_at_30_names(m, mock, capsys):
    many = [f"mod_fake_save_thing_{i:03d}" for i in range(60)]
    mock.on("core_webservice_get_site_info", site_info(userid=987654, functions=many))
    rc, out, _err, lines = run_doctor(m, capsys)
    parse_doctor(lines)
    assert rc == 0
    listed = [name for name in many if name in out]
    assert 1 <= len(listed) <= 30
    assert "60" in out  # the count is still reported


def test_doctor_only_asks_for_site_info(m, mock, capsys):
    mock.on("core_webservice_get_site_info", site_info(userid=987654))
    run_doctor(m, capsys)
    for function in mock.functions_called():
        assert function in {"core_webservice_get_site_info", "tool_mobile_get_public_config"}


def test_doctor_invalid_token_from_moodle_fails(m, mock, capsys):
    mock.on(
        "core_webservice_get_site_info",
        {"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Invalid token"},
    )
    rc, out, err, lines = run_doctor(m, capsys)
    _ok, _warn, fail = parse_doctor(lines)
    assert rc == 1
    assert fail >= 1
    assert any(line.startswith("FAIL:") for line in lines)
    assert_no_private_data(out, err)


def test_doctor_wrong_site_identity_fails_and_never_sends_the_token(m, mock, capsys):
    mock.preflight = [{"error": False, "data": {"wwwroot": "https://evil.example.com"}}]
    rc, out, err, lines = run_doctor(m, capsys)
    _ok, _warn, fail = parse_doctor(lines)
    assert rc == 1
    assert fail >= 1
    assert mock.rest_requests() == []
    assert_no_private_data(out, err)


def test_doctor_with_preflight_skipped_still_runs(m, mock, monkeypatch, capsys):
    monkeypatch.setenv("MOODLE_SKIP_PREFLIGHT", "1")
    mock.on("core_webservice_get_site_info", site_info(userid=987654))
    rc, _out, _err, lines = run_doctor(m, capsys)
    parse_doctor(lines)
    assert rc == 0
    assert mock.preflight_requests() == []


@pytest.mark.parametrize(
    ("env", "value", "secret"),
    [
        ("MOODLE_TOKEN", "short", None),
        ("MOODLE_TOKEN", "has-dashes-0123456789abcdef", "has-dashes-0123456789abcdef"),
        ("MOODLE_SITE", "bogus", None),
        ("MOODLE_URL", "http://moodle.example.edu", None),
        ("MOODLE_URL", "https://user:pw@moodle.example.edu", "user:pw"),
    ],
)
def test_doctor_bad_config_fails_without_traceback_or_secret(
    m, mock, monkeypatch, capsys, env, value, secret
):
    monkeypatch.setenv(env, value)
    rc, out, err, _lines = run_doctor(m, capsys)
    assert rc in (1, 2)  # FAIL line (1) or config error (2): both are non-zero
    assert "Traceback" not in out + err
    if secret:
        assert secret not in out + err
    assert mock.rest_requests() == []


def test_doctor_missing_token_fails(m, mock, monkeypatch, capsys):
    monkeypatch.delenv("MOODLE_TOKEN")
    rc, out, err, _lines = run_doctor(m, capsys)
    assert rc in (1, 2)
    assert "Traceback" not in out + err
    assert mock.rest_requests() == []


# ===================================================================================== main()


def test_main_config_error_returns_2_with_message_on_stderr(m, monkeypatch, capsys):
    monkeypatch.setenv("MOODLE_SITE", "bogus")
    ran = []
    monkeypatch.setattr(m.mcp, "run", lambda *a, **k: ran.append(1))
    assert m.main([]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "bogus" in err
    assert "Traceback" not in err
    assert ran == []


def test_main_default_runs_the_stdio_server(m, monkeypatch, capsys):
    ran = []
    monkeypatch.setattr(m.mcp, "run", lambda *a, **k: ran.append((a, k)))
    assert m.main([]) == 0
    assert len(ran) == 1
    out, _err = capsys.readouterr()
    assert out == ""


def test_main_starts_without_a_token_so_the_server_can_explain_itself(m, monkeypatch):
    monkeypatch.delenv("MOODLE_TOKEN")
    ran = []
    monkeypatch.setattr(m.mcp, "run", lambda *a, **k: ran.append(1))
    assert m.main([]) == 0
    assert ran == [1]


# =================================================================================== subprocess


def run_python(*args: str, env=None, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed interpreter, repo-local script, no shell
        [sys.executable, *args],
        cwd=ROOT,
        env=env or clean_env(MOODLE_TOKEN=FAKE_TOKEN),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def test_importing_the_module_prints_nothing_and_does_not_exit():
    result = run_python("-c", "import moodle_mcp")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_importing_with_a_bogus_site_is_lazy():
    env = clean_env(MOODLE_SITE="bogus", MOODLE_TOKEN_FILE="/definitely/not/here")
    result = run_python("-c", "import moodle_mcp", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_script_sites_listing():
    result = run_python(str(SCRIPT), "--sites")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 37
    assert lines[0].startswith("tau ")
    assert "https://moodle.tau.ac.il" in lines[0]
    assert FAKE_TOKEN not in result.stdout + result.stderr


def test_script_sites_listing_needs_no_token_and_ignores_bogus_site():
    env = clean_env(MOODLE_SITE="bogus", MOODLE_TOKEN_FILE="/definitely/not/here")
    result = run_python(str(SCRIPT), "--sites", env=env)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 37


def test_script_bogus_site_exits_2_without_traceback():
    env = clean_env(MOODLE_SITE="bogus", MOODLE_TOKEN=FAKE_TOKEN)
    result = run_python(str(SCRIPT), "--doctor", env=env)
    assert result.returncode in (1, 2)
    assert "Traceback" not in result.stderr
    assert FAKE_TOKEN not in result.stdout + result.stderr
    assert "bogus" in result.stdout + result.stderr
