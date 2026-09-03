# What it takes to automate the Docs editor — measured 2026-09-03, and it is not cheap

Written after an attempt, so the next one starts further along instead of rediscovering this.

**The goal:** place comments the API cannot — a real `kix.*` anchor, a caret-snap, an image
comment, an assignment — by driving the real editor. Not by calling its private endpoints, which
are undocumented, change without notice, and sit uneasily with Google's terms.

## What was established

**Google Docs is canvas-rendered.** `document.querySelector('.kix-canvas-tile-content')` returns
three `<canvas>` elements and there is no `.kix-page`. So **the document text is not in the DOM**:
no `click("text=…")`, no `getSelection()`, no way to read what is selected.

**Keyboard input does reach the editor.** `document.activeElement` is
`IFRAME.docs-texteventtarget-iframe` — Docs' hidden text event target. So keystrokes are
delivered; the problem is not focus routing.

**The canvas cannot be clicked directly.** `.kix-canvas-tile-content` is covered:
`<div class="kix-page-paginated kix-page-canvas-compact-mode"> intercepts pointer events`.
**Click the `.kix-page-paginated` div instead** — that works and places the caret.

**`Ctrl+F` is intercepted** and does not open Docs' find bar, so the obvious
find-then-select-then-comment route is closed.

**The shortcuts are platform-specific and this cost real time.** On macOS the comment shortcut is
**⌘+Option+M**, not Ctrl+Alt+M; document end is **⌘+↓**, not Ctrl+End; line start is **⌘+←**, not
Home. Sending the Windows/Linux bindings produces *no error and no effect*, which reads exactly
like a selection problem and is not one.

**Even with Mac bindings and the caret placed, ⌘+Option+M did not open a comment box** in this
environment. That is where the attempt stopped.

## Why this is harder than ordinary web automation

Selection is the whole problem. In a DOM editor you select by selector; here you must select by
**geometry** — know where a run of text is *rendered*, and drag between two points. The text
positions are computable (the Docs API gives character offsets, and the rendered layout is
deterministic for a given zoom and page width) but nothing about that is quick, and it breaks
whenever the document reflows.

## What a serious attempt should try next, in order

1. **The menu, not the shortcut.** Docs' menus are real DOM. `Insert ▸ Comment` is clickable and
   sidesteps every keyboard-binding question. That is the single most promising thread and it was
   not reached.
2. **Turn on screen-reader support** (`Tools ▸ Accessibility`). It makes Docs maintain a DOM text
   layer for assistive technology — which is exactly the queryable surface canvas rendering took
   away, and it is a supported product feature rather than a hack.
3. **Geometry from the API.** Character offsets from `documents.get`, mapped to page coordinates,
   then mouse-drag to select. Most work, most fragile, last resort.

## IT WORKS — the recipe, found 2026-09-03 after the focus problem was removed

**The earlier failure was contention for the keyboard, not the technique.** The machine's owner
was using the laptop while automation ran, so focus moved mid-sequence and every keystroke landed
somewhere else. With the machine left alone, the same keys work. **That is worth knowing before
anyone concludes canvas rendering makes this impossible — it does not.**

### The working sequence

```
1. dblclick  .kix-page-paginated >> nth=N     selects a WORD wherever it lands
2. (optional) Shift+Meta+ArrowRight           extends to end of line - keyboard DOES work
3. click     #insertCommentButton             opens the comment draft
4. type into [aria-label="Comment draft"]
5. click     [aria-label="Post Comment"]
```

**`#insertCommentButton`'s `aria-disabled` is the selection oracle.** Canvas gives no
`getSelection()` and draws the highlight on the canvas, so there is no DOM way to ask *"is
anything selected?"* — but the button is disabled when nothing is and enabled when something is.
Check it before every comment; it turns a silent no-op into a fact.

### Two things that will waste your time

**Pick a page that actually has text.** `dblclick` at the centre of a page whose lower half is
blank selects nothing and the button stays disabled. The last page of a document is usually the
wrong choice for exactly this reason.

**Double-clicking non-text still anchors.** MEASURED: a double-click that landed on a
non-textual part of the page produced a comment with a real `kix.*` anchor and **no quoted
text** — the `object` state. So the `object` state does **not** require an image, as the
specimen assumed; it requires anchoring to something with nothing quotable. That was found by
accident and is now the fastest way to produce that state deliberately.

### What it produced

All four anchor states on one file, which this project had never had together:

| comment | state | anchor | quoted text |
|---|---|---|---|
| A (API) | `file` | — | — |
| B, C (API) | `quote_only` | — | present |
| EDITOR-1 (browser) | `object` | `kix.zfrg5l4hj8f2` | — |
| EDITOR-2 (browser) | `text` | `kix.1vzp53ylhunj` | present |

## The judgement, recorded

For **fifteen placements**, a human with the file open does it in a few minutes, and every
specimen already carries its own instructions in its own text. Automating it is worth doing when
the corpus needs **rebuilding repeatedly** — and that is a real prospect, since `--rewrite`
breaks every hand-placed anchor — but it was not worth blocking the corpus on.

*(Superseded by the section above — automation works. The judgement stands only for the case
where somebody is using the machine: automation and a human cannot share one keyboard.)*
