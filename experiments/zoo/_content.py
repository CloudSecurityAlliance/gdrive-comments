"""The text of each specimen — the file's own content IS its documentation.

Every specimen explains itself: what it is, which measured finding it evidences, what to look
at, and what a human still has to place by hand. So the file works as documentation the moment
somebody opens the link, and it cannot drift away from the fixture it describes — because it
*is* the fixture.

Two rules hold for everything in here:

**Synthetic only.** This drive is public, permanently, and indexable. No real document content,
no real names, no real numbers from anything.

**The anchorable material does double duty.** A specimen about anchoring needs text to anchor
comments to, so the explanation and the fixture are the same paragraphs. That is deliberate: a
separate "test area" would invite somebody to comment on the explanation instead.
"""
from __future__ import annotations

HEADER = "SPECIMEN — {title}"

FOOTER = """RULES FOR THIS FILE
This file is cited BY ID from the csa-google-workspace repository, and from the comments
reference it supports. Renaming it is safe. Moving it is safe. A Drive file id survives both.
DELETING it breaks the citation, and COPYING it produces a new id that nothing cites — so a
copy is not a substitute for this file.
Everything in it is synthetic. There is no real content here and there never should be.
Maintained by CSA's CINO office. If something here is wrong, that is a finding: please say so."""


PROVENANCE = """HOW THIS FILE WAS MADE
Created {date} by `experiments/zoo/build.py` in the csa-google-workspace repository, running as
an ordinary user against the live Drive, Docs and Sheets APIs. Re-running that script finds this
file by name and leaves it alone; only `--rewrite` replaces this text, and doing so shifts every
character index and therefore breaks every hand-placed anchor on the file.

The body you are reading was written by one `documents.batchUpdate` — a single `insertText` at
index 1, then `updateParagraphStyle` on each heading. Nothing was typed by hand.

WHICH COMMENTS CAME FROM WHERE, AND WHY IT MATTERS
Comments labelled A, B and C were created through the **Drive API** (`comments.create`). Any
other comment on this file was placed **by a human in the Google Docs editor**.

That distinction is not bookkeeping — it is the finding. An API-created comment cannot carry a
real anchor: Drive stores whatever anchor you send and the editors then treat the comment as
un-anchored, so it renders in the sidebar as "Original content deleted", shows no quoted text,
draws no marker in the document body, and is filtered out of the default sidebar view. Only the
editor mints an anchor that works. So if a comment here looks broken, check its label first: an
A/B/C comment looking broken is the specimen working."""


def body(title: str, what: str, why: str, look: list[str], by_hand: list[str],
         material: list[str], date: str) -> str:
    """Assemble one specimen's text. Plain paragraphs; headings are styled afterwards.

    Order is deliberate: what it is, why it exists, what to look at, **how it was made**, what
    is still missing, then the material. Provenance sits before the material because a reader
    who has not yet learned that A/B/C are API-created will misread the sidebar.
    """
    parts = [HEADER.format(title=title), "", "WHAT THIS IS", what, "",
             "WHY IT EXISTS", why, "", "WHAT TO LOOK AT"]
    parts += [f"{i}. {line}" for i, line in enumerate(look, 1)]
    parts += ["", PROVENANCE.format(date=date), "", "STILL TO BE PLACED BY HAND"]
    parts += ([f"- {line}" for line in by_hand] if by_hand
              else ["Nothing. Every comment on this file was created through the API."])
    parts += ["", "MATERIAL TO ANCHOR AGAINST"]
    parts += material
    parts += ["", FOOTER]
    return "\n".join(parts) + "\n"


# The headings that get HEADING_1, matched by exact text after insertion.
HEADINGS = ("WHAT THIS FOLDER IS", "THESE ARE SPECIMENS, NOT EXAMPLES",
            "EVERY FILE DOCUMENTS ITSELF", "WHY SOME COMMENTS LOOK BROKEN", "HOW TO USE THIS",
            "RULES",
            "WHAT THIS IS", "WHY IT EXISTS", "WHAT TO LOOK AT", "HOW THIS FILE WAS MADE",
            "WHICH COMMENTS CAME FROM WHERE, AND WHY IT MATTERS",
            "STILL TO BE PLACED BY HAND", "MATERIAL TO ANCHOR AGAINST", "RULES FOR THIS FILE")

