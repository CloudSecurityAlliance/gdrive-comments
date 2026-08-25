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


@pytest.fixture(autouse=True)
def _no_ambient_allowlist(tmp_path, monkeypatch):
    """Point every default allowlist path at somewhere that does not exist.

    Without this, assertions here would pass or fail depending on whether the developer
    happens to have files in ~/.csa_google_workspace/ — the same machine-dependent trap that
    once made a `login` test pass only because CI lacked a client_secret.json. Tests that
    *want* a default path patch it themselves.
    """
    for attribute in ("DEFAULT_READ_ALLOWLIST_PATH", "DEFAULT_MODIFY_ALLOWLIST_PATH",
                      "LEGACY_ALLOWLIST_PATH"):
        monkeypatch.setattr(_config, attribute, str(tmp_path / f"absent-{attribute}.txt"))


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


# --- the not-authorized message has to be actionable ------------------------
#
# This text is the entire user experience of an unauthorized server: it starts fine, and
# this is what comes back from every tool. It has to be enough for the model to hand the
# user something they can actually run.

def test_unauthorized_message_offers_the_no_terminal_path_first(monkeypatch):
    def missing(tp, ro):
        raise exceptions.AuthError("no cached credentials")
    monkeypatch.setattr(_config.auth, "load_cached_credentials", missing)
    provider = _config.WorkspaceProvider(_config.Settings(token_path="/nope/token.json"))

    with pytest.raises(exceptions.AuthError) as ei:
        provider()
    msg = str(ei.value)
    assert "authenticate" in msg                    # the in-client path, mentioned first
    assert msg.index("authenticate") < msg.index("login")


