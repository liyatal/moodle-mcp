# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only [MCP](https://modelcontextprotocol.io) server (stdio, `FastMCP`) that exposes a student's Moodle (courses, deadlines, assignments, grades, forums, file download) to Claude. Defaults to Tel Aviv University; ships presets for 37 Israeli institutions. Deps: `mcp[cli]` and `httpx` only (`requirements.txt`); dev tools in `requirements-dev.txt` (pytest, pytest-cov, ruff). Python 3.10+.

Layout (flat, no package; `claude mcp add ... python moodle_mcp.py` must keep working):
- `moodle_mcp.py` — config, `scrub`, HTTP (`_client`, `call`, identity preflight), the 7 tools, `download_file`, `--doctor`, `main`.
- `moodle_safety.py` — pure helpers (no network, token, env or printing): `validate_base_url`, `check_download_url`, `safe_filename`/`safe_subfolder`, `clean_text`/`html_to_text`/`untrusted`, `is_write_function`, limits. Never imports `moodle_mcp`. Everything in it is re-exported from `moodle_mcp` (`__all__`), so `import moodle_mcp as m; m.safe_filename` is the public API and the tests rely on it.
- `tests/` offline suite (~1000 tests), `scripts/check_sites.py` token-less host check, `.github/workflows/ci.yml`.
- Docs: `README.md` (Hebrew first, English below; also holds the "Instructions for Claude" auto-install flow), `SECURITY.md` (threat model). Update README in both languages when you change setup, env vars, tools or the institution list (count must match `SITES`).

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/...
.venv/Scripts/python -m pytest -q                                  # whole suite, no network, no real token
.venv/Scripts/python -m pytest tests/test_download.py -k json -q   # a single test / subset
.venv/Scripts/python -m pytest --cov=moodle_mcp --cov=moodle_safety --cov-branch
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
.venv/Scripts/python moodle_mcp.py --sites      # institution table (needs no token)
.venv/Scripts/python moodle_mcp.py --doctor     # setup check; prints no personal data
.venv/Scripts/python scripts/check_sites.py     # yearly host check (real network, no token)
```

Config is env-only: `MOODLE_SITE` (default `tau`), `MOODLE_URL`, `MOODLE_TOKEN`, `MOODLE_TOKEN_FILE` (default `.token` next to the script), `MOODLE_DOWNLOAD_DIR`, `MOODLE_MAX_DOWNLOAD_MB` (100), `MOODLE_SKIP_PREFLIGHT=1`, `MOODLE_DOWNLOAD_TOKEN_IN_QUERY=1` (fallback only). Importing the module never exits, prints or touches the network; invalid config raises `ConfigError` lazily (`get_base()`, `token()`) and `main()` returns 2.

## Invariants — don't break these (all are pinned by tests)

- **Read-only by code.** `call()` accepts only `READ_FUNCTIONS` (checked before any HTTP, exact `str` type, params can't override `wstoken`/`wsfunction`). The token itself is NOT read-only; never claim it is. Never add write tools; never add `*_view_*` functions (they log "viewed" events).
- **Token never leaves the configured https host and never appears in text.** REST and downloads send it in the POST body; `tool_mobile_get_public_config` is sent token-less. Every error shown to the model goes through `scrub` (scrub *before* truncating); errors never include URLs; httpx/httpcore loggers are forced to WARNING (their INFO logs print URLs). Redirects are never followed. Don't read `.token`, don't print the token, don't ask the user to paste it in chat.
- **Identity preflight** (`ensure_site_identity`) runs once per base before the first token use; response sizes are capped (REST 10 MiB, preflight 64 KiB).
- **Third-party text is untrusted.** Every Moodle-authored string a tool returns goes through `untrusted(...)` (fence `<untrusted_moodle_content source="...">`, HTML stripped, control/zero-width/bidi chars removed, NFKC, fence tags neutralised) or is type-checked/cleaned. Lists are capped (`MAX_ITEMS`); a cut list ends with a `{"truncated": "N of M shown"}` dict.
- **Downloads:** only `<base>/webservice/pluginfile.php/...` on the exact host+port, safe file names, no overwrite, exclusive create, size cap + deadline, final path re-checked inside the download dir, errors never include the URL. The POST-body token for downloads is verified in Moodle's source only, not yet against a live site (user checks with `--doctor`/a real download).
- `stdout` is the MCP channel: only `--sites`/`--doctor` print to it; diagnostics go to stderr.

## Adding a tool

Add its Moodle function to `READ_FUNCTIONS`; wrap/clean every returned third-party string; validate arguments (`_int_arg`); cap lists and append the truncation marker; register it like the existing tools (plain sync function, exposed to FastMCP as a threaded async wrapper); add mock tests; add a README tool-table row (Hebrew + English). Keep `moodle_mcp.py` readable: if it keeps growing, move more pure code to `moodle_safety.py` or split the HTTP core from the tools (keep the `import moodle_mcp as m` API intact).

## Testing seams

Tests swap `moodle_mcp._client` for `httpx.Client(transport=httpx.MockTransport(...))` and reset `_userid`, `_preflight_ok`, `_announced`, `_perm_warned` (autouse fixture in `tests/conftest.py`; Moodle mock helper in `tests/support.py`). Fake token: `a1b2c3d4e5f60718293a4b5c6d7e8f90`. `tests/test_redteam.py` pins attacks found by an adversarial review (one documented strict xfail: misnested end tags inside hidden HTML). Live tests are marked `live` and skipped unless `MOODLE_LIVE=1`.

## Repo notes

- `origin` is the upstream `raztassa2000-eng/moodle-mcp` (default branch `main`); the owner of this checkout has no push access. Work happens on local branches (currently `hardening/security-and-tests`); commits use the repo-local GitHub noreply email. Don't push.
- `demo/` is README media only. Only TAU has been verified end to end with a real token.
