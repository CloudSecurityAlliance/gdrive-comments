---
audit_id: 2026-08-27-01
date_started: 2026-08-27T14:50Z
date_completed: 2026-08-27T16:55Z
target: csa-google-workspace
target_commit: 95c6afa                   # tree state the findings were derived from
main_at_record_commit: ed0ce2d           # the tree moved during the audit — see §2
commits_landed_during_audit: 4           # 33bfa19, f6a8813, 8b07645, ed0ce2d
target_version: 0.28.0

tool: claude-code
tool_harness: anthropics/defending-code-reference-harness
tool_workflow: "/threat-model bootstrap-then-interview, then manual adversarial review"
model: claude-opus-5
subagents: "7 parallel research agents, same model (docs reader, surface mapper, infra reader, asset finder, history miner, advisory fetcher, prior-audit parser)"

human_interaction: heavy
automation: assisted
review_depth: adversarial

scope_covered:
  - "src/csa_google_workspace/ — all 53 modules, static read"
  - "mcp/ server, 34 tool registrations, tool annotations, INSTRUCTIONS prose"
  - "policy.py, allowlist.py, permissions.py — capability and allowlist enforcement"
  - "_apply.py, _export.py — local filesystem read/write paths"
  - "auth.py, mcp/_auth_flow.py, mcp/_login.py — OAuth acquisition and token custody"
  - ".github/workflows/ — tests.yml, release.yml, dependabot-auto-merge.yml"
  - "pyproject.toml, .gitignore, .gitleaks.toml — packaging and secret hygiene"
  - "git history — 252 commits, all refs, security-keyword mined"
  - "GitHub Advisory DB — repo advisories + 12 declared dependencies, via gh"
scope_excluded:
  - "No target code was executed. One exception, isolated: openpyxl cell-typing behaviour was reproduced standalone in a scratch directory (see T35); no project code ran."
  - "No live Google Workspace endpoint was contacted. No token was read."
  - "No dynamic testing, fuzzing, or running-agent prompt-injection exercise."
  - "tests/ read for coverage claims only, not audited as code."
  - "OSV.dev, NVD and the PyPA advisory database were NOT queried — GitHub Advisory DB only. Anything GHSA-unlisted is outside what was checked."
  - "experiments/ and research/ not audited."
  - "Client-side behaviour of Claude Desktop / Claude Code (approval prompts, tool enablement) not tested — see Handoff."
inputs:
  - "SECURITY.md (design doc)"
  - "docs/SECURITY-AUDIT-2026-07-22.md (prior audit, --vulns input)"
  - "docs/AUDIT-2026-07-22.md (prior audit)"
  - "CHANGELOG.md, PROVENANCE.md, DECISIONS.md, TODO.md, API-STABILITY.md, INTERFACE-RESOURCES.md"
  - "MCP specification tool-annotation semantics; Microsoft spotlighting research; arXiv 2506.08837 design patterns"

findings_total: 35
findings_exploitable: 1
findings_hardening: 15
findings_informational: 19

remediation_status: in-progress           # T32 fixed on branch fix/refuse-a-huge-download-before-fetching, not yet on main
remediation_context: "separate session — see Handoff"
supersedes: null

