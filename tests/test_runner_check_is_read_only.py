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


def _enclosing_function(lines: list[str], index: int) -> str | None:
    """The `name() {` this line sits inside, if any.

    A write inside a function is controlled by the function's CALL SITES, which a static test
    cannot evaluate — so those are checked separately, by name, below. Pretending otherwise
    would mean either a false failure or a guard loose enough to miss the real thing.
    """
    depth = 0
    for line in reversed(lines[:index]):
        stripped = line.strip()
        if stripped == "}":
            depth += 1
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*\(\)\s*\{", stripped):
            # A ONE-LINE definition — `row() { printf ...; }` — opens and closes on the same
            # line, so its `}` is never seen as a bare brace. Counting it as an opener skewed
            # the depth and made everything below `write_report` look like it was INSIDE it,
            # which silently exempted the install block from the whole guard. Found by
            # re-running the mutation that used to fail and watching it pass.
            if stripped.rstrip().endswith("}") or stripped.rstrip().endswith("};"):
                continue
            if depth == 0:
                return stripped.split("(")[0]
            depth -= 1
    return None


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


# A write is allowed under exactly two conditions, and the second is narrow on purpose.
#
#   CHECK_ONLY — the write is skipped when the user asked for a check.
#   DEBUG      — the write IS what the user asked for. `--debug`'s entire product is a log
#                file, so demanding a CHECK_ONLY guard there would make `--check --debug`
#                silently produce nothing, which is worse than the write.
#
# Nothing else qualifies. Adding a third name here would be how this guard stops guarding.
PERMITTED_GUARDS = ("CHECK_ONLY", "DEBUG")


@pytest.mark.parametrize("pattern,what", WRITES, ids=[w for _, w in WRITES])
def test_every_write_is_guarded_by_check_only(script: str, pattern: str, what: str):
    """Every writing line must sit inside a conditional consulting `$CHECK_ONLY` or `$DEBUG`."""
    lines = script.splitlines()
    hits = [i for i, line in enumerate(lines)
            if re.search(pattern, line) and _is_a_command(line)]
    assert hits, f"no line matching {pattern!r}; the script changed shape — re-read this guard"
    for i in hits:
        # A same-line guard counts: `$CHECK_ONLY || mkdir -p ...` is as good as an if-block,
        # and is the idiom for a one-line write.
        if any(g in lines[i] for g in PERMITTED_GUARDS):
            continue
        if _enclosing_function(lines, i):
            continue                    # checked by call site, below
        guards = _enclosing_conditions(lines, i)
        assert any(g in c for c in guards for g in PERMITTED_GUARDS), (
            f"line {i + 1} ({what}) is not inside a {' or '.join(PERMITTED_GUARDS)} "
            f"conditional:\n"
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


def test_write_report_is_only_called_when_a_report_was_asked_for(script: str):
    """`write_report` creates a directory, so its CALL SITES carry the guard.

    The write test above skips function bodies because a static check cannot follow calls.
    This is the other half: every call must be inside a failure path or an explicit
    `--report`, so `--check` alone still writes nothing.
    """
    lines = script.splitlines()
    calls = [i for i, line in enumerate(lines)
             if line.strip() == "write_report" or line.strip().startswith("write_report ")]
    assert calls, "write_report is never called; this guard is watching something that moved"
    for i in calls:
        guards = _enclosing_conditions(lines, i)
        joined = " ".join(guards)
        assert "WANT_REPORT" in joined or "FAILED" in joined, (
            f"write_report called at line {i + 1} with no --report or failure guard:\n"
            f"  enclosing: {guards or '(none)'}\n"
            f"--check alone must not write a report."
        )
