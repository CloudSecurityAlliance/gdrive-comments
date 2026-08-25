"""Every registered tool must declare which capability it can require.

This exists because the server advertised authority it could not exercise. `describe_configuration`
reported `content.write`, `file.create`, `comment.edit` and `comment.delete` as enabled — true of
the *policy* — while no tool in the server used any of them. A model read that, planned work on
the strength of it, and only then found the tools missing.

The guard is the same shape as `policy._GATES`: a name absent from the map is a failure, not a
default, so a new tool cannot arrive undeclared and silently widen what the server claims.
"""
import asyncio

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import settings_from_env
from csa_google_workspace.mcp._tools._capabilities import (
    TOOL_CAPABILITIES,
    reachable_capabilities,
)
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import ALL_CAPABILITIES

ENV = {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
       "CSA_GW_PROFILE": "editor"}


def _tool_names():
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    return {t.name for t in asyncio.run(app.list_tools())}


def test_every_registered_tool_declares_a_capability():
    missing = sorted(_tool_names() - set(TOOL_CAPABILITIES))
    assert missing == [], (
        f"no capability declared for: {missing}. Add each to TOOL_CAPABILITIES — `None` if it "
        f"is a read. Without an entry the server cannot report what it is able to do.")


def test_no_declaration_names_a_tool_that_does_not_exist():
    """A stale entry inflates `capabilities_reachable`, which is the direction that misleads."""
    stale = sorted(set(TOOL_CAPABILITIES) - _tool_names())
    assert stale == []


def test_declared_capabilities_are_real():
    named = {c for c in TOOL_CAPABILITIES.values() if c is not None}
    assert not (named - set(ALL_CAPABILITIES))


def test_the_reachable_set_is_smaller_than_the_editor_profile():
    """The condition that caused the bug, asserted rather than assumed: this server exposes
    only part of the library, so some enabled capabilities are genuinely unreachable. If this
    ever becomes equality the reporting is still correct — but the gap is real today."""
    from csa_google_workspace.policy import PROFILES
    assert reachable_capabilities() < PROFILES["editor"]


def test_describe_configuration_separates_enabled_from_reachable():
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    assert "content.write" in out["capabilities_enabled"]
    assert "content.write" not in out["capabilities_reachable"]
    assert "content.write" in out["capabilities_unreachable"]
    # And the three that *are* usable are reported as such.
    assert set(out["capabilities_reachable"]) == {"comment.create", "comment.reply",
                                                 "comment.resolve"}


def test_unrestricted_is_distinguishable_from_empty():
    """`modify_scope: every file` with `modifiable_file_ids: []` read as a contradiction — one
    reader took it for an allowlist that was doing no work. The boolean removes the ambiguity."""
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    assert out["modify_unrestricted"] is True and out["modifiable_file_ids"] == []

    listed = {"CSA_GW_ALLOWLIST_READ": "*",
              "CSA_GW_ALLOWLIST_MODIFY":
                  "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit"}
    app2 = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(listed))
    out2 = asyncio.run(app2.call_tool("describe_configuration", {})).structured_content
    assert out2["modify_unrestricted"] is False and len(out2["modifiable_file_ids"]) == 1


def test_the_config_resource_flags_the_unreachable_ones():
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    text = " ".join(c.content for c in asyncio.run(app.read_resource("csa-gw://config")))
    flat = " ".join(text.split())
    assert "not reachable through this server" in flat
    assert "do not plan work around them" in flat
    assert "not a mistake in the policy" in flat
