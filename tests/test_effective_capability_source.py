"""Which control actually decided the capabilities — and never reporting the one that did not.

**RR-005**, from the 2026-09-01 correctness review. With both `CSA_GW_PROFILE` and
`CSA_GW_CAPABILITIES` set, the explicit list wins and the profile is **ignored** — the log said so
correctly, and then every reporting surface rendered the ignored profile as active:

    log:    ...the explicit capability list wins and the profile is ignored
    config: Profile: **reader**
            Available here: `comment.create`

`reader` grants nothing, so those two lines contradict each other — in exactly the case where an
operator supplied two controls and most needs a straight answer. A debug report generated through
`describe_configuration` would have misled whoever read it.

The fix separates **what was set** from **what decided**: `Settings.profile` still holds the name,
because *"you set this and it did nothing"* is the useful thing to say, and
`Settings.capability_source` says which control was in force.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp._config import startup_warnings
from csa_google_workspace.mcp._resources import render_config
from csa_google_workspace.mcp.server import create_server

BOTH = {"CSA_GW_PROFILE": "reader", "CSA_GW_CAPABILITIES": "comment.create",
        "CSA_GW_ALLOWLIST_READ": "*"}


def described(env):
    app = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(env))
    return asyncio.run(app.call_tool("describe_configuration", {})).structured_content


class TestTheSourceIsTracked:
    @pytest.mark.parametrize("env,expected", [
        ({}, "default"),
        ({"CSA_GW_PROFILE": "reader"}, "profile"),
        ({"CSA_GW_CAPABILITIES": "comment.create"}, "explicit"),
        (BOTH, "explicit"),
    ])
    def test_capability_source_names_what_decided(self, env, expected):
        assert settings_from_env(env).capability_source == expected

    def test_the_profile_name_is_still_kept_when_ignored(self):
        """Deliberately not cleared. An operator who set a profile that did nothing needs to be
        told that, which is impossible if the name is discarded."""
        settings = settings_from_env(BOTH)
        assert settings.profile == "reader"
        assert settings.capability_source == "explicit"


class TestNoSurfaceReportsAnIgnoredProfileAsActive:
    def test_the_config_resource_says_ignored(self):
        text = render_config(settings_from_env(BOTH))
        assert "IGNORED" in text
        assert "Profile: **reader**" not in text, (
            "rendered the ignored profile as the active one, directly above a capability list "
            "that `reader` does not grant")

    def test_the_config_resource_still_names_the_profile_that_was_set(self):
        assert "reader" in render_config(settings_from_env(BOTH))

    def test_describe_configuration_flags_it(self):
        out = described(BOTH)
        assert out["profile"] == "reader"
        assert out["profile_ignored"] is True
        assert out["capability_source"] == "explicit"

    def test_the_startup_warning_describes_the_set_in_force(self):
        """It warned `profile: reader - no mutations at all` while `comment.create` was enabled."""
        warnings = " ".join(startup_warnings(settings_from_env(BOTH)))
        assert "IGNORED" in warnings
        assert "no mutations at all" not in warnings, (
            "described reader's empty set as though it were in force")
        assert "comment.create" in warnings


class TestAProfileThatDOESDecideIsReportedNormally:
    """The regression risk of the fix: over-reporting "ignored" would be as wrong as under-."""

    def test_the_resource_reports_an_active_profile_plainly(self):
        text = render_config(settings_from_env({"CSA_GW_PROFILE": "commenter",
                                                "CSA_GW_ALLOWLIST_READ": "*"}))
        assert "Profile: **commenter**" in text
        assert "IGNORED" not in text

    def test_describe_configuration_does_not_flag_it(self):
        out = described({"CSA_GW_PROFILE": "commenter", "CSA_GW_ALLOWLIST_READ": "*"})
        assert out["profile"] == "commenter"
        assert out["profile_ignored"] is False
        assert out["capability_source"] == "profile"

    def test_no_profile_set_is_not_an_ignored_profile(self):
        out = described({"CSA_GW_ALLOWLIST_READ": "*"})
        assert out["profile"] is None
        assert out["profile_ignored"] is False
        assert out["capability_source"] == "default"
