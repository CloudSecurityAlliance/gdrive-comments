# Correctness and release-readiness reports

**RR-007.** Security audits have a directory, a generated index and a checked coverage table
(`docs/security-audits/`, `scripts/gen_audit_index.py`). Correctness reports had none, so the only
way to find one was to know the filename — and the whole point of the pattern is that **one AI
writes a public report and a later AI remediation worker consumes it.**

This directory is the entry point. It is deliberately *lighter* than the security-audit machinery:
these reports do not amend `THREAT_MODEL.md`, so they need no frozen snapshot and no coverage
table. They need to be **discoverable** and their finding ids need to be **stable**.

## The reports

| report | target | verdict | findings |
|---|---|---|---|
| [`2026-09-01-release-readiness-02.md`](./2026-09-01-release-readiness-02.md) | v0.37.0 @ `5cf8d4e` | not-ready-for-1.0.0 | 6 open at time of writing (1×P0, 3×P1, 2×P2); RR-001 and RR-002 resolved from pass 01 |

Pass 01 was not committed; pass 02 records what it found and what had been resolved, which is
enough to follow the thread.

## Conventions

- **Filename:** `YYYY-MM-DD-<slug>-NN.md`, matching the `report_id` in the front matter, so the
  file sorts chronologically and the id in a commit message resolves to a file.
- **Front matter** carries `report_id`, `target_version`, `target_commit`, `release_verdict` and
  the finding counts. A consumer can triage without reading the body.
- **Finding ids are `RR-NNN`, stable and never reused.** A later report referring to `RR-003`
  means the same finding, whether to close it or to note it recurred.
- **Status lives in the newest report, not in the old one.** A report is a statement about a
  commit and is never edited afterwards; a later pass carries a "Resolved Since Prior Pass"
  section. That mirrors how `THREAT_MODEL.md` §0 supersedes the frozen audit text.

## Where remediation is recorded

In the **commit messages and PR bodies** that cite the finding id, not here. `git log --grep=RR-003`
is the trail, which keeps the report immutable and the fix history reviewable independently — the
same separation the security audits use for `FINDINGS.md` and `REMEDIATION.md`.

## What a report is not

Not a security audit. `security_scope: deferred` in the front matter is load-bearing: these passes
check the public correctness contract and explicitly do not do exploit testing, adversarial
prompt-injection testing, or dependency triage. The follow-on security audit is a separate
artifact with its own directory and its own rules.
