"""check_download_url, safe_filename, safe_subfolder, download_file (CONTRACT s6)."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

import httpx
import pytest

from support import (
    FAKE_TOKEN,
    PLUGINFILE,
    TAU_HOST,
    TAU_URL,
    assert_no_token,
    files_under,
    form,
)

GOOD = f"{TAU_URL}{PLUGINFILE}123/mod_resource/content/1/file.pdf"
RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ============================================================================ check_download_url


@pytest.mark.parametrize(
    "url",
    [
        GOOD,
        GOOD + "?forcedownload=1",
        f"{TAU_URL}:443{PLUGINFILE}1/a.pdf",
        f"HTTPS://MOODLE.TAU.AC.IL{PLUGINFILE}1/a.pdf",
        f"{TAU_URL}{PLUGINFILE}1/My%20File%20%281%29.pdf",
        f"{TAU_URL}{PLUGINFILE}1/%D7%A9%D7%9C%D7%95%D7%9D.pdf",
    ],
)
def test_check_download_url_accepts_moodle_pluginfile_urls(m, url):
    assert m.check_download_url(url, TAU_URL) == url


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("", id="empty"),
        pytest.param("/webservice/pluginfile.php/1/a.pdf", id="relative"),
        pytest.param(f"//{TAU_HOST}{PLUGINFILE}1/a.pdf", id="scheme-relative"),
        pytest.param(f"http://{TAU_HOST}{PLUGINFILE}1/a.pdf", id="http"),
        pytest.param(f"ftp://{TAU_HOST}{PLUGINFILE}1/a.pdf", id="ftp"),
        pytest.param("javascript:alert(1)", id="javascript"),
        pytest.param(f"https://evil.example.com{PLUGINFILE}1/a.pdf", id="other-host"),
        pytest.param(f"https://{TAU_HOST}.evil.com{PLUGINFILE}1/a.pdf", id="suffix-host"),
        pytest.param(f"https://x{TAU_HOST}{PLUGINFILE}1/a.pdf", id="prefix-host"),
        pytest.param(f"https://{TAU_HOST}.{PLUGINFILE}1/a.pdf", id="trailing-dot-host"),
        pytest.param(f"https://user@{TAU_HOST}{PLUGINFILE}1/a.pdf", id="userinfo"),
        pytest.param(f"https://user:pw@{TAU_HOST}{PLUGINFILE}1/a.pdf", id="userinfo-password"),
        pytest.param(f"https://@{TAU_HOST}{PLUGINFILE}1/a.pdf", id="userinfo-empty"),
        pytest.param(f"https://{TAU_HOST}@evil.com{PLUGINFILE}1/a.pdf", id="at-confusion"),
        pytest.param(f"https://evil.com\\@{TAU_HOST}{PLUGINFILE}1/a.pdf", id="backslash-at"),
        pytest.param(f"{TAU_URL}:8443{PLUGINFILE}1/a.pdf", id="other-port"),
        pytest.param(f"{TAU_URL}:80{PLUGINFILE}1/a.pdf", id="port-80"),
        pytest.param(f"{TAU_URL}/pluginfile.php/1/a.pdf", id="legacy-pluginfile-path"),
        pytest.param(f"{TAU_URL}/webservice/rest/server.php?x=1", id="rest-endpoint"),
        pytest.param(f"{TAU_URL}/webservice/pluginfile.php", id="no-trailing-slash"),
        pytest.param(f"{TAU_URL}/other/webservice/pluginfile.php/1/a.pdf", id="nested-prefix"),
        pytest.param(f"{TAU_URL}/mod/resource/view.php?id=5", id="view-page"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/../../../etc/passwd", id="dotdot"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/%2e%2e/%2e%2e/x", id="encoded-dotdot"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/%2E%2E/x", id="encoded-dotdot-upper"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/.%2e/x", id="mixed-dotdot"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/%2e./x", id="mixed-dotdot-2"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/%2E%2e/x", id="mixed-case-dotdot"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/.%2E/x", id="mixed-dotdot-upper"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1%2fa.pdf", id="encoded-slash"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1%2Fa.pdf", id="encoded-slash-upper"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1%5ca.pdf", id="encoded-backslash"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1%5Ca.pdf", id="encoded-backslash-upper"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1\\..\\a.pdf", id="backslashes"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a.pdf#frag", id="fragment"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a.pdf\n", id="trailing-newline"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a\n.pdf", id="inner-newline"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a\r\nHost: evil/.pdf", id="crlf-injection"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a\t.pdf", id="tab"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a b.pdf", id="raw-space"),
        pytest.param(f" {GOOD}", id="leading-space"),
        pytest.param(f"{GOOD} ", id="trailing-space"),
        pytest.param(f"{TAU_URL}{PLUGINFILE}1/a\x00.pdf", id="nul"),
    ],
)
def test_check_download_url_rejects(m, url):
    with pytest.raises(ValueError):
        m.check_download_url(url, TAU_URL)


@pytest.mark.parametrize(
    "path",
    ["/moodle/webservice/pluginfile.php/1/a.pdf"],
)
def test_check_download_url_with_base_path_prefix_accepts(m, path):
    base = "https://moodle.bgu.ac.il/moodle"
    assert m.check_download_url(f"https://moodle.bgu.ac.il{path}", base)


@pytest.mark.parametrize(
    "path",
    [
        "/webservice/pluginfile.php/1/a.pdf",
        "/moodle2/webservice/pluginfile.php/1/a.pdf",
        "/moodlex/webservice/pluginfile.php/1/a.pdf",
        "/moodle/other/webservice/pluginfile.php/1/a.pdf",
        "/Moodle/webservice/pluginfile.php/1/a.pdf",
        "/moodle/webservice/pluginfile.php",
        "/moodle/../webservice/pluginfile.php/1/a.pdf",
    ],
)
def test_check_download_url_with_base_path_prefix_rejects(m, path):
    base = "https://moodle.bgu.ac.il/moodle"
    with pytest.raises(ValueError):
        m.check_download_url(f"https://moodle.bgu.ac.il{path}", base)


# ================================================================================ safe_filename

GOOD_NAMES = [
    "report.pdf",
    "lecture 3 (final).pptx",
    "a-b_c.tar.gz",
    "שלום עולם.pdf",
    "Café – résumé.docx",
    "README",
    "x.y.z",
    "CONSOLE.txt",  # starts with CON but is not CON
    "communication.pdf",
]

HOSTILE_NAMES = [
    "G:planted.txt",
    "name:stream",
    "name.txt:Zone.Identifier",
    "name.txt::$DATA",
    "C:\\Windows\\win.ini",
    "a\x00b.txt",
    "a\x00",
    "a\nb.txt",
    "a\tb.txt",
    "a\x1bb.txt",
    "CON",
    "con",
    "con.txt",
    "CON.tar.gz",
    "NUL",
    "nul.pdf",
    "Prn.doc",
    "AUX",
    "COM1.txt",
    "com9",
    "LPT1.txt",
    "lpt9.doc",
    "Aux.",
    "NUL .txt",
    "file.",
    "file. . .",
    "file   ",
    "file . ",
    ".hidden",
    "...hidden",
    ".bashrc",
    "../../etc/passwd",
    "..\\..\\evil.exe",
    "a/b/c.txt",
    "a\\b.txt",
    "/etc/passwd",
    "\\\\server\\share\\x",
    "/",
    "x" * 500,
    "x" * 500 + ".pdf",
    "ש" * 400 + ".docx",
    "x" * 149 + ".pdf",
    "\u202egnp.exe",
    "evil\u200b.exe",
]


@pytest.mark.parametrize("name", GOOD_NAMES)
def test_safe_filename_keeps_ordinary_names(m, name):
    assert m.safe_filename(name) == name


def _assert_safe_name(name: str, result: str) -> None:
    assert result, f"empty result for {name!r}"
    assert not any(ch in result for ch in "/\\:"), result
    assert "\x00" not in result
    assert not any(unicodedata.category(ch) == "Cc" for ch in result), result
    assert not result.startswith("."), result
    assert not result.endswith((".", " ")), result
    assert result not in {".", ".."}
    assert result.split(".")[0].strip().upper() not in RESERVED, result
    assert len(result) <= 150
    assert Path(result).name == result
    assert os.path.basename(result) == result


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_safe_filename_hostile_names_are_neutralised_or_refused(m, name):
    try:
        result = m.safe_filename(name)
    except ValueError:
        return  # "nothing safe remains" is an allowed outcome
    _assert_safe_name(name, result)
    assert m.safe_filename(name) == result  # deterministic


def test_safe_filename_colon_becomes_a_replacement_not_a_stream(m):
    result = m.safe_filename("G:planted.txt")
    assert ":" not in result
    assert "planted.txt" in result
    result = m.safe_filename("name:stream")
    assert ":" not in result
    assert "name" in result
    assert "stream" in result


def test_safe_filename_separators_are_replaced_not_dropped(m):
    result = m.safe_filename("a/b\\c.txt")
    assert "/" not in result
    assert "\\" not in result
    assert result.endswith("c.txt")


def test_safe_filename_long_names_keep_extension(m):
    for name, ext in [("x" * 500 + ".pdf", ".pdf"), ("ש" * 400 + ".docx", ".docx")]:
        result = m.safe_filename(name)
        assert len(result) <= 150
        assert result.endswith(ext)


@pytest.mark.parametrize("name", ["", ".", "..", "...", "   ", " . ", " .. ", ". . ."])
def test_safe_filename_refuses_empty_or_dot_names(m, name):
    with pytest.raises(ValueError):
        m.safe_filename(name)


@pytest.mark.parametrize("name", ["\x00", "\x00\x00", "\x00.", "\x01\x02"])
def test_safe_filename_control_only_names_are_refused_or_replaced(m, name):
    try:
        result = m.safe_filename(name)
    except ValueError:
        return
    _assert_safe_name(name, result)


@pytest.mark.parametrize("name", ["CON", "con.txt", "NUL", "nul.pdf", "COM1.txt", "LPT9", "aux"])
def test_safe_filename_never_returns_a_device_name(m, name):
    try:
        result = m.safe_filename(name)
    except ValueError:
        return
    assert result.split(".")[0].strip().upper() not in RESERVED


# =============================================================================== safe_subfolder


@pytest.mark.parametrize("sub", ["", "Algorithms", "CS101/Week 1", "שיעורים/שבוע 1", "a/b/c"])
def test_safe_subfolder_accepts_relative_paths(m, sub):
    assert m.safe_subfolder(sub).replace("\\", "/") == sub


@pytest.mark.parametrize(
    "sub",
    [
        "/etc",
        "/",
        "\\abs",
        "C:\\Users\\x",
        "C:/Users/x",
        "C:x",
        "..",
        "../x",
        "a/../b",
        "a/../../b",
        "a\\..\\b",
        "//server/share",
        "\\\\server\\share",
        "~/x/..",
    ],
)
def test_safe_subfolder_rejects_escapes(m, sub):
    with pytest.raises(ValueError):
        m.safe_subfolder(sub)


@pytest.mark.parametrize(
    "sub", ["a/CON/b", "a/x:y", "a\x00b", "a/ .. /b", "week1/", "a//b", "a/./b"]
)
def test_safe_subfolder_odd_segments_are_safe_or_refused(m, sub):
    try:
        result = m.safe_subfolder(sub)
    except ValueError:
        return
    normalised = result.replace("\\", "/")
    assert not normalised.startswith("/")
    assert ":" not in normalised
    assert "\x00" not in normalised
    assert ".." not in normalised.split("/")
    for segment in filter(None, normalised.split("/")):
        assert segment.split(".")[0].strip().upper() not in RESERVED


# =================================================================================== download_file


def _url(name: str = "file.pdf") -> str:
    return f"{TAU_URL}{PLUGINFILE}123/mod_resource/content/1/{name}"


def test_download_saves_file_inside_download_dir(m, mock, dl_dir):
    path = Path(m.download_file(_url()))
    assert path.read_bytes() == b"%PDF-fake"
    assert path.name == "file.pdf"
    assert path.resolve().parent == dl_dir.resolve()
    assert files_under(dl_dir) == [path]


def test_download_sends_token_only_in_post_body(m, mock):
    m.download_file(_url())
    (request,) = mock.download_requests()
    assert request.method == "POST"
    assert FAKE_TOKEN not in str(request.url)
    assert "token" not in request.url.query.decode().lower()
    assert form(request) == {"token": FAKE_TOKEN}
    assert all(FAKE_TOKEN not in v for v in request.headers.values())
    assert mock.foreign_requests() == []


def test_download_uses_subfolder(m, mock, dl_dir):
    path = Path(m.download_file(_url(), "CS101/Week 1"))
    assert path.resolve().parent == (dl_dir / "CS101" / "Week 1").resolve()
    assert path.is_file()


def test_download_unquotes_name_once_and_ignores_query(m, mock, dl_dir):
    path = Path(m.download_file(_url("My%20File%20%281%29.pdf") + "?forcedownload=1"))
    assert path.name == "My File (1).pdf"
    path = Path(m.download_file(_url("%D7%A9%D7%9C%D7%95%D7%9D.pdf")))
    assert path.name == "שלום.pdf"


def test_download_double_encoded_name_is_decoded_only_once(m, mock):
    path = Path(m.download_file(_url("a%2520b.pdf")))
    assert "%20" in path.name


def test_download_never_overwrites(m, mock, dl_dir):
    counter = iter(range(10))
    mock.download = lambda _r: httpx.Response(200, content=f"version {next(counter)}".encode())
    first = Path(m.download_file(_url()))
    second = Path(m.download_file(_url()))
    third = Path(m.download_file(_url()))
    assert len({first, second, third}) == 3
    assert first.name == "file.pdf"
    assert "(1)" in second.name
    assert "(2)" in third.name
    assert second.name.startswith("file")
    assert first.read_bytes() == b"version 0"
    assert second.read_bytes() == b"version 1"
    assert third.read_bytes() == b"version 2"


def test_download_returns_str(m, mock):
    assert isinstance(m.download_file(_url()), str)


def test_download_colon_in_name_cannot_create_a_stream(m, mock, dl_dir):
    path = Path(m.download_file(_url("G%3Aplanted.txt")))
    assert ":" not in path.name
    assert "planted.txt" in path.name
    assert path.resolve().parent == dl_dir.resolve()
    assert [p.name for p in files_under(dl_dir)] == [path.name]


def test_download_device_name_is_refused_or_renamed(m, mock, dl_dir):
    try:
        path = Path(m.download_file(_url("CON.txt")))
    except ValueError:
        assert files_under(dl_dir) == []
        return
    assert path.stem.upper() != "CON"
    assert path.resolve().parent == dl_dir.resolve()


def test_download_url_without_file_name_is_rejected(m, mock, dl_dir):
    with pytest.raises(ValueError):
        m.download_file(f"{TAU_URL}{PLUGINFILE}123/mod_resource/content/1/")
    assert files_under(dl_dir) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com" + PLUGINFILE + "1/a.pdf",
        f"http://{TAU_HOST}{PLUGINFILE}1/a.pdf",
        f"https://{TAU_HOST}@evil.example.com{PLUGINFILE}1/a.pdf",
        f"https://user@{TAU_HOST}{PLUGINFILE}1/a.pdf",
        f"{TAU_URL}:8443{PLUGINFILE}1/a.pdf",
        f"{TAU_URL}/pluginfile.php/1/a.pdf",
        f"{TAU_URL}{PLUGINFILE}1/%2e%2e/%2e%2e/a.pdf",
        f"{TAU_URL}{PLUGINFILE}1%2fa.pdf",
        f"{TAU_URL}{PLUGINFILE}1/a.pdf#x",
    ],
)
def test_download_rejects_bad_urls_before_any_token_leaves(m, mock, dl_dir, url):
    with pytest.raises(ValueError):
        m.download_file(url)
    assert mock.foreign_requests() == []
    assert mock.download_requests() == []
    assert all(FAKE_TOKEN.encode() not in r.content for r in mock.requests)
    assert files_under(dl_dir) == []


@pytest.mark.parametrize(
    "sub", ["../escape", "a/../../escape", "/abs", "\\abs", "C:\\x", "C:/x", "..", "//srv/share"]
)
def test_download_rejects_subfolder_escapes(m, mock, dl_dir, tmp_path, sub):
    with pytest.raises(ValueError):
        m.download_file(_url(), sub)
    assert mock.download_requests() == []
    assert files_under(dl_dir) == []
    assert not (tmp_path / "escape").exists()


# --- failures ---------------------------------------------------------------------------------


def _no_leak(text: str) -> None:
    assert_no_token(text)
    assert "pluginfile" not in text
    assert "://" not in text


@pytest.mark.parametrize("status", [401, 403, 404, 410, 500, 502, 503])
def test_download_non_2xx_is_moodle_error_without_url(m, mock, dl_dir, status):
    mock.download = lambda _r: httpx.Response(status, text=f"nope token={FAKE_TOKEN}")
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    assert f"Download failed (HTTP {status})" in str(info.value)
    _no_leak(str(info.value))
    assert files_under(dl_dir) == []


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_download_redirects_are_refused_not_followed(m, mock, dl_dir, status):
    mock.download = lambda _r: httpx.Response(
        status, headers={"location": f"https://evil.example.com/steal?token={FAKE_TOKEN}"}
    )
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    assert f"HTTP {status}" in str(info.value)
    _no_leak(str(info.value))
    assert mock.foreign_requests() == []
    assert files_under(dl_dir) == []


def test_download_network_error_is_scrubbed(m, mock, dl_dir):
    leaky = f"{_url()}?token={FAKE_TOKEN}"
    request = httpx.Request("POST", _url())
    for error in (
        httpx.ConnectError(f"failed {leaky}", request=request),
        httpx.ReadTimeout(f"timeout {leaky}", request=request),
    ):
        mock.download = lambda _r, error=error: error
        with pytest.raises(m.MoodleError) as info:
            m.download_file(_url())
        text = f"{info.value} {info.value!r}"
        assert_no_token(text)
    assert files_under(dl_dir) == []


@pytest.mark.parametrize("content_type", ["application/json", "Application/JSON; charset=utf-8"])
@pytest.mark.parametrize(
    "body",
    [
        {"error": "Access control exception", "errorcode": "accessexception"},
        {"exception": "moodle_exception", "errorcode": "accessexception", "message": "denied"},
    ],
    ids=["error-shape", "exception-shape"],
)
def test_download_json_body_is_an_error(m, mock, dl_dir, content_type, body):
    mock.download = lambda _r: httpx.Response(
        200, json=body, headers={"content-type": content_type}
    )
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    assert info.value.errorcode == "accessexception"
    _no_leak(str(info.value))
    assert files_under(dl_dir) == []


def test_download_json_error_with_token_in_message_is_scrubbed(m, mock):
    body = {"error": f"bad token {FAKE_TOKEN} wstoken=ZZZ999888777", "errorcode": "weird"}
    mock.download = lambda _r: httpx.Response(200, json=body)
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    assert FAKE_TOKEN not in str(info.value)
    assert "ZZZ999888777" not in str(info.value)


# --- size cap -------------------------------------------------------------------------------


def test_download_size_cap_with_content_length_leaves_nothing(m, mock, dl_dir, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "1")
    mock.download = lambda _r: httpx.Response(200, content=b"x" * (2 * 1024 * 1024))
    with pytest.raises(m.MoodleError):
        m.download_file(_url())
    assert files_under(dl_dir) == []


def test_download_size_cap_mid_stream_deletes_partial_file(m, mock, dl_dir, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "1")
    produced = []

    def chunks():
        for _ in range(64):  # 4 MiB, no Content-Length header
            produced.append(1)
            yield b"x" * 65536

    mock.download = lambda _r: httpx.Response(200, content=chunks())
    with pytest.raises(m.MoodleError):
        m.download_file(_url())
    assert files_under(dl_dir) == []
    assert len(produced) < 64  # aborted early instead of reading everything


def test_download_under_the_cap_succeeds(m, mock, monkeypatch):
    monkeypatch.setenv("MOODLE_MAX_DOWNLOAD_MB", "1")
    mock.download = lambda _r: httpx.Response(200, content=b"x" * (512 * 1024))
    assert Path(m.download_file(_url())).stat().st_size == 512 * 1024


# --- filesystem safety --------------------------------------------------------------------------


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this OS/account")


def test_download_subfolder_symlink_out_of_the_dir_is_refused(m, mock, dl_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    dl_dir.mkdir()
    _symlink(dl_dir / "link", outside)
    with pytest.raises(ValueError):
        m.download_file(_url(), "link")
    assert files_under(outside) == []


def test_download_does_not_follow_a_symlinked_target_file(m, mock, dl_dir, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    dl_dir.mkdir()
    _symlink(dl_dir / "file.pdf", victim)
    try:
        path = Path(m.download_file(_url()))
    except (ValueError, m.MoodleError, OSError):
        path = None
    assert victim.read_text(encoding="utf-8") == "precious"
    if path is not None:
        assert path.resolve().parent == dl_dir.resolve()
        assert path.read_bytes() == b"%PDF-fake"


def test_download_dir_symlink_inside_subfolder_chain_is_refused(m, mock, dl_dir, tmp_path):
    outside = tmp_path / "outside"
    (outside / "deeper").mkdir(parents=True)
    (dl_dir / "week").mkdir(parents=True)
    _symlink(dl_dir / "week" / "x", outside)
    with pytest.raises(ValueError):
        m.download_file(_url(), "week/x/deeper")
    assert files_under(outside) == []


# --- query-token fallback --------------------------------------------------------------------


def test_query_token_fallback_uses_get_with_query(m, mock, monkeypatch):
    monkeypatch.setenv("MOODLE_DOWNLOAD_TOKEN_IN_QUERY", "1")
    path = Path(m.download_file(_url()))
    assert path.read_bytes() == b"%PDF-fake"
    (request,) = mock.download_requests()
    assert request.method == "GET"
    assert request.url.params["token"] == FAKE_TOKEN
    assert mock.foreign_requests() == []


def test_query_token_fallback_errors_are_still_scrubbed(m, mock, monkeypatch, dl_dir):
    monkeypatch.setenv("MOODLE_DOWNLOAD_TOKEN_IN_QUERY", "1")
    request = httpx.Request("GET", _url())
    mock.download = lambda _r: httpx.ConnectError(
        f"failed {_url()}?token={FAKE_TOKEN}", request=request
    )
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    _no_leak(str(info.value))
    mock.download = lambda _r: httpx.Response(500, text="x")
    with pytest.raises(m.MoodleError) as info:
        m.download_file(_url())
    assert "HTTP 500" in str(info.value)
    _no_leak(str(info.value))
    mock.download = lambda _r: httpx.Response(302, headers={"location": "https://evil.example/"})
    with pytest.raises(m.MoodleError):
        m.download_file(_url())
    assert mock.foreign_requests() == []
    assert files_under(dl_dir) == []


def test_fallback_is_off_by_default(m, mock):
    m.download_file(_url())
    assert mock.download_requests()[0].method == "POST"
