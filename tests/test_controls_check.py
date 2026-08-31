"""The control check reports three states, and never mistakes the third for the first.

**T19/T27 (#189).** Three controls this project depends on are configured outside the
repository — the PyPI Trusted Publisher constrained to the `pypi` environment, that
environment's required reviewers, and branch protection on `main`. All three were recorded as
prose, and prose does not notice a setting toggled and forgotten.

`scripts/check_controls.py` asserts them. These tests exercise its **classification** offline,
by substituting the HTTP layer, because the interesting behaviour is not "can it reach
GitHub" but "what does it conclude, and what does it do when it cannot tell".

**Why that distinction carries the whole design.** A control check that cannot reach its
evidence and exits 0 is worse than no check: it reads as a control from the outside while
asserting nothing, and it is the exact failure this repository keeps finding in its own
history — an sdist grep that matched filenames only, a test asserting a default it did not
set, a config reference restating a policy from memory. So UNVERIFIABLE is a first-class
state, it is never collapsed into OK, and a run where *everything* was unverifiable fails.

The script is deliberately not importable as a module (it lives in `scripts/`, which is not a
package and needs the network), so it is loaded here by path — the same reason
`tests/test_release_history.py` covers only the offline half of its script.
"""
from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/check_controls.py"
WORKFLOW = ROOT / ".github/workflows/controls.yml"


