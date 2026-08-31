"""Copying a file loses every comment, and the tool has to say so.

**Measured 2026-08-31** against live Google, while trying to test something else: a copy of a
spreadsheet carrying one anchored comment came back with **zero** comments. Drive v3's
`files.copy` has **no comments parameter at all** — v2 had one, v3 does not — so this is not a
default that can be changed.

**Why this matters more here than in a general Drive library.** This project exists for comment
triage. Duplicating a reviewed document to make a "v2" leaves the entire review behind, and the
failure is **silent and invisible**: the copy has the same text, the same title, and no warning.
Somebody would discover it when they went looking for feedback that no longer exists.

The description is the only place that can warn them — `CLAUDE.md` invariant 10: *a type is not a
contract with the model; the description is.*

**Found by a failing assertion, not by a passing test.** A probe copied a document to test
anchor survival on a throwaway, and asserted the copy carried an anchored comment before
proceeding. It did not, so the probe stopped rather than measuring nothing and reporting a result.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.files import FileCollection
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server


@pytest.fixture(scope="module")
def descriptions() -> dict[str, str]:
    app = create_server(lambda: Workspace(FakeBackend({})),
                        settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                                    "CSA_GW_ALLOWLIST_MODIFY": "*",
                                                    "CSA_GW_PROFILE": "full"}))
    return {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}


class TestTheToolSaysCommentsAreNotCopied:
    def test_it_says_the_copy_has_no_comments(self, descriptions):
        assert "NO COMMENTS" in descriptions["copy_file"].upper()

    def test_it_names_the_tool_that_preserves_them(self, descriptions):
        """A warning without a remedy makes a model report a dead end. `export_comments` is the
        thing to do first, so the description names it."""
        assert "export_comments" in descriptions["copy_file"]

    def test_it_says_the_failure_is_silent(self, descriptions):
        """The reason this needs saying at all: nothing about the copy looks wrong. A model that
        knows only "comments are not copied" may still not think to mention it."""
        assert "silent" in descriptions["copy_file"].lower()

    def test_it_does_not_claim_an_option_exists(self, descriptions):
        """Drive v3 has no comments parameter on `files.copy`. A description hinting at one
        would send a model looking for a flag it cannot find, which is worse than the plain
        limitation."""
        text = descriptions["copy_file"].lower()
        assert "no option" in text or "no comments parameter" in text


class TestTheLibraryMethodSaysItToo:
    def test_the_docstring_carries_the_same_warning(self):
        """Embedders read the library, not the tool description — and `FileCollection.copy` is
        the one they call. The fact has to live in both places or half the callers never see it.
        """
        doc = FileCollection.copy.__doc__ or ""
        assert "no comments" in doc.lower()
        assert "v2 had one" in doc, "say WHY there is no option, or somebody will look for one"