def test_unauthorized_message_gives_a_runnable_command(monkeypatch):
    monkeypatch.setattr(_config.auth, "load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(exceptions.AuthError("none")))
    monkeypatch.setattr(_config.sys, "argv", ["/abs/path/to/csa-google-workspace-mcp"])
    provider = _config.WorkspaceProvider(_config.Settings(token_path="/nope/token.json"))

    with pytest.raises(exceptions.AuthError) as ei:
        provider()
    # The absolute path, not the bare name: on Windows the launcher is frequently not on
    # PATH, so a bare command name is not something the user can paste anywhere.
    assert "/abs/path/to/csa-google-workspace-mcp login" in str(ei.value)


def test_unauthorized_message_says_where_it_looked(monkeypatch):
    monkeypatch.setattr(_config.auth, "load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(exceptions.AuthError("none")))
    provider = _config.WorkspaceProvider(_config.Settings(token_path="/some/where/token.json"))
    with pytest.raises(exceptions.AuthError) as ei:
        provider()
    assert "/some/where/token.json" in str(ei.value)


def test_unauthorized_message_tells_the_model_to_ask_the_user(monkeypatch):
    """Otherwise a capable model tries to fix it itself — shell commands, file hunting."""
    monkeypatch.setattr(_config.auth, "load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(exceptions.AuthError("none")))
    provider = _config.WorkspaceProvider(_config.Settings(token_path="/nope/token.json"))
    with pytest.raises(exceptions.AuthError) as ei:
        provider()
    low = str(ei.value).lower()
    assert "ask the user" in low or "the user" in low


# --- CSA_GW_CAPABILITIES ----------------------------------------------------

def test_no_capabilities_env_means_the_default_capability_set():
    """`policy_from_env` always returns a Policy now: "nothing configured" is a restrictive
    answer, not an absent one. Only the *capabilities* fall back to the built-in set."""
    from csa_google_workspace.policy import DEFAULT_ENABLED
    policy = _config.settings_from_env({}).policy
    assert policy is not None and policy.enabled == DEFAULT_ENABLED


def test_capabilities_default_token_expands_to_the_builtin_set():
    from csa_google_workspace.mcp._config import settings_from_env
    from csa_google_workspace.policy import DEFAULT_ENABLED, FILE_TRASH
    policy = settings_from_env({"CSA_GW_CAPABILITIES": "default,file.trash"}).policy
    assert policy is not None
    assert policy.enabled == DEFAULT_ENABLED | {FILE_TRASH}


def test_capabilities_is_absolute_not_a_delta():
    """Reading the line must tell you everything permitted, without also knowing what the
    defaults were the day it was written (#82: config that reviews like code)."""
    from csa_google_workspace.mcp._config import settings_from_env
    from csa_google_workspace.policy import COMMENT_CREATE
    policy = settings_from_env({"CSA_GW_CAPABILITIES": "comment.create"}).policy
    assert policy is not None and policy.enabled == frozenset({COMMENT_CREATE})


def test_capabilities_none_permits_nothing():
    from csa_google_workspace.mcp._config import settings_from_env
    policy = settings_from_env({"CSA_GW_CAPABILITIES": "none"}).policy
    assert policy is not None and policy.enabled == frozenset()


def test_capabilities_all_permits_everything_including_the_dangerous_three():
    from csa_google_workspace.mcp._config import settings_from_env
    from csa_google_workspace.policy import ALL_CAPABILITIES
    policy = settings_from_env({"CSA_GW_CAPABILITIES": "all"}).policy
    assert policy is not None and policy.enabled == set(ALL_CAPABILITIES)


def test_an_unknown_capability_fails_loudly_rather_than_running_narrower():
    """A typo'd name would otherwise read as "configured" and behave as "off" — the failure
    mode where an operator believes a capability is enabled and it silently is not."""
    import pytest

    from csa_google_workspace.mcp._config import settings_from_env
    with pytest.raises(ValueError) as e:
        settings_from_env({"CSA_GW_CAPABILITIES": "comment.create,file.nuke"})
    assert "file.nuke" in str(e.value) and "file.share" in str(e.value)


def test_read_only_overrides_a_permissive_capability_list():
    """read_only is the stronger statement — it also narrows the OAuth scopes."""
    from csa_google_workspace.mcp._config import WorkspaceProvider, settings_from_env
    settings = settings_from_env({"CSA_GW_READ_ONLY": "1", "CSA_GW_CAPABILITIES": "all"})
    assert settings.read_only is True
    # The provider builds the Workspace, which is where read_only wins.
    assert WorkspaceProvider(settings).settings.read_only is True


# --- the two allowlists -----------------------------------------------------

_ALLOW_URL = "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit"
_ALLOW_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
_OTHER_ID = "2bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_OTHER_URL = f"https://docs.google.com/document/d/{_OTHER_ID}/edit"


def test_unset_means_fail_closed_on_both_scopes():
    """The server's default, and the opposite of the library's. Nothing configured is a
    restrictive answer, not an absent one."""
    policy = _config.settings_from_env({}).policy
    assert policy is not None
    assert not policy.read.all_files and not policy.read.ids
    assert not policy.modify.all_files and not policy.modify.ids


def test_the_usual_posture_read_star_modify_list():
    """READ=* matches what Google's and Anthropic's Drive servers do; MODIFY is the part
    worth locking down."""
    policy = _config.settings_from_env({
        "CSA_GW_ALLOWLIST_READ": "*",
        "CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL,
    }).policy
    assert policy is not None
    assert policy.read.all_files is True
    assert policy.modify.ids == frozenset({_ALLOW_ID})


def test_the_two_scopes_are_independent():
    policy = _config.settings_from_env({
        "CSA_GW_ALLOWLIST_READ": f"{_ALLOW_URL} {_OTHER_URL}",
        "CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL,
    }).policy
    assert policy is not None
    assert policy.read.ids == frozenset({_ALLOW_ID, _OTHER_ID})
    assert policy.modify.ids == frozenset({_ALLOW_ID})


@pytest.mark.parametrize("spelling", ["*", "any", "all", "ANY"])
def test_star_and_its_synonyms_mean_everything(spelling):
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": spelling}).policy
    assert policy is not None and policy.modify.all_files is True


def test_urls_inline_for_a_json_env_block():
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL}).policy
    assert policy is not None and policy.modify.ids == frozenset({_ALLOW_ID})


def test_inline_urls_with_newlines_keep_their_reasons():
    """`\n` in a JSON string, so reason-per-entry survives inline configuration."""
    value = f"{_ALLOW_URL}  # CCM mapping\n{_OTHER_URL}  # AICM tracker"
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": value}).policy
    assert policy is not None
    assert sorted(e.reason for e in policy.modify.entries) == ["AICM tracker", "CCM mapping"]


def test_an_explicit_path(tmp_path):
    path = tmp_path / "modify.txt"
    path.write_text(f"{_ALLOW_URL}  # the one\n", encoding="utf-8")
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": str(path)}).policy
    assert policy is not None and policy.modify.ids == frozenset({_ALLOW_ID})


def test_the_default_paths_are_used_when_they_exist(tmp_path, monkeypatch):
    """Same pattern as client_secret.json: a curated list dropped in place by a setup script
    needs no per-user configuration, because the people running it did not write it."""
    read = tmp_path / "allowlist-read.txt"; read.write_text("*", encoding="utf-8")
    modify = tmp_path / "allowlist-modify.txt"; modify.write_text(_ALLOW_URL, encoding="utf-8")
    monkeypatch.setattr(_config, "DEFAULT_READ_ALLOWLIST_PATH", str(read))
    monkeypatch.setattr(_config, "DEFAULT_MODIFY_ALLOWLIST_PATH", str(modify))
    policy = _config.settings_from_env({}).policy
    assert policy is not None
    assert policy.read.all_files and policy.modify.ids == frozenset({_ALLOW_ID})


def test_an_explicit_value_overrides_the_default_path(tmp_path, monkeypatch):
    default = tmp_path / "allowlist-modify.txt"
    default.write_text(_ALLOW_URL, encoding="utf-8")
    monkeypatch.setattr(_config, "DEFAULT_MODIFY_ALLOWLIST_PATH", str(default))
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": _OTHER_URL}).policy
    assert policy is not None and policy.modify.ids == frozenset({_OTHER_ID})


def test_a_mistyped_path_is_reported_as_a_path_not_read_as_a_url(tmp_path):
    """`://` is the discriminator. Guessing with os.path.exists would silently reinterpret a
    typo'd path as a URL list, which is the failure this must not have."""
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": str(tmp_path / "typo.txt")})
    assert "no allowlist file at" in str(e.value)


def test_a_folder_url_fails_loudly(tmp_path):
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({
            "CSA_GW_ALLOWLIST_MODIFY":
                "https://drive.google.com/drive/folders/1HXZuiBGXD263XdaEOT3siAsakQEuQzVt"})
    assert "folder" in str(e.value)


# --- the v0.8.x variable is refused, not reinterpreted ----------------------

def test_the_legacy_variable_is_an_error_naming_both_replacements():
    """Silently treating it as the modify list would leave read fail-closed and break reads
    for reasons nobody could see."""
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({"CSA_GW_ALLOWLIST": _ALLOW_URL})
    message = str(e.value)
    assert "CSA_GW_ALLOWLIST_READ" in message and "CSA_GW_ALLOWLIST_MODIFY" in message


def test_a_leftover_legacy_file_is_an_error_rather_than_silently_ignored(tmp_path, monkeypatch):
    legacy = tmp_path / "allowlist.txt"; legacy.write_text(_ALLOW_URL, encoding="utf-8")
    monkeypatch.setattr(_config, "LEGACY_ALLOWLIST_PATH", str(legacy))
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({})
    assert "no longer read" in str(e.value)


# --- what the user is told at startup --------------------------------------

def test_startup_warnings_say_when_nothing_is_permitted():
    settings = _config.settings_from_env({})
    lines = " ".join(_config.startup_warnings(settings))
    assert "nothing permitted" in lines
    assert "CSA_GW_ALLOWLIST_READ" in lines and "CSA_GW_ALLOWLIST_MODIFY" in lines


def test_startup_warnings_say_when_everything_is_permitted():
    settings = _config.settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                          "CSA_GW_ALLOWLIST_MODIFY": "*"})
    lines = " ".join(_config.startup_warnings(settings))
    assert lines.count("UNRESTRICTED") == 2


def test_startup_warnings_report_a_narrowed_scope_plainly():
    settings = _config.settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                          "CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL})
    lines = _config.startup_warnings(settings)
    assert any("UNRESTRICTED" in line for line in lines)
    assert any("1 listed file(s)" in line for line in lines)


# --- capabilities compose independently of the allowlists ------------------

def test_capabilities_and_allowlists_are_independent():
    from csa_google_workspace.policy import COMMENT_CREATE
    policy = _config.settings_from_env({
        "CSA_GW_CAPABILITIES": "comment.create",
        "CSA_GW_ALLOWLIST_READ": "*",
        "CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL,
    }).policy
    assert policy is not None
    assert policy.enabled == frozenset({COMMENT_CREATE})
    assert policy.read.all_files and policy.modify.ids == frozenset({_ALLOW_ID})
