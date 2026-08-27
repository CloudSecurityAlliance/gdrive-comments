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
YANKED = "YANKED"


def changelog_versions() -> dict[str, bool]:
    """version -> was it claimed as released."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return {m.group(1): UNRELEASED not in m.group(2) for m in HEADING.finditer(text)}


def changelog_yanked() -> set[str]:
    """Versions whose changelog HEADING says YANKED.

    The heading rather than the body, because the body of a yank notice necessarily mentions
    the version people should move TO, and matching on that would mark the healthy version as
    yanked as well.
    """
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return {m.group(1) for m in HEADING.finditer(text) if YANKED in m.group(2)}


def current_version() -> str:
    """`__version__`, read as text so the check needs nothing importable."""
    match = re.search(r'^__version__ = "([^"]+)"', SRC.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"could not find __version__ in {SRC}")
    return match.group(1)


def git_tags() -> set[str]:
    """Local tags, refreshed first.

    Without the fetch this check invents discrepancies. A clone whose tags are behind - and
    `actions/checkout` fetches none by default - reports the newest release as "claims it was
    released, but there is no git tag", which reads exactly like a release that went to PyPI
    untagged. That happened, and cost a detour through PyPI and `gh release list` to establish
    that nothing was wrong at all.

    A failed fetch is not itself a discrepancy (offline, no remote, no credentials), but it is
    said out loud, because from here on the comparison is against a possibly stale list.
    """
    fetch = subprocess.run(["git", "fetch", "--tags", "--quiet"], cwd=ROOT,
                           capture_output=True, text=True)
    if fetch.returncode != 0:
        print("  ! could not fetch tags; the local list may be stale "
              f"({fetch.stderr.strip().splitlines()[-1] if fetch.stderr.strip() else 'no detail'})")
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


def simple_index_versions() -> set[str] | None:
    """Versions the SIMPLE INDEX carries. `None` when it could not be read.

    Exists to corroborate `pypi_versions()`, which reads the project-level JSON endpoint. That
    endpoint is CDN-cached per edge and lags: minutes after v0.29.0 published, a local check
    saw it and a GitHub runner did not, so this check failed on a claim that was TRUE.

    A release check that is flaky immediately after a release is worse than no check, because
    it trains people to re-run it instead of reading it. The simple index updates first - the
    same asymmetry the yank comparison below already relies on - so it is the tie-breaker.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https URL, not user input
        f"https://pypi.org/simple/{PROJECT}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return set(json.load(response).get("versions") or [])
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return None


def pypi_yanked() -> set[str] | None:
    """Versions PyPI reports as yanked, from the SIMPLE index rather than the JSON API.

    Two reasons for the simple index. It is what pip actually resolves against, so it is the
    authority on whether a yank is in effect. And it updates first — after the project's first
    yank the JSON API still reported `yanked: false` for several minutes while the simple index
    already carried the reason string, so a checker reading JSON would have called a real yank
    a discrepancy.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https URL, not user input
        f"https://pypi.org/simple/{PROJECT}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            files = json.load(response)["files"]
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        print(f"  ! could not read the simple index ({e}); skipping the yank comparison")
        return None
    out = set()
    for f in files:
        # `yanked` is False when not yanked, and either True or the REASON STRING when it is.
        if f.get("yanked"):
            match = re.search(rf"{re.escape(PROJECT.replace('-', '_'))}-([0-9.]+?)(?:-py3|\.tar)",
                              f["filename"])
            if match:
                out.add(match.group(1))
    return out


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
        # Corroborate against the simple index before calling this a discrepancy: the JSON
        # endpoint lags per CDN edge, and a false alarm here is the expensive kind.
        on_index = simple_index_versions() if claimed - published else None
        for version in sorted(claimed - published, key=_key):
            if on_index is not None and version in on_index:
                print(f"  ! v{version} is on the simple index but not yet in the JSON endpoint "
                      f"- a CDN lag, not a discrepancy. Resolves itself within minutes.")
                continue
            problems.append(
                f"v{version}: the changelog claims it was released, but it is not on PyPI. "
                f"`pip install {PROJECT}=={version}` will fail.")

    # Yanks, both directions. PROVENANCE.md requires a yank to be announced in the changelog,
    # and an announcement nobody checks is how the changelog came to claim releases that were
    # never published in the first place.
    yanked_on_pypi = pypi_yanked()
    if yanked_on_pypi is not None:
        said = changelog_yanked()
        for version in sorted(yanked_on_pypi - said, key=_key):
            problems.append(
                f"v{version}: YANKED on PyPI, and the changelog heading does not say so. "
                f"PROVENANCE.md requires a yank to be announced with its reason.")
        for version in sorted(said - yanked_on_pypi, key=_key):
            problems.append(
                f"v{version}: the changelog says YANKED, but PyPI still offers it normally. "
                f"Either the yank did not take, or the notice is wrong.")

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