# --- index metadata, added 2026-08-28 for #198 -------------------------------------------
# docs/security-audits/README.md is now GENERATED from these fields, so the index is no longer
# a shared file every audit has to edit. Only metadata was added here: no finding, rating,
# scope statement or wording of this record was changed.
#
# `modules_covered` restates, in machine-readable form, the coverage `scope_covered` above
# already describes in prose. It is ENUMERATED rather than globbed, and the reason is concrete:
# this audit's target commit is 95c6afa, and a glob like `.github/workflows/*.yml` would claim
# `controls.yml` - written 2026-08-28, which this audit never saw. A glob claims the future, and
# claiming coverage of unaudited code is the exact failure #198 exists to prevent.
#
# Produced from the audited tree itself, so it cannot overstate:
#
#   git ls-tree -r 95c6afa --name-only | grep -E '^(src/.*\.py|\.github/workflows/.*\.yml|...)$'
#
# `tests/`, `experiments/`, `research/` and `scripts/` are absent, matching `scope_excluded`:
# tests were read for coverage claims only, not audited as code. The generated table therefore
# reports them as not yet audited, which is true and was previously easy to overlook.
index_label: "2026-08-27 · defending-code-reference-harness / claude"
modules_covered:
  - ".github/workflows/dependabot-auto-merge.yml"
  - ".github/workflows/release.yml"
  - ".github/workflows/tests.yml"
  - ".gitignore"
  - ".gitleaks.toml"
  - "pyproject.toml"
  - "src/csa_google_workspace/__init__.py"
  - "src/csa_google_workspace/_apply.py"
  - "src/csa_google_workspace/_cellmap.py"
  - "src/csa_google_workspace/_content.py"
  - "src/csa_google_workspace/_environment.py"
  - "src/csa_google_workspace/_errors.py"
  - "src/csa_google_workspace/_export.py"
  - "src/csa_google_workspace/_formats.py"
  - "src/csa_google_workspace/_services.py"
  - "src/csa_google_workspace/allowlist.py"
  - "src/csa_google_workspace/auth.py"
  - "src/csa_google_workspace/backend.py"
  - "src/csa_google_workspace/base.py"
  - "src/csa_google_workspace/comments.py"
  - "src/csa_google_workspace/demo/__init__.py"
  - "src/csa_google_workspace/demo/_cli.py"
  - "src/csa_google_workspace/demo/_feedback.py"
  - "src/csa_google_workspace/demo/_plan.py"
  - "src/csa_google_workspace/demo/_runner.py"
  - "src/csa_google_workspace/documents/__init__.py"
  - "src/csa_google_workspace/documents/doc.py"
  - "src/csa_google_workspace/documents/sheet.py"
  - "src/csa_google_workspace/documents/slides.py"
  - "src/csa_google_workspace/exceptions.py"
  - "src/csa_google_workspace/files.py"
  - "src/csa_google_workspace/mcp/__init__.py"
  - "src/csa_google_workspace/mcp/__main__.py"
  - "src/csa_google_workspace/mcp/_auth_flow.py"
  - "src/csa_google_workspace/mcp/_capabilities.py"
  - "src/csa_google_workspace/mcp/_config.py"
  - "src/csa_google_workspace/mcp/_desktop.py"
  - "src/csa_google_workspace/mcp/_inline.py"
  - "src/csa_google_workspace/mcp/_login.py"
  - "src/csa_google_workspace/mcp/_resources.py"
  - "src/csa_google_workspace/mcp/_schemas.py"
  - "src/csa_google_workspace/mcp/_success_page.py"
  - "src/csa_google_workspace/mcp/_tools/__init__.py"
  - "src/csa_google_workspace/mcp/_tools/_base.py"
  - "src/csa_google_workspace/mcp/_tools/auth.py"
  - "src/csa_google_workspace/mcp/_tools/comments.py"
  - "src/csa_google_workspace/mcp/_tools/config.py"
  - "src/csa_google_workspace/mcp/_tools/content.py"
  - "src/csa_google_workspace/mcp/_tools/content_write.py"
  - "src/csa_google_workspace/mcp/_tools/demo.py"
  - "src/csa_google_workspace/mcp/_tools/feedback.py"
  - "src/csa_google_workspace/mcp/_tools/files.py"
  - "src/csa_google_workspace/mcp/_tools/suggestions.py"
  - "src/csa_google_workspace/mcp/cli.py"
  - "src/csa_google_workspace/mcp/server.py"
  - "src/csa_google_workspace/permissions.py"
  - "src/csa_google_workspace/policy.py"
  - "src/csa_google_workspace/suggestions.py"
  - "src/csa_google_workspace/workspace.py"
findings_summary: "35 total · 1 exploitable · 15 hardening"
remediation_summary: "in progress — see [REMEDIATION.md](2026-08-27-defending-code-reference-harness-claude/REMEDIATION.md)"
---

# Threat model and code review, 2026-08-27

## 1. Summary

This audit produced a threat model — [`THREAT_MODEL.md`](THREAT_MODEL.md) in this
directory, 35 threats across 19 entry points and reviewed the code that both 2026-07-22 audits predate —
which is most of the security-relevant surface. It was run interactively with
heavy owner participation: four separate framings were corrected by the
maintainer mid-audit and three of this auditor's own ratings were withdrawn or
changed as a result. Those corrections are recorded in §6 rather than quietly
absorbed, because they are what a later reader needs in order to calibrate the
rest.

**One finding is a genuinely exploitable security flaw** (T15: server-side
formula evaluation on the Sheets write path, giving out-of-band data
exfiltration with no human in the loop). **One is new and previously
unexamined** (T35: the `.xlsx` export path writes untrusted content as live
formulas — the same class the CSV path was yanked for in 0.24.0, in the sibling
path the fix did not reach). The remaining findings are hardening or design
decisions to document.

