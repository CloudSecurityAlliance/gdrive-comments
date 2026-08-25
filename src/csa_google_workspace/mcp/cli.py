"""Console-script entry point: one command, two modes.

    csa-google-workspace-mcp            # run the stdio server (never prompts)
    csa-google-workspace-mcp login      # interactive consent, in a real terminal

Deliberately hand-rolled argument handling rather than an argparse subparser tree: there is
exactly one verb, and the parsing must not be the interesting part of this file.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

from ._config import WorkspaceProvider, settings_from_env
from .server import create_server

USAGE = """usage: csa-google-workspace-mcp [login [--force]]

  (no argument)   run the MCP server over stdio, for an MCP client to launch
  login           authorize with Google in a browser and cache the token
  login --force   authorize again even if a cached token looks usable

Clients that support MCP URL elicitation (Claude Code) can authorize in-session via
the `authenticate` tool instead, with no terminal step.

environment:
  CSA_GW_TOKEN           token cache path (default ~/.csa_google_workspace/token.json)
  CSA_GW_READ_ONLY=1     refuse writes
  CSA_GW_CLIENT_SECRETS  OAuth client secrets JSON (`login` only; defaults to
                         ~/.csa_google_workspace/client_secret.json if that exists)
"""


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    settings = settings_from_env(env)

    if argv and argv[0] in ("-h", "--help", "help"):
        print(USAGE, file=sys.stderr)      # stderr: stdout belongs to JSON-RPC
        return 0
    if argv and argv[0] == "login":
        from ._login import login  # imported here so the server path never loads it
        rest = argv[1:]
        force = bool(rest) and rest[0] in ("--force", "-f", "--reauth")
        if rest and not force:
            print(f"unknown argument: {rest[0]}\n\n{USAGE}", file=sys.stderr)
            return 2
        return login(settings, env, force=force)
    if argv:
        print(f"unknown argument: {argv[0]}\n\n{USAGE}", file=sys.stderr)
        return 2

    # The server never resolves credentials here: a missing token must not stop the server
    # from starting, or the MCP client reports an opaque "server failed to start" and the
    # user never sees the remedy. Tools surface it instead, where it is readable.
    create_server(WorkspaceProvider(settings), settings=settings).run(transport="stdio")
    return 0
