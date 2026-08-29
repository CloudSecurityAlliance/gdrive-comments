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
from dataclasses import replace

import pytest

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.allowlist import AllowlistError
from csa_google_workspace.mcp import _config

# NOTE: there is deliberately no fixture neutralising an ambient allowlist file here. There
# is no allowlist file — the lists live in the environment — so the tests cannot depend on
# what happens to be in the developer's home directory. That whole class of failure (a test
# passing only because CI lacked a file) is gone with the feature.



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


def test_unset_now_means_every_file_on_both_scopes():
    """**REVERSED in v0.31.0.** Unset used to refuse everything.

    The state nobody actually ran: the README itself told operators to set `*`, so the default
    produced a setup step rather than a control, and a bound every operator removes teaches
    people to paste `*` without reading. See `policy.DEFAULT_ENABLED`.
    """
    policy = _config.settings_from_env({}).policy
    assert policy is not None
    assert policy.read.all_files and policy.modify.all_files


@pytest.mark.parametrize("value", [
    "https://drive.google.com/drive/folders/XYZ",   # a folder, refused loudly by design
    "1a2b3c",                                       # a bare id, indistinguishable from a typo
    "# only a comment",                             # parses, lists nothing
])
def test_a_malformed_list_is_refused_loudly_rather_than_widened(value):
    """The distinction that carries the reversal: **unset is not the same as unparseable.**

    Unset is an operator who has not narrowed anything, and now means `*`. Malformed is an
    operator who *tried* and failed — and widening that to `*` would hand them the exact
    opposite of what they wrote, silently.

    It raises rather than falling back to an empty scope, which is stronger than the old
    behaviour: the server does not start with a policy nobody can read, instead of starting and
    refusing everything for reasons the operator has to go looking for.
    """
    with pytest.raises(AllowlistError):
        _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": value})


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


def test_a_path_value_is_diagnosed_not_loaded():
    """There is no file to read. A path-shaped value is a mistake worth naming — silently
    reading it would put the real policy somewhere the config does not show."""
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": "/etc/csa/wg-documents.txt"})
    message = str(e.value)
    assert "looks like a file path" in message
    assert "set in the environment, not read from a file" in message


@pytest.mark.parametrize("path_shaped", [
    "/etc/csa/allow.txt", "~/allow.txt", "./allow.list", "../a.conf", "allowlist.yaml",
    "C:\\Users\\kurt\\allow.txt",
])
def test_every_path_shape_is_diagnosed(path_shaped):
    from csa_google_workspace.allowlist import AllowlistError
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": path_shaped})
    assert "file path" in str(e.value)


def test_a_url_is_never_mistaken_for_a_path():
    """The path check runs after URL extraction, so a real URL cannot trip it."""
    policy = _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": _ALLOW_URL}).policy
    assert policy is not None and policy.modify.ids == frozenset({_ALLOW_ID})


def test_a_refusal_does_not_send_anyone_looking_for_a_file_to_create():
    """The allowlist lives in the environment; there has never been a file. A message implying
    otherwise sends somebody to create one that would never be read."""
    with pytest.raises(AllowlistError) as e:
        _config.settings_from_env({"CSA_GW_ALLOWLIST_MODIFY": "1a2b3c"})
    assert "create" not in str(e.value).lower()


# --- what the user is told at startup --------------------------------------

def test_startup_warnings_say_when_nothing_is_permitted():
    """**No longer reachable from the environment**, and the message still has to be right.

    After v0.31.0 an unset variable means `*` and a malformed one raises, so no configuration
    produces a silently-empty scope. An *embedder* can still build one — `Policy(read=
    Scope.nothing())` through the DI seam — and when they do, the startup line is what tells
    somebody why nothing works. Constructed directly here because that is now the only route to
    it; deleting the test would drop the message from coverage rather than retire it.
    """
    from csa_google_workspace.policy import Policy, Scope
    settings = replace(
        _config.settings_from_env({}),
        policy=Policy(enabled=frozenset(),
                      read=Scope.nothing(reason="set CSA_GW_ALLOWLIST_READ"),
                      modify=Scope.nothing(reason="set CSA_GW_ALLOWLIST_MODIFY")))
    lines = " ".join(_config.startup_warnings(settings))
    assert "nothing permitted" in lines


