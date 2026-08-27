# Security audit records

One directory per audit. Each records what was examined, by what, under what
conditions, and what was found — including what was looked for and *not* found,
and what was rescored or withdrawn along the way.

The **living** documents are elsewhere and are what to read first:

- [`SECURITY.md`](../../SECURITY.md) — the standing threat framing and the
  division of responsibility between this library and its embedders.
- `THREAT_MODEL.md` at the repository root — the current threat model, once
  adopted. Each audit directory keeps the model as that audit produced it; an
  audit **proposes** the living model by filing an issue rather than editing the
  root file, so parallel audits cannot collide over it. The 2026-08-27 audit's
  model is [here](2026-08-27-defending-code-reference-harness-claude/THREAT_MODEL.md).

Structure, naming, front-matter schema and conventions: [`SCHEMA.md`](SCHEMA.md).

---

## Index

Newest first.

| audit | date | tool | model | interaction | automation | depth | findings | remediation |
|---|---|---|---|---|---|---|---|---|
| [2026-08-27 · defending-code-reference-harness / claude](2026-08-27-defending-code-reference-harness-claude/) | 2026-08-27 | claude-code + anthropics/defending-code-reference-harness | claude-opus-5 | heavy | assisted | adversarial | 35 total · 1 exploitable · 15 hardening | deferred by design · [16 issues prepared](2026-08-27-defending-code-reference-harness-claude/ISSUES.md), file after merge |
| [2026-07-22 · Security audit](../SECURITY-AUDIT-2026-07-22.md) † | 2026-07-22 | claude-code + pip-audit, bandit, defusedxml fuzzing | — | moderate | assisted | standard | 4 (SEC-1…SEC-4) | findings-only |
| [2026-07-22 · Code audit, security-lensed](../AUDIT-2026-07-22.md) † | 2026-07-22 | claude-code | — | moderate | assisted | standard | 29 (#1…#29) | findings-only |

† Predates this directory and still lives in `docs/`, because `SECURITY.md`
references those paths. Migrating them into `2026-07-22-claude-code/` means
updating that reference — filed as an issue rather than done here.

---

## Coverage and staleness

The most useful thing this index can tell you is **which audit covered which
code**. Both 2026-07-22 audits cover **v0.1.0 — 1,308 LOC across 15 modules**.
At v0.28.0 the tree is ~8,500 LOC across 53 modules, and everything implementing
the read-to-act path was written afterwards. That gap was invisible until it was
looked for, which is the reason this table exists.

| module group | first covered by |
|---|---|
| `workspace.py`, `backend.py`, `comments.py`, `documents/`, `auth.py`, `_cellmap.py`, `_errors.py` | 2026-07-22 (both) |
| `mcp/` — server, 34 tools, auth flow, config, resources, schemas | **2026-08-27 · claude** |
| `policy.py`, `allowlist.py`, `permissions.py` | **2026-08-27 · claude** |
| `_apply.py`, `_export.py`, `_environment.py`, `_content.py`, `files.py`, `demo/` | **2026-08-27 · claude** |
| `.github/workflows/`, packaging, secret-scanning config | **2026-08-27 · claude** |
| `tests/` as code | **not yet audited** |
| `experiments/`, `research/` | **not yet audited** |

When adding a record, update this table.

## What an audit may commit

**An audit commits only its own directory.** Nothing else — not `SECURITY.md`,
not the root `THREAT_MODEL.md`, not a README typo it noticed in passing, and not
a source fix however small. Everything outside the audit directory is written up
and **filed as an issue**, including proposed updates to the living threat model.

Two reasons, and the second is the load-bearing one:

1. It keeps the flaw trail and the fix trail separate, so both stay
   independently reviewable.
2. **It lets audits run in parallel.** Several audit agents can work the same
   commit at once — different tools, different scopes — and never touch a shared
   file, so none can conflict with another or with whoever is applying fixes.
   That property disappears the moment an audit is allowed to edit a document
   outside its own directory.

The one exception is this index and `SCHEMA.md`, which every audit needs to
update. That is a known contention point: see the open issue on generating the
index from the per-audit front matter, which removes the last shared file.

## Why fixes are not made in the audit context

Findings are recorded here and remediated elsewhere, deliberately. The audit
directory carries the flaw and the reasoning that produced it; `REMEDIATION.md`
in the same directory carries the fix and the reasoning that produced *that*,
written in a different session. Separating them keeps both independently
reviewable, and stops a fix from quietly reshaping the description of the
problem it was written against.

## Auditing the same commit with a different tool

Encouraged, and the reason the tool name is in the directory name. Two audits of
`95c6afa` by different tools are directly comparable, and the interesting
output is the disagreement: what one found and the other missed, and where they
rated the same finding differently. The `confidence: refuted` entries in
§7 of an existing record are the cheapest thing a second audit can inherit —
they say where not to spend effort.

Worth knowing before running a second audit of this commit: the 2026-08-27
record's §7 clears eleven items with reasons, including openpyxl's automatic
`defusedxml` routing, the non-applicability of the `mcp` SDK's HTTP-transport
advisories to a stdio-only server, and the absence of any SSRF path. Its §6
records three ratings that were withdrawn or changed during the audit, which is
the calibration a comparing reader needs.
