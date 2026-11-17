"""Get a Moodle key without the "Reset" button: `python moodle_mcp.py --login`.

Two ways in, picked per institution:
  browser   Opens a Chrome/Edge window at Moodle's app-login page. You log in as usual
            (university SSO, codes and all) and the key comes straight back from Moodle.
            Used where Moodle sends its own phone app to a browser login (TAU, Technion...).
            Needs: pip install playwright
  password  Asks for your Moodle username and password in this terminal (hidden, never
            stored) and exchanges them for the key. Used where the phone app logs in that way.

Both return your existing key if you already have one, so the Moodle app on your phone
stays logged in. The key is written to the token file and never printed.
"""

import base64
import getpass
import hashlib
import logging
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

SERVICE = "moodle_mobile_app"
logging.getLogger("httpx").setLevel(logging.WARNING)  # keep request URLs out of the terminal
_http = httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0 (moodle-mcp login)"})


def public_config(base: str) -> dict:
    body = [{"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}]
    try:
        res = _http.post(f"{base}/lib/ajax/service.php?info=tool_mobile_get_public_config", json=body).json()[0]
        return res.get("data") or {}
    except Exception:
        return {}


def launch_url(wwwroot: str, passport: str) -> str:
    return (f"{wwwroot}/admin/tool/mobile/launch.php?service={SERVICE}"
            f"&passport={passport}&urlscheme=moodlemobile")


def choose_method(base: str) -> tuple[str, str]:
    """Return (method, wwwroot). Browser if Moodle's app-login page accepts us, else password."""
    wwwroot = (public_config(base).get("wwwroot") or base).rstrip("/")
    try:
        r = _http.get(launch_url(wwwroot, "check"), follow_redirects=False)
        if r.status_code in (301, 302, 303):
            return "browser", wwwroot
    except Exception:
        pass
    return "password", wwwroot


def _browser_token(wwwroot: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Your institution logs in through a browser. Install the helper first:\n"
                 "    .venv/bin/pip install playwright\n"
                 "then run --login again.")

    passport = secrets.token_hex(8)
    found: dict[str, str] = {}

    def grab(u):
        if u and "://token=" in u and "u" not in found:
            found["u"] = u

    with sync_playwright() as p:
        browser = None
        for channel in ("chrome", "msedge", None):
            try:
                browser = p.chromium.launch(channel=channel, headless=False) if channel \
                    else p.chromium.launch(headless=False)
                break
            except Exception:
                continue
        if browser is None:
            sys.exit("Couldn't open Chrome or Edge. Install one of them, or use the manual token (see README).")
        ctx = browser.new_context()
        ctx.on("request", lambda r: grab(r.url))
        ctx.on("response", lambda r: grab(r.headers.get("location")))
        page = ctx.new_page()
        print("A browser window opened. Log in to Moodle there as you normally do.")
        print("If it asks to open an app, cancel. Waiting up to 10 minutes...")
        try:
            page.goto(launch_url(wwwroot, passport))
        except Exception:
            pass  # the final redirect to moodlemobile:// aborts navigation; that's expected
        deadline = time.time() + 600
        while "u" not in found and time.time() < deadline and ctx.pages:
            try:
                pg = ctx.pages[-1]
                grab(pg.evaluate("() => { const a = document.querySelector('a[href*=\"://token=\"]');"
                                 " return a && a.href; }"))
                pg.wait_for_timeout(1000)
            except Exception:
                time.sleep(1)
        browser.close()

    if "u" not in found:
        sys.exit("No key came back (window closed or timed out). Run --login again, or use the manual token.")
    payload = unquote(found["u"].split("token=", 1)[1]).strip()
    parts = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode().split(":::")
    if parts[0] != hashlib.md5((wwwroot + passport).encode()).hexdigest() or len(parts) < 2:
        sys.exit("The key didn't pass Moodle's signature check. Not saved.")
    return parts[1]


def _password_token(wwwroot: str) -> str:
    print(f"Log in to {wwwroot}")
    print("(Your password is sent only to this Moodle and is never saved.)")
    username = input("Moodle username: ").strip()
    password = getpass.getpass("Moodle password (hidden): ")
    res = _http.post(f"{wwwroot}/login/token.php",
                     data={"username": username, "password": password, "service": SERVICE}).json()
    if "token" in res:
        return res["token"]
    code = res.get("errorcode") or res.get("error")
    if code == "invalidlogin":
        sys.exit("Wrong username or password. If you normally log in with a university/Microsoft button, "
                 "this Moodle may not accept passwords here; use the manual token (see README).")
    sys.exit(f"Moodle refused the login ({code}). Use the manual token instead (see README).")


def login(base: str, token_file: Path, method: str | None = None) -> None:
    chosen, wwwroot = choose_method(base)
    method = method or chosen
    print(f"Moodle: {wwwroot}  |  login method: {method}")
    tok = _browser_token(wwwroot) if method == "browser" else _password_token(wwwroot)

    info = _http.post(f"{wwwroot}/webservice/rest/server.php",
                      data={"wstoken": tok, "wsfunction": "core_webservice_get_site_info",
                            "moodlewsrestformat": "json"}).json()
    if "userid" not in info:
        sys.exit(f"Got a key, but Moodle won't accept it for web services ({info.get('errorcode')}). "
                 "Your institution may not allow this; not saved.")

    token_file = Path(token_file)
    if token_file.exists() and token_file.read_text().strip() == tok:
        print("✓ Works. Same key you already had, nothing changed.")
        return
    token_file.write_text(tok)
    try:
        token_file.chmod(0o600)
    except OSError:
        pass
    print(f"✓ Logged in to {info.get('sitename')}. Key saved to {token_file}")
