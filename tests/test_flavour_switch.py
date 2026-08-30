"""A flavour publishes another server's surface — allowed *and* advertised.

**C2.** `CSA_GW_FLAVOUR=google|claude|full`, default `full`.

The feature has two halves and only works with both. Only those tools are **allowed**, and only
those tools are **advertised** — the rest are never registered.

**The advertising half is the one that makes it a drop-in**, and an earlier framing of this
feature missed it. Matching names is not enough: a model shown 36 tools behaves differently from
one shown 8, however identical the eight are. It plans differently, reaches for things absent
from the server it is standing in for, and spends context on schemas it will never call.
Advertising without allowing would be a lie; allowing without advertising is what this server did
until v0.32.0 — every profile registered all 36 tools and refused at call time.

**The tradeoff, and why `ALWAYS` exists.** Hiding a tool changes what a refusal looks like: a
gated-but-registered `share_file` says *"the `file.share` capability is disabled; an operator
enables it"*, while an absent one reads as *"this server cannot do that"* — inviting the
route-around-a-refusal failure `csa-gw://help/capabilities` exists to prevent. So a flavour says
what it is hiding, and three tools survive every flavour because they are not Drive operations:
without `authenticate` an install with no token is bricked rather than restricted, and hiding
`describe_configuration` or `read_server_resource` would hide the explanation of the hiding.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import _flavours, settings_from_env
from csa_google_workspace.mcp.server import create_server


def server(flavour=None):
    env = {"CSA_GW_FLAVOUR": flavour} if flavour else {}
    return create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(env))


def tools(flavour=None) -> set[str]:
    return {t.name for t in asyncio.run(server(flavour).list_tools())}


class TestTheSurfaceIsWhatTheVendorPublishes:
    def test_google_publishes_its_eight_plus_the_always_set(self):
        """Google's surface is the claude.ai connector's minus the three it declines to ship —
        `update_file`, `share_file`, `trash_file`. That is a choice by a vendor who could have
        exposed more, which is exactly why it is worth being able to adopt wholesale."""
        assert tools("google") == _flavours._GOOGLE | _flavours.ALWAYS
        assert len(_flavours._GOOGLE) == 8

    def test_claude_publishes_its_eleven_plus_the_always_set(self):
        assert tools("claude") == _flavours._CLAUDE | _flavours.ALWAYS
        assert len(_flavours._CLAUDE) == 11

    def test_google_is_exactly_claude_minus_the_three_it_declines(self):
        assert _flavours._CLAUDE - _flavours._GOOGLE == {
            "update_file", "share_file", "trash_file"}

    def test_full_is_the_default_and_hides_nothing(self):
        assert tools() == tools("full")
        assert len(tools()) > len(tools("claude"))

    @pytest.mark.parametrize("flavour", ["google", "claude"])
    def test_every_tool_a_flavour_names_actually_exists_here(self, flavour):
        """The alignment work is what makes the switch cheap, and this is what proves it still
        holds. A vendor tool we do not implement would silently shrink the flavour below the
        surface it claims to be — a drop-in that quietly does less."""
        missing = _flavours.FLAVOURS[flavour] - tools("full")
        assert missing == set(), f"{flavour} names tools this server does not have: {missing}"


class TestAdvertisingIsTheHalfThatMatters:
    """Not registered, rather than registered-and-refused. Asserted directly, because the
    difference is the entire feature."""

    @pytest.mark.parametrize("tool", ["create_comment", "list_comments", "export_comments",
                                      "replace_text", "update_cells"])
    def test_a_hidden_tool_is_absent_from_list_tools(self, tool):
        assert tool in tools("full"), "precondition: this server has the tool"
        assert tool not in tools("google")

    @pytest.mark.parametrize("tool", ["create_comment", "replace_text"])
    def test_a_hidden_tool_cannot_be_called_either(self, tool):
        """Advertising and allowing must agree. A tool absent from the listing but still
        callable would be worse than either — an undocumented surface.

        The message is asserted, not just the raise. Every failing call here raises `ToolError`,
        including a PUBLISHED tool that merely errored — so `pytest.raises(Exception)` alone
        passes whether or not the tool was ever hidden, which is the entire claim. `Unknown tool`
        is the only part that distinguishes the two.
        """
        app = server("google")
        with pytest.raises(Exception) as e:
            asyncio.run(app.call_tool(tool, {"fileId": "x"}))
        assert "Unknown tool" in str(e.value), (
            f"{tool} was reached — it is registered, merely failing")

    def test_the_same_call_reaches_a_tool_the_flavour_publishes(self):
        """The contrast that gives the test above its meaning: an identical call to a PUBLISHED
        tool gets past dispatch and fails on its own merits ("not found"), never `Unknown tool`."""
        with pytest.raises(Exception) as e:
            asyncio.run(server("google").call_tool("get_file_metadata", {"fileId": "x"}))
        assert "Unknown tool" not in str(e.value)
        assert "not found" in str(e.value)

    def test_the_comment_surface_is_gone_under_google(self):
        """The sharpest case: comments are this server's whole differentiator, and Google's
        server has no comment tools at all. A `google` flavour that kept them would not be
        Google's surface."""
        assert not [t for t in tools("google") if "comment" in t]


