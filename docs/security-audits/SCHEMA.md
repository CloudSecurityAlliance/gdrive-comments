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

## Conventions

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
