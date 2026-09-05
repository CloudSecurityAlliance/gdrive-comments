"""The shape of a result is readable at runtime, and the two renderings agree (#421, #422).

Both issues came from the same consumer, building an anti-hallucination check on `context` —
*"the model says it read this passage; is the quote really in the document?"* — over a real
90-thread review. Neither is a bug. Both are the interface failing to say something true.

**#421 — 60 of 76 honest quotes read as fabrications.** They compared `context` against
`download_file_content(markdown)`, which is Drive's converter: it escapes punctuation and adds
emphasis. And `context` carries selection markers that were documented nowhere.

**The answer is better than they hoped, and is asserted below: there are TWO renderings, not
three.** `read_file_content` and `context` are the *same* one — strip the two markers and
`context` is a literal substring. Only the markdown export differs.

**#422 — a pinned contract went stale in four days.** `context_kind` gained `spanning`, the
column set grew by two, and neither was discoverable except by diffing payloads. Their consumer
*raises* on an unknown `context_kind` rather than guessing where a comment points — which is the
right call, and means a new member takes the whole run down.

So the vocabularies are declared **open**, and `describe_output_contract` makes the current
members readable from the server the consumer is actually talking to.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import _context, _export
from csa_google_workspace.__init__ import __version__
from csa_google_workspace._content import doc_text
from csa_google_workspace.comments import ANCHOR_STATES
from csa_google_workspace.mcp._schemas import (
    CONTEXT_KIND_ADDED_IN,
    EXPORT_COLUMN_ADDED_IN,
    context_out,
    contract_out,
)


def para(text: str, style: str = "NORMAL_TEXT") -> dict:
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style},
                          "elements": [{"textRun": {"content": text}}]}}


class TestThereAreTwoRenderingsNotThree:
    """#421's central question, answered as a property rather than as prose.

    The consumer assumed three independent renderings and set out to normalise between them.
    They do not need to: two of the three are the same, and the one that differs is Drive's.
    """

    DOC = {"body": {"content": [
        para("1. Introduction", "HEADING_1"),
        # The punctuation matters: `=` and `+` are exactly what Drive's markdown converter
        # escapes, and what made their comparison fail.
        para("The formulation: Thing = Alpha + Beta + Gamma.\n"),
        para("A second paragraph, for surrounding context.\n")]}}
    QUOTE = "Thing = Alpha"

    def test_context_stripped_is_a_SUBSTRING_of_read_file_content(self):
        """The property that resolves the issue. If this ever fails, the two surfaces have
        diverged and every consumer matching one against the other breaks silently."""
        ctx = _context.build(self.DOC, self.QUOTE)
        stripped = ctx.text.replace(_context.OPEN, "").replace(_context.CLOSE, "")
        assert stripped in doc_text(self.DOC), (
            "context is no longer the same rendering as read_file_content - a consumer "
            "checking 'is this quote really in the document' will now get false negatives")

    def test_neither_escapes_punctuation_nor_adds_emphasis(self):
        """Drive's markdown converter does both; these two must not, or they would silently
        become a third rendering."""
        both = doc_text(self.DOC) + _context.build(self.DOC, self.QUOTE).text
        assert "\\=" not in both and "\\+" not in both, "punctuation is being escaped"
        assert "**" not in both, "emphasis markers have appeared"

    def test_the_markers_are_the_ONLY_difference(self):
        """Stated as its own assertion because it is the fact a consumer needs: not merely
        that the two overlap, but that stripping two characters is sufficient."""
        ctx = _context.build(self.DOC, self.QUOTE)
        assert _context.OPEN in ctx.text and _context.CLOSE in ctx.text
        stripped = ctx.text.replace(_context.OPEN, "").replace(_context.CLOSE, "")
        assert stripped.strip() in doc_text(self.DOC)


class TestTheMarkersCanBeOmitted:
    """#421 item 3. They help a human read a register and hurt anything matching on text."""

    def ctx(self):
        d = {"body": {"content": [para("Alpha beta gamma delta.\n")]}}
        return _context.build(d, "beta gamma")

    def test_markers_are_present_by_default(self):
        out = context_out(self.ctx())
        assert _context.OPEN in out["text"] and _context.CLOSE in out["text"]

    def test_markers_false_removes_both(self):
        out = context_out(self.ctx(), markers=False)
        assert _context.OPEN not in out["text"] and _context.CLOSE not in out["text"]

    def test_and_removing_them_changes_nothing_else(self):
        """A stripped passage must be the marked one minus two characters — not re-derived,
        not re-wrapped, not trimmed. Otherwise the option quietly returns different text."""
        with_m = context_out(self.ctx())["text"]
        without = context_out(self.ctx(), markers=False)["text"]
        assert with_m.replace(_context.OPEN, "").replace(_context.CLOSE, "") == without
        assert len(with_m) == len(without) + 2


class TestTheContractIsReadableAtRuntime:
    """#422 item 3 — so a downstream contract file can be regenerated rather than hand-diffed."""

    def test_it_reports_the_live_vocabularies(self):
        c = contract_out(__version__)
        assert set(c["context_kinds"]) == set(_context.KINDS)
        assert set(c["anchor_states"]) == set(ANCHOR_STATES)

    def test_it_reports_the_live_column_set(self):
        c = contract_out(__version__)
        assert c["export_columns_reported"] == list(_export.REPORTED)

    def test_it_says_the_vocabulary_is_OPEN(self):
        """The single most important field. A consumer that knows this can degrade; one that
        reads the description as a closed set raises, and takes a whole run down."""
        c = contract_out(__version__)
        assert c["context_kinds_extensible"] is True
        assert "OPEN" in c["detail"] and "spanning" in c["detail"]

    def test_it_names_the_selection_markers(self):
        """Documented nowhere before #421, and worth 60 of 76 false negatives."""
        m = contract_out(__version__)["selection_markers"]
        assert m["open"] == _context.OPEN and m["close"] == _context.CLOSE

    def test_it_says_which_rendering_each_surface_returns(self):
        r = contract_out(__version__)["renderings"]
        joined = " ".join(r.values())
        assert "SAME rendering as read_file_content" in joined
        assert "DIFFERENT" in joined, "the markdown export must be flagged as not comparable"


class TestTheVersionMapDoesNotGoStale:
    """The one hand-maintained part, guarded — because a member with no recorded version is a
    consumer's question ('did this appear after the release I tested?') with no answer."""

    @pytest.mark.parametrize("kind", sorted(_context.KINDS))
    def test_every_context_kind_records_when_it_arrived(self, kind):
        assert kind in CONTEXT_KIND_ADDED_IN, (
            f"{kind!r} is in KINDS with no entry in CONTEXT_KIND_ADDED_IN. A consumer pinning "
            f"a contract needs to know which release added it.")

    def test_the_map_invents_no_members(self):
        """The mirror: an entry for a kind that no longer exists would promise a value the
        server never returns."""
        assert set(CONTEXT_KIND_ADDED_IN) <= set(_context.KINDS)

    @pytest.mark.parametrize("column", sorted(EXPORT_COLUMN_ADDED_IN))
    def test_every_recorded_column_still_exists(self, column):
        assert column in _export.REPORTED

    def test_spanning_is_recorded_against_the_release_that_added_it(self):
        """The specific member that broke a consumer. Pinned by name so a careless edit to the
        map is visible."""
        assert CONTEXT_KIND_ADDED_IN["spanning"] == "0.48.0"