@pytest.fixture(scope="module")
def controls():
    """Registered in `sys.modules` BEFORE executing, which is not optional here.

    The script uses `from __future__ import annotations` and a `@dataclass`, so every
    annotation is a string and `dataclasses` resolves them via
    `sys.modules[cls.__module__].__dict__`. A module loaded only by path is not in
    `sys.modules`, that lookup returns `None`, and every test errors with a bare
    `AttributeError: 'NoneType' object has no attribute '__dict__'` from inside the standard
    library - which names neither the script nor the cause.
    """
    spec = importlib.util.spec_from_file_location("check_controls", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[spec.name]
        raise
    return module


def responder(mapping):
    """A stand-in for `get()`: maps a URL substring to (status, payload)."""
    def get(url, token=None):
        for fragment, response in mapping.items():
            if fragment in url:
                return response
        raise AssertionError(f"unexpected URL in test: {url}")
    return get


REPO = "CloudSecurityAlliance/csa-google-workspace"
GOOD_PUBLISHER = {"attestation_bundles": [{"publisher": {
    "environment": "pypi", "repository": REPO, "workflow": "release.yml"}}]}
PYPI_INDEX = {"info": {"version": "9.9.9"}, "urls": [{"filename": "p-9.9.9-py3-none-any.whl"}]}


class TestThePublisherBinding:
    def test_a_pypi_environment_attestation_passes(self, controls, monkeypatch):
        monkeypatch.setattr(controls, "get", responder({
            "/pypi/": (200, PYPI_INDEX), "/integrity/": (200, GOOD_PUBLISHER)}))
        assert controls.check_publisher_environment(REPO).state == controls.OK

    def test_publishing_from_outside_the_gated_environment_is_a_violation(
            self, controls, monkeypatch):
        """The thing the constraint exists to prevent: a publish that did not pass the gate.

        `environment: None` is what an UNCONSTRAINED binding produces - PyPI's own default -
        so this is the shape the drift actually takes, not a hypothetical."""
        loose = {"attestation_bundles": [{"publisher": {
            "environment": None, "repository": REPO, "workflow": "release.yml"}}]}
        monkeypatch.setattr(controls, "get", responder({
            "/pypi/": (200, PYPI_INDEX), "/integrity/": (200, loose)}))
        assert controls.check_publisher_environment(REPO).state == controls.VIOLATED

    def test_a_publish_from_another_repository_is_a_violation(self, controls, monkeypatch):
        stolen = {"attestation_bundles": [{"publisher": {
            "environment": "pypi", "repository": "someone/else", "workflow": "release.yml"}}]}
        monkeypatch.setattr(controls, "get", responder({
            "/pypi/": (200, PYPI_INDEX), "/integrity/": (200, stolen)}))
        assert controls.check_publisher_environment(REPO).state == controls.VIOLATED

    def test_a_release_with_no_attestation_at_all_is_a_violation(self, controls, monkeypatch):
        """404 from the integrity endpoint means the newest release was not published by the
        trusted publisher, or attestations were switched off. Neither is a "cannot tell"."""
        monkeypatch.setattr(controls, "get", responder({
            "/pypi/": (200, PYPI_INDEX), "/integrity/": (404, None)}))
        assert controls.check_publisher_environment(REPO).state == controls.VIOLATED

    def test_pypi_being_unreachable_is_not_a_violation(self, controls, monkeypatch):
        """An outage is not a finding. Reporting one as a control failure trains people to
        ignore the check, which costs more than the check is worth."""
        monkeypatch.setattr(controls, "get", responder({"/pypi/": (0, "connection refused")}))
        assert controls.check_publisher_environment(REPO).state == controls.UNVERIFIABLE

    def test_a_406_is_not_read_as_success(self, controls, monkeypatch):
        """The bug that shipped in the first draft: `Accept: application/vnd.github+json` was
        sent to PyPI, which 406s. It degraded to UNVERIFIABLE and the run still exited 0 - a
        check that had stopped checking and did not say so loudly enough."""
        monkeypatch.setattr(controls, "get", responder({
            "/pypi/": (200, PYPI_INDEX), "/integrity/": (406, None)}))
        assert controls.check_publisher_environment(REPO).state == controls.UNVERIFIABLE


class TestTheEnvironmentReviewers:
    def test_required_reviewers_present_passes(self, controls, monkeypatch):
        monkeypatch.setattr(controls, "get", responder({"/environments": (200, {
            "environments": [{"name": "pypi",
                              "protection_rules": [{"type": "required_reviewers"}]}]})}))
        assert controls.check_environment_reviewers(REPO, None).state == controls.OK

    def test_reviewers_removed_is_a_violation(self, controls, monkeypatch):
        """This exact drift already happened once, noted in v0.21.0. A `wait_timer` rule looks
        like protection in the UI and stops nobody."""
        monkeypatch.setattr(controls, "get", responder({"/environments": (200, {
            "environments": [{"name": "pypi",
                              "protection_rules": [{"type": "wait_timer"}]}]})}))
        assert controls.check_environment_reviewers(REPO, None).state == controls.VIOLATED

    def test_the_environment_vanishing_is_a_violation(self, controls, monkeypatch):
        """release.yml names `environment: pypi`. If it does not exist the publish job runs
        with no gate, which is the failure the gate exists to prevent."""
        monkeypatch.setattr(controls, "get", responder({
            "/environments": (200, {"environments": [{"name": "staging",
                                                      "protection_rules": []}]})}))
        assert controls.check_environment_reviewers(REPO, None).state == controls.VIOLATED

    def test_an_unreadable_api_is_not_a_violation(self, controls, monkeypatch):
        monkeypatch.setattr(controls, "get", responder({"/environments": (503, None)}))
        assert controls.check_environment_reviewers(REPO, None).state == controls.UNVERIFIABLE


class TestBranchProtection:
    HEALTHY = {"required_status_checks": {"contexts": ["lint", "test (3.10)"]},
               "enforce_admins": {"enabled": True},
               "allow_force_pushes": {"enabled": False},
               "allow_deletions": {"enabled": False}}

    def test_a_healthy_configuration_passes(self, controls, monkeypatch):
        monkeypatch.setattr(controls, "get", responder({"/protection": (200, self.HEALTHY)}))
        assert controls.check_branch_protection(REPO, "t").state == controls.OK

    def test_no_protection_at_all_is_a_violation(self, controls, monkeypatch):
        """404 means the branch is unprotected - and `dependabot-auto-merge.yml` holds
        `contents: write` on a pull_request trigger and merges on green, with nothing
        enforcing that green means anything."""
        monkeypatch.setattr(controls, "get", responder({"/protection": (404, None)}))
        assert controls.check_branch_protection(REPO, "t").state == controls.VIOLATED

    @pytest.mark.parametrize("field,value,why", [
        ("required_status_checks", {"contexts": []}, "no required checks"),
        ("enforce_admins", {"enabled": False}, "admins exempt"),
        ("allow_force_pushes", {"enabled": True}, "force pushes allowed"),
        ("allow_deletions", {"enabled": True}, "deletion allowed"),
    ])
    def test_each_weakening_is_caught_on_its_own(self, controls, monkeypatch, field, value,
                                                 why):
        """Four separate settings, each of which alone defeats the premise. Checking only the
        first would pass a branch anyone can force-push over."""
        weakened = {**self.HEALTHY, field: value}
        monkeypatch.setattr(controls, "get", responder({"/protection": (200, weakened)}))
        assert controls.check_branch_protection(REPO, "t").state == controls.VIOLATED, why

    @pytest.mark.parametrize("status", [401, 403])
    def test_no_admin_rights_is_unverifiable_not_a_violation(self, controls, monkeypatch,
                                                             status):
        """The normal case in CI: this endpoint needs admin, and a workflow's GITHUB_TOKEN
        cannot be granted it - there is no `administration` permission. Reporting that as a
        violated control would make the weekly run permanently red and therefore ignored."""
        monkeypatch.setattr(controls, "get", responder({"/protection": (status, None)}))
        assert controls.check_branch_protection(REPO, None).state == controls.UNVERIFIABLE


class TestTheScriptIsWiredToCheckAllThree:
    def test_every_control_named_in_the_issue_has_a_check(self, controls):
        for name in ("check_publisher_environment", "check_environment_reviewers",
                     "check_branch_protection"):
            assert callable(getattr(controls, name, None)), f"{name} is missing"

    def test_the_three_states_are_distinct(self, controls):
        assert len({controls.OK, controls.VIOLATED, controls.UNVERIFIABLE}) == 3

    def test_the_token_is_never_sent_to_pypi(self, controls):
        """Found while fixing the 406: the Authorization header was being attached to every
        request, so a GitHub token was going to pypi.org. It has no business there, and a
        credential sent to a host that did not ask for it is a credential leaked to it."""
        source = SCRIPT.read_text(encoding="utf-8")
        assert 'if token and github' in source, (
            "the Authorization header must be conditional on the request going to GitHub")


class TestTheWorkflowRunsIt:
    def test_the_workflow_exists_and_is_scheduled(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "schedule:" in text and "cron:" in text, (
            "external state drifts on its own; a check tied only to code changes goes quiet "
            "exactly when nobody is committing")
        assert "workflow_dispatch:" in text

    def test_it_does_not_run_on_pull_requests(self):
        """It observes state outside the tree, so on a PR it reports something the PR did not
        change and cannot fix."""
        text = WORKFLOW.read_text(encoding="utf-8")
        triggers = text[text.index("on:"):text.index("permissions:")]
        assert "pull_request" not in triggers

    def test_it_holds_no_write_permission(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "contents: read" in text
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.endswith(": write") and not stripped.startswith("#"):
                pytest.fail(f"a read-only check should not hold {stripped!r}")

    def test_the_optional_token_is_optional(self):
        """Two of three controls need no credential. Requiring a secret for the job to run at
        all would mean the two free checks stop happening when nobody sets one up."""
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "CONTROLS_TOKEN" in text
        assert not re.search(r"if:\s*.*CONTROLS_TOKEN", text), (
            "the job must run without the optional token, checking what it can")


class TestTheReleasePathChecksThemToo:
    """The weekly run finds drift within a week. A release is the moment drift actually costs
    something - a removed reviewer lets that very run publish unattended - so the check also
    sits in the release build.

    It is safe there only because of the exit-code discipline: UNVERIFIABLE exits 0, so an
    outage cannot redden a release, while a violated control stops it before anything is
    built. A check that failed on unreachability would have to be removed from this path the
    first time PyPI had a bad minute.
    """

    RELEASE = ROOT / ".github/workflows/release.yml"

    def test_the_build_job_runs_the_check(self):
        text = self.RELEASE.read_text(encoding="utf-8")
        assert "scripts/check_controls.py" in text

    def test_it_runs_in_build_and_not_in_publish(self):
        """`publish` holds the credential and deliberately runs no project code - the property
        the two-job split buys. Putting this there would give it back."""
        text = self.RELEASE.read_text(encoding="utf-8")
        publish = text[text.index("  publish:"):]
        assert "check_controls" not in publish, (
            "the publish job must not run project code; it holds id-token: write")

    def test_unverifiable_exits_zero_so_an_outage_cannot_block_a_release(self, controls,
                                                                        monkeypatch):
        """The property that makes it safe on the release path, asserted directly."""
        monkeypatch.setattr(controls, "check_publisher_environment",
                            lambda repo, **kw: controls.Result("p", controls.OK, ""))
        monkeypatch.setattr(controls, "check_environment_reviewers",
                            lambda repo, token=None, **kw: controls.Result("e", controls.UNVERIFIABLE, ""))
        monkeypatch.setattr(controls, "check_branch_protection",
                            lambda repo, token=None, **kw: controls.Result("b", controls.UNVERIFIABLE, ""))
        monkeypatch.setattr(sys, "argv", ["check_controls.py"])
        assert controls.main() == 0

    def test_a_violation_exits_non_zero(self, controls, monkeypatch):
        monkeypatch.setattr(controls, "check_publisher_environment",
                            lambda repo, **kw: controls.Result("p", controls.OK, ""))
        monkeypatch.setattr(controls, "check_environment_reviewers",
                            lambda repo, token=None, **kw: controls.Result("e", controls.VIOLATED, ""))
        monkeypatch.setattr(controls, "check_branch_protection",
                            lambda repo, token=None, **kw: controls.Result("b", controls.OK, ""))
        monkeypatch.setattr(sys, "argv", ["check_controls.py"])
        assert controls.main() == 1

    def test_everything_unverifiable_exits_non_zero(self, controls, monkeypatch):
        """A run that verified nothing must not read as a clean bill of health - the whole
        reason UNVERIFIABLE is a state rather than a shrug."""
        monkeypatch.setattr(controls, "check_publisher_environment",
                            lambda repo, **kw: controls.Result("p", controls.UNVERIFIABLE, ""))
        monkeypatch.setattr(controls, "check_environment_reviewers",
                            lambda repo, token=None, **kw: controls.Result("e", controls.UNVERIFIABLE, ""))
        monkeypatch.setattr(controls, "check_branch_protection",
                            lambda repo, token=None, **kw: controls.Result("b", controls.UNVERIFIABLE, ""))
        monkeypatch.setattr(sys, "argv", ["check_controls.py"])
        assert controls.main() == 1


class TestItRunsAgainstAnotherRepositoryUnmodified:
    """The three controls are not specific to this project: any repo publishing to PyPI over
    Trusted Publishing rests on the same premises. A sibling repo should run this FILE, not a
    fork of it — a forked copy is how a check quietly stops matching the thing it checks, which
    is the exact failure this script exists to catch.
    """

    def test_the_repo_specific_values_are_all_overridable(self, controls):
        import inspect
        for fn, knob in ((controls.check_publisher_environment, "package"),
                         (controls.check_publisher_environment, "environment"),
                         (controls.check_environment_reviewers, "environment"),
                         (controls.check_branch_protection, "branch")):
            assert knob in inspect.signature(fn).parameters, (
                f"{fn.__name__} hardcodes {knob}, so another repo would have to fork this file")

    def test_the_new_knobs_are_keyword_only(self, controls):
        """The bug this pins, which types do NOT catch and which shipped in the first draft.

        Adding `environment` as the SECOND POSITIONAL parameter silently changed what every
        existing `check_environment_reviewers(repo, token)` call meant — the token became the
        environment. Both are `str | None`, so mypy was happy; only a test that passed a token
        positionally noticed. Keyword-only means a positional call cannot be reinterpreted.
        """
        import inspect
        for fn, knob in ((controls.check_publisher_environment, "package"),
                         (controls.check_environment_reviewers, "environment"),
                         (controls.check_branch_protection, "branch")):
            kind = inspect.signature(fn).parameters[knob].kind
            assert kind is inspect.Parameter.KEYWORD_ONLY, (
                f"{fn.__name__}({knob}=) is positional, so adding it reordered the existing "
                f"arguments rather than extending them")

    def test_repo_still_comes_first_positionally(self, controls):
        """Every caller passes it, and it is the one argument that is never optional."""
        import inspect
        for fn in (controls.check_publisher_environment, controls.check_environment_reviewers,
                   controls.check_branch_protection):
            first = list(inspect.signature(fn).parameters)[0]
            assert first == "repo", f"{fn.__name__} takes {first!r} first, not 'repo'"

    def test_a_failure_message_does_not_assert_facts_about_THIS_repo(self, controls):
        """The branch-protection failure used to say "dependabot-auto-merge.yml holds
        contents: write" — true here, and an unfounded claim about somebody else's repository
        the moment the file is run with `--repo`. A portable check must not report a local
        detail as though it had observed it."""
        source = (controls.check_branch_protection.__doc__ or "")
        message = inspect.getsource(controls.check_branch_protection)
        assert "in another repo, check what can merge" in message.lower() or \
               "dependabot-auto-merge.yml" not in message.split("VIOLATED", 1)[-1], (
            "the VIOLATED message states a fact about this repo's workflows unconditionally")
        assert source is not None
