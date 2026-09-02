# Docs anchor states — Results (run 2026-09-02)

Raw findings for issues **#361** (can a consumer tell the three anchor states apart) and **#358**
(anchors as a localization hint). Written inline as each was measured. **All questions are settled
except one**, and that one says so rather than being quietly left blank — see *NOT MEASURED* below.

The headline: **a real Docs anchor is an opaque `kix.*` id carrying no position** — which was the
opposite of the prediction — **and it turns out not to matter**, because Docs guarantees quoted text
wherever text exists. The reasoning is at the bottom, under *THE CONSEQUENCE*.

Probe: [`probe.py`](probe.py) (Docs anchor states, structure) · [`probe_notes.py`](probe_notes.py)
(Sheets notes, cell headers). Throwaway files created under
`kseifried@cloudsecurityalliance.org`.

---

## Why a human is required for the anchor half

Measured in the 2026-07-09 [`anchor-probe`](../anchor-probe/RESULTS.md): a comment created through
the Drive API has its anchor **stored verbatim** and is then treated as *un-anchored* by the
editor. Google says the same — *"developers can define their own format … Google Workspace editor
apps treat these comments as un-anchored comments."*

**So an API-created comment cannot produce a real anchor.** No amount of scripting substitutes for
a right-click in the UI, and any probe of anchor behaviour has a human in it.

---

## SETTLED: what Google's own documentation already concedes

