# What a Slides comment anchor actually contains

**Measured 2026-09-05** against live Google, on the public zoo specimen
[`slides-comments`](https://docs.google.com/presentation/d/193nXMbPMKy_Ubon_3AMBA4wWxNdxvA8S_xWCc9_s5xk/edit).
Answers **#400**. Six comments placed through the Slides editor (driven by Playwright, which is
the editor either way — only the editor mints a real anchor), then read back raw through
`drive.comments.list`.

Docs was measured in [`../docs-anchor-states/`](../docs-anchor-states/RESULTS.md) and Sheets in
[`../anchor-probe/`](../anchor-probe/RESULTS.md). Slides was the third addressing model and had
never been looked at, while `anchor_state` was already being reported for decks.

## The raw output

```
─────────── SLIDE-6 — a word in a TABLE CELL
  anchor  : {"type":"shape","subtype":"text","uid":1788614572804,"page":"p","targets":["zooTable"]}
  quoted  : {"mimeType": "text/html", "value": "cell"}
─────────── SLIDE-5 — a shape with NO TEXT
  anchor  : {"type":"shape","uid":1788614463461,"page":"p","targets":["zooNoText"]}
  quoted  : null
─────────── SLIDE-4 — a word in the SPEAKER NOTES
  anchor  : {"type":"shape","subtype":"text","uid":1788614396659,"page":"p","targets":["i3"]}
  quoted  : {"mimeType": "text/html", "value": "notes"}
─────────── SLIDE-3 — a word inside a shape
  anchor  : {"type":"shape","subtype":"text","uid":1788614262983,"page":"p","targets":["zooShape1"]}
  quoted  : {"mimeType": "text/html", "value": "shape"}
─────────── SLIDE-2 — the shape selected as an OBJECT
  anchor  : {"type":"shape","subtype":"text","uid":1788614219925,"page":"p","targets":["zooShape1"]}
  quoted  : {"mimeType": "text/html", "value": "this"}
─────────── SLIDE-1 — nothing selected
  anchor  : {"type":"page","uid":1788614049284,"pages":["p"]}
  quoted  : null
─────────── SPECIMEN — file-level, created through the Drive API
  'anchor' key present : False
  quoted  : null
```

The presentation's own object ids, for comparison:

```
  slide objectId: p
    element: i0, i1, zooShape1 (shapes), zooTable (table), zooNoText (shape)
    notesPage objectId: p:notes
      notes element: i2, i3
```

## 1. A Slides anchor is READABLE, and it is the only one that is

This is the headline, and it makes Slides the exception rather than the third example of a rule:

| editor | anchor | resolvable? |
|---|---|---|
| **Docs** | `kix.ce7ypxwipivp` | **no** — opaque id, no position |
| **Sheets** | `{"type":"workbook-range","uid":0,"range":"1453957822"}` | **no** — `range` is an opaque internal id |
| **Slides** | `{"type":"shape","subtype":"text","page":"p","targets":["zooShape1"]}` | **yes** — `targets` names real API object ids |

`p`, `zooShape1`, `zooTable`, `zooNoText`, `i3` all appear verbatim in `presentations.get`. So a
Slides comment can be resolved to the element it is attached to with a JSON parse and one API
call — no XLSX export, no relationship walk, no quoted-text search.

Everything this project has said about anchors being *hints* was generalised from two editors
where it is true. On Slides it is not.

## 2. `page` names the SLIDE, not the page the target lives on

**The sharpest finding, and the one a consumer will get wrong.** SLIDE-4 is a comment on the
speaker notes:

```
{"type":"shape","subtype":"text","page":"p","targets":["i3"]}
```

`i3` is an element of `p:notes`. But `page` still says `"p"` — the slide. The notes page id
appears nowhere in the anchor.

So the field that looks like it answers *"where is this?"* reports a speaker-notes comment as a
comment on the slide body. The **only** way to tell them apart is to resolve `targets` against
`presentations.get` and see which element tree the id belongs to. A reviewer cannot otherwise
distinguish *"this is about the deck"* from *"this is about what I say over the deck"* — which
are different comments requiring different fixes.

Same failure shape as invariant 9 and the `read_only` docstring: the value is present, plausible,
and wrong in a direction nothing checks.

## 3. `subtype: "text"` is present exactly when quoted text is

Across all six, with no exceptions:

