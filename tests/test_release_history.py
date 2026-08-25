"""The changelog must not claim versions nobody can install.

This exists because it already happened: eleven entries accumulated for versions that were
bumped in code, never tagged, and never published. Anyone reading the changelog would
reasonably have tried `pip install ==0.9.0`.

Bumping `__version__` is free; publishing is a separate, gated act. A file that records
*intent* and a registry that records *fact* will drift, and the file is the one people read —
so the distinction is asserted here rather than trusted to discipline.

Offline on purpose: this checks the changelog against itself and against `__version__`. The
three-way reconcile against git tags and PyPI needs network and a full clone, and lives in
`scripts/check_release_history.py`.
"""
import pathlib
import re

import csa_google_workspace

CHANGELOG = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"
HEADING = re.compile(r"^## (?P<date>\d{4}-\d{2}-\d{2}) — v(?P<version>[0-9]+(?:\.[0-9]+)*)"
                     r"(?P<rest>.*)$", re.M)
UNRELEASED = "not released"


def _headings():
    text = CHANGELOG.read_text(encoding="utf-8")
    found = list(HEADING.finditer(text))
    assert found, "no version headings matched — the changelog format changed"
    return found


def _published_line():
    """The `**On PyPI:**` line, as the file's own claim about what was published."""
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(r"\*\*On PyPI:\*\*(?P<versions>[^\n]*(?:\n>[^\n*]*)?)", text)
    assert match, "the changelog no longer states which versions are on PyPI"
    return match.group("versions")


def test_every_heading_is_marked_released_or_not():
    """The two states must be distinguishable without asking PyPI."""
    published = _published_line()
    for heading in _headings():
        version = heading.group("version")
        marked_unreleased = UNRELEASED in heading.group("rest")
        # A published version is named in the summary line; anything else must say so.
        claimed_published = version in published or version.rsplit(".", 1)[0] in published
        assert marked_unreleased or claimed_published, (
            f"v{version} is neither marked '{UNRELEASED}' nor listed as published. If it "
            f"shipped, add it to the '**On PyPI:**' line; if it did not, mark the heading.")


def test_no_heading_claims_both_states():
    published = _published_line()
    for heading in _headings():
        version = heading.group("version")
        if UNRELEASED in heading.group("rest"):
            assert version not in published.split(), (
                f"v{version} is marked '{UNRELEASED}' but also listed as published")


def test_the_current_version_has_an_entry():
    """A release with no changelog entry is a release nobody can read about, and the PyPI
    long-description is frozen at publish time — so this cannot be fixed afterwards."""
    current = csa_google_workspace.__version__
    versions = [h.group("version") for h in _headings()]
    assert current in versions, f"__version__ is {current} but the changelog has no entry for it"


def test_the_current_version_is_the_newest_entry():
    """Guards the ordering mistake where a bump lands above an older heading."""
    newest = _headings()[0].group("version")
    assert newest == csa_google_workspace.__version__, (
        f"the top changelog entry is v{newest} but __version__ is "
        f"{csa_google_workspace.__version__}")


def test_versions_descend():
    def key(v):
        return tuple(int(part) for part in v.split("."))
    versions = [key(h.group("version")) for h in _headings()]
    assert versions == sorted(versions, reverse=True), "changelog entries are out of order"


def test_dates_are_plausible_and_do_not_go_backwards():
    dates = [h.group("date") for h in _headings()]
    assert dates == sorted(dates, reverse=True), "changelog dates are out of order"
