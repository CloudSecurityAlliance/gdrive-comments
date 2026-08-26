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

import logging
import os
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from .. import auth
from ..allowlist import ALL_SYNONYMS, AllowlistError, Listing, diagnose_setting, parse_setting
from ..exceptions import AuthError
from ..policy import ALL_CAPABILITIES, DEFAULT_ENABLED, PROFILES, Policy, Scope
from ..workspace import Workspace

DEFAULT_TOKEN_PATH = "~/.csa_google_workspace/token.json"   # nosec B105 - a path, not a secret
DEFAULT_CLIENT_SECRETS_PATH = "~/.csa_google_workspace/client_secret.json"  # nosec B105 - a path
log = logging.getLogger(__name__)

READ_ALLOWLIST_VAR = "CSA_GW_ALLOWLIST_READ"
MODIFY_ALLOWLIST_VAR = "CSA_GW_ALLOWLIST_MODIFY"
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


PROFILE_VAR = "CSA_GW_PROFILE"


DEFAULT_EXPORT_DIR = "~/Downloads"


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
    profile: str | None = None              # the CSA_GW_PROFILE name, for reporting
    # Where `export_comments(destination="file")` puts a .csv when the caller gives only a
    # NAME. Defaults to ~/Downloads - the platform's designated "a program gave me a file"
    # location: discoverable in the Finder sidebar, persistent (unlike a temp directory, whose
    # macOS path no human can navigate to anyway), and somewhere nobody keeps precious unique
    # files. `CSA_GW_EXPORT_DIR` overrides it.
    #
    # A caller may also give a FULL PATH, and that is honoured. A Claude Desktop *project* may
    # only be able to write inside its own folder, where ~/Downloads is unreachable, and a
    # Claude Code user wants the register in the repo they are in. What makes that safe is not
    # validating the path but making the failures inert - see `_export.resolve_export_path`.
    export_dir: str = DEFAULT_EXPORT_DIR


def policy_from_env(env: Mapping[str, str]) -> Policy:
    """Build the server's policy from the environment. Three independent bounds:

      CSA_GW_CAPABILITIES       *what* may be mutated
      CSA_GW_ALLOWLIST_READ     *which files* may be read     — `*` for the usual posture
      CSA_GW_ALLOWLIST_MODIFY   *which files* may be changed   — a short, reviewed list

    Both hold their lists directly; there is no allowlist file. See `_scope_from_env`.

    Each is a ceiling; none can widen another. **Both allowlists fail closed**: unset means
    nothing is permitted, and unrestricted access must be typed as `*`.

    This always returns a `Policy` — never `None` — because "nothing configured" is now a
    meaningful and restrictive answer rather than an absent one.
    """
    _reject_legacy_allowlist(env)
    capabilities = _capabilities_from_env(env)
    profile = _profile_from_env(env)
    if capabilities is not None:
        if profile is not None:
            # Both set. Honour the explicit list — it is the more specific statement — but say
            # so, because the operator plainly believed the profile was doing something.
            log.warning("both %s and CSA_GW_CAPABILITIES are set; the explicit capability "
                        "list wins and the profile is ignored", PROFILE_VAR)
        enabled = frozenset(capabilities.enabled)
    elif profile is not None:
        enabled = PROFILES[profile]
    else:
        enabled = DEFAULT_ENABLED
    return Policy(
        enabled=enabled,
        read=_scope_from_env(env, READ_ALLOWLIST_VAR),
        modify=_scope_from_env(env, MODIFY_ALLOWLIST_VAR),
    )


