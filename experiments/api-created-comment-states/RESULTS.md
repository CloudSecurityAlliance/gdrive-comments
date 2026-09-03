# The fourth anchor state is real, and only the API can make it

**Measured 2026-09-03** against live Google Drive, on a throwaway Doc (created, probed, trashed).
Settles [#372](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/372).

Run: `probe.py --create`, then `--comments`, then `--dump`, then `--trash`.

## The question

A consumer measured 90 real threads and found **4 with `anchored=false` and substantial
`quoted_text`** — 119, 111, 244 and 35 characters. The documented contract says `anchored=false`
means the comment is about the whole file, so those four are mishandled silently. They could not
tell from outside whether Drive returns a quote with no anchor, or whether the library loses the
anchor somewhere.

## Answer: Drive returns it. The library loses nothing.

Six comments created through `comments.create`, read back with the **same field mask the library
uses** (`backend.py:577`, which does include `anchor`):

| # | sent | `anchor` back | `quotedFileContent` back | `Comment.anchored` |
|---|---|---|---|---|
| A | `content` only | absent | absent | `False` |
| **B** | **`content` + quote (244 chars)** | **absent** | **present, verbatim** | **`False`** ← the state |
| **C** | **`content` + quote (85 chars)** | **absent** | **present, verbatim** | **`False`** ← the state |
| D | `content` + anchor + quote | present, verbatim | present, verbatim | `True` |
| E | `content` + anchor only | present, verbatim | absent | `True` |
| **F** | **`content` + quote with `\n`, `\t`, padding** | **absent** | **present, verbatim** | **`False`** ← the state |

So the state is not merely possible, it is **the ordinary result of creating a comment with a
quote and no anchor** — and Drive accepts that combination without complaint.

`Comment.anchored` is `self.anchor is not None` (`comments.py:153`), so it reported `False` on a
comment carrying 244 characters of quoted text. The derivation is faithful to Drive; **the
contract built on it was wrong**.

## Why the earlier measurement could not have found this

`experiments/docs-anchor-states/` (2026-09-02) produced the three-state table now quoted in four
places. Every comment in that run was created **by the editor**, plus one file-level comment
created through the API. The editor cannot produce a quote without an anchor — it snaps a bare
caret to the enclosing word and refuses to comment on empty space, both measured. So this shape
was **unreachable by construction**, and the table is complete for editor-created comments while
being stated as complete for all comments.

That is the same failure as #361 one level up: a claim derived from a proxy, where the proxy's
coverage silently became the claim's scope.

## Why a sensible tool creates such a comment on purpose

Measured 2026-07-09 (`experiments/anchor-probe/`): an API-supplied anchor is stored verbatim and
returned intact, and the editors then treat the comment as **un-anchored**. Confirmed again here
— D and E round-tripped `kix.probe372anchornotreal` unchanged, an anchor that corresponds to
nothing.

So a client that knows this **omits the anchor as useless** while still recording what it quoted.
That is the better-informed choice, not a bug. Which means this shape should be **expected on any
file another tool has written to**, and treating it as corruption would be wrong.

## Corroboration: the ids say "one API batch"

The reporter noted their four ids "share a prefix and differ only in the final character". These
six, from one run, do exactly the same:

```
A  AAACGezoGWc      common prefix: 'AAACGezoGW' (10 of 11 chars)
B  AAACGezoGWg      final chars:   c  g  k  o  s  w
C  AAACGezoGWk
D  AAACGezoGWo
E  AAACGezoGWs
F  AAACGezoGWw
```

Sequential within a batch, stepping by 4 in the final base64 character. This does not *prove* the
provenance of somebody else's four rows — provenance is not observable from outside — but an
independent reproduction produced the same id signature from the same cause, which is as close as
this can get.

## Two findings that were not the question

**`quotedFileContent.mimeType` carries no information at all.** Sent `text/plain` (case C), Drive
returned **`text/html`**. It normalises the field regardless of what the client sends, so every
comment reports `text/html` whatever it was created with — while the value stays plain text, as
measured on 2026-07-20. The existing note said the mimeType "is `text/html` but the value is
plain text"; the reason is now known, and it is stronger than described: **do not branch on this
field**, because it is a constant.

**The quote value is byte-verbatim.** Case F round-tripped leading spaces, an embedded newline
and a tab unchanged. So a stored quote can be matched against extracted text without
normalisation — which is what `_context.py` already relies on, now confirmed for the API-created
path as well as the editor one.

## The blast radius is smaller than it looks

Three of the reporter's four rows still resolved to `context_kind: paragraph`, because
`_context.py` **locates by quoted text, not by the anchor** — a decision forced by the anchor
carrying no position. That choice made the context feature immune to this bug, and it confines
the damage to the `anchored` flag and the prose describing it.

## How the editor renders these — MEASURED 2026-09-03, and it is worse than expected

Opened the probe document in Docs. **All six comments render identically: a card reading
"Original content deleted".** Including **A**, the plain file-level control with no anchor and no
quote at all.

Three separate facts, and each one matters on its own:

**1. The editor does not display `quotedFileContent` on a comment it cannot anchor.** Comment B
carries 244 characters of quoted text that the API returns verbatim. The sidebar shows body,
author, timestamp — and where a quote would go, "Original content deleted".

*(This was first written as "the editor NEVER displays `quotedFileContent`", which the
anchor-reuse measurement below disproved within the hour: given a valid anchor, the quote is
displayed. The distinction is the whole finding — the quote is not ignored, it is **conditional on
the anchor resolving**. Recorded rather than silently corrected, because the wrong version is the
intuitive one and the next person will reach for it too.)*

**2. An API-created comment leaves no marker in the document body.** Nothing is highlighted, and
there is no margin indicator to click. The comments were **not visible at all** until the
Comments panel was opened explicitly — which follows from having no anchor: no anchor, no place
to draw a marker.

**2b. The editor FILTERS them out of the default view, actively.** *(Scope note: established for
the UNANCHORED comments A-F. The REUSE comments are also absent from the default floating view,
but they share one anchor with the hand-placed donor, so Docs showing a single card per anchor
position explains that without any filtering. Not claimed.)* Observed while placing a
comment by hand: the moment typing started, every orphaned comment disappeared from the sidebar,
and only "show all comments" brought them back. So they are not merely markerless — the default
sidebar view excludes them, and a reviewer working normally in the document will not encounter
them at all. This is stronger than "hard to find": it is *filtered*.

**3. The API cannot tell you any of this.** `comments.list` with `fields=*` returns exactly
eleven keys — `author`, `content`, `createdTime`, `deleted`, `htmlContent`, `id`, `kind`,
`modifiedTime`, `quotedFileContent`, `replies`, `resolved`. **There is no orphan flag, no anchor
validity, nothing.** So a tool reading a comment through Drive sees a rich quoted passage while a
human reading the same comment in the editor sees a deleted-content stub, and nothing in the
payload reveals the disagreement.

### The consequence for this library, stated plainly

`create_comment` sends content only — **state A**. So **every top-level comment this library and
its MCP server create appears to a human in the Docs editor as an orphaned "Original content
deleted" card, with nothing highlighted in the text.** That is a real, user-visible limitation
and it was not documented anywhere.

It does **not** affect replies. `reply_comment` and `resolve_comment` attach to an existing
thread, so a reply to an editor-created comment inherits that thread's anchoring and renders
normally. The limitation is specific to *starting* a new thread.

### What this does NOT settle

Whether "Original content deleted" is a property of **API-created** comments specifically, or of
**any** comment the editor cannot anchor. Distinguishing them needs an **editor-created** comment
in this same document as a control, which needs hands on a browser. Two confounders are already
ruled out: the document has exactly **one** tab (`t.0`), so this is not a comment that failed to
associate with the right tab, and it is not a field-mask artefact.

### The donor comment, for the record

One comment placed by hand in the same document, read back through the API:

```
anchor : kix.iraipalahkb6
quoted : "Drive API"
```

Both fields present, consistent with the 2026-07-20 measurement that Docs comments are
self-describing. This is the control the section above wanted, and it is also the anchor the
reuse probe borrows.

### The follow-up worth doing, because it could change what this library can do

**Can a Drive-API comment reuse a REAL `kix.*` anchor and render as properly anchored?**

Google states that developer-defined anchors are treated as un-anchored, and we measured that in
July with a *synthetic* anchor. A real `kix.*` id taken from an editor-created comment in the same
document is a different proposition: it names an anchor object the document actually has.

If it renders anchored, this library could create comments **attached to real passages**, which
we currently document as impossible — and it would fix the limitation above rather than merely
recording it. If it renders as "Original content deleted" like everything else, then the July
finding generalises and the limitation is inherent to the Drive comments API.

`probe.py --reuse-anchor` implements it. It needs one comment placed **by hand** first, so there
is a real anchor to borrow.

## ANSWERED — a real anchor works, and a synthetic one does not (MEASURED 2026-09-03)

**This is the most consequential result in this directory.** One comment placed by hand
(`anchor: kix.iraipalahkb6`, quoting `"Drive API"`), then two API-created copies reusing that
exact anchor:

| comment | sent | sidebar header | anchored? |
|---|---|---|---|
| the hand-placed donor | *(editor)* | `Tab 1 · Drive API` | yes |
| **REUSE-1** | real anchor, **no** quote | **`Tab 1`** | **yes** |
| **REUSE-2** | real anchor **+** quote | **`Tab 1 · Drive API`** | **yes** |
| A–F | no anchor, or a synthetic one | `Original content deleted` | no |

**So the Drive API CAN create an anchored Docs comment.** Google's statement that
developer-defined anchors are treated as un-anchored, and our own 2026-07-09 measurement, are
both about **synthetic** anchors. A real `kix.*` id — one naming an anchor object the document
actually has — is honoured, and the resulting comment is indistinguishable in the sidebar from
one placed by hand.

`CLAUDE.md` fact 3's "you cannot create an anchored comment via the API" needs qualifying: you
cannot **mint** an anchor, but you can **reuse** one.

**And the quote is displayed when the anchor resolves.** REUSE-1 (anchor, no quote) reads
`Tab 1`; REUSE-2 (anchor + quote) reads `Tab 1 · Drive API`. That is what corrects finding 1
above.

### The limit of this, stated before anyone gets excited

A real `kix.*` anchor can only be **obtained from a comment that already exists**. There is no
way to mint one for an arbitrary passage through the GA API — no Docs v1 method returns or creates
an anchor object. So this permits *"add another thread to a passage somebody has already commented
on"*, which is narrow but not nothing: it is exactly the shape of an AI adding a second opinion to
an existing review thread as a new thread rather than a reply.

General anchored creation still needs the Docs Developer Preview's `insertComment{content, range}`
— see `research/comments-apis-2026-09.md` §2.1.

## `quotedFileContent` IS RENDERED VERBATIM AND NEVER VALIDATED (MEASURED 2026-09-03)

The sharpest finding here, and it is a security one.

| comment | anchor | quote sent | sidebar header |
|---|---|---|---|
| REUSE-2 | real (`"Drive API"`) | `"Drive API"` | `Tab 1 · Drive API` |
| **REUSE-3** | real (`"Drive API"`) | **`"THIS TEXT IS NOT IN THE DOCUMENT AT ALL"`** | **`Tab 1 · THIS TEXT IS NOT IN THE DO…`** |
| **REUSE-4** | real (`"Drive API"`) | **`"A shorter paragraph, about a hundred"`** | **`Tab 1 · A shorter paragraph, about a …`** |

**Docs displays whatever the creator put in `quotedFileContent`, as the document's own words.** It
is not checked against the anchor, and it is not checked against the document. REUSE-3's
"quotation" occurs nowhere in the file.

### What this means for `quoted_text`

This library's tool description has called `quoted_text` *"THE PASSAGE THE COMMENT IS ABOUT —
Drive's own record of what the reviewer selected"*. **Measured, that is false.** It is the
*creator's* record, unvalidated, and it need not occur in the document. For an editor-created
comment it is trustworthy because the editor fills it in; for an API-created one it is
**attacker-controlled free text that both Docs and this library present as document content**.

Two concrete consequences, and the second is worse:

1. **A fabricated quotation reads as genuine.** With a real anchor borrowed from any existing
   comment, the card is indistinguishable from a hand-placed one — same `Tab 1 · …` header — while
   attributing words to the document that were never in it. Anyone with **commenter** access can
   do this; it needs no write access to the content.

2. **The apparent subject of a comment can be redirected.** REUSE-4 is the demonstration: the
   anchor points at *"Drive API"* while the quote names a different real passage. `_context.py`
   locates by quoted text, so **this library would resolve, mark and report the passage the
   attacker named**, not the one the comment is attached to. A comment can therefore be made to
   appear to be about any passage its author chooses.

Neither is detectable from the comment resource: `fields=*` carries no validity signal (see
above), so nothing in the payload distinguishes an honest quote from an invented one.

### What is cheap and worth doing

`_context.py` **already searches the document for the quote**. When it does not occur, that is
currently reported as `not_found` and read as *"the passage was edited or deleted"*. It is the same
observable for *"this quote was never in the document"* — the two cannot be told apart, but the
fact itself ("the quoted text does not occur in this document") is worth surfacing plainly rather
than leaving as a placement failure.

Proposed as a threat-model addition rather than edited in — see the issue filed from this run.
