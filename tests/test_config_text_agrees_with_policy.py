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
from csa_google_workspace.policy import (
    ALL_CAPABILITIES,
    DEFAULT_DISABLED,
    DEFAULT_ENABLED,
    IRREVERSIBLE,
)


def rendered(**env) -> str:
    return render_config(settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", **env}))


class TestTheDefaultSentence:
    def test_every_default_capability_is_listed(self):
        text = rendered()
        for capability in DEFAULT_ENABLED:
            assert f"`{capability}`" in text, f"{capability} is on by default and unmentioned"

    def test_it_does_not_claim_to_exclude_something_it_includes(self):
        """The exact contradiction that shipped: listing `file.trash` and then saying the
        default excludes trashing.

        Skipped when nothing is disabled, because there is then no excludes clause at all -
        and that state has its own tests below, since it is the one that shipped broken."""
        if not DEFAULT_DISABLED:
            pytest.skip("nothing is disabled by default; see TestTheEmptyCaseIsTheOneThatShipped")
        text = rendered()
        excludes = text.split("which excludes", 1)[1].split("\n", 1)[0]
        for capability in DEFAULT_ENABLED:
            assert f"`{capability}`" not in excludes, (
                f"{capability} is IN the default set and the text says it is excluded")

    def test_the_excluded_ones_are_exactly_the_disabled_ones(self):
        if not DEFAULT_DISABLED:
            pytest.skip("nothing is disabled by default; see the empty-case tests below")
        text = rendered()
        excludes = text.split("which excludes", 1)[1].split("\n", 1)[0]
        for capability in DEFAULT_DISABLED:
            assert f"`{capability}`" in excludes, f"{capability} is off by default, unmentioned"


class TestTheEmptyCaseIsTheOneThatShipped:
    """`DEFAULT_DISABLED` became EMPTY in v0.31.0 when everything was turned on by default, and
    the sentence rendered:

        "...which excludes  - the three Google gives you no way to undo."

    An empty gap where a list should be, a hardcoded count that was four by then, and a claim
    that the default excludes capabilities the same sentence had just listed as INCLUDED. It
    understated the default's reach, which is the dangerous direction, in the resource whose
    entire job is telling the truth about the configuration.

    **Both guards above passed it, vacuously.** One iterates `DEFAULT_ENABLED` checking nothing
    appears inside an excludes clause that had become the empty string; the other iterates
    `DEFAULT_DISABLED`, so its body never ran. Iterating a collection that can be empty is not a
    check when it is empty - that is the case to test, not the case to skip.
    """

    def test_it_never_says_it_excludes_nothing_in_particular(self):
        """The literal broken rendering. No assertion above could see it."""
        text = rendered()
        assert "excludes  " not in text
        assert "excludes -" not in text and "excludes," not in text

    def test_when_nothing_is_disabled_it_says_so_plainly(self):
        if DEFAULT_DISABLED:
            pytest.skip("something is disabled by default; the excludes-clause tests apply")
        text = rendered()
        assert "which excludes" not in text, (
            "with nothing disabled there is no excludes clause to write; saying "
            "'excludes <nothing>' is how the broken sentence read")
        assert "everything" in text.lower(), "the default's reach must be stated, not implied"

    def test_the_irreversible_ones_are_named_when_they_are_on_by_default(self):
        """Understating this is the dangerous direction: an operator reading that the default
        excludes the irreversible capabilities will not narrow, and it does not."""
        on_by_default = IRREVERSIBLE & DEFAULT_ENABLED
        if not on_by_default:
            pytest.skip("no irreversible capability is on by default")
        text = rendered()
        for capability in on_by_default:
            assert f"`{capability}`" in text, (
                f"{capability} is irreversible AND on by default, and is not named")

    def test_no_count_is_hardcoded(self):
        """"the three" survived the set becoming four. A number in prose that a constant
        controls has to be derived from it."""
        text = rendered()
        for word in ("the three ", "the two ", "the four ", "the five "):
            assert word not in text, (
                f"{word!r} is a hardcoded count; derive it from the constant so it cannot "
                f"drift the way 'the three' did")

    def test_the_stated_total_matches_the_constant(self):
        text = rendered()
        assert f"all {len(DEFAULT_ENABLED)} capabilities" in text or DEFAULT_DISABLED


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
