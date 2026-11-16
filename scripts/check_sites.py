"""Token-less health check of the SITES table.

For every institution in `moodle_mcp.SITES` this asks the public, unauthenticated
`tool_mobile_get_public_config` endpoint and checks that the site still answers as the host we
list (the same identity check the server performs before it ever sends your token).

    python scripts/check_sites.py            # one line per site, exit 1 on any MISMATCH
    python scripts/check_sites.py --fail-on-error   # also exit 1 when a site is unreachable

No token is read or sent. Nothing runs at import time.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CONFIG_PATH = "/lib/ajax/service-nologin.php?info=tool_mobile_get_public_config"
PUBLIC_CONFIG_BODY = [{"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}]

OK, MISMATCH, ERROR = "OK", "MISMATCH", "ERROR"


def _host(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        return (urlsplit(url).hostname or "").lower() or None
    except ValueError:
        return None


def check_site(client: httpx.Client, base: str) -> tuple[str, str]:
    """Return (status, detail) for one base URL; never raises for network/HTTP problems."""
    expected = _host(base)
    try:
        response = client.post(base + PUBLIC_CONFIG_PATH, json=PUBLIC_CONFIG_BODY)
    except httpx.HTTPError as exc:
        return ERROR, type(exc).__name__
    if response.status_code != 200:
        return ERROR, f"HTTP {response.status_code}"
    try:
        data = response.json()[0]["data"]
        roots = [data.get("wwwroot"), data.get("httpswwwroot")]
    except (ValueError, LookupError, TypeError, AttributeError):
        return ERROR, "not a Moodle public-config response"
    hosts = {h for h in map(_host, roots) if h}
    if not hosts:
        return ERROR, "no wwwroot in response"
    if expected in hosts:
        return OK, ", ".join(sorted(hosts))
    return MISMATCH, f"site says {', '.join(sorted(hosts))}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request")
    parser.add_argument("--workers", type=int, default=8, help="parallel requests")
    parser.add_argument(
        "--fail-on-error", action="store_true", help="exit 1 on unreachable sites too"
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from moodle_mcp import SITES  # imported lazily so `--help` and tests stay cheap

    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            results = list(pool.map(lambda item: check_site(client, item[1][1]), SITES.items()))

    counts = {OK: 0, MISMATCH: 0, ERROR: 0}
    for (key, (_name, base)), (status, detail) in zip(SITES.items(), results, strict=True):
        counts[status] += 1
        print(f"{status:9} {key:11} {base}  {detail}")
    print(
        f"checked {len(results)} sites: {counts[OK]} ok, {counts[MISMATCH]} mismatch, "
        f"{counts[ERROR]} error"
    )

    if counts[MISMATCH] or (args.fail_on_error and counts[ERROR]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
