"""Config + Workspace provisioning for the MCP server (spec §5).

Two things are load-bearing here and neither is obvious:

1. **Nothing resolves at import or startup.** Credentials are looked up on first tool
   use, so a server with no token still *starts* and reports the problem as a tool
   error the user can see in chat. An MCP client surfaces a startup crash as an
   opaque "server failed to start", so failing fast here would fail silently.
2. **A Workspace is thread-local.** mcp 2.x runs sync tool handlers via
   `anyio.to_thread.run_sync`, so two concurrent tool calls land on two threads.
   `googleapiclient` clients are not thread-safe and SECURITY.md forbids sharing a
   Workspace across threads, so each worker thread gets its own.
"""
import threading

import pytest

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.mcp import _config


class FakeCreds:
    valid = True


def _provider(monkeypatch, creds_or_exc=None):
    def loader(token_path, read_only):
        if isinstance(creds_or_exc, Exception):
            raise creds_or_exc
        return creds_or_exc or FakeCreds()
    monkeypatch.setattr(_config.auth, "load_cached_credentials", loader)
    return _config.WorkspaceProvider(_config.Settings(token_path="/nonexistent", read_only=False))


# --- settings ---------------------------------------------------------------

def test_defaults_when_env_is_empty():
    s = _config.settings_from_env({})
    assert s.token_path == _config.DEFAULT_TOKEN_PATH
    assert s.read_only is False


def test_env_overrides_token_path_and_read_only():
    s = _config.settings_from_env({"CSA_GW_TOKEN": "/tmp/t.json", "CSA_GW_READ_ONLY": "1"})
    assert s.token_path == "/tmp/t.json"
    assert s.read_only is True


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("TRUE", True),
                                            ("0", False), ("", False), ("no", False)])
def test_read_only_flag_parsing(value, expected):
    assert _config.settings_from_env({"CSA_GW_READ_ONLY": value}).read_only is expected


def test_client_secrets_are_optional_not_required(monkeypatch, tmp_path):
    """The server must start and serve without any client secrets.

    They are needed only to build a fresh consent URL for the in-band `authenticate` tool;
    reading and refreshing a cached token needs none, because the token carries its own
    client_id and secret. Patch the default path so this does not depend on whether the
    developer's home directory happens to contain one.
    """
    monkeypatch.setattr(_config, "DEFAULT_CLIENT_SECRETS_PATH", str(tmp_path / "absent.json"))
    s = _config.settings_from_env({})
    assert s.client_secrets is None
    assert s.token_path == _config.DEFAULT_TOKEN_PATH        # everything else still resolves


def test_client_secrets_picked_up_from_env_or_default(monkeypatch, tmp_path):
    present = tmp_path / "client_secret.json"
    present.write_text("{}")
    monkeypatch.setattr(_config, "DEFAULT_CLIENT_SECRETS_PATH", str(present))
    assert _config.settings_from_env({}).client_secrets == str(present)
    other = tmp_path / "other.json"
    assert _config.settings_from_env({"CSA_GW_CLIENT_SECRETS": str(other)}).client_secrets == str(other)


# --- provider ---------------------------------------------------------------

def test_provider_builds_a_workspace_from_cached_credentials(monkeypatch):
    assert isinstance(_provider(monkeypatch)(), Workspace)


def test_provider_surfaces_missing_credentials_with_an_actionable_message(monkeypatch):
    provider = _provider(monkeypatch, exceptions.AuthError("no cached credentials"))
    with pytest.raises(exceptions.AuthError) as ei:
        provider()
    assert "login" in str(ei.value)          # tells the user the remedy, not just the symptom


def test_provider_reuses_one_workspace_within_a_thread(monkeypatch):
    provider = _provider(monkeypatch)
    assert provider() is provider()


def test_provider_gives_each_thread_its_own_workspace(monkeypatch):
    """The thread-safety guarantee: googleapiclient clients must never cross threads."""
    provider = _provider(monkeypatch)
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(provider())) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(w) for w in seen}) == 3          # three threads, three Workspaces


def test_provider_does_not_resolve_credentials_until_called(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("credentials must not resolve at construction time")
    monkeypatch.setattr(_config.auth, "load_cached_credentials", explode)
    _config.WorkspaceProvider(_config.Settings(token_path="/nope", read_only=False))   # must not raise
