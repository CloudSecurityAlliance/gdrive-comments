"""Unattended sharing must be asked for, not inherited from the environment.

**CODX-2026-09-01-02**, from the 2026-09-01 audit. Three separately-reasonable behaviours composed
into something nobody chose:

1. `demo` takes its share recipient from `CSA_GW_DEMO_SHARE` if `--share` is absent.
2. `--auto` sets `confirm=None`, so no step is confirmed.
3. `file.share` has been **on by default since v0.31.0**, so the share step is reachable on an
   unconfigured install — and the step suppressed the Drive notification.

Together: an unattended demo could grant a real person access to real files with nobody in the
loop and no notification. Bounded — the files are demo-created and cleanup revokes the grant — but
live if the run is interrupted between the two.

A fourth behaviour made it stickier: `configure` carries every `CSA_GW_*` variable into the Desktop
config, so a value meant for one run became persistent ambient state.
"""
from __future__ import annotations

from csa_google_workspace.mcp import _desktop


class _Stop(Exception):
    """Raised by the probe to stop the run once the value under test is captured."""


class TestDemoOnlyVariablesAreNotPersisted:
    def test_the_share_recipient_is_not_carried_into_desktop_config(self):
        """The config is where policy state persists. A demo recipient is not policy, and it is
        the one demo variable that grants somebody access."""
        carried = _desktop.carried_env({"CSA_GW_DEMO_SHARE": "someone@example.com",
                                        "CSA_GW_PROFILE": "commenter"})
        assert "CSA_GW_DEMO_SHARE" not in carried
        assert carried["CSA_GW_PROFILE"] == "commenter", "real policy must still be carried"

    def test_the_demo_repo_is_not_carried_either(self):
        """Not a security issue on its own — included because "demo-only" is the category that
        should not persist, and drawing the line per-variable invites the next one to be missed."""
        assert "CSA_GW_DEMO_REPO" not in _desktop.carried_env({"CSA_GW_DEMO_REPO": "x/y"})

    def test_the_client_secret_is_still_excluded(self):
        """The original member of that set. Asserted so widening it cannot quietly drop it."""
        assert "CSA_GW_CLIENT_SECRETS" not in _desktop.carried_env(
            {"CSA_GW_CLIENT_SECRETS": "/path/to/secret.json"})

    def test_an_ordinary_variable_is_carried(self):
        """The exclusions must stay exclusions. Desktop has no shell, so anything genuinely
        needed has to arrive through this config."""
        carried = _desktop.carried_env({"CSA_GW_READ_ONLY": "1", "PATH": "/usr/bin"})
        assert carried == {"CSA_GW_READ_ONLY": "1"}, "non-CSA_GW keys must not leak in either"


class TestUnattendedSharingIsExplicit:
    """`--auto` disables confirmation, so the environment cannot be the thing that decides.

    Tested through the REAL `_cli.main`, by replacing `Runner` with a probe that records the
    `share_with` it was handed and stops the run. The first draft of this class mirrored the
    resolution logic into the test file instead — which passes whether or not `_cli` still does
    the same thing, and is the "check that cannot fail" shape this repo keeps finding.
    """

    def _share_handed_to_runner(self, argv, env):
        from csa_google_workspace.demo import _cli

        captured = {}

        class Probe:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, **kwargs):
                captured.update(kwargs)
                raise _Stop

        original = _cli.Runner
        _cli.Runner = Probe
        try:
            _cli.main(list(argv), dict(env))
        except _Stop:
            pass
        finally:
            _cli.Runner = original
        assert "share_with" in captured, (
            "the run never reached Runner.run, so this test proved nothing")
        return captured["share_with"]

    def test_an_env_recipient_is_dropped_under_auto(self):
        assert self._share_handed_to_runner(
            ["--auto"], {"CSA_GW_DEMO_SHARE": "someone@example.com"}) == ""

    def test_an_explicit_flag_is_honoured_under_auto(self):
        assert self._share_handed_to_runner(
            ["--auto", "--share", "e@x.com"], {}) == "e@x.com"

    def test_the_flag_wins_over_the_environment(self):
        assert self._share_handed_to_runner(
            ["--auto", "--share", "flag@x.com"],
            {"CSA_GW_DEMO_SHARE": "env@x.com"}) == "flag@x.com"

    def test_an_interactive_run_still_honours_the_environment(self):
        """The variable is not banned - interactively the confirmation prompt IS the check, and
        removing a working convenience to fix an unattended hazard would be the wrong trade."""
        assert self._share_handed_to_runner(
            [], {"CSA_GW_DEMO_SHARE": "e@x.com"}) == "e@x.com"

    def test_it_says_why_it_ignored_the_variable(self):
        """Silently dropping it would read as the feature being broken. The message has to name
        the flag that would have worked.

        Captured from **stderr**, not stdout: `_echo` writes there deliberately, because a `demo`
        run shares a process image with the server and stdout is the JSON-RPC channel. The first
        draft of this test read stdout and got an empty string — which would have passed as
        vacuously as any other empty capture if the assertion had been weaker.
        """
        import contextlib
        import io

        from csa_google_workspace.demo import _cli

        class Probe:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, **kwargs):
                raise _Stop

        buffer = io.StringIO()
        original = _cli.Runner
        _cli.Runner = Probe
        try:
            with contextlib.redirect_stderr(buffer), contextlib.suppress(_Stop):
                _cli.main(["--auto"], {"CSA_GW_DEMO_SHARE": "someone@example.com"})
        finally:
            _cli.Runner = original
        printed = buffer.getvalue()
        assert "ignoring CSA_GW_DEMO_SHARE" in printed
        assert "--share someone@example.com" in printed, "must name the flag that would work"


class TestTheDemoTellsTheRecipient:
    def test_the_share_step_sends_a_notification(self):
        """The library's own `share()` documents `notify=True` *"deliberately: a share the
        recipient is told about is one somebody can notice and question"* — and the demo
        overrode it to False. A silent grant in a demonstration is the same defect as a silent
        grant anywhere; the demo is not a special case."""
        import inspect

        from csa_google_workspace.demo import _plan
        source = inspect.getsource(_plan)
        assert '"sendNotification": True' in source
        assert '"sendNotification": False' not in source
