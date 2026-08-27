"""The release job's sdist guard, run on every PR instead of only at publish time.

`release.yml` refuses to publish if the built sdist contains a path matching a
credential-or-probe pattern. Good check, wrong moment: it runs **inside the publish job**, so a
false positive surfaces only once a release has been cut, the environment gate approved, and the
tag pushed — which is exactly what happened to v0.30.2. A test file legitimately named
`test_read_only_means_a_read_only_token.py` contains the word `token`, so the pattern matched,
and a **security release stopped one step from PyPI.**

The guard failing closed is correct. Failing closed *at publish time* on a filename anybody might
add is the problem: it ambushes the release it exists to protect, and the person hitting it is
mid-release and inclined to weaken the pattern to get moving.

So the same pattern runs here, over the tracked tree, and a colliding filename fails on the PR
that introduces it.

**Why the tracked tree rather than a built sdist.** Building one per test run costs seconds and
needs `build` installed. `git ls-files` is close enough for the thing being guarded — somebody
adding a file whose *name* collides — and the real sdist check stays in `release.yml` as the
authority. This is the early warning, not the replacement.

**With one correction, found by writing it.** The tracked tree is not the sdist: `research/` and
`experiments/` are tracked deliberately and pruned from the distribution deliberately (setuptools
package discovery, plus `extend-exclude` in `pyproject.toml`). They are the pattern's *intended*
matches, not filename collisions, so checking them here would fail permanently and for the wrong
reason. The two halves of the guard are therefore checked separately:

  * the **word** half (`token`, `credential`, `client_secret`) against every shippable path —
    that is the half a colliding filename trips;
  * the **directory** half against the distribution config — the invariant for those is that they
    are excluded, which is a different assertion from "no file is named like this".
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Kept byte-identical in meaning to release.yml. If you change one, change both — and the
# comment there explains why `.py` is exempt and what that does not cost.
PATTERN = re.compile(r"(^|/)(research|experiments)/|token|credential|client_secret", re.I)
WORDS = re.compile(r"token|credential|client_secret", re.I)
PRUNED = re.compile(r"^(research|experiments)/")
EXEMPT = re.compile(r"\.py$")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=True)
    return [line for line in out.stdout.splitlines() if line]


def flagged(paths):
    return [p for p in paths if not EXEMPT.search(p) and PATTERN.search(p)]


class TestNoShippablePathCollidesWithTheGuard:
    def test_no_shippable_file_would_block_a_release(self):
        """The half a colliding filename trips. `research/` and `experiments/` are excluded
        here because they are pruned from the distribution — see the next class."""
        shippable = [p for p in tracked() if not PRUNED.match(p)]
        offenders = [p for p in shippable if not EXEMPT.search(p) and WORDS.search(p)]
        assert offenders == [], (
            "these paths match the release job's sdist guard and would stop a publish:\n  "
            + "\n  ".join(offenders)
            + "\n\nEither rename the file, or - if it is genuinely a credential or probe "
              "artifact - it must not be tracked at all.")

    def test_the_tree_is_actually_being_read(self):
        """A guard over an empty list passes vacuously and guards nothing."""
        paths = tracked()
        assert len(paths) > 100, f"only {len(paths)} tracked files; git ls-files likely failed"

    def test_the_pruned_directories_are_still_tracked(self):
        """If these ever stop being tracked, the exclusion above starts hiding real matches
        rather than expected ones."""
        assert any(PRUNED.match(p) for p in tracked()), (
            "nothing under research/ or experiments/ is tracked any more; this exclusion is "
            "now silently broadening what the guard ignores")


class TestThePrunedDirectoriesAreExcludedFromTheDistribution:
    """The other half, and a different assertion: those directories may exist and must not ship.

    Guarded because the release-job pattern lists them, and a pattern is not an exclusion — it
    fires only if the packaging config already failed.
    """

    def test_pyproject_excludes_them(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for name in ("experiments", "research"):
            assert f'"{name}"' in text, (
                f"{name}/ is no longer named in pyproject.toml; if packaging stops pruning it, "
                f"the release guard becomes the only thing standing between a probe transcript "
                f"and PyPI")


class TestThePatternStillCatchesWhatItIsFor:
    """Exempting `.py` must not have blunted the check. Every case the guard was written for."""

    @pytest.mark.parametrize("path", [
        "csa_google_workspace-1.0/token.json",
        "csa_google_workspace-1.0/token_full.json",
        "csa_google_workspace-1.0/credentials.json",
        "csa_google_workspace-1.0/client_secret_123.apps.googleusercontent.com.json",
        "csa_google_workspace-1.0/research/notes.md",
        "csa_google_workspace-1.0/experiments/probe/RESULTS.md",
        "csa_google_workspace-1.0/some-probe-token.txt",
        "csa_google_workspace-1.0/.credentials/service.pem",
    ])
    def test_a_real_offender_is_still_flagged(self, path):
        assert flagged([path]) == [path]

    @pytest.mark.parametrize("path", [
        "csa_google_workspace-1.0/tests/test_read_only_means_a_read_only_token.py",
        "csa_google_workspace-1.0/src/csa_google_workspace/auth.py",
        "csa_google_workspace-1.0/tests/test_credentials_are_redacted.py",
    ])
    def test_a_source_file_is_not(self, path):
        assert flagged([path]) == []

    def test_the_exemption_is_narrow(self):
        """`.py` only. A `.json` named like a test is still a data file and still flagged."""
        assert flagged(["pkg/tests/test_token.json"]) == ["pkg/tests/test_token.json"]
