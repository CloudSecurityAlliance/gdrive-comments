# What we actually know about Google Workspace comments — and what we do not

**A coverage map, not the reference.** The reference is #340: 20–50 pages, written primarily for
an AI to read while implementing. This file is the thing that has to exist *first* — an honest
account of which claims are **measured**, which are only **Google's word**, and which are
**unknown** — because a 40-page document that does not distinguish those is exactly the artefact
that made this subject hard in the first place.

Written 2026-09-03, after a run of probing that overturned two of this project's own documented
"facts" in a single day.

## Why this file and not just the reference

Every existing account of Google comments — Google's own included — mixes three kinds of claim
without marking them:

1. what somebody **measured**,
2. what Google **documents** (which we have now caught being wrong three times: the published
   Docs anchor example, `keepForever`'s applicability, and `revisions.update` returning 200 for a
   write it discards),
3. what somebody **inferred** and everyone then repeated (the `R1C2` anchor folklore).

The reference is only worth writing if every line carries which of those it is. So the map comes
first, and the confidence column is the point of it.

**Confidence vocabulary**, used strictly below:

| | |
|---|---|
| **MEASURED** | we ran it against live Google and recorded the output, with a date and a probe |
| **DOCUMENTED** | Google says so; we have not verified it |
| **INFERRED** | follows from something measured, but was not itself observed |
| **UNKNOWN** | nobody here has checked |
| **UNTESTABLE** | cannot be checked without access we do not have (preview enrolment, an admin, a second account) |

## The four surfaces, and which of them is real today

This is the frame the reference needs, because most confusion is people conflating them:

| surface | status | comments? | what it is for |
|---|---|---|---|
| **The web editor** | GA | yes, natively | what every user expectation is set by. Not an API. |
| **Drive API v3** `comments` | GA | **yes — the only GA comment API** | what this library uses |
| **Docs / Sheets / Slides API** (GA) | GA | **NO** | content, structure, suggestions (read-only). **No comment surface at all** |
| **Docs / Sheets / Slides native comments** | Developer Preview | yes | the editors' own comment model; gated |

**The single most common misconception, and worth the reference opening with it:** the Docs API is
not where comments live. It has never had a comments surface. MEASURED 2026-09-03 —
`documents.get(includeTabsContent=True)` on a document with a real anchored comment contains no
`kix.`, no anchor field, no comment field, and no `namedRanges`. Six candidate read parameters
(`commentsViewMode`, `includeCommentsMode`, `commentMode`, `includeComments`, `commentsMode`) are
all rejected as *unknown fields*, identically to a made-up control.

## Coverage: the editor (what users see)

| question | status | source |
|---|---|---|
| Comment with nothing selected → anchor expands to the enclosing word | MEASURED 2026-09-02 | `docs-anchor-states/` |
| Comment on an empty paragraph → editor **refuses**, no box appears | MEASURED 2026-09-02 | `docs-anchor-states/` |
| Comment on an inline image → anchor present, no quoted text | MEASURED 2026-09-02 | `docs-anchor-states/` |
| Editor-created comment carries **both** anchor and quoted text | MEASURED 2026-07-20, again 2026-09-03 | `docs-suggestions/`, `api-created-comment-states/` |
| An API-created comment renders as **"Original content deleted"** | MEASURED 2026-09-03 | `api-created-comment-states/` |
| Those comments are **filtered out of the default sidebar** — visible only under "show all comments", and leave no marker in the body | MEASURED 2026-09-03 | `api-created-comment-states/` |
| A comment reusing a **real** `kix.*` anchor renders as properly anchored | MEASURED 2026-09-03 | `api-created-comment-states/` |
| `quotedFileContent` is displayed **verbatim** beside a valid anchor, unvalidated | MEASURED 2026-09-03 | `api-created-comment-states/` |
| Comment across a paragraph boundary — what the anchor and quote look like | **UNKNOWN** | probe written, state never placed |
| Comment in a **table cell** — from the editor | **UNKNOWN** | probe written, state never placed |
| How a **resolved** thread renders, and whether resolve-by-API differs | **UNKNOWN** | — |
| **@mention** and **assignment** ("action item") in the editor | **UNKNOWN** | see the gap section |
| Whether an API-created comment sends **email notification** | **UNKNOWN** | see the gap section |
| Whether the editor's version history shows more than the API's two revisions | **UNKNOWN** | strongly suspected yes; `revisions/` |

