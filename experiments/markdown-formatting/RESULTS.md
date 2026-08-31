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
