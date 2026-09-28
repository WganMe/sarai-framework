#!/usr/bin/env python3
"""
Wait until the federation engine is ready to answer queries.

`/v1/info` returns HTTP 200 as soon as the HTTP server is up, but the body then
carries `"starting": true` while the coordinator is still initialising. A check
that only looks at the status code therefore passes too early, and subsequent
queries get an empty or non-JSON response -- which surfaces far away as
`json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`.

This waits for `"starting": false`, which is the condition that actually means
the engine will answer.

    python3 tools/wait_for_engine.py                    # localhost:8080, 300 s
    FEDERATION_URL=http://host:8080 python3 tools/wait_for_engine.py

Exit 0 when ready, exit 1 on timeout (printing the last response seen).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("FEDERATION_URL", "http://127.0.0.1:8080")
TIMEOUT = int(os.environ.get("ENGINE_WAIT_TIMEOUT", 300))
INTERVAL = 5


def probe():
    """Return (ready, description)."""
    try:
        with urllib.request.urlopen(f"{URL}/v1/info", timeout=10) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    try:
        info = json.loads(raw)
    except ValueError:
        # Not JSON yet: the server is up but not serving its API.
        return False, f"non-JSON body ({len(raw)} bytes)"

    if info.get("starting", True):
        return False, f"starting (uptime {info.get('uptime', '?')})"
    return True, (f"ready: engine {info.get('nodeVersion', {}).get('version', '?')}, "
                  f"environment {info.get('environment', '?')}")


def main():
    print(f"waiting for the engine at {URL} (up to {TIMEOUT}s)")
    deadline = time.time() + TIMEOUT
    last = "no response"
    while time.time() < deadline:
        ready, desc = probe()
        if ready:
            print(f"  {desc}")
            return 0
        last = desc
        print(f"  not ready: {last}")
        time.sleep(INTERVAL)
    print(f"  timed out after {TIMEOUT}s; last response: {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