## Coverage: Drive API v3 comments

| question | status | source |
|---|---|---|
| `resolved` is **absent**, not `false`, on a never-resolved comment | MEASURED 2026-07-20 | `comment-lifecycle/` |
| Soft delete strips **both** `content` and `author` | MEASURED 2026-07-20 | `comment-lifecycle/` |
| Resolve/reopen is an **action-reply**, never a PATCH, and may be content-less | MEASURED 2026-07-20 | `comment-lifecycle/` |
| `author.email` usually absent even when requested | MEASURED 2026-07-20 | `comment-lifecycle/` |
| Every comments method requires an explicit `fields`; `replies` alone returns them empty | MEASURED 2026-07-20 | `comment-lifecycle/` |
| Anchors are opaque: `kix.*` (Docs), `workbook-range` (Sheets) | MEASURED 2026-07-09 / 2026-09-02 | `anchor-probe/`, `docs-anchor-states/` |
| An **API-written anchor** is stored verbatim and then treated as un-anchored by the editors | MEASURED 2026-07-09 | `anchor-probe/` |
| …but a **real** anchor reused from an existing comment **is** honoured | MEASURED 2026-09-03 | `api-created-comment-states/` |
| **Four** anchor states, not three (`file` / `object` / `text` / `quote_only`) | MEASURED 2026-09-03 | `api-created-comment-states/` |
| `quotedFileContent` is settable at create and validated against nothing | MEASURED 2026-09-03 | `api-created-comment-states/` |
| `quotedFileContent.mimeType` is a **constant** — send `text/plain`, get `text/html` | MEASURED 2026-09-03 | `api-created-comment-states/` |
| The quote value round-trips **byte-verbatim** (whitespace, newlines, tabs) | MEASURED 2026-09-03 | `api-created-comment-states/` |
| Comment ids within one batch are **sequential** in the final character | MEASURED 2026-09-03 | `api-created-comment-states/` |
| **`fields=*` is NOT exhaustive** — it omits `mentionedEmailAddresses` and `assigneeEmailAddress`, both of which a mask accepts | MEASURED 2026-09-03 | this file's own probe |
| Both fields exist on **replies** too, while `quotedFileContent` is **refused** on a reply | MEASURED 2026-09-03 | #398 |
| Neither field is **writable**: accepted at create, 200 returned, **stored neither** | MEASURED 2026-09-03 | #398 |
| No orphan / anchor-validity signal exists on the resource | MEASURED 2026-09-03 | `api-created-comment-states/` |
| No cross-file comment search; `comments.list` is per-file, `files.list` has no comment predicate | MEASURED / DOCUMENTED | `google-drive-comments-reference.md` |
| Sheets comment → cell needs the XLSX-export detour, incl. the three-hop rels walk | MEASURED 2026-07-21 | `sheets-cellmap/`, `_cellmap.py` |
| Notes are not comments: a file with a note returns **zero** comments | MEASURED 2026-09-02 | `docs-anchor-states/probe_notes.py` |
| What a **comment on a Slides shape / slide / speaker notes** looks like | **UNKNOWN** | never probed |
| Whether a Drive-API comment can be **assigned** at create | **UNKNOWN** | — |
| Rate limits and pagination behaviour at scale (hundreds of threads) | **UNKNOWN** | consumer reports 90 threads working |

## Coverage: the native comment APIs (Developer Preview)

**This is the largest gap and it is mostly UNTESTABLE for us.** What is established is only that
the surface *exists* and is *gated*:

