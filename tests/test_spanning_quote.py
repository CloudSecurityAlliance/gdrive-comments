"""A quote that crosses a paragraph boundary is FOUND, not declared absent (#405).

Reported from real material: one thread with `anchor_state=text` — editor-created, so the quote
is Drive's own record of what somebody selected — carrying an **830-character** selection that
spanned a paragraph boundary. This package's own `as_text()` found it **exactly once**.
`context_kind` said:

> **WE SEARCHED THE DOCUMENT AND THIS QUOTED TEXT IS NOT IN IT.**

Two functions in one package, same document, same moment, opposite answers.

## Why it happened, and why it was the worst possible failure

`_context.py` searched **within** each structural element. A quote containing the newline between
two paragraphs is inside neither of them, so the search could not match it *by construction*.

v0.44.0 had deliberately rewritten that note to state the search rather than presume a cause, and
listed three causes that "cannot be told apart": edited, a different revision, or never present.
**There was a fourth it did not contemplate — present, and unfindable by an element-scoped
search** — and the note asserted absence in capitals for a passage the same library could locate.
Strengthening the wording made the wrong answer more convincing, which is worth remembering as a
hazard of writing confident notes.

## The property that should have existed

`as_text()` and `context` must not disagree about whether a quote is *present*. They can
legitimately disagree about where it is or how much of it to show; presence is not a judgement.
`TestTheyAgreeWithAsText` asserts it directly, over every shape, because a per-case test would
have missed this one — the spanning case was simply never written.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import _context
from csa_google_workspace._content import doc_text


def para(text: str, style: str = "NORMAL_TEXT") -> dict:
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style},
                          "elements": [{"textRun": {"content": text}}]}}


def doc(*elements) -> dict:
    return {"body": {"content": list(elements)}}


THREE = doc(para("First paragraph ends here.\n"),
            para("Second paragraph starts here.\n"),
            para("Third one.\n"))


class TestASpanningQuoteIsFound:
    def test_the_reported_case_is_no_longer_not_found(self):
        c = _context.build(THREE, "ends here.\nSecond paragraph starts")
        assert c.kind == _context.KIND_SPANNING
        assert c.kind != _context.KIND_NOT_FOUND, "the #405 regression"

    def test_the_passage_is_every_element_it_TOUCHES(self):
        """Not just the one holding the start — that would report one of three paragraphs.

        The markers are stripped before checking, because they land wherever the selection
        ends and can fall mid-phrase: the passage really reads `Third⟧ one.`, so a naive
        `"Third one" in text` fails on correct output. Worth keeping as a comment — it caught
        me writing the assertion before the marker.
        """
        c = _context.build(THREE, "ends here.\nSecond paragraph starts here.\nThird")
        plain = c.text.replace(_context.OPEN, "").replace(_context.CLOSE, "")
        for expected in ("First paragraph", "Second paragraph", "Third one"):
            assert expected in plain, expected

    def test_the_selection_is_marked_in_place(self):
        c = _context.build(THREE, "ends here.\nSecond paragraph starts")
        assert _context.OPEN in c.text and _context.CLOSE in c.text
        assert c.text.startswith("First paragraph "), "surrounding context is kept"

    def test_it_reports_a_paragraph_index_and_heading_path(self):
        d = doc(para("Section 2", "HEADING_1"),
                para("Alpha ends here.\n"), para("Beta starts here.\n"))
        c = _context.build(d, "ends here.\nBeta starts")
        assert c.heading_path == ("Section 2",)
        assert c.paragraph_index is not None and c.paragraph_total == 3

    def test_the_note_says_it_was_deliberate_rather_than_sloppy(self):
        """The whole `context` feature exists for under-selection. A spanning selection is the
        opposite — somebody dragged across a boundary on purpose — and a note implying
        carelessness would misinform the reader about their own colleague."""
        note = _context.build(THREE, "ends here.\nSecond paragraph starts").note
        assert "crosses 2 structural elements" in note
        assert "deliberate rather than sloppy" in note
        assert "the quote IS the passage" in note

    def test_a_genuinely_absent_quote_is_still_not_found(self):
        """The fix must not turn absence into a match. This is the direction that matters:
        `not_found` remains available and remains correct."""
        c = _context.build(THREE, "no such text anywhere in here")
        assert c.kind == _context.KIND_NOT_FOUND

    def test_a_spanning_quote_that_occurs_TWICE_is_ambiguous_not_guessed(self):
        d = doc(para("End.\n"), para("Start.\n"), para("End.\n"), para("Start.\n"))
        c = _context.build(d, "End.\nStart.")
        assert c.kind == _context.KIND_AMBIGUOUS
        assert "occurs 2 times" in c.note
        assert c.text == "", "no passage is better than a guessed one"

    def test_a_contained_quote_still_takes_the_ordinary_path(self):
        """The element-scoped search is still first, so nothing about the common case moved."""
        assert _context.build(THREE, "Second paragraph starts").kind == _context.KIND_PARAGRAPH

    def test_the_830_character_shape_from_the_report(self):
        """Length was the reporter's distinguishing detail, so it is reproduced rather than
        approximated: a long selection is exactly what crosses a boundary in real material."""
        first = "A " * 200          # 400 chars
        second = "B " * 400         # 800 chars
        d = doc(para(first + "\n"), para(second + "\n"))
        quote = first[-100:] + "\n" + second[:730]   # 100 + 1 + 730
        assert len(quote) == 831 and "\n" in quote
        assert doc_text(d).count(quote) == 1, "the fixture must be findable in rendered text"
        assert _context.build(d, quote).kind == _context.KIND_SPANNING


class TestTheyAgreeWithAsText:
    """The invariant the report asked for: presence is not a matter of opinion.

    Asserted as a property over every shape rather than case by case, because case-by-case is
    what let this through — nobody wrote the spanning case, so nothing tested it.
    """

    CASES = [
        ("within one paragraph", THREE, "Second paragraph starts"),
        ("spanning two", THREE, "ends here.\nSecond paragraph starts"),
        ("spanning three", THREE, "ends here.\nSecond paragraph starts here.\nThird"),
        ("a whole paragraph", THREE, "Third one.\n"),
        ("the entire document", THREE, doc_text(THREE)),
        ("genuinely absent", THREE, "nowhere at all in this text"),
        ("one word", THREE, "paragraph"),
    ]

    @pytest.mark.parametrize("label,document,quote", CASES)
    def test_presence_agrees(self, label, document, quote):
        in_text = doc_text(document).count(quote) > 0
        kind = _context.build(document, quote).kind
        context_found = kind != _context.KIND_NOT_FOUND
        assert in_text == context_found, (
            f"{label}: as_text() {'contains' if in_text else 'does not contain'} the quote but "
            f"context reported {kind!r} - the two must not disagree about PRESENCE")

    def test_the_case_set_covers_both_answers(self):
        """A property test where every case is present would pass while proving half of it."""
        answers = {doc_text(d).count(q) > 0 for _, d, q in self.CASES}
        assert answers == {True, False}, "the cases must include a genuinely absent quote"


def test_the_vocabulary_grew_deliberately():
    """`KINDS` is closed, so a new member is an act with a reason. 10 until 2026-09-03."""
    assert _context.KIND_SPANNING in _context.KINDS
    assert len(_context.KINDS) == 11
