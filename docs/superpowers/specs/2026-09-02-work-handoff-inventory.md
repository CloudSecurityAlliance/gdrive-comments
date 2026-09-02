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
| `revisions.list` | `lastModifyingUser` per revision | N calls | complete for retained revisions; Drive prunes |
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

## The composability seam — this library does not answer "what did they touch"

**Context, 2026-09-02:** a **separate MCP server for the Google Admin Reports API** (read-only) is
under active development. It will supply the authoritative list of a user's documents and activity
domain-wide. That is a strictly better source than anything this library can reach, because it does
not require the person doing the sweep to have access to each file first.

So the division of labour is:

> **The admin-reports server answers *what did they touch*. This library answers *what is in it,
> and who can see it*.**

The design consequence is concrete and is the most important line in this spec:

**The inventory must accept a list of file ids as an input mode, not only a Drive query.** That is
the seam through which the other server drives this one. Without it, the two tools cannot compose
and this library's enumeration becomes a dead end the moment the better source exists.

It also means **`driveactivity` is deliberately NOT wired into this library.** Adding a sixth API
client for a capability another server will supply better would be work we then have to keep.

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

- Live or continuously-updated views — the opposite of the point.
- A local corpus, vector index, or embeddings. `TODO.md`'s value ladder is explicit: do not lead
  with step 3. This is step 1.
- Summarisation inside the library.
- Any new authorization path, or any relaxation of the allowlist.
- `driveactivity` integration.

## Open questions

1. **Where exactly does the boundary with the admin-reports server fall** once it exists — does it
   hand over file ids only, or ids plus per-file activity that becomes inventory columns?
2. **Revisions cost.** One `revisions.list` per file is the only in-library way to answer "did they
   ever edit this". At what inventory size does that stop being acceptable, and is it opt-in?
3. **Does the artifact need a read-back path**, as `_apply.py` gives the comment register? Plausibly
   not — a handoff inventory is read to be acted on by a human, not posted back to Drive.
