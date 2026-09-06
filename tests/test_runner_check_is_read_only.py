"""`--check` must not write. A static guard, because the dynamic one costs a network round trip.

**#440.** `Run-full-test-suite.sh --check` says "prerequisites only, run nothing" and the README
says it "changes nothing" — and it was creating a venv, running a full `pip install`, adding a
git worktree and making `~/.csa_gw_rig`. The `exit 0` sat two hundred lines after the install
block. It was found on a machine where that install then failed on Python 3.9 and buried the
real problem in a pip resolver dump.

Static rather than executed: running the script needs the network, PyPI and a Google token, so a
test that ran it would be skipped on every machine that matters. What can be checked cheaply is
that **every writing operation is guarded**, which is the property that broke.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent.parent / "Run-full-test-suite.sh"

# Each of these writes to disk. `git worktree add` is in the list because creating one is a
# write too — it was the second thing found when the first was fixed, and it would not have
# been noticed by anyone thinking only about the venv.
WRITES = [
    (r"\bmkdir -p ", "creates a directory"),
    (r'"\$PYTHON" -m venv ', "creates the venv"),
    (r'"\$RIG_VENV/bin/pip" install ', "installs into the venv"),
    (r"\bpipx install ", "installs the console script"),
    (r"git .* worktree add ", "creates a git worktree"),
]


@pytest.fixture(scope="module")
def script() -> str:
    assert RUNNER.exists(), f"{RUNNER} is missing"
    return RUNNER.read_text(encoding="utf-8")


def test_the_runner_exists_and_declares_check(script: str):
    """Guard the guard: if the flag were renamed, every test below would pass vacuously."""
    assert "--check)" in script, "no --check flag; this file is guarding something that moved"
    assert "CHECK_ONLY=true" in script


# Output helpers quote the very commands they tell a user to run — `info "Install: pipx
# install playwright"` is advice, not a write. Matching it made the first version of this
# test fail on a line that does nothing. Guarding a HELP STRING would be the vacuous kind of
# check this repository keeps finding.
_HELPERS = ("info ", "warn ", "pass ", "fail ", "error ", "echo ", "step ")


def _is_a_command(line: str) -> bool:
    stripped = line.strip()
    return not stripped.startswith("#") and not stripped.startswith(_HELPERS)


def _enclosing_conditions(lines: list[str], index: int) -> list[str]:
    """Every `if`/`elif` whose block still encloses `lines[index]`.

    A depth walk rather than a fixed window. The first version of this test used "within 25
    lines above", which failed on a write 45 lines inside a correctly-guarded `elif` — and
    widening the window would have weakened exactly the property being guarded, since a real
    unguarded write could then hide below an unrelated mention.
    """
    depth, conditions = 0, []
    for line in reversed(lines[:index]):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped == "fi" or stripped.startswith("fi "):
            depth += 1
        elif stripped.startswith("if "):
            if depth == 0:
                conditions.append(stripped)
            else:
                depth -= 1
        elif stripped.startswith("elif ") and depth == 0:
            conditions.append(stripped)
    return conditions


@pytest.mark.parametrize("pattern,what", WRITES, ids=[w for _, w in WRITES])
def test_every_write_is_guarded_by_check_only(script: str, pattern: str, what: str):
    """Every writing line must sit inside a conditional that consults `$CHECK_ONLY`."""
    lines = script.splitlines()
    hits = [i for i, line in enumerate(lines)
            if re.search(pattern, line) and _is_a_command(line)]
    assert hits, f"no line matching {pattern!r}; the script changed shape — re-read this guard"
    for i in hits:
        # A same-line guard counts: `$CHECK_ONLY || mkdir -p ...` is as good as an if-block,
        # and is the idiom for a one-line write.
        if "CHECK_ONLY" in lines[i]:
            continue
        guards = _enclosing_conditions(lines, i)
        assert any("CHECK_ONLY" in c for c in guards), (
            f"line {i + 1} ({what}) is not inside any CHECK_ONLY conditional:\n"
            f"  {lines[i].strip()}\n"
            f"  enclosing conditions: {guards or '(none — top level)'}\n"
            f"--check promises to change nothing; this writes."
        )


def test_python_is_checked_for_its_VERSION_not_merely_its_presence(script: str):
    """#440's other half: a green tick for python3 3.9.6 when the floor is 3.10.

    macOS ships 3.9 at /usr/bin/python3. Without this the requirement surfaces 300 lines later
    as a pip resolver dump instead of one readable line.
    """
    assert "version_info >= (3, 10)" in script, "no >=3.10 assertion on the interpreter"
    assert "python3.13" in script and "python3.10" in script, (
        "the interpreter search is missing: a Mac often has 3.9 as python3 and a newer one "
        "beside it, and finding it is the difference between 'run DesktopSetup' and 'it works'"
    )
