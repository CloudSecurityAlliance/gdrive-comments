"""Two defects a 205-comment document exposed, and the Excel destination it asked for.

**The response carried the payload it had just written to a file.** `export_comments` with
`destination="file"` wrote the CSV correctly and then returned every row as well - 171,707
characters, over the response limit. The call failed *after* doing its work, so the caller had
to check the filesystem to find out it had succeeded. The whole point of a file destination is
that the payload does NOT come back through the response, and it failed on exactly the large
documents it is most useful for.

**And there was no Excel destination.** Asked for one, the honest answer was "CSV, a Google
Sheet, or rows" - so somebody had to convert it by hand, and hit two things the tool should
have handled: reviewer text containing control characters that XLSX forbids, and three
Sheets-only columns sitting empty on a document register.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
DOC_MIME = "application/vnd.google-apps.document"

COMMENTS = {DOC: [
    {"id": f"c{i}", "content": f"Point {i}", "author": {"displayName": f"Reviewer {i % 3}"},
     "quotedFileContent": {"value": f"passage {i}"},
     "createdTime": "2026-08-20T10:00:00Z",
     "replies": [{"id": f"r{i}", "content": "Noted.", "author": {"displayName": "Kurt"}}]}
    for i in range(4)
]}
# A real reviewer's comment contained control characters - pasted from a terminal or a mail
# client. openpyxl refuses to write them, so the tool must strip them rather than fail.
HOSTILE = {DOC: [
    {"id": "c1", "content": "Make \x07absorption rate\x0b harder to game.",
     "author": {"displayName": "Reviewer"}, "replies": []}]}


def build(comments=None, **env):
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME}},
        documents={DOC: {"body": {"content": []}}}, comments=comments or COMMENTS)
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
         "CSA_GW_PROFILE": "full", **env}))


def call(app, **args):
    return asyncio.run(app.call_tool("export_comments", {"fileId": DOC, **args})
                       ).structured_content


class TestTheResponseDoesNotCarryThePayloadItJustWroteOut:
    """The bug: a file destination returned the rows as well, blowing the response limit on
    exactly the documents worth exporting."""

    def test_a_file_destination_returns_no_rows(self, tmp_path):
        out = call(build(), destination="file", path=str(tmp_path / "r.csv"))
        assert out["rows"] == []
        assert out["written_path"]

    def test_a_sheet_destination_returns_no_rows(self):
        out = call(build(), destination="sheet")
        assert out["rows"] == []
        assert out["sheet_url"]

    def test_a_csv_destination_returns_no_rows_either(self):
        """The CSV text IS the payload; returning the rows beside it doubles the response for
        no benefit."""
        out = call(build(), destination="csv")
        assert out["rows"] == []
        assert out["csv"]

    def test_rows_destination_still_returns_rows(self):
        """The one destination whose entire purpose is the rows."""
        out = call(build(), destination="rows")
        assert len(out["rows"]) == 8            # 4 comments + 4 replies

    def test_the_counts_survive_every_destination(self, tmp_path):
        """Dropping the rows must not drop the ANSWER - "how many comments" has to remain
        answerable without a second call."""
        for kwargs in ({"destination": "rows"}, {"destination": "csv"},
                       {"destination": "file", "path": str(tmp_path / "x.csv")},
                       {"destination": "sheet"}):
            out = call(build(), **kwargs)
            assert out["thread_count"] == 4 and out["row_count"] == 8, kwargs

    def test_the_columns_survive_every_destination(self, tmp_path):
        """Small, and the caller needs them to read the file it just wrote."""
        out = call(build(), destination="file", path=str(tmp_path / "y.csv"))
        assert "thread_id" in out["columns"]


class TestExcel:
    def test_it_writes_a_real_xlsx(self, tmp_path):
        out = call(build(), destination="xlsx", path=str(tmp_path / "register.xlsx"))
        written = tmp_path / "register.xlsx"
        assert written.exists() and out["written_path"] == str(written)
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(written)
        assert wb.active.max_row == 9            # header + 8

    def test_the_extension_is_forced_to_xlsx(self, tmp_path):
        """Same inert-failure property as the CSV path: an influenced name cannot write a
        shell profile."""
        call(build(), destination="xlsx", path=str(tmp_path / "zshrc"))
        assert (tmp_path / "zshrc.xlsx").exists()

    def test_a_csv_named_path_still_becomes_xlsx(self, tmp_path):
        call(build(), destination="xlsx", path=str(tmp_path / "r.csv"))
        assert (tmp_path / "r.csv.xlsx").exists()

    def test_it_never_overwrites(self, tmp_path):
        (tmp_path / "r.xlsx").write_text("mine")
        out = call(build(), destination="xlsx", path=str(tmp_path / "r.xlsx"))
        assert (tmp_path / "r.xlsx").read_text() == "mine"
        assert "already existed" in out["detail"]

    def test_control_characters_are_stripped_not_fatal(self, tmp_path):
        """Reviewer text is arbitrary human input. openpyxl raises IllegalCharacterError on
        control characters, so the tool strips them - a register that refuses to be written
        because somebody pasted from a terminal is no register at all."""
        out = call(build(HOSTILE), destination="xlsx", path=str(tmp_path / "h.xlsx"))
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(tmp_path / "h.xlsx")
        text = " ".join(str(c.value) for row in wb.active.iter_rows() for c in row if c.value)
        assert "absorption rate" in text
        assert "\x07" not in text and "\x0b" not in text
        assert out["written_path"]

    def test_columns_empty_for_every_row_are_omitted(self, tmp_path):
        """On a DOCUMENT the three Sheets-only columns are structurally absent, and carrying
        them suggests the export failed to fill them rather than that they do not apply."""
        call(build(), destination="xlsx", path=str(tmp_path / "c.xlsx"))
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(tmp_path / "c.xlsx")
        header = [c.value for c in next(wb.active.iter_rows(max_row=1))]
        assert "cell_text_by_tab" not in header
        assert "quoted_text" in header

    def test_it_has_no_formulas(self, tmp_path):
        """Deliberate. openpyxl writes formulas with no cached values, so anything reading
        cached values - a previewer, pandas - sees blanks until Excel opens the file and
        recalculates. A faithful register needs no formulas, so it has none, and the problem
        does not arise."""
        call(build(), destination="xlsx", path=str(tmp_path / "f.xlsx"))
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(tmp_path / "f.xlsx")
        for row in wb.active.iter_rows():
            for c in row:
                assert not (isinstance(c.value, str) and c.value.startswith("="))

    def test_it_is_usable_the_moment_it_opens(self, tmp_path):
        """Frozen header and an autofilter, because 221 unsorted rows is not a register."""
        call(build(), destination="xlsx", path=str(tmp_path / "u.xlsx"))
        openpyxl = pytest.importorskip("openpyxl")
        ws = openpyxl.load_workbook(tmp_path / "u.xlsx").active
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref


class TestDiscoverability:
    def test_the_description_names_xlsx(self):
        tool = next(t for t in asyncio.run(build().list_tools())
                    if t.name == "export_comments")
        assert "xlsx" in tool.description.lower()

    def test_an_unknown_destination_lists_xlsx_too(self):
        with pytest.raises(Exception) as raised:
            call(build(), destination="pdf")
        assert "xlsx" in str(raised.value)


class TestTheInputColumnsAreRealFields:
    """Dropdowns, so the two decision columns cannot be typed wrong in the first place.

    The importer already refuses a value it cannot read - "maybe later" in a resolve column
    fails rather than closing somebody's open question - but refusing at import is a round trip
    later than refusing at entry. A dropdown makes the wrong value unreachable.

    The two are NOT symmetrical, and the dropdowns say so:

        resolve_comment   TRUE / FALSE / blank   - three real states: resolve, reopen, leave
        delete_comment    TRUE / blank           - two, because Drive has no undelete. Offering
                                                   FALSE would imply a reversal that does not
                                                   exist, on the one action that cannot be undone.
    """

    def _validations(self, path):
        openpyxl = pytest.importorskip("openpyxl")
        ws = openpyxl.load_workbook(path).active
        header = [c.value for c in next(ws.iter_rows(max_row=1))]
        out = {}
        for dv in ws.data_validations.dataValidation:
            for name, idx in ((h, i) for i, h in enumerate(header, start=1)):
                letter = ws.cell(row=1, column=idx).column_letter
                if any(str(r).startswith(f"{letter}2") for r in dv.sqref.ranges):
                    out[name] = dv
        return out

    def test_resolve_offers_true_and_false(self, tmp_path):
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        dv = self._validations(tmp_path / "v.xlsx")["resolve_comment"]
        assert "TRUE" in dv.formula1 and "FALSE" in dv.formula1

    def test_delete_offers_only_true(self, tmp_path):
        """No undelete exists, so FALSE would promise a reversal Drive cannot perform."""
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        dv = self._validations(tmp_path / "v.xlsx")["delete_comment"]
        assert "TRUE" in dv.formula1 and "FALSE" not in dv.formula1

    def test_blank_is_always_allowed(self, tmp_path):
        """Most rows are untouched; a validation that rejected empty would make the register
        unopenable."""
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        for name in ("resolve_comment", "delete_comment"):
            assert self._validations(tmp_path / "v.xlsx")[name].allow_blank

    def test_the_dropdown_is_actually_shown(self, tmp_path):
        """openpyxl's `showDropDown` is INVERTED against its name: the XML attribute means
        "suppress the in-cell dropdown", so True hides it. False is what shows the arrow."""
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        dv = self._validations(tmp_path / "v.xlsx")["resolve_comment"]
        assert not dv.showDropDown

    def test_the_offered_values_are_ones_the_importer_accepts(self, tmp_path):
        """The sheet and the importer must agree, or the dropdown offers a value that then
        fails on import - which is worse than no dropdown."""
        from csa_google_workspace._apply import truthy
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        for name in ("resolve_comment", "delete_comment"):
            for value in self._validations(tmp_path / "v.xlsx")[name].formula1.strip('"').split(","):
                assert truthy(value) is not None, f"{name} offers {value!r}, unreadable on import"

    def test_the_input_columns_look_different(self, tmp_path):
        """A register is mostly read-only; the cells somebody is meant to WRITE in should not
        look like the rest."""
        openpyxl = pytest.importorskip("openpyxl")
        call(build(), destination="xlsx", path=str(tmp_path / "v.xlsx"))
        ws = openpyxl.load_workbook(tmp_path / "v.xlsx").active
        header = [c.value for c in next(ws.iter_rows(max_row=1))]
        reported = ws.cell(row=2, column=header.index("author") + 1)
        editable = ws.cell(row=2, column=header.index("reply_comment") + 1)
        assert editable.fill.fgColor.rgb != reported.fill.fgColor.rgb
