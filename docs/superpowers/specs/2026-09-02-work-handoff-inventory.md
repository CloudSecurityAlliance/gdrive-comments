# Work-handoff inventory — a dated snapshot of one person's document footprint

**Status:** design, 2026-09-02. Not yet planned or implemented.
**Decided by:** CINO, 2026-09-02 (the four questions the previous draft left open are answered below).

## The problem

Somebody is unavailable — on leave for a month, or handing their work over — and a question
arrives that cannot wait for them. You need to answer *"where is their work, and what is in it?"*
without them.

Concretely: **enumerate every file that person edited or commented on over the last year or two,
and produce something a colleague can work through.** Drive's own UI cannot answer this, and
neither can `files.list` alone — see the three structural limits below.

## Why this is a snapshot and NOT a reversal of the no-caching decision

Accessors re-fetch per call and there is no caching layer; that was settled 2026-08-30, and the
reasoning was specific: *staleness lands exactly in the live multi-reviewer sessions this tool is
for.*

A handoff inventory is the **inverse case**. The person whose footprint you are reconstructing is
not editing, so a frozen view is not a compromise — it is the correct answer, and it should
deliberately *not* drift while a colleague works through it.

Two things keep this from becoming a cache by the back door, and both are load-bearing:

1. **The snapshot is a DELIVERABLE, not an index.** It is a Google Sheet or a CSV — dated, visible,
   shareable, and handed to a person. There is nothing internal to invalidate and no hidden state.
   This is the same shape `export_comments` already ships.
2. **It is never an access path.** Reading any file's *content* still goes through the normal
   authorized call. An id appearing in an inventory grants nothing; the allowlist and Drive's ACLs
   decide, exactly as they do today. This is the rule `CLAUDE.md` already states for a possible
   future corpus: *an index must never become a way to read a file the allowlist would refuse.*

## Security posture — decided

The inventory is built by calls running **as the authorizing user**, so it contains precisely what
that person can already see. No additional control is required or offered. This is the existing
model: capability gating is a ceiling *below* Drive's ACLs, never above them.

## "Touched" means two things, and they stay separate — decided

The CINO's requirement: an **edit** and a **comment** are different signals, each independently
filterable. So the inventory carries them as separate columns with separate timestamps, never
merged into one "last touched".

### Signal 1 — edited

Three sources, in increasing cost and completeness. This matters because the cheap one is
**incomplete in a way that is easy to miss**:

| source | gives | cost | limitation |
|---|---|---|---|
| `lastModifyingUser` | the **most recent** editor only | 1 field per file | if Alice edited and Bob edited after her, Alice is **invisible** |
| `revisions.list` | `lastModifyingUser` per revision | N calls, **opt-in** | complete for retained revisions; Drive prunes |
| **external admin-reports server** | authoritative Drive audit events | not ours | see below |

The middle row is the honest fallback and the top row must not be presented as an answer to *"did
this person ever edit this file"* — only to *"did they edit it last"*.

### Signal 2 — commented

Every piece of this already exists: `comments.list` returns the author per comment, and
`_export.py` already flattens comments and replies to rows. What is missing is only the
**aggregation across files**.

Note the pre-existing identity limit, which applies to both signals.

## Identity — decided: display-name matching, for now

`author.email` is **usually absent even when requested** (probe-verified, `CLAUDE.md` invariant 2).
So "everything by this person" is really "everything by this display name", which is neither unique
nor stable.

Accepted for now, by decision. The inventory must therefore:

- record the **matched display name verbatim** in the artifact, so a reader can see what was
  matched on rather than trusting a name resolved invisibly;
- never silently merge two spellings of a name;
- carry the email **when Drive does supply it**, since that is the stronger key when present.

## The delineation is by PRINCIPAL, not by question — decided

**Refined 2026-09-02.** An earlier draft split the two tools by which *question* each answers.
That was close but wrong, and the correct line is sharper:

> **This server does only what the Drive and Docs APIs support, and it runs AS A USER.
> Administrators use the separate Google audit MCP server.**

So the boundary is *whose authority is being exercised*, not which fact is being retrieved. A
separate read-only **Google Admin Reports** MCP server is under active development; audit-scoped,
domain-wide questions belong there because they need an administrator, and nothing in this library
is domain-wide or ever should be.

Three consequences, and the third is the one the earlier framing missed.

**1. The inventory must accept a list of file ids as an input mode**, not only a Drive query. That
is the seam: an administrator produces the list from the audit server, and this tool is then run —
by them or by a delegate — as a user, against it.