Before any measurement, from
[Manage comments and replies](https://developers.google.com/workspace/drive/api/guides/manage-comments):

> anchors are immutable and **"position relative to content cannot be guaranteed between
> revisions."**

**#358's premise is the vendor's own position.** The anchor is documented as a hint, not ground
truth. That is worth handing to the consumer as a citation rather than as our opinion.

Google's single published Docs anchor example carries a **position**:

```json
{"region": {"kind": "drive#commentRegion", "line": <n>, "rev": "head"}}
```

**Measured below: that is not what the editor produces.**

---

## SETTLED: #361 state 1 — a file-level comment omits both keys

An API-created comment with no anchor, requested with
`fields=id,anchor,quotedFileContent,content`:

```json
{
  "id": "AAACGeL57Sc",
  "content": "STATE 1 - file-level, created via API with no anchor"
}
```

```
'anchor' key present            : False
'quotedFileContent' key present : False
```

**Drive OMITS absent fields rather than returning them as null.** That matters more than it looks:
it means "key absent" is the only form absence takes, so `d.get("anchor")` → `None` is not
conflating two states — there is only one. A `quoted_text` of `""` versus `None` would therefore be
a distinction *we* invented, not one Drive draws.

---

## SETTLED: #358 §4 — a page number is NOT OBTAINABLE

From the Docs v1 **discovery document** (the API surface itself, not a doc page that might lag):

```
StructuralElement can be : ['endIndex', 'paragraph', 'sectionBreak', 'startIndex',
                            'table', 'tableOfContents']
schemas containing 'Page': ['InsertPageBreakRequest', 'PageBreak']
PageBreak properties     : ['suggestedDeletionIds', 'suggestedInsertionIds',
                            'suggestedTextStyleChanges', 'textStyle']
page-number properties   : ['SectionStyle.pageNumberStart',
                            'DocumentStyle.pageNumberStart', …Suggested]
```

- **No page element exists** in the document model.
- `PageBreak` is an *inline* element for a **manual** break, and carries no number.
- `pageNumberStart` is a layout setting — where rendered numbering *begins*, not where anything is.

**Pagination is a rendering output.** The layout engine produces it from page size, margins, fonts
and content; the API exposes the inputs and never the result. A reader's *"page 5"* therefore has
no counterpart to compare against, and the only route would be exporting to PDF and mapping
character offsets onto pages — a separate machine, for the lowest-value item on the list.

This is a **cannot**, with the vendor's schema as the evidence.

---

## SETTLED: #358 §2 — a structural path IS derivable

`documents.get(includeTabsContent=True)` on the probe document, after adding real headings:

```
[1..140]    NORMAL_TEXT  'PROBE DOCUMENT - anchor states. Every paragraph is numbered…'
[140..161]  NORMAL_TEXT  'P1. Short paragraph.'
[161..393]  NORMAL_TEXT  'P2. This paragraph is deliberately longer…'
[393..414]  HEADING_1    'SECTION 2 - Taxonomy'
[414..438]  HEADING_2    'Subsection 2.3 - Naming'
[438..481]  NORMAL_TEXT  'P3. The taxonomy in this section is wrong.'
[570..582]  TABLE 2 rows
```

Every structural element carries `startIndex`/`endIndex` and `namedStyleType`. So:

- **a character offset resolves to a paragraph**, by interval containment;
- **a heading chain is derivable**, by walking backwards for the nearest lower-numbered heading —
  a comment in P3 is under *SECTION 2 › Subsection 2.3*;
- **a paragraph index is free.**

All of which is available **only if something gives us an offset.** The anchor does not (finding 1),
so the offset has to come from locating the quoted text — which finding 3 shows is essentially always
present. See *THE CONSEQUENCE*.

---

## SETTLED: #358 §5 — notes are readable, and cheap to COUNT

Written through the Sheets API (so the write path exists too) and read back:

```
§5 NOTES READABLE: 1 found
   Sheet1!B3  'NOTE: restated after the Q3 audit. Not a comment - no author…'
```

The read costs one `spreadsheets.get` with
`fields=sheets(data(rowData(values(note))))` — **no grid values**, so counting notes for a
`caveats` line is cheap even when not returning them. That is exactly the signal #358 asks for:

> tell us notes exist even before they can be read. A silent zero is the expensive failure.

And, measured rather than assumed:

```
§5 the Drive comments API sees 0 comment(s) on this file
```

A file carrying a note has **zero comments**. A note is a different object — no author, no thread,
not repliable, not resolvable — and the comments API does not see it at all. So a comment-shaped
workflow has no destination for one, which is #358's table stated as a measurement.

---

## SETTLED: #358 §6 — cell headers are FREE

For a comment on B3 of a small grid:

```
cell_text (already shipped) : '388000'
column header (row 1)       : 'Q3 actual'
row header (column A)       : 'Southwest'
-> 'B3, which reads 388000, in the row labelled Southwest, column Q3 actual'
```

Derived from **the same grid `cell_text` already fetches** — no extra API call.

One honesty constraint: *which* row and column are the headers is a **heuristic** (row 1 and
column A). A sheet with a title block above the table, or a transposed layout, breaks it. So this
has to be reported as a guess with its basis, not as a fact — which is the same rule the tab
resolution already follows (`tab_ambiguous` rather than picking the first sheet).

---

## SETTLED: #358 §7 — already shipped

`list_suggestions` returns the proposed **`text`** plus `kind` (`insertion` | `deletion`), and a
*replacement* is deliberately not collapsed: it arrives as one suggestion id carrying a deletion
run **and** an insertion run (`suggestions.py:31-33`), so *"replace X with Y"* is reconstructable
rather than lossy. No work needed; this is a documentation answer.

---

## MEASURED: a real Docs anchor is OPAQUE — the prediction was wrong

Six comments placed through the UI (keyboard-driven Playwright over CDP, so the editor produced
the anchors rather than the API). Raw, unedited:

| state | how it was made | `anchor` | `quotedFileContent` |
|---|---|---|---|
| **1** file-level | API, no anchor | **key absent** | **key absent** |
| **2** caret, nothing selected | click in P1, select nothing | `kix.wbglc1tappnr` | `{"mimeType":"text/html","value":"paragraph"}` |
| **3** three words | select `taxonomy in this` | `kix.ce7ypxwipivp` | `{…,"value":"taxonomy in this"}` |
| **6** on an IMAGE | select the inline image | `kix.y1h574n5va9q` | **key absent** |
| **7** BOLD selection | bold, then select, then comment | `kix.…` | `{…,"value":"Short paragraph"}` |

### Finding 1 — the anchor carries NO position

```
anchor raw    : 'kix.ce7ypxwipivp'
anchor PARSED : not JSON (opaque string)
```

Google's **one published Docs example** is
`{"region": {"kind": "drive#commentRegion", "line": <n>, "rev": "head"}}` — a *position*. **That
is not what the editor produces.** A real Docs anchor is an opaque `kix.*` id, exactly like the
Sheets `workbook-range` id: structured enough to be a key, useless as a coordinate.

This is the same shape of error the Sheets probe corrected — a documented anchor format that no
real UI comment uses. `research/google-drive-comments-reference.md` §7 already listed `kix.XXXX`
as *"the Google Docs editor's internal namespace"*; it turns out to be the whole story for Docs.

**I predicted it would carry a position, and it does not.** Recorded because the wrong prediction
is the reason the probe was worth running.

### Finding 2 — the three states of #361 ARE distinguishable, by ANCHOR PRESENCE

Not by `quoted_text`, which is where the consumer was looking:

- **file-level** → no anchor, no quoted text
- **anchored to a non-text object** → **anchor present, quoted text absent**
- **anchored to text** → anchor present, quoted text present

So the discriminator exists, it is one field, and the library already retains it
(`Comment.anchor`, `comments.py:116`). Both consumer surfaces drop it — which is the defect.

### Finding 3 — Docs EXPANDS a caret to the enclosing word

State 2 was a caret with nothing selected, and the quoted text came back as **`"paragraph"`** — the
word the caret sat in. The editor snapped it.

**So "anchored but nothing selected" does not exist for text in Docs.** The consumer's suspected
most-common imprecision cannot arise the way they pictured it.

### Finding 4 — Docs REFUSES to comment on an empty paragraph

`Cmd+Alt+M` on the document's trailing empty paragraph opened **no comment box at all**; the text
went into the document body instead (visible in the screenshot, and removed afterwards). Docs
requires something to anchor to.

Consistent with finding 3: the editor will not create an anchor with nothing behind it.

### Finding 5 — `mimeType` says `text/html`, the value is PLAIN TEXT

State 7 selected a **bold** run — confirmed bold through the Docs API (`textStyle.bold = True`),
not assumed — and `quotedFileContent.value` came back as `"Short paragraph"` with **no markup**.

This matters for #358's hard constraint. Staleness detection works by testing whether the stored
quote still occurs in the document **exactly once**; had the value carried `<b>` tags it would
never match extracted plain text, and every formatted comment would read as document drift. It
does not. Nothing to strip.

### NOT MEASURED — how a cross-paragraph selection is represented

Three attempts, all defeated by the same **automation artifact**: after the bold operation the
editor's selection stayed on the previously-found run, so `Cmd+F` navigation stopped changing it
and two comments landed on the wrong text. Those two are in the document, labelled 5b and 5c, and
should be ignored.

Recorded as unmeasured rather than guessed. It is also the least consequential of the set: #358 §3
asks *whether the span crosses a paragraph boundary*, and that is **computable from what we already
have** — locate the quoted text against the structural offsets and see whether the matched interval
spans two elements. The probe would only have told us how Docs *represents* it, which we do not
need in order to answer the question.

---

## THE CONSEQUENCE, and it inverts the worry that motivated the probe

Before measuring, the fear was: *the anchor is the only way to locate a comment with no quoted
text, so if the anchor is opaque, a context window is unbuildable exactly where it is most needed.*

**The anchor is opaque — and that turns out not to matter.** Findings 3 and 4 close the gap:

- Docs **guarantees** quoted text wherever there is text, by snapping a caret to its word.
- The only anchored comments **without** quoted text are on **non-text objects** — an image — where
  there is no textual context to give in the first place.

So the two routes and their failure cases line up differently than expected:

| comment | locate by | context window |
|---|---|---|
| anchored to text (incl. bare caret) | quoted-text match — **always available** | **buildable** |
| anchored to an image | nothing to match | **nothing to build** — correctly reported as a caveat |
| file-level | nothing to locate | not a question that applies |

**#358 §1 is therefore buildable for every case in which it is meaningful**, using machinery that
already exists (`_inline.py` locates by unique quote; `documents.get` gives paragraph offsets and
the heading chain). The opaque anchor costs us nothing we needed.

The honest residual, worth stating to the consumer because it is the one thing they should not
expect: a quote occurring **more than once** in the document still cannot be placed — that is the
existing `_inline` limitation, and widening context does not fix it.

---
