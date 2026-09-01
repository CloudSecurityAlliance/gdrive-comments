"""Blanking a cell is `content.write`, deliberately — and this file exists so nobody "fixes" it.

Audit `2026-09-01-02` raised `clear_cells` being gated `content.write` while its three siblings
are `content.delete`, and while four artefacts — the model-facing tool description among them —
said it needed `content.delete`. The finding was **correct about the inconsistency and wrong about
which side to change.**

Two measurements settled it:

1. **A `writer` can already destroy cell contents**, because `update_cells` overwrites whatever
   was there and `replace_text("x", "")` blanks text. Moving `clear_cells` to `content.delete`
   would not have prevented the destruction — only removed the tidy way to do it.
2. **`content.delete` IS a real bound for the other three.** `delete_range`, `delete_tab` and
   `delete_document_tab` are unreachable from `content.write`; all three refuse for a `writer`.
   So the line `content.delete` draws is **structural** destruction, not destruction generally.

The CINO's call (2026-09-01) was to keep cell-level destruction in `content.write`, because
**withholding it does not prevent the destruction — it makes somebody write a placeholder
instead**, and a placeholder is worse than a blank: a blank cell is obviously empty, `-` or `TBD`
or `0` looks like data. The tool description had already made that argument for its own existence,
which is why `clear_cells` is not merely `update_cells` with empty strings.

The same reasoning that put trashing under `writer`: withholding a recoverable capability produced
irreversible litter in real Drives.

**And it is recoverable — by a human.** Drive keeps revision history for content, including
deleted tabs and ranges. What an agent lacks is an undo it can reach. That is a much smaller claim
than "irreversible", and it is what distinguishes this from deleting a *comment*, for which Drive
keeps no revision history at all.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.policy import (
    _GATES,
    CONTENT_DELETE,
    CONTENT_WRITE,
    PROFILES,
    Policy,
    PolicyBackend,
)

SHEET = "s1"
DOC = "d1"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
DOC_MIME = "application/vnd.google-apps.document"


def spreadsheet(profile: str):
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "Book", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}},
                                         {"properties": {"title": "Sheet2", "sheetId": 1}}]}},
        values={(SHEET, "Sheet1!A1:C1"): [["a", "b", "c"]]})
    return Workspace(PolicyBackend(backend, Policy(enabled=PROFILES[profile]))).open(SHEET)


def document(profile: str):
    backend = FakeBackend({DOC: {"id": DOC, "name": "Doc", "mimeType": DOC_MIME}},
                          documents={DOC: {"body": {"content": []}}})
    return Workspace(PolicyBackend(backend, Policy(enabled=PROFILES[profile]))).open(DOC)


class TestCellLevelDestructionIsContentWrite:
    def test_the_gate_is_content_write(self):
        """Asserted against `_GATES` rather than behaviour, so the DECISION is pinned and not
        just its consequence. An audit reading only the sibling gates will call this a defect;
        this test is the answer."""
        assert _GATES["sheets_values_clear"].capability == CONTENT_WRITE

    def test_a_writer_may_clear_cells(self):
        spreadsheet("writer").clear("Sheet1!A1:C1")

    def test_a_writer_could_destroy_the_same_range_anyway(self):
        """The measurement that decided it. If this ever starts refusing, the reasoning above
        changes and the gate is worth revisiting."""
        spreadsheet("writer").update("Sheet1!A1:C1", [["", "", ""]])

    def test_a_writer_may_blank_text_too(self):
        document("writer").replace_text("secret", "")

    def test_a_commenter_may_not(self):
        """`content.write` is still a real bound - one rung down and none of this is reachable."""
        with pytest.raises(Exception) as excinfo:
            spreadsheet("commenter").clear("Sheet1!A1:C1")
        assert "content.write" in str(excinfo.value)


class TestContentDeleteBoundsStructureNotContent:
    """What the capability actually buys, measured rather than asserted from its name."""

    @pytest.mark.parametrize("name", ["docs_delete_range", "sheets_delete_tab",
                                      "docs_delete_tab"])
    def test_the_structural_operations_need_content_delete(self, name):
        assert _GATES[name].capability == CONTENT_DELETE

    def test_a_writer_cannot_delete_a_docs_range(self):
        with pytest.raises(Exception) as excinfo:
            document("writer").delete_range(1, 10)
        assert "content.delete" in str(excinfo.value)

    def test_a_writer_cannot_delete_a_tab(self):
        with pytest.raises(Exception) as excinfo:
            spreadsheet("writer").delete_tab("Sheet2")
        assert "content.delete" in str(excinfo.value)

    def test_file_organizer_can(self):
        """The rung where structural destruction arrives, so the ladder still means something."""
        spreadsheet("fileOrganizer").delete_tab("Sheet2")


class TestTheDescriptionsDoNotPromiseABoundThatDoesNotExist:
    """The original defect was a CLAIM, not a gate. These pin the corrected claims."""

    def _clear_description(self) -> str:
        import asyncio

        from csa_google_workspace.mcp import settings_from_env
        from csa_google_workspace.mcp.server import create_server
        app = create_server(lambda: Workspace(FakeBackend({})),
                            settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
        tools = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        return tools["clear_cells"]

    def test_clear_cells_does_not_claim_to_need_content_delete(self):
        assert "Requires `content.delete`" not in self._clear_description()

    def test_clear_cells_says_it_is_destructive(self):
        """Removing the false capability claim must not remove the warning - the operation IS
        destructive, and that is the part a model needs to relay."""
        assert "DESTRUCTIVE" in self._clear_description()

    def test_it_says_a_human_can_recover(self):
        """The accurate framing. "No undo" alone reads as irreversible, which overstates it."""
        described = self._clear_description().lower()
        assert "revision history" in described and "human" in described

    def test_no_tool_description_promises_destruction_can_be_refused(self):
        """The same false promise lived in `delete_tab`'s description too, which the first sweep
        missed. Checked across EVERY registered description rather than the one tool the audit
        named - the phrase is the defect, not its location."""
        import asyncio

        from csa_google_workspace.mcp import settings_from_env
        from csa_google_workspace.mcp.server import create_server
        app = create_server(lambda: Workspace(FakeBackend({})),
                            settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
        for tool in asyncio.run(app.list_tools()):
            described = (tool.description or "")
            assert "permit editing and refuse destruction" not in described, (
                f"{tool.name} offers a bound the design does not provide: `content.write` "
                f"already destroys cell contents")

    def test_the_readme_does_not_promise_destruction_can_be_refused(self):
        """The exact sentence that was wrong: it offered an operator a bound the design cannot
        provide, because `update_cells` destroys just as thoroughly."""
        from pathlib import Path

        from tests.test_docs_do_not_drift import without_historical_notes  # noqa: PLC0415

        readme = without_historical_notes(
            (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8"))
        assert "so editing can be allowed and destruction refused" not in readme
