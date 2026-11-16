"""validate_base_url, get_base, token, scrub, download_dir, max_download_bytes (CONTRACT s3)."""

from __future__ import annotations

import sys

import pytest

from support import FAKE_TOKEN

# --------------------------------------------------------------------------- validate_base_url

VALID_URLS = [
    ("https://moodle.tau.ac.il", "https://moodle.tau.ac.il"),
    ("https://moodle.tau.ac.il/", "https://moodle.tau.ac.il"),
    ("\t https://moodle.tau.ac.il \n", "https://moodle.tau.ac.il"),
    ("https://MOODLE.Tau.AC.il", "https://moodle.tau.ac.il"),
    ("https://moodle.bgu.ac.il/moodle", "https://moodle.bgu.ac.il/moodle"),
    ("https://moodle.bgu.ac.il/moodle/", "https://moodle.bgu.ac.il/moodle"),
    ("https://moodle.example.edu:8443/lms", "https://moodle.example.edu:8443/lms"),
    ("https://localhost", "https://localhost"),
    ("http://localhost", "http://localhost"),
    ("http://localhost:8080/", "http://localhost:8080"),
    ("http://LOCALHOST:8080", "http://localhost:8080"),
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("http://[::1]:8000", "http://[::1]:8000"),
]

INVALID_URLS = [
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
    pytest.param("moodle.tau.ac.il", id="no-scheme"),
    pytest.param("//moodle.tau.ac.il", id="scheme-relative"),
    pytest.param("https://", id="no-host"),
    pytest.param("https:///path", id="empty-host-with-path"),
    pytest.param("https://:443", id="empty-host-with-port"),
    pytest.param("http://moodle.tau.ac.il", id="http-remote"),
    pytest.param("http://localhost.evil.com", id="http-localhost-lookalike"),
    pytest.param("http://evil.com/localhost", id="http-localhost-in-path"),
    pytest.param("http://127.0.0.1.evil.com", id="http-127-lookalike"),
    pytest.param("ftp://moodle.tau.ac.il", id="ftp"),
    pytest.param("file:///etc/passwd", id="file"),
    pytest.param("javascript:alert(1)", id="javascript"),
    pytest.param("https://user@moodle.tau.ac.il", id="userinfo-user"),
    pytest.param("https://user:pw@moodle.tau.ac.il", id="userinfo-password"),
    pytest.param("https://@moodle.tau.ac.il", id="userinfo-empty"),
    pytest.param("https://moodle.tau.ac.il@evil.com", id="host-confusion-at"),
    pytest.param("https://moodle.tau.ac.il?x=1", id="query"),
    pytest.param("https://moodle.tau.ac.il/?x=1", id="query-after-slash"),
    pytest.param("https://moodle.tau.ac.il/moodle?token=abc", id="query-token"),
    pytest.param("https://moodle.tau.ac.il#frag", id="fragment"),
    pytest.param("https://moodle.tau.ac.il/#frag", id="fragment-after-slash"),
    pytest.param("https://moodle.tau .ac.il", id="space-in-host"),
    pytest.param("https://moodle.tau.ac.il/a b", id="space-in-path"),
    pytest.param("https://moodle.tau.ac.il/a\nb", id="newline-in-path"),
    pytest.param("https://moodle.tau.ac.il/a\rb", id="cr-in-path"),
    pytest.param("https://moodle.tau.ac.il/\x00", id="nul"),
    pytest.param("https://moodle.tau.ac.il/\x07", id="bell"),
    pytest.param("https://moodle.tau.ac.il\\evil.com", id="backslash-host"),
    pytest.param("https://moodle.tau.ac.il/a\\b", id="backslash-path"),
    pytest.param("https://moodle.tau.ac.il:abc", id="junk-port"),
    pytest.param("https://moodle.tau.ac.il:99999999", id="huge-port"),
]


def test_config_error_is_a_value_error(m):
    assert issubclass(m.ConfigError, ValueError)


@pytest.mark.parametrize(("raw", "expected"), VALID_URLS)
def test_validate_base_url_accepts_and_normalizes(m, raw, expected):
    assert m.validate_base_url(raw) == expected


@pytest.mark.parametrize("raw", INVALID_URLS)
def test_validate_base_url_rejects(m, raw):
    with pytest.raises(m.ConfigError):
        m.validate_base_url(raw)


def test_every_builtin_site_passes_validation(m):
    assert len(m.SITES) == 37
    for key, (name, url) in m.SITES.items():
        assert name.strip(), key
        assert url.startswith("https://"), key
        assert m.validate_base_url(url) == url, key


# --------------------------------------------------------------------------------- get_base


