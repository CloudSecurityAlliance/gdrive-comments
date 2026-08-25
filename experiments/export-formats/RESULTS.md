# What Drive will actually convert — probed 2026-08-25

**Question.** Roadmap item #6 ("format breadth") was written as *"PDF, Office, ODF, images"*.
Before exposing `Document.export()` through a tool, get the real matrix rather than a
remembered one — because the tool's enum of allowed formats is a contract, and a wrong entry
becomes a 400 the user cannot act on.

**Method.** `drive.about.get(fields="exportFormats,importFormats")` — Drive reporting its own
conversion table. This is the same table the server enforces for `files.export` and for
conversion on `files.create`, so it cannot disagree with itself. Runner:
[`probe.py`](probe.py). Reads no document content.

**Account.** A `@cloudsecurityalliance.org` Workspace account, full `drive` scope, 2026-08-25.
The table is a property of the API, not the account, but it is worth re-running if a format
ever 400s.

## Export — what `files.export` accepts

| Google type | Formats | Count |
|---|---|---|
| **document** | `text/markdown`, `text/x-markdown`, `text/plain`, `text/html`, `application/pdf`, `application/rtf`, `application/epub+zip`, `application/zip`, DOCX, ODT | **10** |
| **spreadsheet** | `text/csv`, `text/tab-separated-values`, `application/pdf`, `application/zip`, XLSX, ODS (both `vnd.` and `x-vnd.` spellings) | 7 |
| **presentation** | `application/pdf`, `text/plain`, PPTX, ODP | **4** |
| **drawing** | `image/png`, `image/jpeg`, `image/svg+xml`, `application/pdf` | 4 |
| form | `application/zip` | 1 |
| site | `text/plain` | 1 |

## Findings, including two that contradict the roadmap as written

1. **Markdown export is real, and Docs-only.** `text/markdown` is there (and the legacy
   `text/x-markdown` alias). This is the headline: it makes a Google Doc a *source* for
   Markdown toolchains rather than a dead end. See "Why Markdown is the important one" below.

2. **There is no Markdown or HTML export for Slides, and none for Sheets.** A deck exports to
   PDF, PPTX, ODP or `text/plain` — that is the whole list. Any tool that offers a single
   `format` enum across all three types will produce an unfixable 400 for two thirds of its
   callers unless **the enum is validated per document type**. This is the finding with
   direct consequences for #6's implementation.

3. **"images" was wrong for our three types.** Only **drawings** export PNG/JPEG/SVG, and
   `application/vnd.google-apps.drawing` is not in `MIME_TO_TYPE` at all — the library cannot
   open one. Nothing in Docs/Sheets/Slides exports an image. Per-slide thumbnails exist, but
   through `slides.presentations.pages.getThumbnail`, a different API and a separate item.

4. **`application/zip` is two different things.** For a Doc it is the HTML export plus its
   images; for a Sheet, one CSV per tab. Useful, and needs saying in the description, since
   "zip" alone tells a model nothing.

5. **EPUB, from a Doc.** Unexpected, and free.

## Import — `files.create` converting on upload (for roadmap #4)

| Uploaded as | Becomes |
|---|---|
| `text/markdown`, `text/x-markdown` | **document** |
| `text/plain`, `text/html`, `text/rtf`, `text/richtext` | document |
| DOCX/DOC/ODT (+ templates, macro-enabled) | document |
| **`application/pdf`** | **document** |
| **`image/png`, `image/jpeg`, `image/gif`, `image/bmp`** | **document** |
| CSV, TSV, XLSX/XLS, ODS | spreadsheet |
| PPTX/PPT, ODP | presentation |
| `application/x-msmetafile` | drawing |

6. **Markdown round-trips.** `text/markdown` imports *to* a Doc and exports *from* one. Both
   directions confirmed present in the same table, which is what makes the pipeline in the
   next section a loop rather than a one-way trip.

7. **PDF and images import *as documents*** — i.e. Drive will OCR them into a Doc. This is
   probably how the claude.ai connector's `read_file_content` reads PDFs and PNGs. Note what
   it costs: reading a PDF that way **creates a file**, so it is not a read operation and does
   not belong behind a `readOnlyHint` tool. Reaching those 13 mime types honestly needs local
   extraction, not this.

## Why Markdown is the important one

CSA already has a Markdown-consuming toolchain: the internal **`document-pipeline`** plugin
(v2.3.1) takes *Markdown → tagged PDF/UA-1*, with a design-rule preflight, composition review,
citations and CSA brand styling. Its input is exactly what `export("text/markdown")` produces.

So the two halves compose into a loop that neither piece offers alone:

    Google Doc --export text/markdown--> document-pipeline --> branded, accessible PDF/UA-1
         ^                                                                 |
         +----- import text/markdown (#4 create_file) <--- revised source -+

Draft and review where the comments are, typeset where the brand rules are, and put the result
back where it can be reviewed again. The export half is item #6 and needs no library change;
the import half is #4. A **public** document-pipeline plugin is planned, which is what makes
this worth designing for rather than treating as one org's internal convenience.

## Consequences

- #6 ships a per-type format enum, not a shared one (finding 2), and drops "images" (3).
- `text/markdown` gets first-class treatment and names the pipeline use case in its
  description, so a model reaches for it when asked for something publishable.
- #4's `create_file` should accept `text/markdown` and let Drive convert (6).
- PDF/image *reading* is not free and is not a read (7). Its own item, or decline it.
