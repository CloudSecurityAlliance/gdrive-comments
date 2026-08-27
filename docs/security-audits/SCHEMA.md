# Security audit records — structure and schema

One **directory per audit**, so an audit can carry more than one artifact and so
several audits of the same commit by different tools sit side by side and can be
compared.

## Naming

```
docs/security-audits/YYYY-MM-DD-<harness-or-tool>-<model-or-vendor>/
```

Examples:

```
2026-08-27-defending-code-reference-harness-claude/
2026-08-27-chatgpt-codex/
2026-07-22-claude-code/
```

The tool goes in the directory name because the most useful comparison between
two audits is usually *what found this and what missed it*. Suffix `-01`, `-02`
if one tool runs twice in a day.

## Contents

| file | written by | purpose |
|---|---|---|
| `README.md` | the auditing context | The record: YAML front matter, summary, scope, method, corrections made during the audit, investigated-and-cleared items, handoff. **What the audit was and how much to trust it.** |
| `FINDINGS.md` | the auditing context | Per-finding detail sufficient to remediate without re-deriving the analysis. **What the remediation context reads.** |
| `THREAT_MODEL.md` | the auditing context | Frozen snapshot of the model as this audit produced it. The living model is at the repository root and continues to change; this one does not. |
| `REMEDIATION.md` | the **remediation** context | What was fixed, what was deliberately not fixed, and the reasoning behind both. Written in a different session from the audit, on purpose. |
| `ISSUES.md` | the auditing context | Issues to file once the audit branch merges: title, labels and a copy-pasteable body per issue, each linking back to `FINDINGS.md`. Prepared pre-merge because the post-merge permalinks are predictable. Optional, but it is what turns a report into tracked work. |

Optional, where they exist: raw scanner output, transcripts, reproduction
scripts. Keep them; a finding whose evidence has been discarded is hard to
re-check.

Section numbering runs continuously across `README.md` and `FINDINGS.md`
(§1–3 and §6–8 in the former, §4–5 in the latter), so cross-references resolve
regardless of which file a reader has open.

---

## Required YAML front matter (`README.md`)

```yaml
---
audit_id: 2026-08-27-01                  # unique, sortable
date_started: 2026-08-27T14:50Z          # ISO 8601, UTC
date_completed: 2026-08-27T16:55Z
target: csa-google-workspace
target_commit: 95c6afa                   # mandatory — line numbers drift
target_version: 0.28.0

tool: claude-code                        # see enum below
tool_harness: anthropics/defending-code-reference-harness
tool_workflow: "/threat-model bootstrap-then-interview"
model: claude-opus-5
subagents: "7 parallel research agents, same model"

human_interaction: heavy                 # none | light | moderate | heavy
automation: assisted                     # manual | assisted | mostly-automated | fully-automated
review_depth: adversarial                # skim | standard | adversarial

scope_covered:   ["..."]
scope_excluded:  ["..."]                 # an audit that does not state its blind spots cannot be trusted later
inputs:          ["..."]

findings_total: 35
findings_exploitable: 1
findings_hardening: 15
findings_informational: 19

remediation_status: deferred-by-design   # not-started | deferred-by-design | in-progress | complete
remediation_context: "separate session"
remediation_record: null                 # path to REMEDIATION.md once written
supersedes: null                         # audit_id this replaces, or null
---
```

## Enums

**`tool`** — reuse existing values so records stay comparable: `claude-code`,
`chatgpt`, `codex`, `codeql`, `bandit`, `pip-audit`, `trufflehog`, `gitleaks`,
`semgrep`, `human`, or `<vendor>-<product>`.

**`human_interaction`** — how much a person *shaped* the audit, not how much
they read afterwards.

| value | means |
|---|---|
| `none` | fully unattended; nobody saw it until it finished |
| `light` | a person set scope and read the output |
| `moderate` | a person steered mid-run, answered questions, or redirected |
| `heavy` | a person argued with findings, corrected framings, and changed ratings |