class TestTheThreeThatSurviveEveryFlavour:
    """`ALWAYS` is not a hedge — these are not Drive operations."""

    @pytest.mark.parametrize("flavour", ["google", "claude"])
    @pytest.mark.parametrize("tool", sorted(_flavours.ALWAYS))
    def test_it_survives(self, flavour, tool):
        assert tool in tools(flavour)

    def test_authenticate_survives_because_otherwise_the_server_is_bricked(self):
        """An install with no cached token and no `authenticate` cannot obtain one. That is not
        a restricted server, it is a broken one."""
        assert "authenticate" in tools("google")

    def test_the_tool_that_explains_the_hiding_is_not_hidden(self):
        """Hiding `describe_configuration` under a restrictive flavour would remove the only
        in-band way to learn that the surface is restricted."""
        assert "describe_configuration" in tools("google")

    def test_always_adds_nothing_a_vendor_already_publishes(self):
        """If `ALWAYS` overlapped a vendor's surface the counts would double-count and the
        set arithmetic in these tests would quietly stop meaning anything."""
        assert not _flavours.ALWAYS & _flavours._CLAUDE


class TestItSaysWhatItIsHiding:
    """A restriction that announces itself is a restriction; a silent one is a missing feature."""

    def test_the_instructions_tell_the_model_absent_means_switched_off(self):
        note = server("google").instructions
        assert "SWITCHED OFF BY CONFIGURATION" in note
        assert "not impossible" in note

    def test_the_instructions_tell_it_not_to_route_around(self):
        """The failure worth preventing is not the agent giving up — it is the agent satisfying
        the request through another integration, which succeeds and looks fine."""
        assert "another integration" in server("google").instructions

    def test_full_adds_no_note_at_all(self):
        """An unrestricted server must not carry restriction language; it would be describing a
        state it is not in, in the prompt, every session."""
        assert _flavours.instruction_note("full") == ""
        assert "TOOL SURFACE RESTRICTED" not in server().instructions

    def test_describe_configuration_reports_the_flavour_and_the_counts(self):
        out = asyncio.run(server("google").call_tool("describe_configuration", {}))
        text = str(out)
        assert "google" in text
        assert "hidden" in text, "a restriction that cannot say its own size discloses little"

    def test_the_counted_note_is_empty_for_full(self):
        assert _flavours.describe("full", published=36, hidden=0) == ""


class TestTheValueIsRefusedRatherThanGuessed:
    def test_an_unknown_flavour_is_an_error(self):
        """The worst available outcome is a silent fallback to `full`: somebody typing
        `CSA_GW_FLAVOUR=googl` to RESTRICT the server would get the unrestricted one."""
        with pytest.raises(ValueError) as e:
            settings_from_env({"CSA_GW_FLAVOUR": "googl"})
        assert "google" in str(e.value), "the refusal must name the values that work"

    @pytest.mark.parametrize("spelling", ["GOOGLE", "  google ", "Google"])
    def test_case_and_whitespace_do_not_matter(self, spelling):
        assert settings_from_env({"CSA_GW_FLAVOUR": spelling}).flavour == "google"

    def test_unset_is_full(self):
        assert settings_from_env({}).flavour == "full"


class TestItComposesWithThePolicyRatherThanReplacingIt:
    """Two different questions: a flavour says which tools EXIST, a profile says what they may
    DO. Neither substitutes for the other, and a flavour must not widen anything."""

    def test_a_flavour_does_not_grant_a_capability(self):
        settings = settings_from_env({"CSA_GW_FLAVOUR": "claude", "CSA_GW_PROFILE": "reader"})
        assert settings.policy is not None
        assert settings.policy.enabled == frozenset(), (
            "the flavour must not have widened the policy")

    def test_a_narrow_profile_still_refuses_a_tool_the_flavour_publishes(self):
        """`claude` publishes `share_file`; `reader` forbids `file.share`. The tool is listed
        and the call is refused — which is correct, and is why the flavour is not a policy."""
        from csa_google_workspace.policy import PROFILES, Policy, PolicyBackend

        settings = settings_from_env({"CSA_GW_FLAVOUR": "claude", "CSA_GW_PROFILE": "reader"})
        backend = PolicyBackend(FakeBackend({}), Policy(enabled=PROFILES["reader"]))
        app = create_server(lambda: Workspace(backend), settings=settings)
        assert "share_file" in {t.name for t in asyncio.run(app.list_tools())}
        with pytest.raises(Exception) as e:
            asyncio.run(app.call_tool(
                "share_file", {"fileId": "x", "emailAddress": "a@b.com"}))
        # The refusal a *policy* produces, not the one a flavour produces — it names the
        # capability and says an operator can enable it. `Unknown tool` here would mean the
        # flavour had swallowed the tool and the policy never got its say.
        assert "file.share" in str(e.value) and "Unknown tool" not in str(e.value)