SPECIMENS: dict[str, dict] = {
    "docs-anchor-states": dict(
        title="the four anchor states of a Drive comment",
        what=("A Drive comment can be attached in four different ways, and three of them are "
              "easy to confuse. This file is meant to carry one comment in each state so a "
              "consumer can see what its own code receives."),
        why=("Measured 2026-09-02 and 2026-09-03. The published guidance describes three "
             "states; there are four. `anchor` presence and `quotedFileContent` presence are "
             "INDEPENDENT, so the combinations are file-level (neither), object-anchored "
             "(anchor only), text-anchored (both), and quote-only (quote, NO anchor). The "
             "fourth is producible only through the API, which is why an editor-only "
             "investigation cannot find it — and why one missed it for a year."),
        look=["A file-level comment: no anchor, no quoted text. Created through the API.",
              "A quote-only comment: quoted text and NO anchor. API-created, and it renders "
              "in the editor as 'Original content deleted' with the quote NOT shown.",
              "A second quote-only comment whose quoted text is NOT IN THIS DOCUMENT AT ALL. "
              "Drive validates that field against nothing, so a comment can attribute words "
              "to a document that never contained them.",
              "An object-anchored comment, once an image is added and commented on by hand.",
              "A text-anchored comment, once somebody selects a sentence and comments."],
        by_hand=["An image comment, for the classic form of the object state. NOT the only "
                 "way to produce it - measured 2026-09-03, anchoring to any non-textual part "
                 "of the page gives an anchor with no quoted text - but the clearest one.",
                 "Select the whole of paragraph P2 below and comment on it, for the ordinary "
                 "text-anchored state.",
                 "Click inside P1 without selecting anything and comment. The editor expands "
                 "the anchor to the enclosing WORD, which is worth seeing."],
        material=[
            "P1. This paragraph exists to be commented on with nothing selected, so that the "
            "editor's habit of snapping a bare caret to its enclosing word can be observed "
            "rather than described.",
            "P2. A whole paragraph to select. It is deliberately long enough that selecting "
            "three words out of it produces an anchor much smaller than the point a comment "
            "would be making, which is the under-selection case that motivates context.",
            "P3. A short paragraph."]),

    "docs-sloppy-selections": dict(
        title="selections that are hard to place",
        what=("Comments whose quoted text cannot be located, or can be located in more than "
              "one place. These are the cases where locating a comment by its quoted text — "
              "the only method available, since a Docs anchor carries no position — either "
              "fails or has to refuse."),
        why=("A one-word quote is ambiguous almost immediately: in a nine-paragraph document, "
             "the word a caret snapped to occurred four times. And a selection that crosses a "
             "paragraph boundary was reported as ABSENT from its own document until 2026-09-03, "
             "because an element-scoped search cannot match a quote containing the newline "
             "between two paragraphs. Anchor length predicts this: no anchor over 40 "
             "characters was ambiguous on one real 90-thread document."),
        look=["A comment quoting a single word that appears four times below. Locating it can "
              "only report candidates; choosing one would be a guess.",
              "A comment quoting text that spans a paragraph boundary — it contains a newline, "
              "so it is inside no single paragraph.",
              "A comment quoting three words of a long paragraph, where the passage the "
              "commenter means is the whole paragraph."],
        by_hand=["Select just the word 'threshold' in P1 and comment on it. Four paragraphs "
                 "below contain it, so this is the ambiguous case.",
                 "Select from the end of P3 into the start of P4, crossing the boundary, and "
                 "comment. That is the spanning case.",
                 "Select the three words 'the taxonomy here' in P2 and comment something that "
                 "is clearly about the whole paragraph."],
        material=[
            "P1. The threshold in this section is stated once and relied on repeatedly.",
            "P2. The taxonomy here conflates two different failure modes, and a reader cannot "
            "tell which one they are looking at from the text alone, which is the sort of "
            "point a three-word selection makes badly.",
            "P3. A paragraph that ends mid-thought so that a selection can run past its end",
            "P4. and continue into this one, producing a quote containing a newline.",
            "P5. The threshold appears here as well.",
            "P6. And the threshold appears here.",
            "P7. A fourth mention of the threshold, so the count is unambiguous."]),

    "docs-structure": dict(
        title="headings, tables and empty paragraphs",
        what=("Structural elements that change what 'the passage a comment is about' should "
              "mean. A comment on a heading, a comment inside a table cell, and the fact that "
              "an empty paragraph cannot be commented on at all."),
        why=("The unit of context is the enclosing structural element, and that rule has three "
             "exceptions worth seeing rather than reading about: a heading expands FORWARD "
             "because it heads what follows; a table cell takes the WHOLE table, because a "
             "table is one element and neighbouring prose is unrelated; and the editor "
             "REFUSES to comment on an empty paragraph, which is why there is no 'anchored "
             "but nothing selected' state for text."),
        look=["The heading below, once commented on by hand — context should extend forward "
              "into the prose it heads, not backward.",
              "A cell in the table, once commented on — context should be the whole table.",
              "The empty paragraph. Try to comment on it; the editor will not let you."],
        by_hand=["Comment on the heading 'Section Two' below.",
                 "Comment on a cell inside the table.",
                 "Try to comment on the empty paragraph between P1 and P2, and confirm no "
                 "comment box appears. That refusal is the finding."],
        material=["Section Two",
                  "P1. Prose that the heading above heads, which is what makes forward "
                  "expansion structural rather than inferred.",
                  "",
                  "P2. Prose after the empty paragraph."]),

    "docs-lifecycle": dict(
        title="what a comment looks like through its life",
        what=("The same thread, resolved and reopened, plus a soft-deleted comment and a "
              "reply that carries no text. Each of these arrives in a shape that surprises "
              "code written from the documentation."),
        why=("Measured 2026-07-20, and ALL OF IT IS STAGED THROUGH THE API - resolve and reopen "
             "are action-REPLIES rather than a field update, which is exactly why they are "
             "reachable without a browser and exactly why naive code misses them. "
             "`resolved` is ABSENT on a comment that was never resolved, "
             "not false — so a missing field must read as unresolved. Soft delete strips BOTH "
             "the content and the author, leaving a tombstone. Resolve and reopen are "
             "action-REPLIES rather than a field update, and may carry no text at all, so a "
             "blank reply is a state change and not a mistake."),
        look=["A thread with several replies, for the ordinary case.",
              "A resolved thread — note that resolving added a reply.",
              "A soft-deleted comment: the id and timestamps survive, the content and author "
              "do not.",
              "A comment that was never resolved, whose `resolved` field is absent rather "
              "than false."],
        by_hand=["Nothing for the lifecycle itself - see below. What is still missing is an "
                 "ANCHORED thread: every comment here is file-level or quote-only, because "
                 "only the editor mints an anchor. Select P1 and comment, then reply to it, "
                 "to get a lifecycle on a properly anchored thread."],
        material=["P1. A paragraph to hang a thread on.",
                  "P2. A second paragraph, for a thread that stays open."]),
}


