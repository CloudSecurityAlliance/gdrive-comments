"""`anchored` tells the three anchor states apart, and cell headers make a cell comment readable.

**#361.** Three different situations arrive as a falsy `quoted_text`, and a consumer could not
tell them apart: a comment about the whole file, a comment attached to something with no text
(an image, a cell), and a comment on text. All three were measured against live Google on
2026-09-02 — `experiments/docs-anchor-states/RESULTS.md`.

The discriminator turned out **not** to be where the request looked. It is `anchor` PRESENCE,
which the library already retained (`Comment.anchor`) and both consumer surfaces dropped. So the
fix is additive and `quoted_text` keeps meaning exactly what was selected — the hard constraint
#358 states, and for a good reason: staleness detection works by testing whether the stored quote
still occurs in the document exactly once, so a widened `quoted_text` would present a contract
change as document drift.

Two measured facts underpin the whole thing, and a future reader should not have to re-derive
them:

**There is no "anchored but nothing selected" state for text.** Docs expands a bare caret to its
enclosing word, and refuses to comment on an empty paragraph at all. So an anchored comment with
no quoted text is anchored to something that is *not text*.

**The anchor is opaque** — `kix.…` in Docs, `workbook-range` in Sheets. A key, not a coordinate.
It is deliberately not exposed; `anchored` is the part of it that carries information.

**#358 §6.** `row_header`/`column_header` cost nothing — the same grid `cell_text` already reads —
and they are what turns *"a comment on B11"* into something a reader can act on. They are a
**guess** (column A, row 1) and are reported as one.
"""
from __future__ import annotations

from csa_google_workspace import Workspace
from csa_google_workspace._export import comment_rows
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.comments import Comment

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
F = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"


def raw(**kw):
    d = {"id": "c1", "content": "x", "author": {"displayName": "A"}}
    d.update(kw)
    return d


class TestTheThreeAnchorStates:
    """The exact states measured on live Docs, asserted on the model."""

    def test_file_level_is_not_anchored(self):
        """Drive omits the key entirely rather than nulling it, so absence is the only form."""
        c = Comment.from_api(raw())
        assert c.anchored is False and c.quoted_text is None

    def test_anchored_to_a_non_text_object_has_an_anchor_and_no_quote(self):
        """The image case, and the reason this field exists. MEASURED: a comment on an inline
        image returned `anchor: kix.y1h574n5va9q` with `quotedFileContent` absent."""
        c = Comment.from_api(raw(anchor="kix.y1h574n5va9q"))
        assert c.anchored is True and c.quoted_text is None

    def test_anchored_to_text_has_both(self):
        c = Comment.from_api(raw(anchor="kix.ce7ypxwipivp",
                                 quotedFileContent={"mimeType": "text/html",
                                                    "value": "taxonomy in this"}))
        assert c.anchored is True and c.quoted_text == "taxonomy in this"

    def test_the_two_None_cases_are_now_distinguishable(self):
        """The whole point, stated as the comparison a consumer could not previously make."""
        file_level = Comment.from_api(raw())
        on_an_image = Comment.from_api(raw(anchor="kix.abc"))
        assert file_level.quoted_text == on_an_image.quoted_text is None
        assert file_level.anchored != on_an_image.anchored

    def test_a_sheets_anchor_counts_too(self):
        """Sheets anchors are `workbook-range`, a different opaque form. `anchored` is about
        presence, so it must not care which editor produced it."""
        c = Comment.from_api(raw(anchor='{"type":"workbook-range","uid":0,"range":"145395"}'))
        assert c.anchored is True

    def test_the_opaque_anchor_itself_is_not_promised_to_be_meaningful(self):
        """`anchor` stays on the model for the library, but it is a KEY: `kix.…` carries no
        position, measured 2026-09-02 against Google's own published example which does."""
        c = Comment.from_api(raw(anchor="kix.ce7ypxwipivp"))
        assert c.anchor == "kix.ce7ypxwipivp"


