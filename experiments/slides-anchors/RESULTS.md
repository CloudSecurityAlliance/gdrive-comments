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

## 3. `subtype: "text"` implies quoted text — but NOT the reverse

*(This section first said the two were present "exactly when" the other was, "across all six,
with no exceptions". **That was wrong**, and it was wrong in the way this repository keeps
catching: six samples that happened to agree, stated as a biconditional. §9's multi-select case
is the counterexample. The corrected table is below; what the first pass measured is unchanged.)*

| anchor | `quotedFileContent` | this library's `anchor_state` |
|---|---|---|
| `type: "page"` | absent | `object` |
| `type: "shape"`, no subtype, one target | absent | `object` |
| `type: "shape"`, `subtype: "text"` | **present** | `text` |
| `type: "shape"`, no subtype, **two targets** | **present** (§9) | `text` |
| absent (API-created) | absent | `file` |

So `subtype: "text"` → a quote is present. A quote present does **not** imply `subtype: "text"`.

The four-state model **holds on Slides** — `file`, `object` and `text` are all reachable, and
`quote_only` remains API-only as it is everywhere else. `anchor_state` has been reporting truth
for decks; it was just never checked.

But see §5 and §9: it is *lossy* here in a way it is not on Docs, and the multi-select row above
is the sharpest case — a comment on two whole shapes reports `anchor_state: "text"`.

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

---

# Second pass — the claims the first pass ASSERTED but never measured

**2026-09-05, later the same day.** The first pass shipped two sentences that were inferences
dressed as findings, in the specimen's own provenance text and in the v0.51.0 changelog:

> changing a shape's text keeps the comment attached and only makes its quote stale; DELETING the
> shape is what orphans it

Neither half had been tested. Both are now, on a **throwaway deck** (`1FJmPm17…`, since the tests
destroy their subjects) rather than on the published specimen. Four more gaps closed with them.

## 9. A comment can name TWO targets, and then a quote appears with no `subtype`

Two shapes selected together (click, then shift-click), one comment:

```
{"type":"shape","uid":1788627102429,"page":"p","targets":["shapeMultiA","shapeMultiB"]}
quoted: "MULTI A"
```

Three things at once:

* **`targets` really is plural** — #427 flagged the multi-target shape as unknown; it is a plain
  list of object ids, in selection order.
* **No `subtype`, yet `quotedFileContent` is present.** This is the counterexample that breaks
  §3's original biconditional. The editor quotes the text of the *first* selected shape while
  anchoring to both as objects.
* **`anchor_state` therefore reports `text` for a comment on two whole shapes** — because it
  reads quote-presence, and the quote is there. Not a lie the model can currently avoid; it is
  §6's lossiness showing up as an actively misleading value rather than a merely incomplete one.

## 10. `page` names the real slide — confirmed against a second slide

The whole first pass was a **one-slide** deck, where `page: "p"` is equally consistent with
*"names the slide"* and *"always names the first slide"*. A comment on a shape on slide 2:

```
{"type":"shape","subtype":"text","uid":…,"page":"slideTwo","targets":["shapeOnTwo"]}
```

`page` tracks the slide. So §2's finding is exactly as narrow as it was stated: `page` is right
about *which slide*, and wrong only about **notes vs body**.

## 11. An image behaves like any other shape

```
{"type":"shape","uid":…,"page":"p","targets":["imgOne"]}   quoted: null
```

`type` is `"shape"` for an image too — nothing in the anchor says *image*. This is the realistic
`object` case that §4 said would be rare; it needed no purpose-built empty ellipse.

## 12. NEITHER mutation changes the payload, and NOTHING marks the comment

The two claims under test. `shapeEdit`'s text was replaced wholesale (so the quoted string exists
nowhere in the deck) and `shapeDelete` was removed entirely (`deleteObject`).

**Before and after are byte-identical:**

```
EDIT2    {"type":"shape","subtype":"text","page":"p","targets":["shapeEdit"]}    quoted ". This text"
DELETE2  {"type":"shape","subtype":"text","page":"p","targets":["shapeDelete"]}  quoted "after a comment"
```

`shapeDelete` no longer appears in `presentations.get`. The anchor still names it.

**And the editor shows both as ordinary, healthy comments.** No *"Original content deleted"*, no
orphan marker, no strikethrough — each still displays its quote as the sidebar card header, so a
reviewer reads *"after a comment"* as though that text were in the deck. It is not.

### What that means for the claim that was published

*"Changing the text keeps the comment attached"* — true, and it makes the quote stale. Fine.

***"Deleting the shape is what orphans it"* — wrong, or at least it implies something false.**
Nothing orphans it in any observable way. The correct statement is the opposite in tone: a Slides
comment pointing at a **deleted** object is indistinguishable, in both the API payload and the
editor sidebar, from one pointing at a live object. The danger is not that a comment breaks
loudly; it is that it keeps looking fine while referring to content that is gone.

This is consistent with the already-recorded *"no orphan / anchor-validity signal exists on the
resource"* (2026-09-03, `api-created-comment-states/`) — that finding simply also holds for a
target destroyed **after** the fact, on a third editor.

### The consequence for #427

It converts one of that issue's constraints from a precaution into a measured requirement.
Resolving `targets` against `presentations.get` is the **only** way to know whether a Slides
comment still points at anything — and since a dangling target is invisible everywhere else, a
resolver must report it explicitly rather than dropping the comment or silently reporting it as
file-level.

## 13. Two notes for anyone driving the Slides editor

* **A double-click does not reliably select a word** — it often lands as a bare caret, and the
  first double-click into a shape only enters text-edit mode. `Alt+Shift+ArrowRight` (extend by
  word) is deterministic where hit-testing a glyph box is not, and a screenshot is still the only
  selection oracle.
* Verify **every** placement by reading its anchor back before building on it. Two of the four
  comments in this pass landed on the wrong element on the first attempt — one became a
  whole-slide comment, the other attached to the layout placeholder `i0` — and both looked
  entirely normal in the sidebar.