Both flaws are being recorded rather than minimised, and both are being fixed
rather than accepted, which is the posture this project is maintained under:
defaults are chosen to be safe, the conservative reading wins where a finding is
ambiguous, and findings are disclosed. That is a design commitment with
observable consequences in the tree — fail-closed allowlists, irreversible
operations off by default, no permanent delete anywhere, a typo'd profile as a
hard error — and it is the standard the two flaws below are measured against
rather than an exemption from it.

The structural conclusion is narrower and more useful than the finding count.
Both genuine flaws are cases where **a safe default exists in the library and
stops applying at the MCP boundary**: `RAW` in every library Sheets write
declaration (eight of them, across the `Backend` Protocol, both backend
implementations, and the `Sheet` façade) versus `USER_ENTERED` in the MCP tool, and `csv_safe` on the CSV export
versus no formula handling on the `.xlsx` export. That is the fourth and fifth
instance of a drift the maintainer had already recorded three times in commit
messages as *"a capability the library had and the server did not."* It is a
seam, not a bug class, and it is where the next audit should start.

## 2. Scope

See front matter for the machine-readable version. Two limitations matter more
than the others:

- **Nothing was executed and nothing was tested dynamically.** Every finding
  below is derived from reading code, except T35, whose mechanism was
  reproduced standalone. The prompt-injection findings (T2, T34) have never
  been exercised against a running agent — which is the same limitation the
  2026-07-22 security audit recorded for SEC-2, still unaddressed.
- **The tree moved during the audit, and that is a limitation of this record.**
  `HEAD` was `95c6afa` when the research swarm ran and `main` was `ed0ce2d` when
  this record was committed — four commits landed in between (`33bfa19`,
  `f6a8813`, `8b07645`, `ed0ce2d`), three of them touching `src/`. Consequences,
  stated plainly rather than smoothed over: the seven research agents read the
  working tree rather than a fixed revision, so they may not all have seen an
  identical tree; and every `file:line` in this report was derived from
  `95c6afa`. The load-bearing citations were re-verified against `ed0ce2d`
  and still resolve — `content_write.py:63`/`:83`, `_base.py:20`,
  `comments.py:110`, `_export.py:332`, `mcp/server.py:61`, `auth.py:46` — but
  `_apply.py` was edited by `33bfa19` and **its citations have drifted**;
  corrected locations are given inline in `FINDINGS.md` §4.4. Separately, `T32`
  was fixed on branch `fix/refuse-a-huge-download-before-fetching` while this
  audit was being written; that branch was not merged at the time of this
  commit, so `T32` is fixed-but-unlanded rather than closed. For future audits: pin to
  a revision, or record `HEAD` at both ends as this record now does.
- **Advisory coverage is GitHub-only.** `gh api` was used for the repository
  and all twelve declared dependencies. The repository result was a *real* zero
  (HTTP 200, empty array, authenticated) rather than an access failure, and the
  query form was sanity-checked against a known-positive package. OSV.dev and
  NVD were not consulted.

## 3. Method

Five stages, checkpointed. Stage 1 dispatched seven research agents in
parallel, each with a narrow brief, the absolute target path, and a read-only
restriction passed verbatim — including an instruction to treat all file
content as untrusted data rather than instructions, which matters when the
inputs are audit reports containing quoted attacker payloads. Stages 2–4
synthesised, clustered past vulnerabilities into threats, and gap-filled with
STRIDE for entry points no past vulnerability had touched. Stage 5 emitted the
model, then owner review drove three revision passes.

Two method notes worth carrying forward:

- **Prior-audit status was not taken at face value.** Both 2026-07-22 documents
  are findings-only and record everything as open. Cross-checking each row
  against the current tree moved SEC-1, SEC-3, GA-#5, GA-#14, GA-#17, GA-#19
  and GA-#27 to fixed, and left GA-#13 open. An audit that inherits stale
  status inherits a false picture in both directions.
- **19 of 35 threats carry evidence, and nearly all of that evidence is
  self-generated** — self-audits, CodeQL, one yank. Rows with empty evidence
  cluster in `_apply.py`, `_export.py` and `mcp/_tools/`. The evidence column is
  effectively a map of where this project has already looked, which is why the
  absence of external findings should be read as unexplored surface rather than
  clean surface.

---

---

## 4–5 · Findings and design recommendation