README = """google-workspace-api-specimens

WHAT THIS FOLDER IS
Files that exhibit specific, measured behaviours of the Google Workspace APIs. They exist so a
claim about how comments work can be CHECKED rather than taken on trust: open the file, look at
the sidebar, see the thing.

Maintained by CSA's CINO office, alongside the open-source csa-google-workspace library.

THESE ARE SPECIMENS, NOT EXAMPLES
Do not copy anything here as a template. Several of these files are deliberately malformed: a
comment quoting text the document does not contain, a header row that is not row 1, a selection
that crosses a paragraph boundary. They are useful precisely because they are wrong in specific,
documented ways.

EVERY FILE DOCUMENTS ITSELF
Open one. It says what it is, which measured finding it evidences, what to look at, how it was
made, and what a human still has to place by hand. There is no separate key to hold, and the
documentation cannot drift from the fixture because it IS the fixture.

WHY SOME COMMENTS LOOK BROKEN
Comments labelled A, B or C were created through the Drive API. An API-created comment cannot
carry a real anchor — Drive stores whatever you send and the editors then treat it as
un-anchored — so it renders as "Original content deleted", shows no quoted text, draws no
marker in the body, and is hidden from the default sidebar view. Only the editor mints an
anchor that works.

So an A/B/C comment looking broken is the specimen working. That behaviour is the finding.

HOW TO USE THIS
Read: open the files. Experiment: take a copy into your own Drive and change it freely — but
note that copying a Google file DROPS EVERY COMMENT, which is itself one of the findings here,
so a copy is not an equivalent fixture.

RULES
Everything here is synthetic. There is no real content and there never should be.
These files are cited BY ID from csa-google-workspace. Renaming and moving are safe — a Drive
file id survives both. Deleting breaks the citation. Please do not tidy this folder."""


