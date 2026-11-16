"""
Pure security primitives for moodle_mcp: no network, no token, no environment, no printing.

URL validation, untrusted-text cleaning and fencing, download URL / file name checks and the
write-function heuristic. moodle_mcp imports from here; this module never imports moodle_mcp.
"""

import ipaddress
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

MAX_ITEMS = 50
MAX_TEXT = 1500
MAX_NAME = 200
MAX_ASSIGN_STATUS_CALLS = 25
MAX_FORUMS = 10
MAX_HTML_CHARS = 200_000  # html_to_text reads at most this much input
MAX_HTML_DEPTH = 200  # and stops at this element nesting depth

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_HOST_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")


class ConfigError(ValueError):
    """Bad URL, site, token format or environment value."""


def _has_bad_chars(s: str) -> bool:
    return any(c.isspace() or unicodedata.category(c) in ("Cc", "Cf") for c in s)


def validate_base_url(url: str) -> str:
    """Normalize a Moodle base URL; raise ConfigError unless it is a clean https URL."""
    if not isinstance(url, str) or not url.strip():
        raise ConfigError("Moodle URL is empty")
    url = url.strip()
    if _has_bad_chars(url) or "\\" in url:
        raise ConfigError("Moodle URL contains whitespace, control characters or backslashes")
    if "?" in url or "#" in url:
        raise ConfigError("Moodle URL must not contain a query (?) or fragment (#)")
    try:  # urlsplit itself raises on e.g. a fullwidth `？` in the host or a broken `[::1`
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        raise ConfigError("Moodle URL could not be parsed") from None
    if "@" in parts.netloc:
        raise ConfigError("Moodle URL must not contain a user name or password")
    try:
        port = parts.port
    except ValueError:
        raise ConfigError("Moodle URL has an invalid port") from None
    if not host:
        raise ConfigError("Moodle URL has no host name")
    if parts.scheme == "http" and host not in LOCAL_HOSTS:
        raise ConfigError("Moodle URL must use https:// (http is allowed only for localhost)")
    if parts.scheme not in ("https", "http"):
        raise ConfigError("Moodle URL must start with https://")
    try:
        is_ip6 = ipaddress.ip_address(host).version == 6
    except ValueError:
        is_ip6 = False
        if not _HOST_RE.fullmatch(host):
            raise ConfigError("Moodle URL has an invalid host name (use the ASCII form)") from None
    netloc = f"[{host}]" if is_ip6 else host
    if port is not None and port != {"https": 443, "http": 80}[parts.scheme]:
        netloc += f":{port}"
    path = parts.path.rstrip("/")
    if any(seg in (".", "..") for seg in path.split("/")):
        raise ConfigError("Moodle URL path must not contain . or .. segments")
    return f"{parts.scheme}://{netloc}{path}"


# Invisible code points that are not Cf: variation selectors (emoji smuggling), the combining
# grapheme joiner and Hangul fillers.
_INVISIBLE = frozenset(
    [*map(chr, range(0xFE00, 0xFE10)), *map(chr, range(0xE0100, 0xE01F0))] + ["͏", "ᅟ", "ᅠ", "ㅤ", "ﾠ"]
)


def clean_text(s, limit: int = MAX_TEXT) -> str:
    """Drop control/format/surrogate/invisible chars (keep \\n, \\t), squeeze blank lines,
    truncate."""
    s = "" if s is None else s if isinstance(s, str) else str(s)
    s = "".join(
        c
        for c in s
        if c in "\n\t"
        or (unicodedata.category(c) not in ("Cc", "Cf", "Cs") and c not in _INVISIBLE)
    )
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:limit] + "…[truncated]" if len(s) > limit else s


class _TooDeep(Exception):
    """Raised inside the parser to stop at MAX_HTML_DEPTH."""