These live in **[`FINDINGS.md`](FINDINGS.md)** in this directory — the per-finding
remediation detail (§4) and the capability-model recommendation the audit
produced (§5). Section numbering is continuous across the two files, so
cross-references such as §4.1 or §6.3 resolve regardless of which file you are
reading.

`FINDINGS.md` is the document the remediation context should read. This file is
the record of what the audit was, how it was produced, and how much to trust it.


## 6. Corrections made during the audit

Recorded because they are how a later reader calibrates the rest. Four framings
were corrected by the maintainer; three ratings by this auditor were wrong.

### 6.1 T1 — over-rated, and structurally mis-modelled

Originally `critical × almost_certain`, ranked first, described as the read
ceiling being "documented away." The maintainer's correction: full-Drive read
access is the product, not a defect; the default is fail-closed and `*` is an
explicit typed choice that logs a warning; Google-side ACLs bound the token
independently; the wide posture is a known-operator internal deployment; and
1.0.0 moves the value to an install-time choice. All correct and all
under-credited. **Rescored to `high × likely`, `risk_accepted`, and reframed as
the blast-radius modifier on T2** rather than an independent threat — it was a
double-count, which is what made the ordering read as alarmist.

### 6.2 T7 mis-characterised as exfiltration; T23 over-rated

**T7** was described as *"exfiltration of Drive content to an uncontrolled local
path"* and rated critical. That is wrong: writing to the operator's own disk
does not move data to an attacker, who cannot read it back. What T7 actually is:
a constrained file-*create* primitive plus a genuine trust-model defect in the
annotation. Real, worth fixing, not critical.

**T23** was described as an unhardened XML parser. openpyxl auto-detects
`defusedxml` (env `OPENPYXL_DEFUSEDXML`, default `True`) and `defusedxml` is a
hard dependency of this project, so entity expansion and XXE on that path are
already covered — by accident, but covered. Reduced to decompression bounds
only.

### 6.3 Severity classification: the maintainer's evaluator test

The maintainer argued that formula-injection consequences evaluated by a human
opening a file are the opener's responsibility, not the generator's, and
therefore hardening rather than a flaw. Accepted, and applied as a general
test — **who evaluates the payload?**

| site | evaluator | human in the loop | classification |
|---|---|---|---|
| CSV export | Excel on open | yes, with a DDE warning | hardening (already fixed) |
| XLSX export (T35) | Excel on open | yes | hardening |
| Sheets `USER_ENTERED` (T15) | Google's servers | **no** | flaw |

The same test classified **T3 as hardening**: it requires a compromised
dependency, a precondition the maintainer does not control. Its amplification
property is recorded so the priority does not fall to zero.

This is a good test and it is now the classification rule for this report.
Where it produced a different answer from this auditor's initial rating, the
test won.

### 6.4 Withdrawn recommendation

An earlier draft recommended a recipient allowlist on `share_file`. Withdrawn:
Drive supports target-audience and domain-restricted sharing natively, and
reimplementing it in the server would duplicate it worse. The server's
contribution is that `file.share` is a separate, default-off capability at all;
enforcement of *who* belongs at the Drive layer.

---

## 7. Investigated and cleared

Kept so the next audit does not repeat the work.