def test_get_base_defaults_to_tau(m):
    assert m.get_base() == "https://moodle.tau.ac.il"


def test_get_base_follows_site_with_path_prefix(m, monkeypatch):
    monkeypatch.setenv("MOODLE_SITE", "bgu")
    assert m.get_base() == "https://moodle.bgu.ac.il/moodle"


def test_get_base_is_not_cached(m, monkeypatch):
    first = m.get_base()
    monkeypatch.setenv("MOODLE_SITE", "technion")
    assert m.get_base() != first
    monkeypatch.setenv("MOODLE_SITE", "tau")
    assert m.get_base() == first


def test_get_base_unknown_site_lists_keys(m, monkeypatch):
    monkeypatch.setenv("MOODLE_SITE", "bogus")
    with pytest.raises(m.ConfigError) as info:
        m.get_base()
    message = str(info.value)
    assert "bogus" in message
    assert "tau" in message
    assert "technion" in message


def test_get_base_moodle_url_overrides_site(m, monkeypatch, capsys):
    monkeypatch.setenv("MOODLE_URL", "https://LMS.Example-Print-Once.edu/moodle/")
    assert m.get_base() == "https://lms.example-print-once.edu/moodle"
    assert m.get_base() == "https://lms.example-print-once.edu/moodle"
    out, err = capsys.readouterr()
    assert out == ""  # stdout is the MCP channel
    assert err.count("lms.example-print-once.edu") <= 1  # announced at most once
    assert FAKE_TOKEN not in err


def test_get_base_moodle_url_overrides_even_invalid_site(m, monkeypatch):
    monkeypatch.setenv("MOODLE_SITE", "bogus")
    monkeypatch.setenv("MOODLE_URL", "https://moodle.example.edu")
    assert m.get_base() == "https://moodle.example.edu"


@pytest.mark.parametrize(
    "bad",
    ["http://moodle.example.edu", "https://u:p@moodle.example.edu", "https://x.edu/?a=1", "junk"],
)
def test_get_base_rejects_bad_moodle_url(m, monkeypatch, bad):
    monkeypatch.setenv("MOODLE_URL", bad)
    with pytest.raises(m.ConfigError):
        m.get_base()


def test_get_base_empty_moodle_url_falls_back_to_site(m, monkeypatch):
    monkeypatch.setenv("MOODLE_URL", "")
    assert m.get_base() == "https://moodle.tau.ac.il"


# ----------------------------------------------------------------------------------- token

BAD_TOKENS = [
    pytest.param("a" * 15, id="too-short"),
    pytest.param("a" * 129, id="too-long"),
    pytest.param("abcd-efgh-ijkl-mnop-qrst-uvwx", id="dashes"),
    pytest.param("abcdefgh_ijklmnop_qrstuvwx", id="underscores"),
    pytest.param("abcdefgh ijklmnop qrstuvwx", id="inner-space"),
    pytest.param("Bearer a1b2c3d4e5f60718293a4b5c6d7e8f90", id="bearer-prefix"),
    pytest.param("token=a1b2c3d4e5f60718293a4b5c6d7e8f90", id="key-value"),
    pytest.param('"a1b2c3d4e5f60718293a4b5c6d7e8f90"', id="quoted"),
    pytest.param("a1b2c3d4e5f60718293a4b5c6d7e8f9١", id="non-ascii-digit"),
    pytest.param("ünïcödé-token-0123456789abcdef", id="unicode"),
    pytest.param("a1b2c3d4e5f60718\n293a4b5c6d7e8f90", id="inner-newline"),
]


def _assert_value_not_in(message: str, value: str) -> None:
    assert value.strip() not in message
    for i in range(max(0, len(value) - 11)):
        assert value[i : i + 12] not in message, "token fragment leaked into the message"


@pytest.mark.parametrize("value", ["a" * 16, "a" * 128, FAKE_TOKEN, "A1b2C3d4E5f6G7h8"])
def test_token_accepts_alnum_16_to_128(m, monkeypatch, value):
    monkeypatch.setenv("MOODLE_TOKEN", value)
    assert m.token() == value


def test_token_env_is_stripped(m, monkeypatch):
    monkeypatch.setenv("MOODLE_TOKEN", f"  {FAKE_TOKEN}\r\n")
    assert m.token() == FAKE_TOKEN


@pytest.mark.parametrize("value", BAD_TOKENS)
def test_token_env_bad_format_rejected_without_leaking(m, monkeypatch, value):
    monkeypatch.setenv("MOODLE_TOKEN", value)
    with pytest.raises(m.ConfigError) as info:
        m.token()
    _assert_value_not_in(str(info.value), value)
    _assert_value_not_in(repr(info.value), value)