**`automation`** — how much the tool did unaided: `manual` · `assisted` ·
`mostly-automated` · `fully-automated` (scanner output, unreviewed).

**`review_depth`** — `skim` (pattern-matching only) · `standard` (read the
relevant code) · `adversarial` (actively tried to disprove findings, verified
mechanisms empirically where possible).

**Per-finding `confidence`** — every finding carries one:

| value | means |
|---|---|
| `confirmed-empirically` | reproduced or demonstrated by running something |
| `confirmed-by-read` | the code plainly says so; cited by `file:line` |
| `plausible` | a reasoned inference not yet verified |
| `refuted` | investigated and found not to hold — **keep these**, they save the next audit the work |

---

---

## Running an audit safely in a shared repository

**An audit agent must never run `git checkout`, `git switch`, or `git checkout -b`
in a working tree it does not exclusively own.** If another agent or person may be
working in that tree, take one of these two paths instead.

**Preferred — an isolated worktree.** One command, and the shared tree is never
touched:

```bash
git worktree add -b docs/security-audit-YYYY-MM-DD /tmp/audit-wt origin/main
# write, commit and push from /tmp/audit-wt
git worktree remove /tmp/audit-wt
```

**Alternative — read-only audit.** Analyse in place without any git write, and
hand the audit directory to a human to commit.

To push a single existing commit somewhere safe without switching branches:

```bash
git push origin <sha>:refs/heads/<branch-name>
```

### Why this rule exists

It was learned the hard way during audit `2026-08-27-01`. That audit called
`git checkout -b` in a working tree another agent was actively using. The other
agent's next commit landed on the audit's branch — 259 lines across four files,
on a branch named for someone else's work, unpushed and reachable from that one
ref. Nothing was lost, but only because it was noticed; deleting that branch
would have destroyed it.

The failure is the same class as the two flaws that audit found in the code: **a
premise that was true when established and stopped being true.** `HEAD` pointed
at the audit's branch when the audit created it, and the audit kept assuming it
still did. Git branch state is process-global for a working tree, so it is
exactly the kind of shared mutable thing the rest of this workflow is designed to
avoid — which is also why an audit commits only its own directory, and why the
index should be generated rather than edited.

### Practical consequences for parallel audits

Several audit agents on one commit is the point of this structure, and it works
only if none of them mutates shared state. With the rule above:

| shared thing | contention |
|---|---|
| the audit's own directory | none — one owner |
| source files | none — audits never write them |
| the living `THREAT_MODEL.md` | none — proposed by issue, never edited |
| git branch / `HEAD` | **none, if each agent uses its own worktree** |
| this index and `SCHEMA.md` | the last one — generate the index from front matter |

Record `HEAD` at both the start and the end of the audit
(`target_commit` and `main_at_record_commit`) regardless. In a repository with
concurrent work the tree will move underneath the audit, and a record that does
not say so will be read as more current than it is.

## Conventions

- **Never switch branches in a working tree you do not exclusively own.** Use
  `git worktree`, or audit read-only and hand the directory over. See the section
  above for why.
- **Findings are not fixed in the context that found them.** The flaw record and
  its reasoning live in `README.md` / `FINDINGS.md`; the fix and its reasoning
  live in `REMEDIATION.md`, written by a different session. Separating them keeps
  both independently reviewable, and stops a fix from quietly reshaping the
  description of the problem it was written against.
- **Records are point-in-time and are not edited after completion**, except to
  update `remediation_*` fields and to add a superseding pointer.
- **Cite `file:line`, always** — which is why `target_commit` is mandatory.
- **Record refuted findings.** A documented dead end is worth as much as a
  finding, and is the main thing that makes a second audit cheaper than the
  first.
- **State severity reasoning, not just a label.** Where two audits disagree on a
  rating, the reasoning is what lets a reader decide; the label alone does not.
- **Update the index** in [`README.md`](README.md), including its
  coverage-by-module table. An audit whose coverage is not recorded there will
  later be mistaken for broader than it was.
