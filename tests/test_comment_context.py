"""The passage around a comment's anchor — #358 §1 and §2.

The anchor records where a comment was ATTACHED, not what it is ABOUT, and the gap between
those is ordinary rather than exotic: a reviewer selects three words of a paragraph-length
point, or writes *"at the end of this paper"* while sitting on page 1.

**Located by quoted text, not by the anchor**, because the anchor cannot be used — MEASURED
2026-09-02, a real Docs anchor is an opaque `kix.…` id carrying no position. That looked fatal
and is not: the editor expands a bare caret to its enclosing word and refuses to comment on
empty space, so quoted text is present wherever text is.

Two results here came from running it against a live document rather than from reasoning, and
both changed the design:

**A one-word quote is ambiguous almost immediately.** In a NINE-paragraph document, the word a
caret snapped to occurred four times. So `ambiguous` is not an edge case — it is the dominant
outcome for the commonest under-selection, which is why it reports `candidates` rather than
merely refusing. The consumer holds the comment text and can usually tell; we cannot.

**A table's unit is the table**, not a neighbouring paragraph. The enclosing structural element
is the unit throughout, and for a table cell that element is the whole table.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import _context


def para(text, style="NORMAL_TEXT"):
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style},
                          "elements": [{"textRun": {"content": text}}]}}


def table(rows):
    return {"table": {"tableRows": [
        {"tableCells": [{"content": [para(c)]} for c in row]} for row in rows]}}


def doc(*elements):
    return {"body": {"content": list(elements)}}


class TestTheOrdinaryCase:
    def test_the_enclosing_paragraph_with_the_selection_marked_in_place(self):
        """Marking it in place IS the under-selection signal: three words at the head of a long
        paragraph is visible at a glance and needs no computation."""
        d = doc(para("The taxonomy in this section is wrong and needs rework.\n"))
        c = _context.build(d, "taxonomy in this")
        assert c.kind == _context.KIND_PARAGRAPH
        assert c.text == "The ⟦taxonomy in this⟧ section is wrong and needs rework.\n"

    def test_it_reports_where_in_the_document_it_is(self):
        """`paragraph_index` of `paragraph_total` is what makes a prose claim like "at the end
        of this paper" CHECKABLE — by the caller. We supply the fact, never the verdict."""
        d = doc(para("one\n"), para("two\n"), para("three\n"), para("four\n"))
        c = _context.build(d, "three")
        assert (c.paragraph_index, c.paragraph_total) == (3, 4)

    def test_the_heading_chain_comes_back_outermost_first(self):
        d = doc(para("Title", "TITLE"), para("Section 2", "HEADING_1"),
                para("Naming", "HEADING_2"), para("the body text\n"))
        assert _context.build(d, "body text").heading_path == (
            "Title", "Section 2", "Naming")

    def test_a_later_sibling_heading_does_not_displace_its_parent(self):
        """H1 › H2, then a second H2 — the chain must still report the H1 above both."""
        d = doc(para("Section 2", "HEADING_1"), para("First", "HEADING_2"),
                para("Second", "HEADING_2"), para("the body text\n"))
        assert _context.build(d, "body text").heading_path == ("Section 2", "Second")


