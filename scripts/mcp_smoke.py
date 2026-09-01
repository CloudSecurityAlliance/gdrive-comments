#!/usr/bin/env python3
"""Start the installed MCP server over stdio and prove a client can talk to it.

**RR-004.** Every install in this repository's CI is hash-pinned, which is the right default and
leaves one gap: the `[mcp]` extra — the optional dependency that *is* the server — is never
resolved the way a user resolves it. `mcp = ["mcp>=2.1", ...]` is a range, so a future SDK release
inside that range could break the shipped server while the pinned suite stays green.

This script is what closes that. It deliberately depends on **nothing from this repository**: no
pytest, no fixtures, no `src/` on the path. It imports the package the way a user's client would,
from wherever `pip install .[mcp]` put it, so running it in a clean environment tests the published
artifact rather than the working tree.

    python scripts/mcp_smoke.py            # against whatever is installed
    python scripts/mcp_smoke.py --verbose  # print each response

Exits non-zero with a readable reason on the first failure, so CI needs no wrapper.

## Why the handshake looks like this

Four attempts were needed to get the modern one right, and none of it is guessable from the Python
API:

* `server/discover` before `initialize` is `Method not found`.
* `initialize` with `params.protocolVersion: "2026-07-28"` negotiates **down** to `2025-11-25` —
  that field is the *legacy* channel, and `server/discover` is then gated off as unreachable.
* The modern handshake carries the version in `params._meta` under
  `io.modelcontextprotocol/protocolVersion`, and the envelope **also requires**
  `io.modelcontextprotocol/clientCapabilities`; omitting it is `-32602`, not a default.

`tests/test_mcp_wire_protocol.py` asserts the same things against the working tree. This runs
against an install. Both exist because they answer different questions.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
MODERN = "2026-07-28"
LEGACY = "2025-11-25"


def speak(requests: list[dict], *, timeout: int = 90) -> tuple[list[dict], str, str]:
    """Send JSON-RPC to a fresh server subprocess and parse stdout as a client would."""
    env = dict(os.environ)
    env.update({
        "CSA_GW_ALLOWLIST_READ": "*",
        # Cannot exist: this must never touch a real cached token, and the server starts
        # without one by design.
        "CSA_GW_TOKEN": "/nonexistent/csa-gw-smoke/token.json",
    })
    # No PYTHONPATH manipulation: the point is to run what is INSTALLED.
    env.pop("PYTHONPATH", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "csa_google_workspace.mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env)
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    try:
        out, err = proc.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        fail("the server did not answer over stdio within "
             f"{timeout}s. Is `pip install .[mcp]` complete?")
    messages = []
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            fail(f"stdout carried a non-protocol line, which corrupts the JSON-RPC channel "
                 f"under stdio: {line[:160]!r}")
    return messages, out, err


def fail(reason: str) -> None:
    print(f"FAIL: {reason}", file=sys.stderr)
    raise SystemExit(1)


def check(condition: object, label: str, detail: str = "") -> None:
    if condition:
        print(f"  ok    {label}")
        return
    fail(f"{label}{': ' + detail if detail else ''}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", action="store_true", help="print each response")
    args = parser.parse_args()

    try:
        from csa_google_workspace import __version__
    except ImportError as exc:                     # pragma: no cover - that IS the failure
        fail(f"the package is not importable: {exc}")
    print(f"smoke-testing the installed csa-google-workspace {__version__}")

    # ── the modern discovery handshake
    discover = {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                "params": {"_meta": {PROTOCOL_VERSION_KEY: MODERN,
                                     CLIENT_CAPABILITIES_KEY: {}}}}
    messages, _out, err = speak([discover])
    if args.verbose:
        print(json.dumps(messages, indent=2)[:2000])
    check(messages, "server/discover produced a response", "nothing arrived on stdout")
    result = messages[0].get("result")
    check(result is not None, "server/discover succeeded", str(messages[0].get("error")))
    check(result.get("resultType") == "complete",
          "resultType is complete", str(result.get("resultType")))
    check(result.get("supportedVersions") == [MODERN],
          f"advertises {MODERN}", str(result.get("supportedVersions")))
    info = (result.get("_meta") or {}).get(SERVER_INFO_KEY) or {}
    check(info.get("version") == __version__,
          "serverInfo.version matches the package", f"wire said {info.get('version')!r}")

    # ── the legacy path, which is what most clients still use
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": LEGACY, "capabilities": {},
                             "clientInfo": {"name": "smoke", "version": "0"}}}
    messages, _out, err = speak([
        initialize,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    first = next((m for m in messages if m.get("id") == 1), None)
    check(first and first.get("result"), "legacy initialize succeeded")
    check(first["result"].get("protocolVersion") == LEGACY,
          f"negotiates {LEGACY}", str(first["result"].get("protocolVersion")))
    check(first["result"].get("serverInfo", {}).get("version") == __version__,
          "serverInfo.version on the legacy path too")

    listed = next((m for m in messages if m.get("id") == 2), None)
    check(listed and listed.get("result"), "tools/list succeeded",
          str(listed.get("error") if listed else "no response"))
    tools = listed["result"]["tools"]
    check(len(tools) > 40, f"{len(tools)} tools registered", "far fewer than expected")
    names = {t["name"] for t in tools}
    for expected in ("list_comments", "read_file_content", "describe_configuration"):
        check(expected in names, f"`{expected}` is present")
    missing_schema = [t["name"] for t in tools if "inputSchema" not in t]
    check(not missing_schema, "every tool carries inputSchema on the wire",
          f"missing on {missing_schema[:5]}")

    check(err.strip(), "the server logs to stderr", "nothing on stderr at all")

    print("\nall smoke checks passed against the installed package.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
