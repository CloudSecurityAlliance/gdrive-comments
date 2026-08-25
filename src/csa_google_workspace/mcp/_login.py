"""The `login` subcommand — the only code path permitted to run interactive consent.

Isolated in its own module on purpose. The server imports `_config`, never this, so
`InstalledAppFlow` is not reachable from the stdio process even by mistake: it is not in
the call graph. `run_local_server()` prints the consent URL with a bare `print()` and
blocks on the browser redirect — harmless in a terminal, fatal under stdio where stdout
carries JSON-RPC.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping

from ..auth import load_cached_credentials
from ..exceptions import AuthError
from ..workspace import Workspace
from ._config import Settings


def _client_id_of(path: str) -> str | None:
    """The client_id from a client-secrets file, or None if unreadable."""
    try:
        with open(os.path.expanduser(path)) as f:
            d = json.load(f)
        return (d.get("installed") or d.get("web") or {}).get("client_id") or None
    except (OSError, ValueError):
        return None


def _token_client_id(token_path: str) -> str | None:
    try:
        with open(os.path.expanduser(token_path)) as f:
            return json.load(f).get("client_id") or None
    except (OSError, ValueError):
        return None


def login(settings: Settings, env: Mapping[str, str], *, force: bool = False, out=None) -> int:
    """Run interactive OAuth and cache the token. Returns a process exit code."""
    out = out or sys.stdout
    client_secrets = env.get("CSA_GW_CLIENT_SECRETS")
    if not client_secrets:
        print("CSA_GW_CLIENT_SECRETS is not set — point it at your OAuth client secrets JSON",
              file=sys.stderr)
        return 2

    if not force:
        try:
            load_cached_credentials(settings.token_path, settings.read_only)
        except AuthError:
            pass                                  # nothing usable cached — consent below
        else:
            # A cached token can be valid, carry exactly the right scopes, and still have
            # been issued by a *different* OAuth client. Everything then works while
            # running against the wrong project's quota and consent screen — silently.
            # Worth naming, because no error will ever surface it.
            want, have = _client_id_of(client_secrets), _token_client_id(settings.token_path)
            if want and have and want != have:
                print(f"Warning: the cached token was issued by a different OAuth client\n"
                      f"  cached: {have}\n  wanted: {want}\n"
                      f"Re-authorize with `csa-google-workspace-mcp login --force` to use the "
                      f"intended client.", file=sys.stderr)
            print(f"Already authorized (token cache: {settings.token_path}).\n"
                  f"Use `login --force` to authorize again.", file=out)
            return 0

    print(f"Opening a browser to authorize access to your Google Workspace files.\n"
          f"  token cache: {settings.token_path}", file=out)
    # force=True bypasses the cache but deletes nothing: the old token is replaced only
    # once a new one exists, so a cancelled consent leaves the previous one working.
    Workspace.from_oauth(client_secrets, settings.token_path,
                         read_only=settings.read_only, force=force)
    print("Authorized. The MCP server can now start without prompting.", file=out)
    return 0