class _VisibleText(HTMLParser):
    """Collects visible text. Linear time: a hidden-depth counter and per-tag open counts."""

    SKIP = frozenset({"script", "style", "template"})
    # fmt: off
    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                      "param", "source", "track", "wbr"})
    # fmt: on
    BREAK = frozenset({"p", "div", "li"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        # (tag, hides its subtree, (href, index in out) for a visible <a href>, else None)
        self.stack: list[tuple[str, bool, tuple[str, int] | None]] = []
        self.hidden_depth = 0  # how many open elements hide their subtree
        self.open_counts: dict[str, int] = {}

    @staticmethod
    def _hides(tag: str, attrs) -> bool:
        if tag in _VisibleText.SKIP or any(k == "hidden" for k, _ in attrs):
            return True
        style = next((v for k, v in attrs if k == "style"), None) or ""  # browsers use the 1st
        if "\\" in style:  # CSS escapes (d\isplay, \6e one) could hide text from a plain match
            return True
        style = re.sub(r"\s+|/\*.*?\*/", "", style.lower())
        return "display:none" in style or "visibility:hidden" in style

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            if tag == "br" and not self.hidden_depth:
                self.out.append("\n")
            return
        if len(self.stack) >= MAX_HTML_DEPTH:
            raise _TooDeep
        hides = self._hides(tag, attrs)
        link = None
        if tag == "a" and not hides and not self.hidden_depth:
            href = (next((v for k, v in attrs if k == "href"), None) or "").strip()
            if (
                len(href) <= 200
                and href.lower().startswith(("http://", "https://"))
                and not _has_bad_chars(href)
            ):
                link = (href, len(self.out))
        self.stack.append((tag, hides, link))
        self.hidden_depth += hides
        self.open_counts[tag] = self.open_counts.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.hidden_depth:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if not self.open_counts.get(tag):  # unmatched end tag: ignore in O(1)
            return
        was_hidden = self.hidden_depth > 0
        while True:  # each element is popped once overall, so this stays linear
            name, hides, link = self.stack.pop()
            self.hidden_depth -= hides
            self.open_counts[name] -= 1
            if link and not self.hidden_depth:
                href, start = link
                if "".join(self.out[start:]).strip() != href:
                    self.out.append(f" ({href})")
            if name == tag:
                break
        if tag in self.BREAK and not was_hidden:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    """Visible text of an HTML fragment; hidden elements, scripts and styles are dropped.

    Reads at most MAX_HTML_CHARS characters and stops at MAX_HTML_DEPTH nested elements.
    """
    parser = _VisibleText()
    try:
        parser.feed(("" if html is None else str(html))[:MAX_HTML_CHARS])
        parser.close()
    except Exception:  # noqa: BLE001, S110 - malformed or too deep: keep what was parsed so far
        pass
    text = re.sub(r" *\n *", "\n", "".join(parser.out))
    return text.strip()


_FENCE_OPEN_RE = re.compile(r"<(\s*untrusted_moodle_content)", re.IGNORECASE)


def untrusted(text, source: str, *, html: bool = False, limit: int = MAX_TEXT) -> str | None:
    """Fence third-party Moodle text so the model treats it as data, not instructions."""
    if text is None:
        return None
    if html:
        text = html_to_text(text)
    text = unicodedata.normalize("NFKC", text if isinstance(text, str) else str(text))
    text = clean_text(text, limit)
    text = re.sub(r"<(\s*)/", r"<\1\\/", text)  # any closing tag, so also the fence's own
    text = _FENCE_OPEN_RE.sub(r"<\\\1", text)  # and a fake opening fence
    return f'<untrusted_moodle_content source="{source}">{text}</untrusted_moodle_content>'


def check_download_url(fileurl: str, base: str) -> str:
    """Allow only <base>/webservice/pluginfile.php/... on exactly the base host and port."""
    if not isinstance(fileurl, str) or _has_bad_chars(fileurl) or "\\" in fileurl:
        raise ValueError("Invalid file URL")
    if "#" in fileurl:
        raise ValueError("File URL must not contain a fragment")
    default = {"https": 443, "http": 80}
    try:
        u, b = urlsplit(fileurl), urlsplit(base)
        same_host = bool(u.hostname) and u.hostname == b.hostname
        same_port = (u.port or default.get(u.scheme)) == (b.port or default.get(b.scheme))
    except ValueError:
        raise ValueError("File URL could not be parsed") from None
    if "@" in u.netloc or u.scheme != b.scheme or not same_host or not same_port:
        raise ValueError("Only file URLs on your Moodle host are allowed")
    if not u.path.startswith(b.path.rstrip("/") + "/webservice/pluginfile.php/"):
        raise ValueError("Only Moodle file URLs (/webservice/pluginfile.php/...) are allowed")
    low = u.path.lower()
    if ";" in u.path or any(e in low for e in ("%2e%2e", "%2f", "%5c", "%252e", "%252f", "%255c")):
        raise ValueError("File URL path must not contain ';' or encoded dots or separators")
    decoded = unquote(u.path)  # decode ONCE, so `.%2e`, `%2E.` ... are seen as `..`
    if (
        any(s in ("..", ".") for s in decoded.split("/"))
        or "\\" in decoded
        or any(unicodedata.category(c) == "Cc" for c in decoded)
    ):
        raise ValueError("File URL path must not contain dot segments or control characters")
    return fileurl


_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{p}{d}" for p in ("COM", "LPT") for d in "123456789¹²³"
}


def safe_filename(name: str) -> str:
    """A file name that is safe on Windows, macOS and Linux (bad chars become '_').

    At most 150 characters and 240 UTF-8 bytes (ext4/APFS allow 255), extension kept.
    """
    if not isinstance(name, str):
        raise ValueError("File name must be text")  # noqa: TRY004
    s = "".join(
        "_" if c in '/\\:*?"<>|' or unicodedata.category(c) in ("Cc", "Cf", "Cs") else c
        for c in name
    )
    s = s.lstrip(". ").rstrip(". ")
    if len(s) > 150 or len(s.encode("utf-8")) > 240:
        dot = s.rfind(".")
        ext = s[dot:] if 0 < dot and len(s) - dot <= 16 else ""
        root = s[: 150 - len(ext)] if len(s) > 150 else s[: len(s) - len(ext)]
        while root and len((root + ext).encode("utf-8")) > 240:
            root = root[:-1]  # character boundary, never a split UTF-8 sequence
        s = (root.rstrip(". ") or "_") + ext
    if s in ("", ".", "..") or s.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES:
        raise ValueError("Unsafe or empty file name")
    return s


def safe_subfolder(subfolder: str) -> str:
    """A relative folder path ('a/b'); no absolute paths, drive letters or '..'."""
    if subfolder is None or subfolder == "":
        return ""
    if not isinstance(subfolder, str):
        raise ValueError("subfolder must be text")  # noqa: TRY004
    if subfolder.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", subfolder):
        raise ValueError("subfolder must be a relative path")
    parts = [p for p in re.split(r"[/\\]", subfolder) if p not in ("", ".")]
    if ".." in parts:
        raise ValueError("subfolder must stay inside the download directory")
    return "/".join(safe_filename(p) for p in parts)


_WRITE_VERBS = re.compile(
    r"(?:^|_)(?:add|create|delete|remove|update|save|submit|send|set|unset|toggle|start|finish|"
    r"mark|block|unblock|lock|unlock|enrol|unenrol|join|leave|trigger|process|upload|edit|new|"
    r"launch|evaluate|approve|revert|reveal|insert|agree|confirm|decline|mute|unmute|enable|"
    r"end|login|copy|post|override|reset|import)(?:_|$)"
)
# fmt: off
HIGH_RISK = frozenset({
    "tool_mobile_call_external_functions", "tool_mobile_get_autologin_key",
    "core_user_add_user_device", "mod_wiki_get_page_for_editing",
    "mod_bigbluebuttonbn_get_join_url", "tool_mobile_validate_subscription_key",
    "core_message_message_processor_config_form",
    # writes in Moodle's mobile service that the verb regex misses
    "core_competency_grade_competency_in_course", "mod_bigbluebuttonbn_completion_validate",
    "mod_forum_prepare_draft_area_for_post", "report_insights_action_executed",
    "tool_dataprivacy_cancel_data_request", "tool_dataprivacy_contact_dpo",
})
# fmt: on


def is_write_function(name: str) -> bool:
    """Heuristic: does this web service function change data in Moodle?

    Names are <component>_<method> (core_enrol_get_users_courses); verbs are only looked for
    in the method part, so a component like core_enrol or core_block is not a write. Case is
    ignored (Moodle's database resolves function names case-insensitively).
    """
    if not isinstance(name, str):
        return False
    name = name.lower()
    method = name.split("_", 2)[2] if name.count("_") >= 2 else name
    return name in HIGH_RISK or bool(_WRITE_VERBS.search(method))
