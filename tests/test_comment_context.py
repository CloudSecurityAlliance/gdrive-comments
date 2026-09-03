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
    def test_no_quoted_text_returns_None_rather_than_a_kind(self):
        """A file-level comment, or one on an image, has no passage — that is not a failure, so
        reporting a `kind` would imply a question where there is none."""
        assert _context.build(doc(para("x\n")), None) is None
        assert _context.build(doc(para("x\n")), "") is None
        assert _context.build(doc(para("x\n")), "   ") is None

    def test_a_quote_that_is_gone_says_so(self):
        c = _context.build(doc(para("something else\n")), "deleted passage")
        assert c.kind == _context.KIND_NOT_FOUND
        assert "not in the document any more" in c.note


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
    assert len(_context.KINDS) == 8


def test_the_repr_does_not_leak_the_passage():
    c = _context.build(doc(para("confidential restructuring plan\n")), "restructuring")
    assert "confidential" not in repr(c) and "kind=" in repr(c)