| checked | result |
|---|---|
| XXE / billion-laughs on `_apply.py`'s openpyxl path | **Cleared.** openpyxl routes through `defusedxml` when installed (`OPENPYXL_DEFUSEDXML` defaults `True`); it is a hard dependency here. Decompression bounds remain (T23). |
| `+`, `-`, `@` prefixes in the XLSX export | **Cleared.** openpyxl types these `'s'`; only `=` becomes a formula. Verified empirically on 3.1.5. |
| `mcp` SDK advisories — HTTP transport principal confusion (CVE-2026-52869), cross-client task access (CVE-2026-52870), DNS rebinding (CVE-2025-66416), WebSocket origin (CVE-2026-59950), FastMCP DoS (CVE-2025-53365/53366) | **Not applicable, twice over.** All below the declared `mcp>=2.1` floor, *and* the server constructs no HTTP, SSE or WebSocket transport — `mcp/cli.py:170` is `run(transport="stdio")`. |
| SSRF | **Cleared.** All egress goes through `googleapiclient` to fixed Google endpoints. A 403's `activation_url` is interpolated into an error string and never fetched. No URL from document content is ever requested. |
| Repository security advisories | **Real zero.** `gh api /repos/CloudSecurityAlliance/csa-google-workspace/security-advisories` → HTTP 200, `[]`, authenticated. Not an access failure. |
| Google API client libraries (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`), `defusedxml` | **Zero advisories** in the GitHub Advisory DB, all queried successfully. |
| SQL / command / LDAP / XPath / template injection | **Not present.** No database, ORM or template engine on any data path. The one subprocess call (`demo/_feedback.py` invoking `gh issue create`) uses an absolute path from `shutil.which`, a list argv, and no shell. |
| Unsafe deserialization (`pickle`, `marshal`, `yaml.load`), `eval`/`exec` on external data | **Not present.** |
| `pull_request_target` in any workflow | **Absent.** `tests.yml` runs fork-PR code but is correctly declawed: `permissions: contents: read`, no secrets, no deploy step. |
| Memory-safety classes | **Not applicable.** Pure Python, no unsafe blocks, no FFI, no C extensions authored here. |
| Allowlist host validation | **Currently correct.** Exact equality against four Google hostnames, host checked *before* id extraction, enforcement by extracted file id. Three past defects here (`bab2a8f`, `35c74d8`, `62b6bbf`) are all fixed and covered by `tests/test_policy_matrix.py`. |

---

## 8. Handoff

**For the remediation context.** This report is intended to be sufficient to
fix without re-deriving the analysis. [`ISSUES.md`](ISSUES.md) carries the
issue set to file once this lands on `main` — sixteen issues plus a tracking
issue, each with labels and a copy-pasteable body, ordered P1 through P4. Every location is `file:line` at
`95c6afa`; re-verify line numbers against the tree you are working on.

Suggested order, by (severity × containment):

1. **T15** — two-line default change, closes the one exploitable flaw.
2. **T35** — the sibling the yank fix missed. Verify the chosen text-forcing
   mechanism empirically against openpyxl 3.1.5; do not trust documentation for
   inference behaviour.
3. **T7** — annotation correction. Whichever of the two fixes is chosen,
   `mcp/server.py:61` must change with it.
4. **T34** — escape newlines in comment and reply content. Preserve the
   header-without-footer design.
5. **T9** — the load-bearing open item from 2026-07-22.
6. **T3** — the job split. Independent of everything else and of the release
   schedule.
7. The remainder of §4.4 and §4.5 in any order.

**Decisions this report deliberately does not make:**

- Whether to build the `content.active` capability (§5.2) or fix T15 and T35 as
  point changes. §5 argues for the capability; the trade-off is scope against a
  cleaner premise, and it is a product decision.
- Whether T15 warrants disclosure beyond a release note. The precedent is
  recorded rather than applied, but it is a close precedent: 0.24.0 was yanked
  within one hour fifty minutes for the CSV variant of this same class, and that
  variant required a human to open a file and click through Excel's warning.
  T15 requires neither a human nor a warning — Google evaluates the formula
  server-side and the data leaves before anyone could inspect anything. Two
  considerations pull the same way. The project's stated posture is that where a
  finding is ambiguous between a defect and an acceptable trade-off, the
  conservative reading wins; and this is maintained by the Cloud Security
  Alliance, where the cost of under-disclosing is measured in more than one
  project's credibility. Neither consideration decides it — the affected version
  range, whether any deployment has `content.write` enabled against a sheet
  reachable from untrusted comments, and whether a fix can ship before a
  disclosure would all bear on it, and none of those is an audit judgement.
  What this report does assert is that the *mechanism* is more severe than the
  one that triggered the yank, and that the difference is not in the attacker's
  favour.
- The final naming of any new capability.

**What could not be determined here, and gates two ratings:**

- **Which MCP clients are in use, and what each does with `readOnlyHint` in
  non-strict approval modes.** The spec maps it to "skip the confirmation
  dialog" for a trusted server. If a deployed client honours that, T7 is
  reachable with no human in the loop; if every client always confirms, T7 is
  misleading metadata. One experiment settles it.
- **Which tools are enabled in the deployed client configurations.** Per-tool
  enablement is available in the major clients and is the strongest control for
  T7 — it removes the path entirely, without a code change. If `export_comments`
  is already disabled in the deployed configs, T7 is closed in practice today.

**Living-document updates this audit proposes but does not make.** This audit
commits only its own directory — see `../README.md` on why. The 35-row model,
the three control layers and the §5 mitigations live in
[`THREAT_MODEL.md`](THREAT_MODEL.md) here; **adopting it as the living
`THREAT_MODEL.md` at the repository root is filed as an issue**, not done by this
branch, along with the documentation corrections in `ISSUES.md` #16. Nothing in
`src/` was modified by this audit.