class TestNoPassageToGive:
    """Every outcome explains itself, so a bare absence means only "nobody asked".

    This class used to assert the opposite — that no quoted text returns `None`, on the
    reasoning that a `kind` "would imply a question where there is none". The first half was
    right and the conclusion was wrong: `None` was ALSO what a caller got for an unsupported
    file type and for not requesting context, so one value carried "no question", "not
    supported" and "never looked". A consumer could not tell that the search had run.
    """

    @pytest.mark.parametrize("quote", [None, "", "   "])
    def test_no_quoted_text_says_there_was_nothing_to_look_for(self, quote):
        c = _context.build(doc(para("x\n")), quote)
        assert c is not None, "an absence is what this change exists to remove"
        assert c.kind == _context.KIND_NO_QUOTE
        assert c.text == ""

    def test_and_says_it_is_not_a_failure(self):
        """The distinction the note has to carry: no question asked, versus asked and failed."""
        note = _context.build(doc(para("x\n")), None).note
        assert "not a failure" in note and "no question to answer" in note
        assert "anchor_state" in note, "it should say where to look for WHICH no-quote state"

    def test_a_quote_that_is_not_there_says_WE_LOOKED(self):
        """The requested change. "Missing" and "we searched and it is absent" are different
        answers, and a consumer that cannot tell them apart has to assume the software broke."""
        c = _context.build(doc(para("something else\n")), "deleted passage")
        assert c.kind == _context.KIND_NOT_FOUND
        assert "WE SEARCHED THE DOCUMENT" in c.note
        assert "not an error" in c.note, "it must not read as a malfunction"

    def test_it_offers_the_causes_without_choosing_one(self):
        """Including the one measured in #380: the quote may never have been in the document,
        because its creator supplies that field and Google validates nothing. The old note
        asserted the passage "is not in the document ANY MORE", which presupposes it once was."""
        note = _context.build(doc(para("something else\n")), "never here").note
        assert "edited or deleted" in note      # it was there and changed
        assert "different revision" in note     # it is there, in another version
        assert "NEVER" in note                  # it was never there at all
        assert "any more" not in note, "that phrasing presupposes the passage once existed"

    def test_it_tells_the_caller_not_to_repeat_the_quote_as_fact(self):
        note = _context.build(doc(para("something else\n")), "fabricated").note
        assert "Do not repeat the quoted text as something the document says" in note


class TestTheAmbiguousCase:
    """The dominant outcome for a caret-placed comment, found by running it live."""

    def test_a_repeated_quote_is_not_guessed_at(self):
        d = doc(para("the word paragraph here\n"), para("and paragraph again\n"))
        c = _context.build(d, "paragraph")
        assert c.kind == _context.KIND_AMBIGUOUS
        assert c.text == "", "no passage is better than a guessed one"

    def test_it_says_how_many_and_that_this_is_expected(self):
        d = doc(para("paragraph\n"), para("paragraph\n"), para("paragraph\n"))
        note = _context.build(d, "paragraph").note
        assert "occurs 3 times" in note
        assert "EXPECTED" in note, (
            "a one-word selection is ambiguous by nature; a reader must not read this as a "
            "damaged document")

    def test_it_reports_the_candidate_locations(self):
        """Facts, so the caller can decide. Holding the comment text they can often tell which
        occurrence was meant — and that judgement is theirs, not ours."""
        d = doc(para("Section 2", "HEADING_1"), para("target\n"),
                para("Section 3", "HEADING_1"), para("target\n"))
        c = _context.build(d, "target")
        assert [i for i, _ in c.candidates] == [2, 4]
        assert [p for _, p in c.candidates] == [("Section 2",), ("Section 3",)]


class TestHeadings:
    def test_a_heading_gets_the_paragraph_it_HEADS(self):
        """Forward only, and it is structural rather than inferred: `namedStyleType` says this
        element heads what follows."""
        d = doc(para("Section 2 - Taxonomy", "HEADING_1"), para("The body of the section.\n"))
        c = _context.build(d, "Section 2 - Taxonomy")
        assert c.kind == _context.KIND_HEADING
        assert "⟦Section 2 - Taxonomy⟧" in c.text
        assert "The body of the section." in c.text

    def test_consecutive_headings_are_skipped(self):
        """Two labels and no prose is the thing being fixed; the chain already reports the
        subsection, so the context should carry content."""
        d = doc(para("Section 2", "HEADING_1"), para("Subsection", "HEADING_2"),
                para("actual prose here\n"))
        assert "actual prose here" in _context.build(d, "Section 2").text

    def test_a_heading_with_nothing_after_it_still_returns_the_heading(self):
        d = doc(para("Dangling heading", "HEADING_1"))
        c = _context.build(d, "Dangling heading")
        assert c.kind == _context.KIND_HEADING and "Dangling heading" in c.text


