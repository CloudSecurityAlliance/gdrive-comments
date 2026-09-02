#!/usr/bin/env python3
"""Re-verify what the documentation claims about the code, and report what has drifted.

**The prose here is the design record**, not decoration — specs, docstrings and README sections
carry reasoning nothing else records — so a stale sentence is what the next change gets built on.
Combined with a release most weeks, claims go stale faster than anyone notices. This makes the
periodic re-check a command rather than an intention.

## Why a script and not only tests

`tests/test_docs_do_not_drift.py` pins the specific claims that have gone wrong before, and it
must keep doing that: a named regression test is a promise about one fact. This is the other half
— a **survey** that enumerates reality and asks the docs about all of it, so a claim nobody
thought to pin still gets checked. It is advisory by default because some drift is acceptable
between releases; `--strict` makes it exit non-zero for CI.

## What it can and cannot see

It checks the claims that are *mechanically* checkable: tool names, capability names, environment
variables, profile names, module paths, and counted assertions ("50 tools"). It cannot check
whether a paragraph's *reasoning* is still true, which is the more valuable and less tractable
half. Treat a clean run as "no contradiction found", never as "the documentation is correct".

## The lesson that shaped it

Two guards in this repo passed while the thing they guarded rotted, both for the same reason:
they looked for a string *somewhere* in a file, or iterated a collection that had become empty.
`INTERFACE-RESOURCES.md` claimed release v0.2.3 for thirty-five releases under a repeatedly
refreshed "Last verified" date, because the check only asserted the current version appeared
*somewhere* — which the header satisfied on its own.

So the rule here is: **enumerate reality and compare against it.** Never ask "is the right
string present"; ask "is everything that exists accounted for, and does everything claimed
exist".

    python scripts/check_doc_claims.py [--strict] [--quiet]
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Documents that make claims about the code. CHANGELOG.md is deliberately absent: its entries are
# statements about the past and are SUPPOSED to name things that no longer exist.
DOCS = [
    "README.md", "CLAUDE.md", "SECURITY.md", "TODO.md", "RELEASING.md",
    "INTERFACE-RESOURCES.md", "API-STABILITY.md", "CONTRIBUTING.md",
    # Added 2026-09-02 (#317). It was absent, which made `FROZEN_COUNTS` below DEAD CODE - the
    # file never entered the loop that consults it - so the comment there was false in both
    # halves. The surveyor built to "enumerate reality and compare against it" was skipping the
    # document `SECURITY.md` explicitly delegates the register to.
    "THREAT_MODEL.md",
]
DOC_GLOBS = ["research/*.md", "docs/superpowers/specs/*.md"]

# Source files are scanned for DEFAULT-POSTURE CLAIMS only (see `_posture_problems`), not for the
# name and count checks. Docstrings and MCP tool descriptions are documentation that a MODEL reads
# as operational context, and the drift that mattered most lived there rather than in any `.md`:
# an external audit found thirteen such claims surviving eleven releases after the default
# reversed (CODX-2026-09-01-01). A sweep that only opens Markdown cannot see them.
SOURCE_ROOT = "src/csa_google_workspace"

# Exempt from the COUNT checks and nothing else. The register's threat text is carried verbatim
# as the audit wrote it, so a number inside a threat or its evidence is a QUOTATION of what was
# true when that audit looked - not a claim about now. Its name checks and posture checks do
# apply, which is the half worth having: a threat citing a capability that no longer exists, or
# a mitigation describing the old default posture, is a real defect in a live document.
#
# This was dead code until #317 added the file to DOCS above; the exemption is now real.
FROZEN_COUNTS = {"THREAT_MODEL.md"}

# A tool count belongs to somebody else when one of these appears just before it - the README
# compares against other servers ("`piotr-agier` ships **115 tools**"). Everything else is a claim
# about us, in EVERY file.
#
# This replaced a per-file allowlist (`{"CLAUDE.md", "INTERFACE-RESOURCES.md"}`) which excluded
# README.md to suppress exactly those comparison rows - and in doing so hid "**34 tools**" in the
# README's own introduction for eleven releases. An external review found it (RR-003, 2026-09-01).
# The lesson is narrow and worth keeping: **suppressing a false positive by excluding a whole file
# excludes its true positives too.** Exclude the sentence, never the document.
OTHER_SERVER_MARKERS = ("piotr-agier", "taylorwilsdon", "ships", "google's server",
                        "claude.ai connector", "distant-tuna", "mkummer")

# Names that are legitimately absent from the code, with the reason. A bare "known failure" list
# would rot exactly like the docs it checks, so each entry says why it is not drift.
EXPECTED_ABSENT = {
    # Proposed by a design document that is explicitly not implemented.
    "CSA_GW_ACCOUNTS": "proposed by the multi-account spec; marked as not existing",
    "CSA_GW_TOKEN_CSA": "proposed by the multi-account spec (per-account suffix form)",
    "CSA_GW_PROFILE_CSA": "proposed by the multi-account spec (per-account suffix form)",
    "CSA_GW_ALLOWLIST_READ_CSA": "proposed by the multi-account spec (per-account suffix form)",
    "CSA_GW_ALLOWLIST_MODIFY_CSA": "proposed by the multi-account spec (per-account suffix form)",
    "CSA_GW_ALLOWLIST_READ_PERSONAL": "proposed by the multi-account spec (per-account suffix)",
    # Test gates. Real, but defined in tests/ rather than src/.
    "CSA_GW_INTEGRATION": "gate for tests/integration/, defined in the test suite",
    "CSA_GW_OAUTH": "gate for tests/oauth/, defined in the test suite",
    "CSA_GW_MCP_LIVE": "proposed by the MCP spec for a gated live smoke test; never built",
}

# Capability-shaped names a design document DISCUSSES AND REJECTS. Both of these appear under a
# heading saying so ("`export.file` is not an axis"), which is exactly the kind of reasoning that
# should stay written down — so they are expected, not drift.
REJECTED_CAPABILITIES = {
    "export.file": "considered and rejected as an axis (view ~= download) in the capability spec",
    "content.active": "considered and rejected as an axis in the capability spec",
}

# The second half of a capability name. Matching on these rather than on `noun.anything` is what
# keeps `Comment.location` and `Comment.replies` - MODEL FIELDS, not capabilities - out of the
# report. A checker that cries wolf is one nobody runs.
CAPABILITY_VERBS = ("create", "reply", "resolve", "edit", "delete", "write", "update",
                    "share", "trash", "read")


def _tools() -> set[str]:
    from csa_google_workspace import Workspace
    from csa_google_workspace.backend import FakeBackend
    from csa_google_workspace.mcp import settings_from_env
    from csa_google_workspace.mcp.server import create_server

    app = create_server(lambda: Workspace(FakeBackend({})),
                        settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
    return {t.name for t in asyncio.run(app.list_tools())}


def _env_vars() -> set[str]:
    """Every CSA_GW_* literal in the source. Read from the AST rather than by grepping strings,
    so a name that only appears in a comment does not count as implemented."""
    found: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                     # pragma: no cover - never in a clean tree
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("CSA_GW_"):
                    found.add(node.value)
    return found




# This repository RECORDS what a document used to get wrong, next to the correction - it is how the
# reasoning survives. A quotation of a stale claim is byte-identical to an assertion of it, so the
# convention is that a historical aside is wrapped in `*( ... )*` and every check strips those
# spans first. `tests/test_docs_do_not_drift.py` uses the same rule.
_HISTORICAL_ASIDE = re.compile(r"\*\(.*?\)\*", re.DOTALL)


def without_historical_notes(text: str) -> str:
    """`text` with `*( ... )*` asides removed, so a quoted mistake is not read as a live claim."""
    return _HISTORICAL_ASIDE.sub(" ", text)


# Phrases that assert a capability or scope is CLOSED by default. Checked against the actual
# constants, because this exact sentence outlived its truth in eighteen places across three
# separate review passes - and it is neither a name nor a count, so nothing else here catches it.
#
# The check is one-directional on purpose: a text claiming "off by default" when nothing is off is
# a false sense of safety, which is the dangerous direction. The reverse (failing to mention a
# default) is a gap, not a lie, and is left to human review.
CLOSED_POSTURE_CLAIMS = (
    "off by default",
    "off unless an operator",
    "off unless named",
    "disabled by default",
    "fails closed when nothing is configured",
    "fails closed when unset",
    "unset means nothing is permitted",
)

# The phrase alone is far too blunt: of thirteen matches on the first run, TWELVE were correct —
# negations ("nothing is off by default"), past tense ("capabilities that WERE off by default"),
# and three about **caching**, which genuinely is off by default. A checker with a 92% false
# positive rate is one nobody runs, so two filters narrow it to the claim that actually drifts.
#
# 1. The claim must sit near a CAPABILITY or a lifecycle tool name. That is what excludes caching
#    and every other subject the phrase legitimately describes.
# 2. It must not be negated or in the past tense.
#
# The one real finding on that first run was in `CLAUDE.md` — the agent-facing guide — and neither
# an external correctness report nor a security audit had caught it.
_POSTURE_SUBJECTS = ("file.share", "file.trash", "file.update", "comment.delete", "comment.edit",
                     "content.delete", "content.write", "file.create", "share_file",
                     "trash_file", "update_file", "delete_comment", "edit_comment",
                     "capabilit", "allowlist")
_POSTURE_NEGATIONS = ("nothing is", "no longer", "whatever is", "were", "used to", "once nothing",
                      "these said", "said", "not ", "stopped", "any more", "until v0", "wrong by")


def _posture_problems(paths, anything_disabled: bool, unset_is_everything: bool) -> list[str]:
    """Text asserting a closed default that the constants contradict.

    Scans Markdown *and* source, because `--help` strings, docstrings and MCP tool descriptions
    are read by operators and models as authoritative — and that is where this drift hid longest.
    An external audit found thirteen such claims surviving eleven releases after the default
    reversed; a sweep that only opens Markdown cannot see them (CODX-2026-09-01-01).

    One-directional on purpose: text claiming "off by default" when nothing is off gives a false
    sense of safety, which is the dangerous direction. Failing to mention a default is a gap, not
    a lie, and is left to human review.
    """
    if anything_disabled and not unset_is_everything:
        return []                                  # the claims would be true; nothing to check
    problems = []
    for path in paths:
        flat = " ".join(without_historical_notes(
            path.read_text(encoding="utf-8")).split()).lower()
        for claim in CLOSED_POSTURE_CLAIMS:
            start = 0
            while (found := flat.find(claim, start)) != -1:
                start = found + 1
                before = flat[max(0, found - 70):found]
                if any(negation in before for negation in _POSTURE_NEGATIONS):
                    continue
                window = flat[max(0, found - 160):found + 160]
                if not any(subject in window for subject in _POSTURE_SUBJECTS):
                    continue                       # about caching, or some other subject
                problems.append(
                    f"{path.name}: says {claim!r} of a capability, but nothing is disabled by "
                    f"default and an unset allowlist permits every file. If the sentence is "
                    f"historical, wrap it in *( ... )* so it reads as a quotation")
    return problems


def _test_count() -> int:
    """How many tests the offline suite collects.

    Counted by collecting, not by parsing `def test_`: parametrisation means the two numbers
    differ substantially, and the figure the README quotes is the one a reader would see from
    `pytest`. Falls back to a `def test_` count if collection is unavailable, which keeps this
    script usable in an environment without the dev extra.
    """
    import subprocess
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                              str(ROOT / "tests")], capture_output=True, text=True, timeout=180,
                             cwd=ROOT)
        for line in reversed(out.stdout.splitlines()):
            if "test" in line and "collected" in line:
                for token in line.split():
                    if token.isdigit():
                        return int(token)
    except Exception:                              # pragma: no cover - environment-dependent
        pass
    return sum(line.count("def test_")
               for path in (ROOT / "tests").rglob("test_*.py")
               for line in path.read_text(encoding="utf-8").splitlines())

def _docs() -> list[Path]:
    paths = [ROOT / d for d in DOCS]
    for pattern in DOC_GLOBS:
        paths.extend(sorted(ROOT.glob(pattern)))
    return [p for p in paths if p.exists()]


def check() -> list[str]:
    """Every disagreement found, as human-readable lines."""
    from csa_google_workspace import __version__
    from csa_google_workspace.policy import ALL_CAPABILITIES, PROFILES

    tools, env_vars = _tools(), _env_vars()
    TEST_COUNT = _test_count()
    capabilities, profiles = set(ALL_CAPABILITIES), set(PROFILES)
    problems: list[str] = []

    # A backticked lower_snake token that IS a tool name is a reference to one; the point of the
    # check is the reverse direction, below.
    # A trailing `*` is a legitimate wildcard reference ("the CSA_GW_LOCAL_* switches").
    env_pattern = re.compile(r"\b(CSA_GW_[A-Z][A-Z0-9_]*)(?!\w)(?!\*)")
    cap_pattern = re.compile(
        r"`((?:comment|content|file|export)\.(?:" + "|".join(CAPABILITY_VERBS) + r"))`")
    bare_count = re.compile(r"\*\*(\d+) tools\*\*")
    # Ours wherever it appears, including inside a comparison with another server.
    ours_count = re.compile(r"this (?:project|server)'s (\d+)\b")
    # "over 1,600 offline tests" and friends. A floor, not an exact count, so it does not break
    # every time a test is added - but a badly stale one still fails, which is the case that
    # mattered: the README claimed 963 when the suite had 1631.
    test_floor = re.compile(r"(?:over|more than)\s+([\d,]+)\s+(?:offline\s+)?tests")
    cap_count = re.compile(r"\*\*(\d+) capabilities\*\*|all (\d+) capabilities")

    for path in _docs():
        name = path.relative_to(ROOT).as_posix()
        text = without_historical_notes(path.read_text(encoding="utf-8"))

        for var in sorted(set(env_pattern.findall(text)) - env_vars):
            if var not in EXPECTED_ABSENT:
                problems.append(f"{name}: names {var}, which no source file defines")

        for cap in sorted(set(cap_pattern.findall(text)) - capabilities):
            if cap not in REJECTED_CAPABILITIES:
                problems.append(
                    f"{name}: names capability `{cap}`, which policy.py does not define")

        if path.name not in FROZEN_COUNTS:
            # Whitespace-normalised, because these claims are prose and wrap across lines - the
            # README's own "**50\ntools**" slipped past a line-anchored pattern.
            flat = " ".join(text.split())
            claims = {int(n) for n in ours_count.findall(flat)}
            for match in bare_count.finditer(flat):
                before = flat[max(0, match.start() - 80):match.start()].lower()
                if not any(marker in before for marker in OTHER_SERVER_MARKERS):
                    claims.add(int(match.group(1)))
            for match in test_floor.finditer(flat):
                floor = int(match.group(1).replace(",", ""))
                if floor > TEST_COUNT:
                    problems.append(
                        f"{name}: claims over {floor:,} tests; the suite has {TEST_COUNT:,}")
                elif TEST_COUNT > floor * 1.5:
                    problems.append(
                        f"{name}: claims over {floor:,} tests and the suite has "
                        f"{TEST_COUNT:,} - stale enough to mislead. Raise the floor")
            for claimed in claims:
                if claimed != len(tools):
                    problems.append(
                        f"{name}: claims a tool count of {claimed}; the server registers "
                        f"{len(tools)}")
            for a, b in cap_count.findall(text):
                claimed = int(a or b)
                if claimed != len(capabilities):
                    problems.append(
                        f"{name}: claims {claimed} capabilities; policy.py defines "
                        f"{len(capabilities)}")

    # The inventory direction: INTERFACE-RESOURCES.md promises to list the interface, so a tool
    # missing from it is an understatement of what the server does. This is the check that would
    # have caught fifteen unlisted tools.
    inventory = ROOT / "INTERFACE-RESOURCES.md"
    if inventory.exists():
        text = inventory.read_text(encoding="utf-8")
        missing = sorted(t for t in tools if f"`{t}`" not in text)
        if missing:
            problems.append(
                f"INTERFACE-RESOURCES.md: does not name {len(missing)} tool(s) the server "
                f"exposes: {', '.join(missing)}")
        stale = re.findall(r"Current release \*\*v(\d+\.\d+\.\d+)\*\*", text)
        for claimed in {v for v in stale if v != __version__}:
            problems.append(
                f"INTERFACE-RESOURCES.md: claims current release v{claimed}; this is "
                f"v{__version__}")

    # Modules that exist but no guide mentions. CLAUDE.md's layout section is how an agent learns
    # what is in the package; a module absent from it is a module nobody is told about.
    guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for module in sorted((ROOT / "src/csa_google_workspace").glob("*.py")):
        if module.name == "__init__.py":
            continue
        if f"`{module.name}`" not in guide:
            problems.append(
                f"CLAUDE.md: does not mention `{module.name}` in the code-layout section")

    # The default-posture sweep: Markdown plus every source file, since model-facing text lives
    # in docstrings and tool descriptions.
    from csa_google_workspace.mcp._config import settings_from_env
    from csa_google_workspace.policy import DEFAULT_DISABLED

    sources = sorted((ROOT / SOURCE_ROOT).rglob("*.py"))
    problems.extend(_posture_problems(
        _docs() + sources,
        anything_disabled=bool(DEFAULT_DISABLED),
        unset_is_everything=settings_from_env({}).policy.modify.all_files))

    for profile in sorted(profiles):
        if f"`{profile}`" not in (ROOT / "README.md").read_text(encoding="utf-8"):
            problems.append(f"README.md: does not document the `{profile}` profile")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero when anything has drifted (for CI)")
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args()

    problems = check()
    if not args.quiet:
        print(f"checked {len(_docs())} document(s) against the code")
    if problems:
        print(f"\n{len(problems)} claim(s) disagree with the code:\n")
        for line in problems:
            print(f"  - {line}")
        print("\nA claim is either wrong or the code moved. Fix whichever is stale — and if the "
              "claim is deliberately historical, say so in the text so it reads as a quotation.")
        return 1 if args.strict else 0
    if not args.quiet:
        print("no contradictions found.")
        print("NOTE: this checks mechanically verifiable claims only — names, counts, "
              "inventories.\nWhether a paragraph's REASONING is still true is not checkable "
              "here, and is the more\nvaluable half. A clean run is not a correct document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