def _scope_from_env(env: Mapping[str, str], variable: str) -> Scope:
    """One allowlist scope, from its environment variable. **Fail closed.**

    The variable holds the list itself; **there is no file to read**. The client configuration
    is the artifact an operator controls and can see, so the policy lives there rather than
    behind a path whose target can change without the config changing.

    Unset — or set to anything unusable — means `Scope.nothing()`: every operation of that
    kind is refused, with a message saying which variable and why. That is the opposite of the
    library's default, deliberately: `Workspace.from_credentials` is called by a developer who
    has made a decision, while this is configuration handed to a model.

    Unrestricted access is available and must be *typed* as `*`. It logs a warning every time
    it is parsed, because the point of writing the policy down is that it can be reviewed.

      <VAR>=*                          every file, deliberately
      <VAR>=https://…                  the documents, newline- or comma-separated
      (unset, blank, malformed)        nothing
    """
    raw = env.get(variable)
    value = (raw or "").strip()
    if not value:
        return Scope.nothing(reason=diagnose_setting(variable, raw))
    if value.lower() in ALL_SYNONYMS:
        log.warning("%s=%s grants access to EVERY file the credentials can reach",
                    variable, value)
        return Scope.from_listing(Listing(all_files=True))
    return Scope.from_listing(parse_setting(value, variable=variable))


def _reject_legacy_allowlist(env: Mapping[str, str]) -> None:
    """`CSA_GW_ALLOWLIST` was v0.8.x. Its meaning changed, so it must not be reinterpreted.

    Silently treating it as the modify list would leave `read` fail-closed and break reads for
    reasons nobody could see. An error naming both replacements costs one restart.
    """
    if env.get("CSA_GW_ALLOWLIST"):
        raise AllowlistError(
            f"CSA_GW_ALLOWLIST has been split into {READ_ALLOWLIST_VAR} and "
            f"{MODIFY_ALLOWLIST_VAR}, because reads and mutations want different answers. The "
            f"usual posture is {READ_ALLOWLIST_VAR}=* with {MODIFY_ALLOWLIST_VAR} set to your "
            f"list of document URLs. Refusing to guess which you meant.")


def _profile_from_env(env: Mapping[str, str]) -> str | None:
    """`CSA_GW_PROFILE` — a named capability set, so "what may this install do?" has an answer
    shorter than a list.

    Profiles cover capabilities only. The file allowlists are deliberately *not* profiled:
    which documents a deployment may touch is specific to that deployment, and a named default
    for it would be a named default for "which of your files an agent may change".
    """
    name = (env.get(PROFILE_VAR) or "").strip().lower()
    if not name:
        return None
    if name not in PROFILES:
        raise ValueError(
            f"{PROFILE_VAR}={name!r} is not a known profile. Choose one of: "
            f"{', '.join(f'{p} ({len(c)} capabilities)' for p, c in PROFILES.items())}. "
            f"Or set CSA_GW_CAPABILITIES to an explicit list instead.")
    return name


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
        profile=_profile_from_env(env),
        export_dir=(env.get("CSA_GW_EXPORT_DIR") or "").strip() or DEFAULT_EXPORT_DIR,
    )


def startup_warnings(settings: Settings) -> list[str]:
    """What to tell the user on stderr before the first tool call.

    An unconfigured server *starts* by design (a startup crash reaches the user as an opaque
    "server failed to start"), so anything they need to know has to be said here or in a tool
    error. Both fail-closed and wide-open are worth saying out loud: one means nothing will
    work until they configure it, the other means everything is permitted.
    """
    policy = settings.policy
    if policy is None:
        return []
    out: list[str] = []
    if settings.profile:
        out.append(f"profile: {settings.profile} — "
                   f"{', '.join(sorted(PROFILES[settings.profile])) or 'no mutations at all'}")
    for label, scope, variable in (
            ("READ", policy.read, READ_ALLOWLIST_VAR),
            ("MODIFY", policy.modify, MODIFY_ALLOWLIST_VAR)):
        if scope.all_files:
            out.append(f"{label}: UNRESTRICTED — every file your Google account can reach. "
                       f"Set {variable} to a list of document URLs to narrow it.")
        elif not scope.ids:
            why = scope.reason or f"{variable} is not configured."
            out.append(f"{label}: nothing permitted — every {label.lower()} will be refused. "
                       f"{why} Set it to a list of document URLs, or to `*` for unrestricted "
                       f"access.")
        else:
            out.append(f"{label}: {scope.describe()}.")
    return out


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
