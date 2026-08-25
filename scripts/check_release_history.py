#!/usr/bin/env python3
"""Reconcile CHANGELOG.md, git tags, and PyPI. Run before cutting a release.

Three records of the same thing that drift apart, each for its own reason:

* the **changelog** records intent, and is written when the change lands
* **git tags** record what was released, and are cut later — or forgotten
* **PyPI** records what people can actually install, and is immutable

The changelog is the one people read, so it is the one that must not lie. This exits non-zero
on any disagreement and prints what to do about each.

Deliberately a script rather than a test: it needs the network and a full clone with tags,
and `tests/` is offline by contract. `tests/test_release_history.py` covers what can be
checked without either.

    python scripts/check_release_history.py [--offline]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "csa-google-workspace"
SRC = ROOT / "src" / "csa_google_workspace" / "__init__.py"
HEADING = re.compile(r"^## \d{4}-\d{2}-\d{2} — v([0-9]+(?:\.[0-9]+)*)(.*)$", re.M)
UNRELEASED = "not released"


def changelog_versions() -> dict[str, bool]:
    """version -> was it claimed as released."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return {m.group(1): UNRELEASED not in m.group(2) for m in HEADING.finditer(text)}


def current_version() -> str:
    """`__version__`, read as text so the check needs nothing importable."""
    match = re.search(r'^__version__ = "([^"]+)"', SRC.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"could not find __version__ in {SRC}")
    return match.group(1)


def git_tags() -> set[str]:
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return {line.strip().lstrip("v") for line in out.splitlines() if line.strip()}


def pypi_versions() -> set[str] | None:
    """None when PyPI could not be reached — an unreachable index is not a discrepancy."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed https URL, not user input
                f"https://pypi.org/pypi/{PROJECT}/json", timeout=15) as response:
            return set(json.load(response)["releases"])
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        print(f"  ! could not reach PyPI ({e}); skipping that comparison")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="skip the PyPI comparison")
    args = parser.parse_args()

    entries = changelog_versions()
    claimed = {v for v, released in entries.items() if released}
    tags = git_tags()
    published = None if args.offline else pypi_versions()

    # The point of this script is to run *before* tagging, so the version about to be released
    # is legitimately in the changelog, untagged and unpublished. Reporting that as a
    # discrepancy every single time is how a check earns its way onto the list of output people
    # skim past. Named explicitly instead.
    pending = current_version()
    if pending in claimed and pending not in tags and (published is None or
                                                       pending not in published):
        print(f"pending  : v{pending} — the current __version__, in the changelog and not yet "
              f"released.\n           Expected if you are about to tag it; a problem if you "
              f"thought you already had.\n")
        claimed = claimed - {pending}
        entries = {v: r for v, r in entries.items() if v != pending}

    print(f"changelog: {len(entries)} version entries, {len(claimed)} claimed released")
    print(f"git tags : {len(tags)}")
    if published is not None:
        print(f"pypi     : {len(published)}")
    print()

    problems: list[str] = []

    for version in sorted(claimed - tags, key=_key):
        problems.append(
            f"v{version}: the changelog claims it was released, but there is no git tag. "
            f"Either tag the commit that bumped it, or mark the heading '{UNRELEASED}'.")

    for version in sorted(tags - set(entries), key=_key):
        problems.append(f"v{version}: tagged, but the changelog has no entry for it.")

    for version in sorted(tags - claimed, key=_key):
        if version in entries:
            problems.append(
                f"v{version}: tagged, but the changelog marks it '{UNRELEASED}'. A tag should "
                f"mean released — remove one or the other.")

    if published is not None:
        for version in sorted(published - claimed, key=_key):
            problems.append(
                f"v{version}: on PyPI, but the changelog does not claim it was released. "
                f"People can install it; the changelog should say so.")
        for version in sorted(claimed - published, key=_key):
            problems.append(
                f"v{version}: the changelog claims it was released, but it is not on PyPI. "
                f"`pip install {PROJECT}=={version}` will fail.")

    if problems:
        print(f"{len(problems)} discrepancy/ies:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("changelog, tags and PyPI agree.")
    return 0


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


if __name__ == "__main__":
    sys.exit(main())