| question | status | source |
|---|---|---|
| Request names recognised — Docs/Sheets/Slides each have five comment request types | MEASURED 2026-09-02 | `comments-apis-2026-09.md` §2.1 |
| Anchor field is per-editor: Docs `range`, Sheets `coordinate`, Slides `objectId` | MEASURED 2026-09-02 | ditto |
| `acceptSuggestion` / `rejectSuggestion` exist in Docs | MEASURED 2026-09-02 | ditto |
| Sheets read side: `spreadsheets.get?commentsViewMode=` → `sheets.commentAnchors` | MEASURED (name recognised, gated) | ditto |
| Docs read side | **MEASURED ABSENT** — six candidate names all rejected | 2026-09-03, above |
| Everything behavioural: does an anchored native comment survive edits? Does it render as a native comment? Does it notify? | **UNTESTABLE** | needs preview enrolment |
| **Do native and Drive comments share an identity?** | **UNTESTABLE** | `comments-apis-2026-09.md` §2.5 — the question that gates the dedup design |
| `PostAuthor.user` as a stable identity | **DOCUMENTED** | Google; unverified |
| Whether preview→GA changes any of the above | **UNKNOWN** | Google says preview typically 3–6 months |

## The gaps that are worth closing, ranked

**1. ~~`mentionedEmailAddresses` and `assigneeEmailAddress` are not in our field mask.~~ CLOSED
on the read side in v0.47.0 (#398)** — both are now named in the mask, modelled on `Comment` and
`Reply`, exposed on both consumer surfaces, and redacted from `__repr__`. **The write side is not
a gap but a limit**: `comments.create` accepts either in the body, returns 200 and stores neither
(MEASURED 2026-09-03), so nothing can assign a comment through the Drive API. What remains UNKNOWN
is whether an *editor* assignment populates the field, and whether resolving clears it — a zoo
fixture (#388). Original text follows.

**1a. The original finding.** MEASURED
2026-09-03: both are accepted in a mask (an invented name and `action` are refused, so these are
real fields), and **`fields=*` omits them**. Zero occurrences in `src/`. So **an assigned comment
— an action item, the single most workflow-relevant kind — is invisible to this library**, and
structured @mentions read as absent. The README already warns about exactly this trap and our own
mask falls into it. *Functional gap, not just a documentation one.*

**2. The editor states nobody has placed.** Cross-paragraph selection, a table-cell comment, a
resolved thread, an @mention, an assignment. Each needs a human in a browser — which is precisely
the argument for the zoo (#388), and the reason the zoo should be built *with* #340.

**3. Notification behaviour is completely unknown.** Does a Drive-API comment email anybody? Both
answers are operationally serious: if it does, an AI review pass could notify a whole team without
intending to; if it does not, humans may never learn the comments exist — which compounds the
"Original content deleted" finding, since they are filtered from the default view as well. Testable
with a second account.

**4. Slides comments have never been probed at all.** We support them through the uniform Drive
axis and have never looked at what an anchor on a shape, a slide or speaker notes actually
contains.

**5. Scale.** Everything measured here is on documents of tens of comments. A consumer has run 90
threads. Pagination, rate limits and the XLSX detour's cost at hundreds are unmeasured.

## What cannot be established, and by what

Worth stating plainly so nobody plans around it:

| blocked on | what it would unlock |
|---|---|
| **Developer Preview enrolment** | every behavioural question about native comments, and the identity/dedup question |
| **A human in a browser** | the unplaced editor states — and this is cheap, it is just not scriptable |
| **A second Google account** | notification behaviour, and cross-user attribution |
| **A Workspace admin** | audit-log attribution (Drive Activity API needs `drive.activity.readonly`; admin reports are a separate surface) |

## How the reference should be built from this

1. Close gap 1 (it is a code change, and small).
2. Build the zoo (#388) **with** the reference, placing the unplaced states as fixtures — that
   converts four UNKNOWNs into MEASURED and gives every claim a citable artefact.
3. Write #340 from this map, carrying the confidence marker on every claim.
4. Leave the native-API chapter explicitly incomplete, marked UNTESTABLE, rather than filling it
   from Google's documentation — which is the failure mode this whole file exists to avoid.
