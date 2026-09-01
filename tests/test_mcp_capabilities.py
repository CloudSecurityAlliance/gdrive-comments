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
from csa_google_workspace.mcp._capabilities import (
    TOOL_CAPABILITIES,
    reachable_capabilities,
)
from csa_google_workspace.mcp._config import settings_from_env
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


def test_the_reachable_set_never_exceeds_what_exists():
    """The direction that would be a bug: claiming reachability for a capability that is not a
    capability, or for one the profile does not grant."""
    from csa_google_workspace.policy import PROFILES
    assert reachable_capabilities() <= set(ALL_CAPABILITIES)
    assert reachable_capabilities() <= PROFILES["organizer"]


def test_describe_configuration_separates_enabled_from_reachable():
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    # Asserted as a property rather than a fixed set, so closing a gap does not break the
    # test that exists to prove gaps are reported. The invariant is that the three lists
    # partition what the policy enables, and that nothing is in two of them.
    enabled = set(out["capabilities_enabled"])
    reachable = set(out["capabilities_reachable"])
    unreachable = set(out["capabilities_unreachable"])
    assert reachable | unreachable == enabled
    assert not (reachable & unreachable)
    assert not (enabled & set(out["capabilities_disabled"]))
    # Comment writes are reachable today; anything still unreachable must be real.
    assert {"comment.create", "comment.reply", "comment.resolve"} <= reachable


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


def test_the_writer_profile_is_fully_reachable():
    """The gap is closed: every capability the default profile enables has a tool behind it.

    This started as a test that the *gap was reported*, which is why the reporting exists. It
    is inverted rather than deleted, because "advertises nothing it cannot do" is the property
    actually worth holding — and the reporting machinery still earns its keep for `full`, whose
    file.update/trash/share have no tools and are not planned to."""
    from csa_google_workspace.policy import PROFILES
    assert PROFILES["writer"] <= reachable_capabilities()

    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    assert out["capabilities_unreachable"] == []


def test_full_no_longer_has_an_unreachable_capability():
    """The acceptance test for A5, and the reason this file exists.

    `full` used to enable three operations - update, trash, share - that no tool implemented,
    so the server advertised authority it could not exercise. Each now has a tool, and the
    right assertion is that the set is EMPTY rather than that it contains those three: an
    assertion naming them would have had to be deleted to let the work land, which is a test
    holding a gap open rather than tracking one.
    """
    env = dict(ENV, CSA_GW_PROFILE="full")
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(env))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    assert out["capabilities_unreachable"] == [], (
        f"enabled but no tool uses them: {out['capabilities_unreachable']}. Either add the "
        f"tool or stop claiming the capability.")


def test_the_config_resource_still_flags_a_gap_when_there_is_one(monkeypatch):
    """The mechanism, exercised against a synthetic gap.

    Tested separately from the state above because the two say different things: that one is
    "we have no gap today", this one is "we would still notice one". Without this, closing the
    last gap would silently retire the reporting along with it.
    """
    # Patch the TABLE, not the function. Both consumers do `from .._capabilities import
    # reachable_capabilities`, binding it by value at import time, so replacing the function
    # at its source changes nothing for them. The function reads the table on every call, so
    # the table is the seam that actually works - and it is the thing a real regression would
    # touch anyway.
    from csa_google_workspace.mcp import _capabilities
    monkeypatch.setattr(_capabilities, "TOOL_CAPABILITIES",
                        {"create_comment": "comment.create"})
    env = dict(ENV, CSA_GW_PROFILE="full")
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(env))
    out = asyncio.run(app.call_tool("describe_configuration", {})).structured_content
    assert "file.share" in out["capabilities_unreachable"]

    flat = " ".join(" ".join(c.content for c in
                             asyncio.run(app.read_resource("csa-gw://config"))).split())
    assert "not reachable through this server" in flat
    assert "do not plan work around them" in flat
    assert "not a mistake in the policy" in flat


def _descriptions() -> dict[str, str]:
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(ENV))
    return {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}


def test_every_gated_tool_names_the_capability_it_requires():
    """#332 settled what a tool description is for: *"name the capability it requires and
    stop"*. Fourteen of the twenty-seven gated tools did not do the first half.

    That is not cosmetic. A model that cannot see which capability a tool needs cannot tell the
    user WHY a refusal happened or WHAT to change, and the refusal message is the only other
    place the name appears - which is after the failure rather than before it. Every content and
    file tool already named its capability; every comment tool did not, so the surface was
    inconsistent as well as thin.
    """
    descriptions = _descriptions()
    missing = sorted(name for name, capability in TOOL_CAPABILITIES.items()
                     if capability and capability not in descriptions.get(name, ""))
    assert missing == [], (
        f"these tools are gated but their description never names the capability: {missing}. "
        f"A model reading the description cannot then explain a refusal or say what to change. "
        f"Add the capability name; do NOT add whether it is currently enabled - that is "
        f"`describe_configuration`'s job and it drifts (#332).")


def test_the_reverse_is_deliberately_not_asserted():
    """**`TOOL_CAPABILITIES` is a floor, not a complete statement**, so "an ungated tool must
    name no capability" would be wrong - and this test exists to stop somebody adding it.

    `export_comments` is declared `None` and its description names `content.write` and
    `file.create`. That is CORRECT: with `destination="sheet"` it creates a Drive file and
    writes to it, so those capabilities genuinely apply to that argument. `apply_comment_actions`
    is declared `comment.reply` and needs `comment.resolve` too, for the same reason - the
    requirement depends on the arguments, and a one-capability-per-tool map cannot say so.

    This is the same lossiness as the dynamic gate on `create_reply` (see
    `tests/test_policy_matrix.py`): the static table is a useful second opinion and not a
    complete specification. Where the two disagree, EXECUTION decides.
    """
    descriptions = _descriptions()
    assert TOOL_CAPABILITIES.get("export_comments") is None
    assert "file.create" in descriptions["export_comments"], (
        "export_comments creates a Drive file for destination='sheet' and should say which "
        "capability that needs, even though the map declares it ungated")
