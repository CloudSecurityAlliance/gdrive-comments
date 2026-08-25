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

import threading
from collections.abc import Mapping
from dataclasses import dataclass

from .. import auth
from ..exceptions import AuthError
from ..workspace import Workspace

DEFAULT_TOKEN_PATH = "~/.csa_google_workspace/token.json"   # nosec B105 - a path, not a secret
LOGIN_HINT = "run `csa-google-workspace-mcp login` to authorize"

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Server configuration. Note there is no `client_secrets`: the server only ever reads
    and refreshes a cached token, and a cached token carries its own client_id/secret.
    Client secrets are a `login` concern."""
    token_path: str = DEFAULT_TOKEN_PATH
    read_only: bool = False


def settings_from_env(env: Mapping[str, str]) -> Settings:
    return Settings(
        token_path=env.get("CSA_GW_TOKEN") or DEFAULT_TOKEN_PATH,
        read_only=(env.get("CSA_GW_READ_ONLY") or "").strip().lower() in _TRUE,
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
            raise AuthError(f"{e}; {LOGIN_HINT}") from e
        workspace = Workspace.from_credentials(creds, read_only=self._settings.read_only)
        self._local.workspace = workspace
        return workspace