class TestItReachesBothConsumerSurfaces:
    """It was retained by the library and dropped by both. That was the defect."""

    def _ws(self, comments):
        return Workspace(FakeBackend({F: {"id": F, "name": "n", "mimeType": DOC}},
                                     comments={F: comments},
                                     documents={F: {"body": {"content": []}}}))

    def test_the_mcp_result_carries_it(self):
        from csa_google_workspace.mcp._schemas import comment_out
        doc = self._ws([raw(anchor="kix.abc")]).open(F)
        assert comment_out(doc.comments.all()[0])["anchored"] is True

    def test_and_reports_false_rather_than_omitting_it(self):
        """A missing key and `false` read differently to a model; this is always known."""
        from csa_google_workspace.mcp._schemas import comment_out
        doc = self._ws([raw()]).open(F)
        out = comment_out(doc.comments.all()[0])
        assert "anchored" in out and out["anchored"] is False

    def test_the_register_carries_it_as_text(self):
        doc = self._ws([raw(anchor="kix.abc")]).open(F)
        columns, rows, _ = comment_rows(doc, list(doc.comments.all()))
        assert "anchored" in columns
        assert rows[0]["anchored"] == "TRUE"

    def test_the_register_never_leaves_it_blank(self):
        """Unlike the decision columns, this has no third state - it is known for every
        comment, so a blank would be a defect rather than 'not decided'."""
        doc = self._ws([raw(), raw(id="c2", anchor="kix.x")]).open(F)
        _, rows, _ = comment_rows(doc, list(doc.comments.all()))
        assert {r["anchored"] for r in rows if not r["reply_to"]} == {"TRUE", "FALSE"}


GRID = [["", "Q3 actual", "Q3 plan"],
        ["Northeast", "412000", "400000"],
        ["Southwest", "388000", "410000"]]


class TestCellHeaders:
    def _sheet(self):
        return Workspace(FakeBackend(
            {F: {"id": F, "name": "n", "mimeType": SHEET}},
            comments={F: [raw(anchor='{"type":"workbook-range"}')]},
            spreadsheets={F: {"sheets": [{"properties": {"title": "Sheet1", "sheetId": 0},
                                          "data": [{"rowData": []}]}]}})).open(F)

    def test_headers_come_from_column_A_and_row_1(self):
        """Indices are 1-based throughout, like `_at` and `Location.row`/`col`."""
        from csa_google_workspace._export import _headers
        assert _headers(GRID, 3, 2) == ("Southwest", "Q3 actual")

    def test_a_comment_ON_a_header_is_not_labelled_with_itself(self):
        """B1 holds "Q3 actual" and IS the column header. Reporting `column_header="Q3 actual"`
        would be circular — it reads as an independent fact and is not one. Its row header is
        A1, which is empty in this layout, so the honest answer is neither."""
        from csa_google_workspace._export import _headers
        assert _headers(GRID, 1, 2) == (None, None)

    def test_the_same_in_the_header_column(self):
        """A3 holds "Southwest" and IS the row header; its column header would be A1, empty."""
        from csa_google_workspace._export import _headers
        assert _headers(GRID, 3, 1) == (None, None)

    def test_a_header_cell_still_gets_the_OTHER_axis_when_there_is_one(self):
        """The suppression is per-axis, not all-or-nothing: with a corner label present, a
        comment in the header row still gets its row header."""
        from csa_google_workspace._export import _headers
        titled = [["Region", "Q3 actual"], ["Southwest", "388000"]]
        assert _headers(titled, 1, 2) == ("Region", None)
        assert _headers(titled, 2, 1) == (None, "Region")

    def test_A1_gets_neither(self):
        from csa_google_workspace._export import _headers
        assert _headers(GRID, 1, 1) == (None, None)

    def test_an_empty_header_cell_is_None_not_empty_string(self):
        """`None` and `''` mean different things downstream, and a blank label is not a label."""
        from csa_google_workspace._export import _headers
        assert _headers([["", "", ""], ["", "x", ""]], 2, 2) == (None, None)
