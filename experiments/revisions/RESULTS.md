# A Google Doc exposes TWO revisions through the Drive API. That is the whole finding.

**Measured 2026-09-03** against live Google. Bears on
[#389](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/389) (read a past
revision) and on the versioning/recovery item in `TODO.md`.

Run: `probe.py` for the mechanism questions, `long_baseline.py --gap 300 --edits 5` for durability.

## The verdict, first

```
VERDICT: 2 revision(s) survive 5 edits spaced 300s apart.

  edit 1: revisions=['1', '3']  (disappeared since: none)
  edit 2: revisions=['1', '4']  (disappeared since: ['3'])
  edit 3: revisions=['1', '5']  (disappeared since: ['3', '4'])
  edit 4: revisions=['1', '6']  (disappeared since: ['3', '4', '5'])
  edit 5: revisions=['1', '7']  (disappeared since: ['3', '4', '5', '6'])
```

Every intermediate revision **appeared and then vanished**. What survives is revision `1` — the
file's creation — and the current head. Nothing else.

**Five minutes between edits was chosen deliberately** to rule out the obvious objection. An
earlier run with 4–6 second gaps saw the same collapse, which coalescing-within-a-window would
explain. It does not explain this one.

So for an actively-edited Google Doc, ***"read a past revision" means "read the state the file was
created in."*** That is a very different capability from the one the phrase suggests, and any tool
description has to say so.

*(Scope: one document, one account, edits by a single author, gaps up to five minutes. Whether a
multi-author document, or gaps of hours, or a Workspace plan with different retention behaves
differently is NOT established here. What is established is that "edits far apart get their own
durable revisions" is false at this timescale.)*

## `keepForever` is accepted and silently discarded

The field that would have made this survivable does nothing on a Google Doc:

```
revisions.update(fileId, revisionId, {"keepForever": True})   ->  200 OK
revisions.get(fileId, revisionId)                             ->  {"id": "3", "modifiedTime": …}
                                                                  keepForever ABSENT
next edit                                                     ->  revision 3 pruned anyway
```

Google's reference says the field is *"only applicable to files with binary content in Drive"* — so
the **semantics are documented and the API is wrong to return success.** This is the same shape as
the anchor trap in `google-drive-comments-reference.md` §7: a write that reports success, stores
nothing, and gives no indication.

**Consequence: you cannot pin the revision you might later want.** Any design that says "snapshot
the good state, then experiment" cannot rest on Drive's revision history.

## There is no revert method

`revisions` exposes exactly `list`, `get`, `get_media`, `update`, `delete`. A reset must be
**read-then-write**.

## But read-then-write works, with real fidelity

Export the good revision as `.docx`, then `files.update` with it as media:

| | |
|---|---|
| bold runs before the damaging edit | `['OLD']` |
| after the damaging edit | `[]` |
| **after restore** | **`['OLD']`** |
| paragraph styles after restore | `['HEADING_1', 'NORMAL_TEXT', …]` |
| the damaging text after restore | **gone** |
| revisions after restore | `['1', '4', '5']` — a **new** revision |

Two properties worth keeping: it is **non-destructive** (it rolls forward to a copy of the past, so
the bad state stays recoverable), and it reuses the upload-and-convert route `_export.py` already
depends on.

Each revision offers **ten** export formats: `docx`, `markdown`, `x-markdown`, `html`, `pdf`,
`rtf`, `odt`, `epub+zip`, `plain`, `zip`.

**"Preserved these three things once" is not "lossless."** Bold, headings and text survived one
round trip. The gaps need enumerating before anyone is told this restores a document.

## Attribution cannot be recovered from revisions

`lastModifyingUser` is **singular per revision**, and revisions coalesce. So Bob's edits and
Alice's can share one revision with one name on it, and diffing two snapshots recovers *what*
changed, never *who* changed which part.

**The missing half is the Drive Activity API v2** — it exists, `activity.query` is present, and it
returns **403 insufficient scopes** for us because we do not request `drive.activity.readonly`. It
carries actors and action kinds; it carries no content deltas. So the shape of any *"undo what Bob
did"* feature is **activity for who, snapshots for what**, and adding that scope is a decision
rather than a detail.

## What this means for the request

- **`list_revisions` is honest but thin.** It will usually return two rows. Reporting that plainly
  beats returning two rows that look like a history.
- **A revision-scoped read is worth having** — the creation state is genuinely useful, and it is
  what recovered a document here once already.
- **Reset can only reach the creation state**, not "the state before the bad edit", unless the bad
  edit happened to be the first thing after creation.
- **Selective reapply cannot be built on this at all.** There is nothing to reapply *from*.

Which points at the same conclusion from a different direction: if the baseline matters, **we have
to take the snapshot ourselves.** Drive will not keep one for us.
