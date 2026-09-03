"""Cell notes are reachable, and a comment register says when it is not showing them.

A **note** is not a comment, and the difference is the whole point:

| | author | threaded | repliable | resolvable |
|---|---|---|---|---|
| comment | yes | yes | yes | yes |
| **note** | **no** | **no** | **no** | **no** |

So a reply-and-resolve workflow has no destination for one — and, MEASURED 2026-09-02
(`experiments/docs-anchor-states/probe_notes.py`), **a file carrying a note returns ZERO comments
from the Drive comments API.** The two are different objects and the comments API does not see
notes at all.

That is why the register carries a caveat rather than silently omitting them. #358 names this as
the expensive failure and says why from experience:

> A silent zero is the expensive failure. We once had a `resolved` field parsed against the wrong
> vocabulary, which turned 17 closed threads into 0 while every test stayed green.

A tool reporting "no comments" on a sheet covered in notes is telling the truth and giving the
wrong impression.
"""
from __future__ import annotations

from csa_google_workspace import Workspace
from csa_google_workspace._cellmap import column_letters
from csa_google_workspace._export import comment_rows
from csa_google_workspace.backend import FakeBackend

SHEET = "application/vnd.google-apps.spreadsheet"
F = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"


def sheet_with(notes: dict[tuple[int, int], str], tab: str = "Sheet1", comments=None):
    """`notes` keyed by 0-based (row, col), the shape Google's `rowData` uses."""
    max_r = max((r for r, _ in notes), default=-1) + 1
    max_c = max((c for _, c in notes), default=-1) + 1
    row_data = [{"values": [{"note": notes[(r, c)]} if (r, c) in notes else {}
                            for c in range(max_c)]} for r in range(max_r)]
    return Workspace(FakeBackend(
        {F: {"id": F, "name": "n", "mimeType": SHEET}},
        comments={F: comments or []},
        spreadsheets={F: {"sheets": [{"properties": {"sheetId": 0, "title": tab},
                                      "data": [{"rowData": row_data}]}]}})).open(F)


class TestReadingNotes:
    def test_a_note_is_found_with_its_cell_and_tab(self):
        s = sheet_with({(2, 1): "restated after the Q3 audit"})
        assert len(s.notes) == 1
        note = s.notes[0]
        assert (note.tab, note.cell, note.text) == ("Sheet1", "B3", "restated after the Q3 audit")

    def test_cells_without_notes_are_not_reported(self):
        """`rowData` returns an entry for every cell in range, most with no `note` key. Treating
        a missing key as an empty note would report a note on every populated cell."""
        assert sheet_with({(0, 0): "only this one"}).notes[0].cell == "A1"
        assert len(sheet_with({(0, 0): "only this one"}).notes) == 1

    def test_an_empty_note_string_is_not_a_note(self):
        """A cleared note can arrive as `""` rather than as a missing key. Truthiness is what
        separates them, and `if text is not None` would report a note on every cleared cell —
        which is the same shape as the missing-key case and worth pinning separately."""
        s = sheet_with({(0, 0): ""})
        assert s.notes == []

    def test_a_sheet_with_no_notes_returns_an_empty_list(self):
        assert sheet_with({}).notes == []

    def test_the_repr_does_not_leak_the_note_text(self):
        """Note text is document content and embedders log these objects — the same rule every
        other model here follows."""
        text = repr(sheet_with({(0, 0): "confidential restatement"}).notes[0])
        assert "confidential" not in text and "text_chars=24" in text


class TestTheA1ColumnConversion:
    """Bijective base-26, which is where this is usually got wrong."""

    def test_the_first_twenty_six(self):
        assert column_letters(1) == "A" and column_letters(26) == "Z"

    def test_the_boundary_that_catches_plain_base_26(self):
        """27 is AA. Plain `divmod(col, 26)` gives `A@` for 26 and shifts everything after."""
        assert column_letters(27) == "AA"
        assert column_letters(52) == "AZ"
        assert column_letters(53) == "BA"
        assert column_letters(702) == "ZZ"
        assert column_letters(703) == "AAA"

    def test_it_round_trips_against_the_existing_parser(self):
        """The inverse of `location_from_ref`'s loop, so they must agree — asserted rather than
        assumed, because they are written in different directions in different functions."""
        from csa_google_workspace._cellmap import location_from_ref
        for col in (1, 2, 26, 27, 28, 52, 53, 701, 702, 703, 1000):
            assert location_from_ref(f"{column_letters(col)}1").col == col


class TestTheRegisterSaysWhenItIsHidingNotes:
    def _rows(self, notes, comments):
        doc = sheet_with(notes, comments=comments)
        return comment_rows(doc, list(doc.comments.all()))

    def test_a_caveat_names_the_count_and_says_they_are_not_comments(self):
        _, _, caveats = self._rows({(2, 1): "a note"},
                                   [{"id": "c1", "content": "x", "author": {"displayName": "A"}}])
        note_caveat = [c for c in caveats if "NOTE" in c]
        assert note_caveat, "the register did not mention the notes it is not showing"
        assert "1 cell NOTE" in note_caveat[0]
        assert "cannot be replied to or resolved" in note_caveat[0]
        assert "list_notes" in note_caveat[0], "a caveat should say what to do about it"

    def test_no_notes_means_no_caveat(self):
        """A caveat that always fires is noise, and the reader stops reading the list."""
        _, _, caveats = self._rows({}, [{"id": "c1", "content": "x",
                                         "author": {"displayName": "A"}}])
        assert not [c for c in caveats if "NOTE" in c]

    def test_notes_do_not_become_rows(self):
        """They are a different object with no place in a reply-and-resolve register. The
        caveat is how they are surfaced; a row would offer actions that cannot be taken."""
        _, rows, _ = self._rows({(2, 1): "a note"},
                                [{"id": "c1", "content": "x", "author": {"displayName": "A"}}])
        assert len(rows) == 1 and rows[0]["text"] == "x"

    def test_the_caveat_appears_even_with_no_comments_at_all(self):
        """The sharpest case: zero comments and several notes. Without this the register says
        nothing at all about a file that is covered in annotations."""
        _, rows, caveats = self._rows({(0, 0): "one", (1, 0): "two"}, [])
        assert rows == []
        assert any("2 cell NOTE" in c for c in caveats)


def test_a_document_without_notes_does_not_break_the_register():
    """`_note_count` is best-effort: a Doc has no `notes` at all, and a register for one must
    not fail looking for them."""
    doc = Workspace(FakeBackend(
        {F: {"id": F, "name": "n", "mimeType": "application/vnd.google-apps.document"}},
        comments={F: [{"id": "c1", "content": "x", "author": {"displayName": "A"}}]},
        documents={F: {"body": {"content": []}}})).open(F)
    _, rows, caveats = comment_rows(doc, list(doc.comments.all()))
    assert len(rows) == 1
    assert not [c for c in caveats if "NOTE" in c]
