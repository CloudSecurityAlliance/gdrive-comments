"""OAuth installed-app flow + scope logic. Acts as a real user; writes on by default."""
import os

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .exceptions import AuthError

_BASE = "https://www.googleapis.com/auth/"
_RW = [f"{_BASE}drive", f"{_BASE}documents", f"{_BASE}spreadsheets", f"{_BASE}presentations"]
_RO = [f"{s}.readonly" for s in _RW]


def scopes_for(read_only: bool) -> list[str]:
    return list(_RO if read_only else _RW)


def needs_reconsent(granted: list[str], required: list[str]) -> bool:
    granted_set = set(granted or [])
    for scope in required:
        if scope in granted_set:
            continue
        base = scope[: -len(".readonly")] if scope.endswith(".readonly") else None
        if base and base in granted_set:
            continue  # a granted RW scope satisfies a required readonly scope
        return True
    return False


def _read_cached(token_path: str, required: list[str]) -> Credentials | None:
    """The token cache, or None if absent / scope-stale — both meaning 'consent is needed'."""
    if not os.path.exists(token_path):
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path)
    except (ValueError, GoogleAuthError) as e:
        # Generic message: don't interpolate the cause (may echo token material). The
        # original is preserved via `from e` for debugging (#19).
        raise AuthError("could not load cached credentials") from e
    # (#13) A cached read-write token satisfies a required read-only scope set, so
    # read_only=True reuses it rather than forcing an interactive re-consent — deliberate,
    # to keep headless refresh working. read_only still blocks writes client-side; for a
    # scope-level read-only guarantee use a separate token path or from_credentials.
    if needs_reconsent(list(creds.scopes or []), required):
        return None
    return creds


def _refresh(creds: Credentials) -> None:
    try:
        creds.refresh(Request())
    except (ValueError, GoogleAuthError) as e:
        raise AuthError("could not refresh cached credentials") from e


def _write_token(token_path: str, creds: Credentials) -> None:
    token_dir = os.path.dirname(token_path)
    if token_dir and not os.path.isdir(token_dir):
        os.makedirs(token_dir, exist_ok=True)
        os.chmod(token_dir, 0o700)      # only harden a dir we created; don't mutate a caller's (#4)
    # O_NOFOLLOW refuses a symlink at token_path (symlink/TOCTOU attack); fchmod enforces
    # 0o600 even when the file already existed, since O_TRUNC keeps a file's prior mode (#17).
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as f:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        f.write(creds.to_json())


def load_credentials(client_secrets: str, token_path: str, read_only: bool,
                     *, force: bool = False) -> Credentials:
    """Interactive: reuse the cache, else open a browser for consent. Terminal use only.

    `force=True` ignores the cache and re-consents. It does not delete anything: the
    existing token is replaced only once a new one is in hand, so a cancelled or failed
    consent leaves the old credentials working.

    Do NOT call this from a stdio MCP server — `run_local_server()` prints the consent URL
    to stdout (the JSON-RPC channel) and blocks on the browser redirect. Servers call
    `load_cached_credentials` instead, which has no such branch.
    """
    required = scopes_for(read_only)
    token_path = os.path.expanduser(token_path)
    creds = None if force else _read_cached(token_path, required)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        _refresh(creds)
    else:
        creds = InstalledAppFlow.from_client_secrets_file(client_secrets, required).run_local_server(port=0)
    _write_token(token_path, creds)
    return creds


def load_cached_credentials(token_path: str, read_only: bool) -> Credentials:
    """Non-interactive: usable credentials from the token cache, or `AuthError`.

    This function deliberately contains **no** `InstalledAppFlow` branch, so a caller that
    must never prompt — the stdio MCP server — cannot reach interactive consent even by
    mistake. That is a structural guarantee rather than a convention. Refreshing an expired
    token is pure HTTP with no stdout writes, so it stays on this path.

    No `client_secrets` argument is needed: `to_json()` persists client_id/client_secret/
    token_uri into the cache, so a cached token is self-sufficient for refresh.
    """
    token_path = os.path.expanduser(token_path)
    if not os.path.exists(token_path):
        raise AuthError("no cached credentials")
    creds = _read_cached(token_path, scopes_for(read_only))
    if creds is None:
        raise AuthError("cached credentials lack the required scopes")
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        _refresh(creds)
        _write_token(token_path, creds)     # persist the refreshed token
        return creds
    raise AuthError("cached credentials are invalid and cannot be refreshed")
