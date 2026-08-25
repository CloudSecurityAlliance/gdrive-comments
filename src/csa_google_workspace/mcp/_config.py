"""Environment -> Settings -> Workspace, for the MCP server.

Deliberately free of any `mcp` SDK import, so it is testable without the optional extra.

Two design points worth stating, because both are easy to "fix" into bugs:

* **Nothing resolves eagerly.** Credentials are looked up on first use, not at startup.
  An MCP client reports a startup crash as an opaque "server failed to start", so a
  fail-fast here is a *silent* failure; deferring makes it a tool error the user reads
  in chat, with the remedy in it.
* **One `Workspace` per thread.** mcp 2.x dispatches sync tool handlers through
  `anyio.to_thread.run_sync`, so concurrent calls run on different threads.
  `googleapiclient` clients are not thread-safe and SECURITY.md forbids sharing a
  `Workspace` across threads, so the provider hands each thread its own.
"""
from __future__ import annotations

import os
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from .. import auth
from ..exceptions import AuthError
from ..policy import ALL_CAPABILITIES, DEFAULT_ENABLED, Policy
from ..workspace import Workspace

DEFAULT_TOKEN_PATH = "~/.csa_google_workspace/token.json"   # nosec B105 - a path, not a secret
DEFAULT_CLIENT_SECRETS_PATH = "~/.csa_google_workspace/client_secret.json"  # nosec B105 - a path
def _launcher() -> str:
    """The command a user can actually paste, absolute where we can determine it.

    A bare `csa-google-workspace-mcp` is useless when the launcher is not on PATH — the
    normal case on Windows, where pipx puts it somewhere PATH does not reach until a new
    shell. argv[0] is the real path we were started from, so prefer it.
    """
    argv0 = (sys.argv[0] or "").strip()
    if argv0 and (os.sep in argv0 or (os.altsep and os.altsep in argv0)):
        return argv0
    return "csa-google-workspace-mcp"


def unauthorized_message(token_path: str, reason: str) -> str:
    """What every tool returns while the server is unauthorized.

    This text IS the user experience of an unauthorized server: it starts fine by design,
    so this message is the only thing anyone sees. It has to (a) offer the no-terminal path
    first, (b) give a command that can be pasted verbatim, (c) say where it looked, and
    (d) tell the model to ask the user rather than trying to fix it itself — a capable model
    given only "no credentials" will otherwise start hunting the filesystem, which is
    exactly what happened before this message said so.
    """
    return (
        f"Not authorized to reach Google yet ({reason}). "
        f"No usable token at {token_path}.\n"
        f"\nTwo ways to fix this, easiest first:\n"
        f"  1. Call the `authenticate` tool. It sends the user a Google sign-in link right "
        f"here — no terminal needed. (Requires a client that supports URL elicitation; "
        f"Claude Code does, Claude Desktop does not yet.)\n"
        f"  2. Or have the user run this in a terminal, once:\n"
        f"       {_launcher()} login\n"
        f"\nAsk the user to do one of these and wait for them. Do not retry other tools "
        f"until authorization completes, and do not try to locate or read credential files "
        f"yourself."
    )

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Server configuration.

    `client_secrets` is **optional and never needed to start**: reading and refreshing a
    cached token requires no client file, because the token carries its own client_id and
    secret. It is used only by the in-band `authenticate` tool, which has to construct a
    fresh consent URL and therefore does need the client. Absent, that tool reports how to
    run `login` instead; everything else works unchanged.
    """
    token_path: str = DEFAULT_TOKEN_PATH
    read_only: bool = False
    client_secrets: str | None = None
    policy: Policy | None = None            # None -> Policy.default()


def policy_from_env(env: Mapping[str, str]) -> Policy | None:
    """`CSA_GW_CAPABILITIES` — the complete list of mutations this server may perform.

    Absolute, not a delta, because #82 asks for config that *reviews like code*: reading the
    line should tell you everything that is permitted, without also knowing what the
    defaults were on the day it was written. The token `default` expands to the built-in
    set, so a delta is still expressible and still self-describing:

        CSA_GW_CAPABILITIES=default,file.trash        # the usual set, plus trashing
        CSA_GW_CAPABILITIES=comment.create,comment.reply   # exactly these two
        CSA_GW_CAPABILITIES=none                      # read-only, reached from this side

    Unset returns `None`, which the `Workspace` constructors read as `Policy.default()`.
    """
    raw = (env.get("CSA_GW_CAPABILITIES") or "").strip()
    if not raw:
        return None
    tokens = [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]
    if tokens == ["none"]:
        return Policy(enabled=frozenset())
    enabled: set[str] = set()
    unknown: list[str] = []
    for token in tokens:
        if token == "default":
            enabled |= DEFAULT_ENABLED
        elif token == "all":
            enabled |= set(ALL_CAPABILITIES)
        elif token in ALL_CAPABILITIES:
            enabled.add(token)
        else:
            unknown.append(token)
    if unknown:
        # Fail loudly rather than silently running with a smaller policy than intended: a
        # typo'd capability name would otherwise read as "configured" and behave as "off".
        raise ValueError(
            f"CSA_GW_CAPABILITIES contains unknown value(s): {', '.join(unknown)}. "
            f"Known capabilities: {', '.join(ALL_CAPABILITIES)}. "
            f"Also accepted: 'default', 'all', 'none'.")
    return Policy(enabled=frozenset(enabled))


def settings_from_env(env: Mapping[str, str]) -> Settings:
    explicit = env.get("CSA_GW_CLIENT_SECRETS")
    default = os.path.expanduser(DEFAULT_CLIENT_SECRETS_PATH)
    return Settings(
        token_path=env.get("CSA_GW_TOKEN") or DEFAULT_TOKEN_PATH,
        read_only=(env.get("CSA_GW_READ_ONLY") or "").strip().lower() in _TRUE,
        client_secrets=explicit or (default if os.path.exists(default) else None),
        policy=policy_from_env(env),
    )


class WorkspaceProvider:
    """Callable returning a `Workspace` for the calling thread, building it on first use.

    Raises `AuthError` (with the login remedy appended) when there is no usable cached
    token — callers turn that into a tool error rather than a crash.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._local = threading.local()

    @property
    def settings(self) -> Settings:
        return self._settings

    def __call__(self) -> Workspace:
        existing = getattr(self._local, "workspace", None)
        if existing is not None:
            return existing
        try:
            creds = auth.load_cached_credentials(self._settings.token_path, self._settings.read_only)
        except AuthError as e:
            raise AuthError(unauthorized_message(self._settings.token_path, str(e))) from e
        workspace = Workspace.from_credentials(
            creds, read_only=self._settings.read_only, policy=self._settings.policy)
        self._local.workspace = workspace
        return workspace
