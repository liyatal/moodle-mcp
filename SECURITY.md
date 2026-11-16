# Security

`moodle-mcp` is a local, read-only [MCP](https://modelcontextprotocol.io) server that lets an AI assistant read a student's Moodle. This file states what it defends, how well, and where it stops.

## Threat model

**Assets**

- The Moodle web service token (a bearer secret).
- The student's data: courses, grades, deadlines, forum posts, files.

**Adversaries considered**

| Adversary | Typical attack |
| --- | --- |
| A forum, course or file author on Moodle | Text written to steer the assistant (prompt injection), hidden text, odd file names |
| A hostile `MOODLE_URL`, or a stale or hijacked institution host | Collect the token, or serve malicious files |
| Someone who can read local logs or config | Find the token in logs, error text or config files |
| A poisoned README or AI-install channel | Trick an installing assistant into running attacker-chosen steps |

## The most important fact: the token is not read-only

The token is the Moodle mobile web service token. It carries whatever the Moodle phone app can do: post to forums, submit assignments, send messages, start quiz attempts. Anyone who holds it can do those things.

"Read-only" in this project is enforced **in this code**: every call goes through `call()`, which accepts only functions from a fixed allowlist (`READ_FUNCTIONS`) and raises before any HTTP request otherwise. It is not enforced by Moodle and not by the token.

`python moodle_mcp.py --doctor` lists the write-capable functions your token grants, as a warning.

## Mitigations and their honest limits

| Mitigation | What it does | Limit |
| --- | --- | --- |
| Function allowlist | Only listed read functions can be called; request parameters cannot override the function name or token | Protects against this server being misused, not against someone with the token using Moodle directly |
| https-only URL validation | Rejects `http://` (except localhost), credentials in the URL, queries, fragments, odd characters | A valid https URL to the wrong host is still valid; you must check the host (`--sites`, `--doctor`) |
| Preflight identity check | Before the first token use, asks the site (no token) for its public config and requires its reported address to match the configured host | Weak against a determined impostor, who can fake that response. It catches stale hosts and honest mistakes, not a hostile server |
| Token in the POST body | Token never appears in a URL, so it doesn't land in logs or error text | Downloads rely on Moodle accepting the token in the body (checked in Moodle's source, not yet verified live). `MOODLE_DOWNLOAD_TOKEN_IN_QUERY=1` is a fallback and puts the token in the URL |
| Scrubbing and quiet logging | Token patterns are removed from error messages; HTTP client logging is silenced | Best effort; a new code path could leak, which is why tests cover it |
| Untrusted-content wrapping | Moodle text is fenced in `<untrusted_moodle_content>` tags, NFKC-normalised, stripped of control, zero-width, bidi and other invisible characters, and length-limited; fake fence tags inside it are neutralised. Forum HTML is stripped, links are kept as `text (url)`, hidden elements and scripts are dropped. The server tells the assistant that this text is data, not instructions | **Mitigation, not a fix.** The assistant may still be influenced. Prompt injection is reduced, not eliminated. Known gap: misnested HTML end tags inside a hidden element can still leak hidden text (it stays inside the fence) |
| Download hardening | Only the configured host and path prefix, no redirects, safe file names (capped at 240 UTF-8 bytes), `;` and double-encoded dots in the path refused, no overwrite, no escape from the download folder, size cap (`MOODLE_MAX_DOWNLOAD_MB`), 120 s deadline. JSON files can be downloaded; a Moodle error reply is told apart from a genuine `.json` file | Downloaded files are untrusted content; the server does not scan them |
| Response size caps | REST replies are capped at 10 MiB, the identity preflight at 64 KiB | Limits memory abuse by a hostile host, nothing more |
| Token-less public config | The public-config call (`tool_mobile_get_public_config`) never sends the token | Only protects that one call |
| Result limits | Caps on items, text length and number of calls per tool. A capped list ends with `{"truncated": "<shown> of <total> <what> shown"}`; ask for a narrower query (e.g. one course) | Limits blast radius, not intent |
| Worker threads | Tools run in worker threads, so a slow Moodle or download cannot freeze the server | Availability only |

## Code layout

The pure checks (URL validation, text cleaning and fencing, download URL and file name checks, `is_write_function`) live in `moodle_safety.py`, which has no network, token or environment access. `moodle_mcp.py` imports and re-exports them. Installing clones the whole repository, so users notice nothing.

Tests: about 1000 offline tests (`pytest`), including a red-team file of attack cases; lint with `ruff check .`.

CLI notes: an unknown argument exits with code 2 and a usage line. `MOODLE_SKIP_PREFLIGHT=1` disables the identity check and prints a one-time warning on stderr (`--doctor` also warns).

## Token storage

The token is stored as **plaintext** (the `.token` file, or an environment variable). That is normal for local MCP servers but means anyone with access to your user account can read it.

- Windows: `icacls .token /inheritance:r /grant:r "${env:USERNAME}:(R,W)"` restricts the file to your user.
- macOS/Linux: `chmod 600 .token`. The server warns if the file is group- or world-accessible.
- Prefer the file over `MOODLE_TOKEN` in a client config, which stores it in plaintext there too.
- Never paste the token into a chat.

**If the token may be exposed:** in Moodle, Preferences, Security keys, click **Reset** on *Moodle mobile web service*. The old key stops working immediately.

## Not in scope

- A compromised machine, or anyone already running code as you.
- A compromised or malicious Moodle server (it can lie about anything it returns).
- Moodle's own vulnerabilities, or your institution's token policy.
- Vulnerabilities in the assistant, its client, or the MCP SDK, beyond how this server uses them.
- Guarantees for institutions other than Tel Aviv University: only TAU has been tested end to end with a real token.

## Reporting a vulnerability

Please do not open a public issue. Open a **private security advisory** on the upstream GitHub repository (the Security tab, "Report a vulnerability"). Include what you did, what you expected, what happened, and the version or commit. Never include a real token.

## Yearly maintenance checklist

Some institutions embed the academic year in the hostname (`moodle26`, `moodle27`), and an abandoned name is a takeover risk.

- [ ] Update year-named hosts in `SITES` in `moodle_mcp.py`.
- [ ] Run `python scripts/check_sites.py` and fix or remove dead hosts.
- [ ] Keep the institution count and lists in `README.md` in sync with `SITES`.
- [ ] Update dependencies (`mcp`, `httpx`) and run `pytest` and `ruff check .`.