def test_an_unconfigured_server_says_it_is_unrestricted():
    """The default is now the permissive one, so the startup line has to be loud about it.
    "Everything" must never be something an operator discovers later."""
    lines = " ".join(_config.startup_warnings(_config.settings_from_env({})))
    assert lines.count("UNRESTRICTED") == 2


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


# --- CSA_GW_PROFILE ---------------------------------------------------------

def test_a_profile_sets_the_capabilities():
    from csa_google_workspace.policy import PROFILES
    settings = _config.settings_from_env({"CSA_GW_PROFILE": "commenter"})
    assert settings.profile == "commenter"
    assert settings.policy is not None
    assert settings.policy.enabled == PROFILES["commenter"]


@pytest.mark.parametrize("name", ["reader", "commenter", "writer", "fileOrganizer",
                                 "organizer", "editor", "full"])
def test_every_profile_name_is_accepted_and_case_insensitive(name):
    """Aliases included: `editor` and `full` are our pre-v0.31.0 vocabulary and keep working.

    `fileOrganizer` is the one worth parametrizing by name — it is Drive's own camelCase
    spelling, and an earlier draft of `resolve_profile` lowercased the input and compared
    against the raw keys, so the documented name was rejected as unknown."""
    from csa_google_workspace.policy import PROFILES, resolve_profile
    expected = PROFILES[resolve_profile(name)]
    for spelling in (name, name.upper(), f"  {name} "):
        policy = _config.settings_from_env({"CSA_GW_PROFILE": spelling}).policy
        assert policy is not None and policy.enabled == expected


def test_an_unknown_profile_lists_the_real_ones():
    """A typo'd profile must not silently fall back to the default — that would be a wider
    policy than the operator asked for."""
    with pytest.raises(ValueError) as e:
        _config.settings_from_env({"CSA_GW_PROFILE": "admin"})
    message = str(e.value)
    assert "not a known profile" in message
    for name in ("reader", "commenter", "writer", "fileOrganizer", "organizer"):
        assert name in message


@pytest.mark.parametrize("label,target", [
    ("manager", "organizer"), ("Content Manager", "fileOrganizer"),
    ("viewer", "reader"), ("contributor", "writer"), ("owner", "organizer"),
])
def test_a_google_ui_label_is_refused_by_naming_the_api_name(label, target):
    """Config accepts one spelling - the API string, because it is what `get_file_permissions`
    returns. But an operator who writes `manager` has not made a typo; they used Google's own
    interface label. A bare "unknown profile" would send them to the docs to discover that the
    thing they already know is called something else here."""
    with pytest.raises(ValueError) as e:
        _config.settings_from_env({"CSA_GW_PROFILE": label})
    message = str(e.value)
    assert target in message
    assert "interface label" in message


def test_an_explicit_capability_list_overrides_a_profile():
    """The list is the more specific statement, so it wins — and it is logged, because the
    operator plainly believed the profile was doing something."""
    from csa_google_workspace.policy import COMMENT_CREATE
    policy = _config.settings_from_env({"CSA_GW_PROFILE": "full",
                                        "CSA_GW_CAPABILITIES": "comment.create"}).policy
    assert policy is not None and policy.enabled == frozenset({COMMENT_CREATE})


def test_no_profile_keeps_the_historical_default():
    from csa_google_workspace.policy import DEFAULT_ENABLED
    settings = _config.settings_from_env({})
    assert settings.profile is None
    assert settings.policy is not None and settings.policy.enabled == DEFAULT_ENABLED


def test_the_profile_appears_in_the_startup_warnings():
    lines = " ".join(_config.startup_warnings(
        _config.settings_from_env({"CSA_GW_PROFILE": "reader"})))
    assert "profile: reader" in lines and "no mutations at all" in lines
