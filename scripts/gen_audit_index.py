#!/usr/bin/env python3
"""Generate the security-audit index and coverage table from per-audit front matter (#198).

`docs/security-audits/README.md` was the one file every audit had to edit — the index row and
the coverage-by-module table — in a workflow otherwise designed so that parallel audit agents
never share a file. It was the last shared mutable document, and therefore the only thing that
could make two concurrent audits conflict.

Everything the index needs is already in each audit's own front matter. This regenerates both
tables from it, so an audit writes **only its own directory**.

## The coverage table is computed against the real tree, not restated

This is the half that matters. The old table was hand-maintained, and a hand-maintained
coverage claim is how the July-to-August gap stayed invisible: both 2026-07-22 audits cover
v0.1.0's 16 modules, the tree is now 53, and *everything* implementing the read-to-act path was
written afterwards — but the table said "first covered by" and nothing checked it against what
exists.

So coverage is derived: each audit **enumerates** the files it saw, the script walks the
**tracked** files in each group, and a group is reported as covered only when an audit's list
contains **every** one of them. Partial coverage is named as partial, with the count. A group no
audit matches is reported as **not yet audited**, which means a newly-added module shows up as
uncovered on its own rather than when somebody thinks to look.

Enumerated rather than globbed because **a glob claims the future**. The first version of this
had the 2026-08-27 record declaring `.github/workflows/*.yml`; that audit's commit is `95c6afa`
and the directory gained `controls.yml` the next day, so the table read *fully covered* for a
directory whose newest file no audit had seen. The overstatement this script exists to prevent,
reproduced inside the fix for it. `tests/test_audit_index.py` now rejects a glob in that field.

That last property is the point of doing this at all. The failure being fixed is not a stale
table; it is a coverage claim that reads as broader than it is.

## --check is what CI runs

`--check` regenerates in memory and diffs. A drifted index fails rather than misleads. Writing
is the local action; CI never writes, so the committed file is always the reviewed one.

    python scripts/gen_audit_index.py [--check]
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs/security-audits/README.md"

INDEX_BEGIN = "<!-- BEGIN GENERATED INDEX -->"
INDEX_END = "<!-- END GENERATED INDEX -->"
COVERAGE_BEGIN = "<!-- BEGIN GENERATED COVERAGE -->"
COVERAGE_END = "<!-- END GENERATED COVERAGE -->"

# Where audit records live. The two 2026-07-22 records predate the per-audit directory layout
# and still sit in `docs/`, because `SECURITY.md` links those paths; they carry the same front
# matter so the index has one mechanism rather than a generated table plus hand-written rows.
RECORD_GLOBS = ["docs/security-audits/*/README.md", "docs/*AUDIT-*.md"]

# Groups the coverage table reports on. Defined here rather than in front matter because a
# group is a fact about the repository's layout, not about any one audit - and an audit must
# not be able to invent a group that makes its own coverage look complete.
#
# Adding a group is rare and deliberate. Leaving one OUT is the dangerous direction: an
# unlisted directory is invisible to the coverage table, so `test_audit_index.py` asserts that
# every tracked Python file falls into some group.
GROUPS: list[tuple[str, list[str]]] = [
    ("`src/csa_google_workspace/` — top level", ["src/csa_google_workspace/*.py"]),
    ("`documents/` — per-type content", ["src/csa_google_workspace/documents/*.py"]),
    ("`mcp/` — server, auth flow, config, resources", ["src/csa_google_workspace/mcp/*.py"]),
    ("`mcp/_tools/` — the tool registrations",
     ["src/csa_google_workspace/mcp/_tools/*.py"]),
    ("`demo/`", ["src/csa_google_workspace/demo/*.py"]),
    ("`tests/` as code", ["tests/*.py", "tests/*/*.py"]),
    ("`.github/workflows/`", [".github/workflows/*.yml"]),
    ("packaging and secret-scanning config",
     ["pyproject.toml", ".gitignore", ".gitleaks.toml"]),
    ("`scripts/`", ["scripts/*.py", "scripts/*.sh"]),
    ("`experiments/`", ["experiments/*/*.py", "experiments/*/*.md"]),
    ("`research/`", ["research/*.md"]),
]



def matches(path: str, pattern: str) -> bool:
    """Path-aware glob: `*` does NOT cross a directory separator.

    `fnmatch` alone is wrong here and wrong in a way that looks right. Its `*` matches `/`, so
    `src/csa_google_workspace/*.py` matched every module in every subpackage - the top-level
    group reported 53 files instead of its own 17, and the coverage verdict came out as a
    plausible "partial - 16/53" for a group that is in fact fully covered.

    A generated table that is confidently wrong is worse than the hand-written one it replaced,
    which is why this is a named function with tests rather than a call to fnmatch.
    """
    parts, globs = path.split("/"), pattern.split("/")
    return len(parts) == len(globs) and all(
        fnmatch.fnmatch(part, glob) for part, glob in zip(parts, globs, strict=True))


@dataclass
class Audit:
    path: Path
    meta: dict

    @property
    def date(self) -> str:
        raw = self.meta.get("date_completed") or self.meta.get("date_started") or ""
        return str(raw)[:10]

    @property
    def link(self) -> str:
        """Relative to `docs/security-audits/`, where the index lives."""
        if self.path.parent.parent.name == "security-audits":
            return f"{self.path.parent.name}/"
        return f"../{self.path.name}"

    @property
    def label(self) -> str:
        return str(self.meta.get("index_label") or self.meta.get("audit_id") or self.path.name)

    def covers(self, file: str) -> bool:
        return any(matches(file, pattern)
                   for pattern in (self.meta.get("modules_covered") or []))


def front_matter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    parsed = yaml.safe_load(text[4:end])
    return parsed if isinstance(parsed, dict) else None


def load_audits() -> list[Audit]:
    audits = []
    for glob in RECORD_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            meta = front_matter(path)
            if meta and meta.get("audit_id"):
                audits.append(Audit(path, meta))
    # Newest first, which is how the index reads and how "first covered by" is resolved
    # (reversed) below.
    return sorted(audits, key=lambda a: a.date, reverse=True)


def tracked_files() -> list[str]:
    """`git ls-files`, so the coverage table describes what is IN the repository.

    Not `Path.glob`: that would count untracked scratch files and a `.venv`, and would make
    the answer depend on the state of somebody's working tree rather than on the commit.
    """
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                         capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def render_index(audits: list[Audit]) -> str:
    header = ("| audit | date | tool | model | interaction | automation | depth | findings |"
              " remediation |\n|---|---|---|---|---|---|---|---|---|")
    rows = []
    for audit in audits:
        meta = audit.meta
        findings = meta.get("findings_summary")
        if not findings:
            parts = [f"{meta['findings_total']} total"] if meta.get("findings_total") else []
            for key, word in (("findings_exploitable", "exploitable"),
                              ("findings_hardening", "hardening")):
                if meta.get(key) is not None:
                    parts.append(f"{meta[key]} {word}")
            findings = " · ".join(parts) or "—"
        tool = meta.get("tool", "—")
        if meta.get("tool_harness"):
            tool = f"{tool} + {meta['tool_harness']}"
        rows.append(
            f"| [{audit.label}]({audit.link}){' †' if meta.get('legacy_location') else ''} "
            f"| {audit.date} | {tool} | {meta.get('model') or '—'} "
            f"| {meta.get('human_interaction', '—')} | {meta.get('automation', '—')} "
            f"| {meta.get('review_depth', '—')} | {findings} "
            f"| {meta.get('remediation_summary') or meta.get('remediation_status', '—')} |")
    return "\n".join([header, *rows])


def render_coverage(audits: list[Audit], files: list[str]) -> str:
    oldest_first = sorted(audits, key=lambda a: a.date)
    # No standalone file-count column, deliberately. It made the table churn on every PR that
    # added a test - the count moved, the verdict did not - so `--check` failed on changes that
    # said nothing about coverage, and a check that fails for uninteresting reasons gets
    # regenerated reflexively rather than read. The count survives where it carries information:
    # inside a `partial - n/m` verdict, which by definition only appears when there IS a gap.
    header = "| group | first covered by |\n|---|---|"
    rows = []
    for name, patterns in GROUPS:
        members = [f for f in files if any(matches(f, p) for p in patterns)]
        if not members:
            continue
        # The EARLIEST audit that covers the group in full - not the earliest that covers any
        # of it. Breaking on the first partial match reported `src/` top level as "partial -
        # 12/20 at 2026-07-22" while the 2026-08-27 audit covers all twenty, understating
        # current coverage. Understating is the safer direction to be wrong in, and it is still
        # wrong: the table's job is "is this covered, and since when".
        full = [a for a in oldest_first
                if all(a.covers(f) for f in members)]
        if full:
            verdict = f"{full[0].date} · {full[0].meta.get('tool', '?')}"
        else:
            best = max(oldest_first,
                       key=lambda a: sum(1 for f in members if a.covers(f)),
                       default=None)
            count = sum(1 for f in members if best.covers(f)) if best else 0
            verdict = (f"**partial** — {count}/{len(members)} at {best.date}"
                       if count else "**not yet audited**")
        rows.append(f"| {name} | {verdict} |")
    return "\n".join([header, *rows])


def splice(text: str, begin: str, end: str, body: str) -> str:
    start, stop = text.index(begin) + len(begin), text.index(end)
    return text[:start] + "\n" + body + "\n" + text[stop:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed index differs from the generated one")
    args = parser.parse_args()

    audits = load_audits()
    if not audits:
        print("No audit records with front matter found. Refusing to write an empty index - "
              "an index that lists no audits is not a fixed index.", file=sys.stderr)
        return 1

    current = INDEX.read_text(encoding="utf-8")
    for marker in (INDEX_BEGIN, INDEX_END, COVERAGE_BEGIN, COVERAGE_END):
        if marker not in current:
            print(f"{INDEX} is missing the marker {marker!r}.", file=sys.stderr)
            return 1

    files = tracked_files()
    updated = splice(current, INDEX_BEGIN, INDEX_END, render_index(audits))
    updated = splice(updated, COVERAGE_BEGIN, COVERAGE_END, render_coverage(audits, files))

    if args.check:
        if updated == current:
            print(f"Index is current ({len(audits)} audit record(s)).")
            return 0
        print("docs/security-audits/README.md is out of date. Run:\n"
              "    python scripts/gen_audit_index.py\n"
              "A stale coverage table does not merely look untidy - it claims an audit covered "
              "code it never saw.", file=sys.stderr)
        return 1

    if updated == current:
        print(f"Index already current ({len(audits)} audit record(s)).")
        return 0
    INDEX.write_text(updated, encoding="utf-8")
    print(f"Regenerated from {len(audits)} audit record(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
