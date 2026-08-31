# Can Markdown carry formatting, instead of a formatting API?

**Measured 2026-08-31** against live Google, on throwaway files created and trashed by the two
probes here. The question came from the CINO: rather than build a Sheets/Docs formatting API
([#277](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/277)), *make the text
field Markdown on send and receive*.

**Answer: yes for Docs, no for Sheets.** They are different problems and the same idea does not
serve both.

## Docs — Markdown works, at higher fidelity than expected

```
create with Markdown, read back via as_markdown():
    '# Heading One'
    'Some **bold** and *italic* text.'
    '- first bullet  '
    '| Col A | Col B |'
    '| :---- | :---- |'

  heading survived : True
  bold survived    : True
  bullets survived : True
  table survived   : True
```

**And convert-on-UPDATE works, not just on create** — which was the open question, since only
`files.create` was known to convert:

```
drive.files().update(fileId=…, media_body=<text/markdown>)
  update accepted  : yes
  new heading there: True
  old heading gone : True
```

So a full Markdown round trip already exists in the API: `as_markdown()` out, `files.update` with
`text/markdown` in. **Docs formatting needs no formatting API** — one tool, no parameter surface.

**`batchUpdate` has no Markdown path**, checked against the discovery document: 40 request types,
none Markdown. So the *incremental* edit path stays plain text; this is whole-document replacement.

### What that costs, and the question still open

Whole-document replacement is not a patch. Anything Markdown cannot represent is lost — exact
styling, section breaks, positioned objects, and probably suggestions.

**Comments survive**, measured:

```
BEFORE update: count=1 quoted_text=None
AFTER  update: count=1 quoted_text=None
```

**But that says nothing about ANCHORED comments**, and the distinction matters more here than
anywhere. `create_comment` cannot anchor — the API has no way to (see
`experiments/anchor-probe/`) — so the only comment this probe could make was already unanchored.
A first pass reported *"anchor destroyed"* on the strength of `quoted_text=None` **after** the
update; checking the **before** state showed it was `None` all along and nothing had been
destroyed. The claim was withdrawn.

**Testing it needs a document with a UI-placed anchored comment**, which no probe can create. Until
then: whether a Markdown update preserves `quoted_text` is **unknown**, and it is the deciding
factor for whether this is usable in a comment-triage tool. Losing anchors silently would remove
the field that makes `export_comments` worth reading.

## Sheets — Markdown is the wrong shape

The values API is **plain text, and formatting is not in it**:

```
wrote:      [['**bold?**'], ['# Heading?'], ['- bullet?']]
read back:  [['**bold?**'], ['# Heading?'], ['- bullet?']]

  A1: value={'stringValue': '**bold?**'} textFormatRuns=None bold=None
  A2: value={'stringValue': '# Heading?'} textFormatRuns=None bold=None
```

Literal asterisks. Nothing converts, and nothing would: `ValueRange` carries only
`majorDimension`, `range`, `values`.

Formatting lives in `CellData` — `userEnteredFormat`, `textFormatRuns` — reachable only through
`spreadsheets.batchUpdate`. Per-character-range styling **inside** one cell does work:

```
updateCells with textFormatRuns -> [{'format': {}},
                                    {'startIndex': 6, 'format': {'bold': True}},
                                    {'startIndex': 10, 'format': {}}]
  the same cell via the values API: [['plain bold plain']]
```

Note the last line: **the values API reads the text with formatting stripped.** The two are
parallel structures over the same cell, not one thing.

### Why Markdown does not answer the Sheets case

* `# Heading`, `- bullet` and tables are **meaningless in a cell**. Markdown's vocabulary is
  document structure; a cell has no structure to describe.
* Inline `**bold**` → `textFormatRuns` *would* be expressible — but that is a narrow slice, and it
  is not what anybody asked for.
* **What #277 and #278 actually want is cell-level formatting**: a bold header row, a background
  fill, a frozen top row, column widths. Markdown cannot express any of it. `userEnteredFormat`
  and `updateSheetProperties` can.

## Consequence for the roadmap

| | route | cost |
|---|---|---|
| **Docs formatting** | Markdown in / Markdown out | **one tool**, no formatting API — but whole-document, and the anchored-comment question is open |
| **Sheets formatting** | `userEnteredFormat` · `textFormatRuns` · `updateSheetProperties` | a real API surface; Markdown does not help |

So the Markdown idea **removes most of the Docs half of #277** and **leaves the Sheets half exactly
where it was**. That is worth knowing before scoping, and it is the opposite of the intuition that
one representation would cover both.

---

# Slides, and the authoritative answer for all three

The CINO then asked about Slides. Rather than probe format by format, ask Drive: `about.get`
returns **`importFormats`**, its own declaration of what converts into what.

```
Doc:    23 source formats — markdown/plain among them: text/markdown, text/plain, text/x-markdown
Sheet:  10 source formats — markdown/plain among them: NONE
Slides:  9 source formats — markdown/plain among them: NONE
```

**Slides cannot take Markdown at all**, and neither can Sheets. Drive will not convert it. Their
only structured imports are PowerPoint/ODP and Excel/ODS/CSV/TSV respectively.

That is definitive and cheap — it replaces a probe per format with one call.

## But asking the question this way found the better answer

`importFormats` says what *does* convert, and two of those entries carry formatting:

| target | Markdown? | structured import that carries formatting |
|---|---|---|
| Doc | ✅ | DOCX, ODT, **HTML**, RTF |
| Sheet | ❌ | **XLSX**, ODS |
| Slides | ❌ | **PPTX**, ODP |

### Sheets: the tooling is already here, and already formatting

**`export_comments(destination="xlsx")` already writes a fully formatted workbook.** From
`_export.py`:

```python
fill = PatternFill("solid", fgColor=HEADER_FILL)
cell.font = Font(name=font, bold=True, color="FFFFFF")
cell.alignment = Alignment(vertical="center", wrap_text=True)
ws.freeze_panes = "A2"
ws.column_dimensions[letter].width = …
```

Bold white header on a fill, frozen top row, column widths — **that is #277's wish list, already
implemented and tested**, in `openpyxl`, which is already in the `mcp` extra rather than optional.

So the cheap route for Sheets formatting is **not** a formatting API and **not** Markdown: build
the XLSX that already gets built, and **upload it with conversion** instead of writing values.
`export_comments(destination="sheet")` currently goes through `values.update`, which by measurement
cannot carry formatting at all.

### Slides: no Markdown, but no PPTX needed either

Slides `batchUpdate` has **44 request types**, 29 of them text/shape/style:
`updateTextStyle`, `updateParagraphStyle`, `createParagraphBullets`, `createTable`, `createShape`,
`replaceAllText` and the rest. So Slides formatting is a native API surface — reachable today
through the existing `batch_update`, and needing no new dependency. PPTX import would only matter
for whole-deck authoring, and would add `python-pptx`.

## The complete answer

| | Markdown import | best formatting route | new tooling needed |
|---|---|---|---|
| **Doc** | ✅ works, high fidelity | **Markdown whole-file** — `as_markdown` out, `files.update` in | **none** |
| **Sheet** | ❌ never | **XLSX upload** — reuse the formatted workbook `_export` already writes | **none** — `openpyxl` is already a dependency |
| **Slides** | ❌ never | **native `batchUpdate`** — 29 style requests | none (PPTX only for whole-deck authoring) |

**So #277 needs no new formatting API for any of the three.** Docs gets it from Markdown, Sheets
from an XLSX upload path that is 90% written, Slides from an API that already exists behind
`batch_update`. What is left is exposure and wiring, not a new surface — which is a materially
smaller piece of work than the issue assumed, and a different one.

The open question from the Docs section stands and gates only the Docs route: **does a Markdown
whole-file update preserve an anchored comment?** The Sheets XLSX route has the same question, and
it matters as much there.

## Corroborated from the product, not just the API

**Checked independently in the web UI by the CINO, 2026-08-31:** Google **Docs** offers *"paste as
Markdown"*; **Sheets and Slides explicitly do not.**

That matters as evidence rather than as a footnote. An API-only finding leaves open the reading
*"maybe the product supports it and the API simply lags"* — a real possibility, since Google ships
UI features ahead of API surface routinely. Two independent surfaces agreeing closes it: Markdown
is a **Docs** feature at Google, not a Workspace one.

So this is not a gap waiting to be filled by the next API release. It is the shape of the product.

## Why a uniform Markdown interface would be worse than three honest ones

The appeal of "make the text field Markdown everywhere" was one representation across all three.
Having measured, that interface would be a **lie for two of them**:

* A **cell** has no document structure. `# Heading`, `- bullet` and a pipe table have nothing to
  mean there. Accepting Markdown and silently ignoring most of it is the failure mode this
  project keeps finding elsewhere — a caller sends something plausible, gets no error, and half
  their intent is discarded.
* A **slide** is shape-addressed. Text lives inside a shape you must name; there is no linear
  document for Markdown's block structure to describe.
* Only *inline* marks — bold, italic, links — carry across all three. That is a small slice of
  Markdown, and offering the whole syntax to get it would misrepresent what is supported.

So the three-route answer is not a consolation prize for a failed idea. **The interface should
match the model**: Markdown where the thing is a document, `textFormatRuns`/`userEnteredFormat`
where it is a grid, shape-scoped style requests where it is a canvas.