| anchor | `quotedFileContent` | this library's `anchor_state` |
|---|---|---|
| `type: "page"` | absent | `object` |
| `type: "shape"`, no subtype | absent | `object` |
| `type: "shape"`, `subtype: "text"` | **present** | `text` |
| absent (API-created) | absent | `file` |

So the four-state model **holds on Slides** — `file`, `object` and `text` are all reachable, and
`quote_only` remains API-only as it is everywhere else. `anchor_state` has been reporting truth
for decks; it was just never checked.

But see §5: it is *lossy* here in a way it is not on Docs.

## 4. Selecting a shape does NOT give you an object anchor — if the shape has text

SLIDE-2 was placed with the shape selected as an object: single click, blue resize handles, no
text cursor. The anchor came back `subtype: "text"` quoting `"this"` — the word that happened to
be under the click point.

This is the same family as the measured Docs behaviour where the editor expands a bare caret to
its enclosing word. The editor prefers a text anchor whenever text is available, regardless of
what the selection looks like.

Consequence: **the `object` state is reachable only through an element with nothing to quote.**
SLIDE-5 needed a purpose-built empty ellipse to produce one. On a real deck, `object` will
essentially only ever mean an image, a line, or an empty shape.

## 5. A table cell anchors to the TABLE, not the cell

SLIDE-6 was placed on a word inside row 1, column 0. The anchor names `zooTable` and carries no
row, no column, no cell location of any kind.

So the hoped-for result — that a deck might be the one place in Workspace where comment-to-cell
needs nothing but a JSON parse — **does not hold**. You learn which table; the quoted word is the
only cell-level signal, and it is ambiguous the moment that word appears twice in the table.

## 6. `anchor_state` discards something on Slides that it does not discard elsewhere

`type: "page"` (SLIDE-1, the whole slide) and `type: "shape"` (SLIDE-5, one element on it) both
collapse to `object`, because the model's only inputs are *anchor present?* and *quote present?*.

On Docs that collapse costs nothing — the anchor is opaque, so there is genuinely nothing more to
say. On Slides the anchor distinguishes *"this comment is about the whole slide"* from *"this
comment is about that ellipse"*, and the library throws it away. Recorded as a follow-up rather
than fixed here; the natural home is a `Slides._locate_comment` hook, exactly parallel to the one
`Sheet` already defines (`CommentsMixin.comments` picks it up via `getattr`), and unlike the
Sheets one it needs no export — a JSON parse plus one `presentations.get`.

## 7. The editor does NOT orphan an API-created comment on a deck

On Docs, a comment created through the Drive API renders as *"Original content deleted"*, shows
no quoted text, draws no marker, and is filtered out of the default sidebar
([`../api-created-comment-states/`](../api-created-comment-states/RESULTS.md)).

On Slides the same thing renders **normally**. The file-level `SPECIMEN` comment appears in the
sidebar's *All comments* list as an ordinary comment with no quote header and no orphan
treatment.

Not a contradiction of the Docs finding — a different editor making a different choice — but it
means *"API-created comments look broken in the editor"* is a **Docs** statement, not a Workspace
one, and this repository has stated it as the latter.

## 8. Incidental, and worth knowing before automating the Slides editor

* **Slides is SVG-rendered, not canvas.** 21 SVGs, 0 canvases — the opposite of Docs, which
  paints text into `.kix-canvas-tile-content` with no DOM text at all.
* **The editor exposes API object ids in the DOM**: the shape whose `objectId` is `zooShape1` is
  the SVG group `#editor-zooShape1`. That is a direct DOM-to-API bridge Docs does not have, and
  it is what made this probe reliable — targets were selected by id, not by coordinate.
* **`#insertCommentButton` is enabled with nothing selected**, unlike Docs where its
  `aria-disabled` is the selection oracle. On Slides it is not an oracle for anything.
* **The button becomes invisible when a shape is selected** — the toolbar swaps to shape-format
  controls. `⌘+Option+M` works in every state and does not disturb the selection; use it.
* **`window.getSelection()` is empty** even with text visibly selected, as in Docs. The only
  reliable selection oracle is a screenshot.
* Two placements initially landed on the wrong target and were only caught by reading the anchors
  back — one click hit `speakernotes-bottom-spacer` instead of `speakernotes-workspace`, 6px
  away, and produced a comment that *looked* fine and was attached to the wrong element. Verify
  by reading the anchor, never by the fact that a comment appeared.