class TestTables:
    def test_a_cell_comment_gets_the_WHOLE_TABLE(self):
        """The insight that fixed the rule: the enclosing structural element is the unit, and
        for a table cell that element is the table. A neighbouring paragraph is unrelated."""
        d = doc(para("intro\n"), table([["Region", "Q3"], ["Southwest", "388000"]]))
        c = _context.build(d, "388000")
        assert c.kind == _context.KIND_TABLE
        assert "Region" in c.text and "Southwest" in c.text
        assert "intro" not in c.text

    def test_a_table_too_large_for_the_cap_degrades_to_the_row_and_header(self):
        """A 200-row table would blow any cap and tell the reader nothing. The row plus its
        header is what a person would actually want — the same instinct as a Sheets cell."""
        rows = [["Region", "Q3"]] + [[f"Row{i}", "x" * 60] for i in range(200)]
        c = _context.build(doc(table(rows)), "Row137")
        assert c.kind == _context.KIND_TABLE_ROW
        assert "Row137" in c.text and "Region" in c.text
        assert "Row12" not in c.text, "only the matching row, not the whole table"
        assert "201-row table" in c.note   # 200 data rows plus the header


class TestExpansion:
    def test_paragraphs_1_adds_one_either_side(self):
        d = doc(para("before\n"), para("target here\n"), para("after\n"))
        c = _context.build(d, "target here", paragraphs=1)
        assert c.kind == _context.KIND_PARAGRAPHS
        assert c.text.startswith("before") and c.text.endswith("after\n")

    def test_the_default_is_the_enclosing_paragraph_only(self):
        """Chosen from the case analysis rather than guessed: for under-selection the enclosing
        paragraph IS the answer, and neighbours only help the wrong-area case, which context
        cannot fix anyway."""
        d = doc(para("before\n"), para("target here\n"), para("after\n"))
        assert _context.build(d, "target here").text == "⟦target here⟧\n"

    def test_expansion_stops_at_the_boundaries_without_special_casing(self):
        d = doc(para("only one\n"))
        assert _context.build(d, "only one", paragraphs=3).text == "⟦only one⟧\n"


class TestTheCap:
    def test_a_huge_paragraph_is_truncated_and_says_so(self):
        """Structural expansion is the unit; the cap is a GUARD. A truncation the reader cannot
        see is a claim that this was the whole passage."""
        d = doc(para("start " + "filler " * 2000 + "\n"))
        c = _context.build(d, "start")
        assert c.truncated is True
        assert "truncated" in c.text and "truncated at the character limit" in c.note
        assert len(c.text) < _context.MAX_CHARS + 100


def test_every_kind_is_in_the_closed_vocabulary():
    """Closed for the reason the threat-model statuses are: a near-miss like "expanded" reads
    as meaningful while saying less than any real member. A new member — an AI-chosen passage,
    say — should be a deliberate act that updates this test."""
    for name, value in vars(_context).items():
        if name.startswith("KIND_"):
            assert value in _context.KINDS, f"{name} is not in KINDS"
    # 8 until 2026-09-03, when `no_quote` and `unsupported` were added so that a context the
    # caller asked for always explains itself. Bump this deliberately, with a reason.
    assert len(_context.KINDS) == 10


def test_the_repr_does_not_leak_the_passage():
    c = _context.build(doc(para("confidential restructuring plan\n")), "restructuring")
    assert "confidential" not in repr(c) and "kind=" in repr(c)


