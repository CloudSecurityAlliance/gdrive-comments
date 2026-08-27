"""The configuration text must agree with the configuration.

Two bugs of the same shape, one after the other, both found by a real install rather than by a
test — which is why these exist.

**The resource contradicted itself in a single paragraph.** `render_config` listed the default
set, correctly including `file.trash` and `file.update`, and then said it "excludes renaming,
trashing and sharing". True when written; false after v0.21.0 regrouped the profiles on
recoverability. In the one resource whose entire job is telling the truth about the config.

**The installer's grant notice described a config the user did not have.** It was hardcoded to
the default posture, and when it kept an existing environment instead of writing one, it told
somebody `file.share` was off while it was enabled. A notice about permissions has to be
GENERATED from the permissions.

Both are the same failure: prose about configuration, written once, drifting from the constant
it describes. Prose has no compiler, so the check goes here.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from csa_google_workspace.mcp._config import settings_from_env
from csa_google_workspace.mcp._resources import render_config
from csa_google_workspace.policy import ALL_CAPABILITIES, DEFAULT_DISABLED, DEFAULT_ENABLED


def rendered(**env) -> str:
    return render_config(settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", **env}))


class TestTheDefaultSentence:
    def test_every_default_capability_is_listed(self):
        text = rendered()
        for capability in DEFAULT_ENABLED:
            assert f"`{capability}`" in text, f"{capability} is on by default and unmentioned"

    def test_it_does_not_claim_to_exclude_something_it_includes(self):
        """The exact contradiction that shipped: listing `file.trash` and then saying the
        default excludes trashing."""
        text = rendered()
        excludes = text.split("which excludes", 1)[1].split("\n", 1)[0]
        for capability in DEFAULT_ENABLED:
            assert f"`{capability}`" not in excludes, (
                f"{capability} is IN the default set and the text says it is excluded")

    def test_the_excluded_ones_are_exactly_the_disabled_ones(self):
        text = rendered()
        excludes = text.split("which excludes", 1)[1].split("\n", 1)[0]
        for capability in DEFAULT_DISABLED:
            assert f"`{capability}`" in excludes, f"{capability} is off by default, unmentioned"


class TestItReportsTheACTUALPolicy:
    """Not the default one. This is the installer-notice bug, at the layer that should have
    prevented it."""

    def test_an_enabled_non_default_capability_is_reported_available(self):
        text = rendered(CSA_GW_CAPABILITIES="default,file.share")
        available = text.split("Available here:", 1)[1].split("\n", 1)[0]
        assert "`file.share`" in available, (
            "file.share was enabled and the config text did not say so - the exact shape of "
            "the notice that told somebody sharing was off while it was on")

    def test_a_disabled_default_capability_is_reported_refused(self):
        text = rendered(CSA_GW_CAPABILITIES="comment.create")
        refused = text.split("Refused:", 1)[1].split("\n", 1)[0]
        assert "`content.write`" in refused

    @pytest.mark.parametrize("capability", sorted(ALL_CAPABILITIES))
    def test_every_capability_appears_somewhere(self, capability):
        """Available or refused - never silently absent, which is how somebody ends up
        believing a permission they have is one they do not."""
        text = rendered(CSA_GW_CAPABILITIES="default,file.share")
        assert f"`{capability}`" in text


class TestTheDescribeVerb:
    """`csa-google-workspace-mcp describe` — so an installer can print the truth instead of
    assuming it, the same reason `--version` exists."""

    def run(self, **env):
        import os
        return subprocess.run(
            [sys.executable, "-m", "csa_google_workspace.mcp", "describe"],
            capture_output=True, text=True,
            env={**os.environ, "CSA_GW_ALLOWLIST_READ": "*", **env})

    def test_it_exits_zero_and_reports_the_policy(self):
        done = self.run()
        assert done.returncode == 0
        assert "effective configuration" in done.stderr

    def test_it_writes_to_stderr_not_stdout(self):
        """stdout is the JSON-RPC channel. A single stray byte on it corrupts a session, and
        this command shares an entry point with the server."""
        done = self.run()
        assert done.stdout == ""

    def test_it_reflects_a_non_default_capability_set(self):
        done = self.run(CSA_GW_CAPABILITIES="default,file.share")
        available = done.stderr.split("Available here:", 1)[1].split("\n", 1)[0]
        assert "`file.share`" in available
