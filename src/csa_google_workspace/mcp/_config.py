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
from ..allowlist import Entry, is_inline, load_allowlist, parse_inline
from ..exceptions import AuthError
from ..policy import ALL_CAPABILITIES, DEFAULT_ENABLED, Policy
from ..workspace import Workspace

DEFAULT_TOKEN_PATH = "~/.csa_google_workspace/token.json"   # nosec B105 - a path, not a secret
DEFAULT_CLIENT_SECRETS_PATH = "~/.csa_google_workspace/client_secret.json"  # nosec B105 - a path
DEFAULT_ALLOWLIST_PATH = "~/.csa_google_workspace/allowlist.txt"
# The escape hatch. Explicit, so that running with unrestricted writes is something somebody
# typed — which is what makes flipping the no-allowlist default at 1.0.0 possible without
# leaving anyone stuck.
ALLOWLIST_ANY = "any"
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
    """Build the mutation policy from the environment, or `None` for the built-in default.

    Two variables, one per dimension of #82:

      CSA_GW_CAPABILITIES   *what* may be mutated  (see `_capabilities_from_env`)
      CSA_GW_ALLOWLIST      *which files*          — path to a plain-text list of URLs

    They compose one way only: capabilities are a ceiling, the allowlist narrows. An
    unset allowlist means no file restriction, which is what this library has always done;
    making that fail-closed is a 1.0.0 decision recorded in TODO.md, not a silent change.
    """
    capabilities = _capabilities_from_env(env)
    entries = _allowlist_from_env(env)
    if capabilities is None and entries is None:
        return None
    enabled = frozenset(capabilities.enabled if capabilities is not None else DEFAULT_ENABLED)
    if entries is None:
        return Policy(enabled=enabled)
    return Policy.from_entries(enabled, entries)


def _allowlist_from_env(env: Mapping[str, str]) -> tuple[Entry, ...] | None:
    """The write allowlist, from `CSA_GW_ALLOWLIST` or the default path.

    `None` means *no file restriction* — either nothing was configured, or the operator asked
    for unrestricted writes explicitly with `CSA_GW_ALLOWLIST=any`.

    Three sources, in order of precedence:

      CSA_GW_ALLOWLIST=any                     unrestricted, deliberately
      CSA_GW_ALLOWLIST=https://…               URLs inline, for a JSON `env` block
      CSA_GW_ALLOWLIST=/path/to/file           an explicit path
      (unset)                                  ~/.csa_google_workspace/allowlist.txt if present

    The default path exists for the same reason `client_secret.json` has one: a curated list
    distributed by a setup script should need no per-user configuration, because the people
    running it did not write it. Anything configured but unusable **raises** — never a
    fallback to unrestricted writes.
    """
    value = (env.get("CSA_GW_ALLOWLIST") or "").strip()
    if value.lower() == ALLOWLIST_ANY:
        return None
    if value:
        return parse_inline(value) if is_inline(value) else load_allowlist(value)
    default = os.path.expanduser(DEFAULT_ALLOWLIST_PATH)
    return load_allowlist(default) if os.path.exists(default) else None


def _capabilities_from_env(env: Mapping[str, str]) -> Policy | None:
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
    # Named `entries`, not `tokens`: in this codebase "token" means an OAuth credential, and
    # bandit's B105 wordlist agrees strongly enough to fail the build over `token == "..."`.
    entries = [e.strip() for e in raw.replace(";", ",").split(",") if e.strip()]
    if entries == ["none"]:
        return Policy(enabled=frozenset())
    enabled: set[str] = set()
    unknown: list[str] = []
    for entry in entries:
        if entry == "default":
            enabled |= DEFAULT_ENABLED
        elif entry == "all":
            enabled |= set(ALL_CAPABILITIES)
        elif entry in ALL_CAPABILITIES:
            enabled.add(entry)
        else:
            unknown.append(entry)
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
