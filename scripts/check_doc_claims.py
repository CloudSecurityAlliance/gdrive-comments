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
]
DOC_GLOBS = ["research/*.md", "docs/superpowers/specs/*.md"]

# THREAT_MODEL.md is excluded from the COUNT checks but not the name checks: its threat text is
# frozen as the audit wrote it, so "34 tools" there is a quotation rather than a claim about now.
FROZEN_COUNTS = {"THREAT_MODEL.md"}

# Where a bare "**N tools**" is a claim about US. Everywhere else - the README's comparison
# section especially - a tool count usually belongs to somebody else ("`piotr-agier` ships **115
# tools**"), and only the explicit "this project's N" form is ours. Stated per file rather than
# inferred from the sentence, because the line that prompted this contains BOTH numbers and no
# amount of regex cleverness reads it correctly.
OWN_TOOL_COUNT_FILES = {"CLAUDE.md", "INTERFACE-RESOURCES.md"}

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
    cap_count = re.compile(r"\*\*(\d+) capabilities\*\*|all (\d+) capabilities")

    for path in _docs():
        name = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")

        for var in sorted(set(env_pattern.findall(text)) - env_vars):
            if var not in EXPECTED_ABSENT:
                problems.append(f"{name}: names {var}, which no source file defines")

        for cap in sorted(set(cap_pattern.findall(text)) - capabilities):
            if cap not in REJECTED_CAPABILITIES:
                problems.append(
                    f"{name}: names capability `{cap}`, which policy.py does not define")

        if path.name not in FROZEN_COUNTS:
            claims = {int(n) for n in ours_count.findall(text)}
            if path.name in OWN_TOOL_COUNT_FILES:
                claims |= {int(n) for n in bare_count.findall(text)}
            for claimed in claims:
                if claimed != len(tools):
                    problems.append(
                        f"{name}: claims **{claimed} tools**; the server registers {len(tools)}")
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