# Specimens that are NOT Google Docs. Kept separate because `build.py` creates each type
# through a different API, and because their material is a grid or a deck rather than prose.
SHEET_SPECIMENS: dict[str, dict] = {
    "sheets-notes-are-not-comments": dict(
        title="a note is not a comment, and the comments API cannot see one",
        what=("A spreadsheet carrying cell NOTES and no comments. Ask the Drive comments API "
              "for its comments and it returns zero - truthfully, and misleadingly."),
        why=("Measured 2026-09-02: a file carrying a note returns ZERO comments from the Drive "
             "comments API, because a note and a comment are different objects and the comments "
             "API does not see notes at all. A note has no author, no thread, and cannot be "
             "replied to or resolved, so nothing in a reply-and-resolve workflow applies to "
             "one. A tool reporting 'no comments' on a sheet covered in notes is telling the "
             "truth and giving exactly the wrong impression."),
        look=["Cells B2, B3 and B4 carry notes. Hover them in the UI.",
              "`list_comments` on this file returns nothing. That is correct.",
              "`list_notes` returns the three. That is the tool for this."],
        by_hand=[],
        material=["(the grid is the material - see the tabs)"]),

    "sheets-header-not-row-1": dict(
        title="a header row that is not row 1, so the header guess is wrong",
        what=("A grid whose real header row is row 4, under a title block. Any tool that "
              "assumes 'column A and row 1 are the headers' will label a cell wrongly here."),
        why=("`comments_by_cell` reports `row_header` and `column_header` to turn 'a comment on "
             "B11' into 'the row labelled Southwest, column Q3 actual' - which is what makes a "
             "cell comment interpretable, and how a comment on the WRONG cell becomes "
             "detectable. But the header row and column are a GUESS (column A, row 1), and a "
             "caveat says so. This file is what the guess gets wrong: a title block sits above "
             "the table, so row 1 is a title and row 4 is the header."),
        look=["Row 1 is a title, rows 2-3 are blank, row 4 is the real header.",
              "A comment on a data cell should report a row_header of 'Southwest' and a "
              "column_header taken from row 4 - and a naive reading takes it from row 1.",
              "The caveat in the export is the point: the guess is declared, not hidden."],
        by_hand=["Comment on cell C6 in the editor. Only the editor anchors a comment to a "
                 "cell, so this one genuinely cannot be staged - and a Sheets anchor is an "
                 "opaque `workbook-range`, which is why mapping it to A1 needs the XLSX "
                 "export detour."],
        material=["(the grid is the material)"]),
}

SLIDE_SPECIMENS: dict[str, dict] = {
    "slides-comments": dict(
        title="comments on a deck - never before probed",
        what=("A three-slide deck with a shape, text inside the shape, and speaker notes, so a "
              "comment can be placed on each and the anchor compared."),
        why=("**Nothing in this project has ever looked at what a Slides comment contains.** "
             "We support them through the uniform Drive axis and everything said about them is "
             "generalised from the Docs and Sheets measurements - which is precisely the "
             "reasoning that produced a three-anchor-state table that turned out to have four "
             "members. Docs anchors are `kix.*`, Sheets are `workbook-range`; Slides is a third "
             "addressing model and no one here has seen one."),
        look=["A comment on the slide itself.",
              "A comment on a shape.",
              "A comment on text INSIDE a shape - does it carry quoted text?",
              "A comment on the speaker notes, which are a separate element tree."],
        by_hand=["All four. Only the editor anchors a comment, and this is the whole point of "
                 "the specimen: place one on the slide, one on the shape, one on text inside "
                 "the shape, and one on the speaker notes, then we read the raw anchors and "
                 "find out what a Slides anchor actually looks like."],
        material=["(the deck is the material - see the slides)"]),
}
