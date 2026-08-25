"""The `login` subcommand — the only code path permitted to run interactive consent.

Isolated in its own module on purpose. The server imports `_config`, never this, so
`InstalledAppFlow` is not reachable from the stdio process even by mistake: it is not in
the call graph. `run_local_server()` prints the consent URL with a bare `print()` and
blocks on the browser redirect — harmless in a terminal, fatal under stdio where stdout
carries JSON-RPC.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping

from ..workspace import Workspace
from ._config import Settings


def login(settings: Settings, env: Mapping[str, str], *, out=None) -> int:
    """Run interactive OAuth and cache the token. Returns a process exit code."""
    out = out or sys.stdout
    client_secrets = env.get("CSA_GW_CLIENT_SECRETS")
    if not client_secrets:
        print("CSA_GW_CLIENT_SECRETS is not set — point it at your OAuth client secrets JSON",
              file=sys.stderr)
        return 2
    # Deliberately does not echo the client-secrets path. It is only a path, not the
    # credential — but printing anything derived from a variable named `*secret*` is a trap
    # worth not setting: if that value ever became the file's *contents*, this line would
    # leak for real. CodeQL flags it (py/clear-text-logging-sensitive-data) and, while the
    # literal finding is a false positive, the shape it objects to is one we can simply not have.
    print(f"Opening a browser to authorize access to your Google Workspace files.\n"
          f"  token cache: {settings.token_path}", file=out)
    Workspace.from_oauth(client_secrets, settings.token_path, read_only=settings.read_only)
    print("Authorized. The MCP server can now start without prompting.", file=out)
    return 0