**2. `driveactivity` is deliberately NOT wired in.** A sixth API client for a capability the audit
server supplies better, with the right authority, is work we would then have to keep.

**3. THE INVENTORY MUST REPORT WHAT IT COULD NOT REACH.** This falls straight out of the
principal split and is a hard requirement rather than a nicety. If an administrator hands over 500
file ids and the user running this can see 340, that is **not a failure** — it is the boundary
working exactly as designed. But an artifact that silently lists 340 rows is *lying by omission*:
it reads as a complete footprint, and somebody handing over work would conclude those 160 files do
not exist.

So every id supplied and not reachable appears in the artifact **with the reason** —
`no_access`, `trashed`, `not_found` — never dropped. This is the same asymmetry the labels code
already applies: an unreachable label name is reported as `None` with a reason rather than omitted,
*because reporting a classified document as unclassified is the dangerous direction.* The dangerous
direction here is reporting a partial sweep as a whole one.

## Derived values live in the Sheet — decided

Summaries, keywords and tags go in **columns of the snapshot**, filled in by the caller.

Two consequences worth stating, because an earlier draft proposed otherwise:

- **`description` / `appProperties` writes are OUT of scope.** The idea of writing summaries into
  Drive's `description` — where `fullText` may index them — is set aside. It is not needed for this
  feature and would add a write surface. (The *probe* of whether `fullText` indexes `description`
  remains independently interesting; it is no longer on this critical path.)
- **The library does not summarise.** It is embedded in AI tooling that is already holding a model;
  the moment it calls an LLM itself it acquires an API key, a cost model and a second trust
  boundary, and stops being embeddable. The library provides the columns and the round trip.

## What has to exist first

- **#338 — no drives API, `driveId` unreported.** This is a **correctness dependency, not an
  enhancement**: a person's work often lives in shared drives, and an inventory that cannot say
  which drive a file is in will silently mis-attribute or omit it.
- **`owners`, `createdTime`, `lastModifyingUser` in search results.** Today `_SEARCH_FIELDS` asks
  Drive for `id, name, mimeType, webViewLink, modifiedTime` and nothing else, so an inventory would
  need one extra call per file for facts Drive would have returned for free.
- **`orderBy` beyond three descending keys** — `createdTime` in particular is filterable but not
  sortable today.

## The three structural limits this feature exists because of

Recorded so nobody later proposes "just use a Drive query":

1. **`lastModifyingUser` is readable but not queryable.** Drive's `q` supports `owners`, `writers`,
   `readers` — *membership*, not authorship. There is no last-editor predicate, so "files they
   edited but do not own" is necessarily query-then-filter-locally.
2. **Cross-file comment search does not exist.** `comments.list` is a sub-resource of a file; there
   is no `/comments` collection and no comment predicate in `q`. Absent by construction.
3. **Retention is Drive's, not ours.** Revisions are pruned, and a two-year window may outlive
   what Drive kept. The artifact must say what it could not see rather than imply completeness.

## Non-goals

- **A read-back path.** Decided 2026-09-02: the artifact is **read and analyse, one-directional.**
  There is no bulk upload and none is planned. Named explicitly because `_apply.py` gives the
  *comment* register a read-back — replies and resolutions posted from a filled-in sheet — and the
  obvious next thought is to generalise it. Do not: a comment register is a set of intended actions
  on one file, while a handoff inventory is a description of somebody's work. Nothing in it is an
  instruction, and treating derived columns as one would make an analyst's notes into Drive writes.
- Live or continuously-updated views — the opposite of the point.
- A local corpus, vector index, or embeddings. `TODO.md`'s value ladder is explicit: do not lead
  with step 3. This is step 1.
- Summarisation inside the library.
- Any new authorization path, or any relaxation of the allowlist.
- `driveactivity` integration.

## Open questions

All three of the original questions were answered on 2026-09-02 and are recorded above:
the delineation is by **principal**; revisions cost is the **user's call**, so it is an explicit
opt-in with the cost documented rather than an internal cap; and there is **no read-back path**.

What genuinely remains open:

1. **The handover format between the two servers.** Ids alone are enough to compose, but if the
   audit server can also supply *per-action* detail — edited on this date, commented on that one —
   those become inventory columns this library cannot otherwise fill, and the artifact gets better
   without this tool gaining any authority. Worth settling once the audit server's shape is firm.
2. **Whether `owners` in the artifact should be a display name, an email, or both.** Drive supplies
   both on a permission but the identity caveat above applies to the name half.