class TestNullMeansExactlyOneThing:
    """The invariant this change buys: a `context` of `null` means "you did not ask", and
    nothing else. Every other outcome carries a `kind` and a `note`.

    Asserted through the MCP surface rather than on `_context`, because that is where the three
    meanings were being conflated — `build()` was only one of the three producers of `None`.
    """

    DOC = "application/vnd.google-apps.document"
    SHEET = "application/vnd.google-apps.spreadsheet"
    F = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"

    def server(self, mime, comments):
        import asyncio

        from csa_google_workspace import Workspace
        from csa_google_workspace.backend import FakeBackend
        from csa_google_workspace.mcp.server import create_server
        be = FakeBackend(
            {self.F: {"id": self.F, "name": "n", "mimeType": mime}},
            comments={self.F: comments},
            documents={self.F: {"body": {"content": [
                {"paragraph": {"elements": [{"textRun": {"content": "real prose here\n"}}]}},
            ]}}},
            spreadsheets={self.F: {"sheets": [{"properties": {"sheetId": 0, "title": "S1"}}]}},
        )
        return create_server(lambda: Workspace(be)), asyncio

    def quoted(self, cid, value):
        return {"id": cid, "content": "c", "author": {"displayName": "A"},
                "anchor": "kix.a",
                "quotedFileContent": {"mimeType": "text/html", "value": value}}

    def test_not_requested_is_the_only_null(self):
        server, asyncio = self.server(self.DOC, [self.quoted("c1", "real prose here")])
        out = asyncio.run(server.call_tool("list_comments", {"fileId": self.F}))
        assert out.structured_content["comments"][0]["context"] is None

    def test_requested_and_found_explains_itself(self):
        server, asyncio = self.server(self.DOC, [self.quoted("c1", "real prose here")])
        out = asyncio.run(server.call_tool(
            "list_comments", {"fileId": self.F, "context": True}))
        ctx = out.structured_content["comments"][0]["context"]
        assert ctx is not None and ctx["kind"] == _context.KIND_PARAGRAPH

    def test_requested_with_nothing_to_find_explains_itself(self):
        """A file-level comment. The caller asked; "no passage exists" is an answer."""
        server, asyncio = self.server(
            self.DOC, [{"id": "c1", "content": "looks good", "author": {"displayName": "A"}}])
        out = asyncio.run(server.call_tool(
            "list_comments", {"fileId": self.F, "context": True}))
        ctx = out.structured_content["comments"][0]["context"]
        assert ctx is not None, "asked and got silence is the defect being fixed"
        assert ctx["kind"] == _context.KIND_NO_QUOTE

    def test_requested_but_absent_says_we_searched(self):
        server, asyncio = self.server(self.DOC, [self.quoted("c1", "not in this document")])
        out = asyncio.run(server.call_tool(
            "list_comments", {"fileId": self.F, "context": True}))
        ctx = out.structured_content["comments"][0]["context"]
        assert ctx["kind"] == _context.KIND_NOT_FOUND
        assert "WE SEARCHED THE DOCUMENT" in ctx["note"]

    def test_an_unsupported_file_type_says_so_instead_of_going_quiet(self):
        """A spreadsheet has no passage lookup here. Before, the loop returned early and every
        row kept a null the caller could not distinguish from "not requested"."""
        server, asyncio = self.server(self.SHEET, [self.quoted("c1", "anything")])
        out = asyncio.run(server.call_tool(
            "list_comments", {"fileId": self.F, "context": True}))
        ctx = out.structured_content["comments"][0]["context"]
        assert ctx is not None, "we did not look, and that must not read as nothing to find"
        assert ctx["kind"] == _context.KIND_UNSUPPORTED
        assert "cell_text" in ctx["note"], "it should name the equivalent that DOES exist"
        assert "gap in this tool, not a property of the file" in ctx["note"]

    def test_every_requested_context_is_non_null_whatever_the_outcome(self):
        """The invariant itself, over all four outcomes at once."""
        for mime, comments in (
            (self.DOC, [self.quoted("c1", "real prose here")]),        # found
            (self.DOC, [self.quoted("c2", "not in this document")]),   # searched, absent
            (self.DOC, [{"id": "c3", "content": "x",
                         "author": {"displayName": "A"}}]),            # nothing to find
            (self.SHEET, [self.quoted("c4", "anything")]),             # unsupported
        ):
            server, asyncio = self.server(mime, comments)
            out = asyncio.run(server.call_tool(
                "list_comments", {"fileId": self.F, "context": True}))
            for row in out.structured_content["comments"]:
                assert row["context"] is not None, (mime, row["id"])
                assert row["context"]["kind"] in _context.KINDS
                assert row["context"]["note"], "a kind without a note explains nothing"