def test_token_missing(m, monkeypatch):
    monkeypatch.delenv("MOODLE_TOKEN")
    with pytest.raises(m.ConfigError, match="No Moodle token"):
        m.token()


def test_token_empty_env_means_missing(m, monkeypatch):
    monkeypatch.setenv("MOODLE_TOKEN", "   ")
    with pytest.raises(m.ConfigError, match="No Moodle token"):
        m.token()


def test_token_from_file_with_bom_and_crlf(m, monkeypatch, tmp_path):
    path = tmp_path / "tok.txt"
    path.write_bytes(b"\xef\xbb\xbf" + FAKE_TOKEN.encode() + b"\r\n")
    monkeypatch.delenv("MOODLE_TOKEN")
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(path))
    assert m.token() == FAKE_TOKEN


def test_token_file_used_when_env_empty(m, monkeypatch, tmp_path):
    path = tmp_path / "tok.txt"
    path.write_text(FAKE_TOKEN + "\n", encoding="utf-8")
    monkeypatch.setenv("MOODLE_TOKEN", "")
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(path))
    assert m.token() == FAKE_TOKEN


def test_token_env_wins_over_file(m, monkeypatch, tmp_path):
    path = tmp_path / "tok.txt"
    path.write_text("f" * 32, encoding="utf-8")
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(path))
    assert m.token() == FAKE_TOKEN


@pytest.mark.parametrize(
    "content",
    [b"short", b"has-dashes-0123456789abcdef", b"a1b2c3d4e5f60718\x00293a4b5c6d7e8f90"],
)
def test_token_file_bad_content_rejected_without_leaking(m, monkeypatch, tmp_path, content):
    path = tmp_path / "tok.txt"
    path.write_bytes(content)
    monkeypatch.delenv("MOODLE_TOKEN")
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(path))
    with pytest.raises(m.ConfigError) as info:
        m.token()
    text = content.decode("utf-8", errors="replace")
    _assert_value_not_in(str(info.value), text)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_token_file_group_readable_warns_on_stderr(m, monkeypatch, tmp_path, capsys):
    path = tmp_path / "tok.txt"
    path.write_text(FAKE_TOKEN, encoding="utf-8")
    path.chmod(0o644)
    monkeypatch.delenv("MOODLE_TOKEN")
    monkeypatch.setenv("MOODLE_TOKEN_FILE", str(path))
    assert m.token() == FAKE_TOKEN
    out, err = capsys.readouterr()
    assert out == ""
    assert err.strip() != ""
    assert FAKE_TOKEN not in err


# ----------------------------------------------------------------------------------- scrub

SECRET = "SECRETVALUE0123456789"


@pytest.mark.parametrize(
    "text",
    [
        f"https://x.example/y?token={SECRET}&a=1",
        f"wstoken={SECRET}",
        f"token={SECRET}",
        f"boom wstoken={SECRET} bam",
        f"POST /server.php?wstoken={SECRET}&wsfunction=x",
    ],
)
def test_scrub_removes_token_patterns(m, text):
    out = m.scrub(text)
    assert SECRET not in out
    assert "***" in out


def test_scrub_removes_current_token_value(m):
    out = m.scrub(f"error talking to host with {FAKE_TOKEN} inside, twice: {FAKE_TOKEN}")
    assert FAKE_TOKEN not in out
    assert out.count("***") >= 2


def test_scrub_leaves_clean_text_alone(m):
    assert m.scrub("Connection refused") == "Connection refused"
    assert m.scrub("") == ""


def test_scrub_never_raises_without_token(m, monkeypatch):
    monkeypatch.delenv("MOODLE_TOKEN")
    assert m.scrub("plain") == "plain"
    assert SECRET not in m.scrub(f"token={SECRET}")


def test_scrub_never_raises_with_malformed_token(m, monkeypatch):
    monkeypatch.setenv("MOODLE_TOKEN", "not a valid token!!")
    assert m.scrub("plain") == "plain"


# ------------------------------------------------------------------- download_dir / max bytes


def test_download_dir_is_resolved_env_path(m, dl_dir):
    assert m.download_dir() == dl_dir.resolve()
    assert m.download_dir().is_absolute()


def test_max_download_bytes_default_is_100_mb(m):
    assert m.max_download_bytes() == 100 * 1024 * 1024


def test_max_download_bytes_from_env(m, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "5")
    assert m.max_download_bytes() == 5 * 1024 * 1024


def test_max_download_bytes_junk_env_is_a_config_error(m, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "lots")
    with pytest.raises(m.ConfigError):
        m.max_download_bytes()
