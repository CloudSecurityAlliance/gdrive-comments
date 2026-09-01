---
audit_id: 2026-09-01-02                  # -01 is the concurrent chatgpt-codex-gpt5 audit, which completed first
date_started: 2026-09-01T07:32Z
date_completed: 2026-09-01T08:05Z
target: csa-google-workspace
target_commit: d33034b                   # tree state the findings were derived from
main_at_record_commit: 2a0e073           # #305 and #307 landed after this audit's commit, before it merged — see 'Concurrent audit'
commits_landed_during_audit: 2           # f8acda6, 2a0e073
target_version: 0.38.0

prior_audit: 2026-08-27-01               # @ 95c6afa (v0.28.0) — 10 minor versions back
concurrent_audit: 2026-09-01-01          # chatgpt-codex-gpt5, same target_commit, ran 07:10–07:40Z
prior_audit_findings_reverified: 19      # all 19 remediated items re-checked; see FINDINGS §2

tool: claude-code
tool_harness: anthropics/defending-code-reference-harness
tool_workflow: "/threat-model bootstrap (re-audit shape), then manual adversarial verification of every load-bearing claim"
model: claude-opus-5
subagents: "7 parallel research agents, same model (capability/policy reader, new-module reader, infrastructure and CI reader, history miner, prior-audit re-verifier, test-suite reader, docs/drift/asset reader)"

human_interaction: heavy
automation: assisted
review_depth: adversarial

scope_covered:
  - "src/csa_google_workspace/ — all 57 modules, 12,266 lines, static read"
  - "mcp/ server — 50 tool registrations, annotations, INSTRUCTIONS prose, tool descriptions as model-facing text"
  - "policy.py, allowlist.py, permissions.py — capability, allowlist, and gate enforcement"
  - "NEW since prior audit: access_proposals.py, labels.py, mcp/_flavours.py, mcp/_logging.py, mcp/_capabilities.py"
  - "_apply.py, _export.py, _desktop.py — local filesystem read/write paths"
  - "auth.py, mcp/_auth_flow.py, mcp/_login.py — OAuth acquisition, scopes, token custody"
  - "tests/ — AUDITED AS CODE this time, not merely read for coverage claims (see Scope change)"
  - ".github/workflows/ — tests.yml, release.yml, controls.yml"
  - "scripts/check_doc_claims.py, scripts/check_controls.py, scripts/check_artifact.py — the drift and control guards themselves"
  - "THREAT_MODEL.md (living), SECURITY.md, README.md, CLAUDE.md, TODO.md, docs/DECISIONS.md, INTERFACE-RESOURCES.md, docs/superpowers/specs/, docs/correctness-reports/"
  - "prior audit directory + REMEDIATION.md — every cleared item re-checked against the tree"
  - "git history — d33034b and all refs, security-keyword mined; f481733 (v0.31.0) read in full"
index_label: "2026-09-01 · defending-code-reference-harness / claude (re-audit)"
findings_summary: "43 threats · 9 flaws · 10 guards-that-cannot-fail · 1 refuted · 1 fixed upstream mid-audit"
remediation_summary: "not started — 24 issues listed in ISSUES.md, fixing deferred to a separate session"

# Enumerated, not globbed: a glob claims the future (SCHEMA.md). Produced from the audited
# tree itself with `git ls-tree -r d33034b --name-only`. tests/ is deliberately partial —
# 13 of 116 files were audited as code, and the coverage table should say so.
modules_covered:
  - .github/workflows/controls.yml
  - .github/workflows/dependabot-auto-merge.yml
  - .github/workflows/doc-claims.yml
  - .github/workflows/release.yml
  - .github/workflows/relock.yml
  - .github/workflows/tests.yml
  - .gitignore
  - .gitleaks.toml
  - pyproject.toml
  - scripts/check_controls.py
  - scripts/check_doc_claims.py
  - scripts/check_release_history.py
  - scripts/gen_audit_index.py
  - scripts/lock.sh
  - scripts/mcp_smoke.py
  - src/csa_google_workspace/__init__.py
  - src/csa_google_workspace/_apply.py
  - src/csa_google_workspace/_cellmap.py
  - src/csa_google_workspace/_content.py
  - src/csa_google_workspace/_environment.py
  - src/csa_google_workspace/_errors.py
  - src/csa_google_workspace/_export.py
  - src/csa_google_workspace/_formats.py
  - src/csa_google_workspace/_services.py
  - src/csa_google_workspace/access_proposals.py
  - src/csa_google_workspace/allowlist.py
  - src/csa_google_workspace/auth.py
  - src/csa_google_workspace/backend.py
  - src/csa_google_workspace/base.py
  - src/csa_google_workspace/comments.py
  - src/csa_google_workspace/demo/__init__.py
  - src/csa_google_workspace/demo/_cli.py
  - src/csa_google_workspace/demo/_feedback.py
  - src/csa_google_workspace/demo/_plan.py
  - src/csa_google_workspace/demo/_runner.py
  - src/csa_google_workspace/documents/__init__.py
  - src/csa_google_workspace/documents/doc.py
  - src/csa_google_workspace/documents/sheet.py
  - src/csa_google_workspace/documents/slides.py
  - src/csa_google_workspace/exceptions.py
  - src/csa_google_workspace/files.py
  - src/csa_google_workspace/labels.py
  - src/csa_google_workspace/mcp/__init__.py
  - src/csa_google_workspace/mcp/__main__.py
  - src/csa_google_workspace/mcp/_auth_flow.py
  - src/csa_google_workspace/mcp/_capabilities.py
  - src/csa_google_workspace/mcp/_config.py
  - src/csa_google_workspace/mcp/_desktop.py
  - src/csa_google_workspace/mcp/_flavours.py
  - src/csa_google_workspace/mcp/_inline.py
  - src/csa_google_workspace/mcp/_logging.py
  - src/csa_google_workspace/mcp/_login.py
  - src/csa_google_workspace/mcp/_resources.py
  - src/csa_google_workspace/mcp/_schemas.py
  - src/csa_google_workspace/mcp/_success_page.py
  - src/csa_google_workspace/mcp/_tools/__init__.py
  - src/csa_google_workspace/mcp/_tools/_base.py
  - src/csa_google_workspace/mcp/_tools/auth.py
  - src/csa_google_workspace/mcp/_tools/comments.py
  - src/csa_google_workspace/mcp/_tools/config.py
  - src/csa_google_workspace/mcp/_tools/content_write.py
  - src/csa_google_workspace/mcp/_tools/content.py
  - src/csa_google_workspace/mcp/_tools/demo.py
  - src/csa_google_workspace/mcp/_tools/feedback.py
  - src/csa_google_workspace/mcp/_tools/files.py
  - src/csa_google_workspace/mcp/_tools/suggestions.py
  - src/csa_google_workspace/mcp/cli.py
  - src/csa_google_workspace/mcp/server.py
  - src/csa_google_workspace/permissions.py
  - src/csa_google_workspace/policy.py
  - src/csa_google_workspace/suggestions.py
  - src/csa_google_workspace/workspace.py
  - tests/test_allowlist.py
  - tests/test_annotations_and_claims.py
  - tests/test_apibackend_contract.py
  - tests/test_config_text_agrees_with_policy.py
  - tests/test_demo.py
  - tests/test_docs_do_not_drift.py
  - tests/test_every_capability_is_reachable.py
  - tests/test_logging_level.py
  - tests/test_mcp_capabilities.py
  - tests/test_policy_matrix.py
  - tests/test_release_workflow_shape.py
  - tests/test_repr_redaction.py
  - tests/test_threat_model.py
scope_excluded:
  - "No target code was executed: the package was never imported, no pytest, no pip install, no console entry point."
  - "One script was run, deliberately: scripts/gen_audit_index.py, which SCHEMA.md requires an audit to regenerate the index with and which CI checks. It imports only stdlib plus yaml, shells out to `git ls-files`, never imports csa_google_workspace, and touches no credential or network. Nothing else in scripts/ was executed."
  - "No live Google Workspace endpoint was contacted. No token, .env, or credential file was read or printed."
  - "No dynamic testing, fuzzing, or running-agent prompt-injection exercise."
  - "No stdio wire-level probe this round (the prior audit's blind spot was closed by RR-002; not re-tested here)."
  - "Client-side behaviour of Claude Desktop / Claude Code (approval prompts, per-tool enablement) not tested."
  - "Advisory databases not re-queried — the dependency set changed by one declared package since 2026-08-27."
  - "experiments/ and research/ not audited."
inputs:
  - "SECURITY.md (design doc / framing)"
  - "THREAT_MODEL.md (living register, v0.28.0 → v0.37.0 delta table)"
  - "docs/security-audits/2026-08-27-defending-code-reference-harness-claude/ (prior audit + REMEDIATION.md)"
  - "docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md (the design this audit tests)"
---

# Security re-audit · csa-google-workspace @ `d33034b` (v0.38.0)

Second full audit. The first was 2026-08-27 at `95c6afa` (v0.28.0); ten minor
versions, 19 remediated findings, and one deliberate reversal of the project's
security defaults separate the two trees.

**The tree did not move while the audit ran.** `origin/main == d33034b` from
07:32Z to 08:05Z, so every line citation in `FINDINGS.md` and `THREAT_MODEL.md`
is exact at `target_commit` and none required a drift caveat during the read.

It moved immediately afterwards. Two commits landed between this audit's commit
and its merge — `f8acda6` (#305) and `2a0e073` (#307) — both processing and
closing out a **concurrent** audit that was reading the same commit. Citations here are deliberately **not** rewritten
to match — they are pinned to `target_commit`, which is what makes them
checkable. What moved is recorded below.

## Concurrent audit — and one finding fixed before this record merged

A second audit of the same commit, `2026-09-01-01`
(`docs/security-audits/2026-09-01-chatgpt-codex-gpt5/`, Codex / GPT-5), ran
07:10–07:40Z while this one ran 07:32–08:05Z. Neither knew about the other. Both
read `d33034b`. That is the corpus design working as intended, and it is worth
recording what it produced:

**The two audits converged on the defaults-drift finding independently.** Their
`CODX-2026-09-01-01` is this audit's **F2** — the three `mcp/_tools/files.py`
tool descriptions telling the model that `file.update`, `file.trash`, and
`file.share` are off by default. Two different tools, two different models,
reading the same tree without coordination, both ranked it the most urgent
finding and for the same reason: it is model-facing text, so a model reads it as
a reason not to warn. That is about as strong a corroboration signal as this
kind of review produces.

**#305 fixed it before this record merged**, and `#307` closed that audit out
with its own `REMEDIATION.md`. All four `files.py` sites are
corrected on `f8acda6`, along with two of the source docstrings this audit cites
under F3 (`policy.py:369-374` and `:445-448`) and `policy.py:264-266`. The
finding is retained rather than deleted — a record is point-in-time, and the
evidence of what the tree looked like at `d33034b` is the thing that makes the
fix reviewable. `FINDINGS.md` marks it fixed and names the commit;
`ISSUES.md` #1 is marked already-done so nobody files it twice.

**The two audits did not otherwise overlap.** Their register is three findings,
zero exploitable; this one is 25 across a much wider scope, and every other
finding here — including the headline **F1** — is untouched by `f8acda6` and
live on current `main`:

| this audit | status on `f8acda6` |
|---|---|
| **F1** `clear_cells` gated `content.write` | **live** — `policy.py:421`, still `Gate(CONTENT_WRITE, MODIFY)` while `:404`/`:409` are `CONTENT_DELETE`. Line shifted 420→421 by #305's comment edit; the gate is unchanged |
| **F2** three tool descriptions | **fixed** by #305 (= their CODX-01) |
| **F3** threat-model + docstring sweep | **partially fixed** — `policy.py:264-266`, `:369-374`, `:445-448` corrected; `THREAT_MODEL.md` §1, `:112`, `:124`, the three statuses, and `TODO.md:588-591` untouched |
| **F5** `README.md:263`, `:704` | **live** — both still present. #305 fixed a third instance at `README.md:37` and left these two |
| **F10** `check_doc_claims.py` | **live** — `FROZEN_COUNTS` still dead, comment still false. Lines shifted 58/60/214 → 65/67/293 |
| F4, F6–F9, F11–F25 | **live**, untouched |

Line-number drift for the five findings whose files `f8acda6` touched is recorded
above and in `FINDINGS.md`. Everything else cites `d33034b` unchanged.

The one genuine collision was `docs/security-audits/README.md` — the generated
index — because both audits regenerate it. That is a merge conflict resolved by
re-running `scripts/gen_audit_index.py`, which is the outcome `SCHEMA.md`
designed for. The `audit_id` collided too: both records claimed
`2026-09-01-01`, and this one is renumbered `-02` because theirs completed
first. Worth a line in `SCHEMA.md` — filed as `ISSUES.md` #25.

## Scope change from the prior audit

The 2026-08-27 audit recorded `tests/` as excluded: *"read for coverage claims
only, not audited as code."* This audit **audited the test suite as code**, on
the reasoning that in a repository whose primary security mechanism is a
capability policy, the tests are not commentary on the control — they are part
of it. Seven of this audit's findings come from that change of scope, including
the headline one (F1), and one of them is a **shipped test that asserts a
security property the code does not have**.

That is worth stating plainly for whoever plans the next audit: the most
serious defect found this round was sitting behind a passing test, in a
directory the previous audit declared out of scope.

## What the audit found, in one paragraph

All 19 prior findings hold; none was reverted, and several were fixed more
thoroughly than recommended. The project has since built genuine anti-drift
machinery — a maintained delta table, a doc-claim surveyor, a controls checker,
tests that make the threat model load-bearing — and it is more self-aware about
its own risk than most codebases twice its age. Against that, one commit
(`f481733`, v0.31.0, the day after the first audit) inverted the entire default
posture from fail-closed to fully open, deliberately and by decision; and
nothing swept the documentation, the threat model's control narrative, the
model-facing tool descriptions, or the startup warnings to match. The result is
a codebase whose *stated* controls and *actual* controls disagree in the
operator's and the model's favour respectively — the documentation understates
what a default install permits, and three tool descriptions tell the model a
destructive capability is switched off when it is on. Separately, and
independently of the defaults change, one capability gate is wired to the wrong
capability and two tests certify the wrong wiring.

## The structural finding

Every guard in this repository that **derives** its subject from the live
registry still works. Every guard that **enumerates by hand** has fallen behind.
That much was expected. The sharper result is the one that explains the headline
defect:

> **Derivation protects against incompleteness, not against incorrectness.**

`mcp/_capabilities.py`'s `TOOL_CAPABILITIES` is named in-tree as "the single
source of truth," and a test proves every tool has a row in it, that no row
names a dead tool, and that every capability named is real. Nothing compares it
to `policy.py`'s `TOOL_GATES`, which is what actually gates. So the repository
has strong coverage of *"did you remember to add the row"* and none of *"is the
row right"* — and because three other artefacts derive from the same table,
a single wrong value propagates consistently instead of surfacing as a
contradiction. Four artefacts agree with each other and all four disagree with
the enforcer.

`grep -rln TOOL_GATES tests/` returns nothing.

## Ranked findings

Full evidence, reproduction, and fix guidance in [`FINDINGS.md`](FINDINGS.md).
Issues to file in [`ISSUES.md`](ISSUES.md). The re-scored register is
[`THREAT_MODEL.md`](THREAT_MODEL.md) — 43 threats across 25 entry points, frozen
snapshot; adopting it at root is an issue, not a change made here.

| id | finding | class | confidence |
|---|---|---|---|
| F1 | `clear_cells` enforces `content.write`; four artefacts and two tests say `content.delete`. A `writer`/`editor` can blank any range on any reachable sheet, and `demonstration_plan` promises a refusal that will not happen | flaw | confirmed-by-read |
| F2 | Three model-facing tool descriptions assert `file.update` / `file.trash` / `file.share` are "off unless an operator enables it". All three are on by default | flaw | confirmed-by-read |
| F3 | The living `THREAT_MODEL.md` §1 posture paragraph and the `status` column of T4/T20/T29 describe the fail-closed world that ended at v0.31.0. T20 is `mitigated` on a control that no longer exists | flaw | confirmed-by-read |
| F4 | `startup_warnings` announces the two allowlist axes and is silent about capabilities on a default install — the one axis that changed is the one not announced | flaw | confirmed-by-read |
| F5 | `README.md:263` and `:704` claim a capability-level security advantage that a default install does not have | flaw | confirmed-by-read |
| F6 | A `writer` can change **who has access** to a file, by reparenting it. `spec:107`'s "our move is a rename" is factually wrong | flaw | confirmed-by-read |
| F7 | Exception messages carry the content that `__repr__` redaction was built to withhold, at a level above the default threshold, into a client-side log the server cannot purge | flaw | confirmed-by-read |
| F8 | `request_message` — attacker-authored text from someone with no access to the file — reaches the model with no `one_line()`, no fence, and no length cap, while ordinary comment bodies get all three | flaw | confirmed-by-read |
| F9 | `apply_comment_actions` checks `is_file()` before the `local_read` switch, leaving a local-path existence oracle inside the control added to remove local exposure | flaw | confirmed-by-read |
| F10 | `scripts/check_doc_claims.py` never reads `THREAT_MODEL.md`; its `FROZEN_COUNTS` guard is dead code and its explanatory comment is false in both halves | guard-cannot-fail | confirmed-by-read |
| F11 | `test_threat_model.py`'s "§4 only" filter is a *shape* filter; T36's 12-field row inside §0 is parsed as a §4 threat, and `SECURITY.md`'s "36 threats" agrees only because both count it | guard-cannot-fail | confirmed-by-read |
| F12 | The weekly controls drift detector cannot fail: `controls.yml:49` pipes through `tee` with no `pipefail` | guard-cannot-fail | confirmed-by-read |
| F13 | Zero tests read `TOOL_GATES`. `test_policy_matrix.py` drives the real enforcement path but takes its oracle from the reporting table, certifying F1; `EXPECTED` has no `content.delete` row at all | guard-cannot-fail | confirmed-by-read |
| F14 | `TOUCHES_STORAGE` hand-lists 16 of 50 tools, omitting 10 mutating ones; its anti-staleness guard detects removals only, never additions | guard-cannot-fail | confirmed-by-read |
| F15 | Three guards from the prior remediation went dark: removing the defect emptied the guard's input, so they now assert nothing | guard-cannot-fail | confirmed-by-read |
| F16 | `test_docs_do_not_drift.py` matches three literal phrases across three files; every surviving drift site uses different wording in a file not on the list | guard-cannot-fail | confirmed-by-read |
| F17 | The coverage table's unit is the file path, not content: ~3,400 of 4,061 new `src/` lines sit inside files marked "fully covered" | guard-cannot-fail | confirmed-by-read |
| F18 | `test_release_workflow_shape.py` never reads the workflow-level `permissions:` block, so a future top-level `id-token: write` would reach the `build` job with both assertions green | latent guard gap | confirmed-by-read |
| F19 | The MCP conformance test checks protocol → implementation only, not the reverse; currently latent (no divergence) | latent guard gap | confirmed-by-read |
| F20 | `has_write_scope` has no test and recognises only this project's four write scopes | hardening | confirmed-by-read |
| F21 | `test_all_writes_are_non_idempotent` covers 15 of 26 writes, omitting `create_permission` — the sharing write | guard-cannot-fail | confirmed-by-read |
| F22 | `openWorldHint` is set nowhere, on a server whose entire read surface returns third-party content. §8 of the prior model recommended it | hardening | confirmed-by-read |
| F23 | `REMEDIATION.md` is stale: `in-progress`, versions `0.30.0…0.30.4`, no entries for #190–#194 | housekeeping | confirmed-by-read |
| F24 | Capability count drift: "ten capabilities" in `CLAUDE.md:82`, `docs/DECISIONS.md:34` and three spec sites; `INTERFACE-RESOURCES.md:104` says v0.36.1 against `:3`/`:33` v0.38.0 | housekeeping | confirmed-by-read |
| F25 | Three Drive-shaped id constants are hardcoded across 18 test files (one in 15, one in 7), in a public repository. Reported by shape and location only | disclosure | confirmed-by-read |

One agent claim was **refuted** and is recorded as such: the release workflow
does *not* leak `id-token: write` to the build job today (`release.yml:27-28`
sets `contents: read` only). See F18 for the narrower guard gap that survives.

## Credited as right

Findings are cheap; these took deliberate design and are worth naming because
the next audit should not re-litigate them.

- **`valueInputOption` was deleted from the tool surface, not defaulted.**
  The prior audit's T15 recommended a safe default; v0.30.13 removed the
  parameter entirely and writes `RAW` unconditionally. The stronger fix.
  Removing an attack surface beats configuring it.
- **Drive labels are read-only by construction, at three independent layers.**
  The write scope is never requested, no capability exists to enable a write,
  and no gate is defined. The reasoning in-tree is the right reasoning:
  *"unlike a bad edit, nobody sees a diff."* A control that cannot be switched
  on cannot be switched on by a confused deputy.
- **The flavour control's two halves cannot diverge.** The allowed set and the
  advertised set come from one derivation, and enforcement is by removal from
  the live registry (`app.remove_tool`) rather than a parallel list. This is the
  pattern the rest of the repository needs.
- **`accept()` defaults to `reader`, never the requested role**, and `owner` is
  refused on every grant path including access proposals.
- **`_filter_listing` post-filters listings**, so a narrow read scope genuinely
  cannot be used to enumerate excluded files — the allowlist bounds naming, not
  just fetching.
- **No permanent delete exists anywhere in the backend.** No `files.delete`, no
  `emptyTrash`.
- **`type="anyone"` link-sharing is structurally unreachable**, because `share()`
  requires an `@` in the address.
- **A malformed allowlist refuses everything, loudly, and never widens.** The
  distinction between *unset* and *malformed* is drawn deliberately and
  correctly.
- **`tests/test_release_workflow_shape.py` carries an anti-staleness guard**, and
  `mcp/_config.py:177-181` documents its own prior drift with the single best
  sentence in the repository on why source docstrings matter:
  *"an internal docstring is the version an AI remediation agent is most likely
  to preserve while changing the code around it."*

## On the defaults reversal

`f481733` (v0.31.0) set `DEFAULT_ENABLED = frozenset(ALL_CAPABILITIES)` and
`DEFAULT_DISABLED = frozenset()`, and both file allowlists to every file when
unset. This was a decision, recorded as one, with reasoning
(`docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md:213-215`):
Drive owns sharing policy, the capability model constrains the deputy rather
than the principal, and the documentation's job becomes *how to narrow this*
rather than *how to switch it on*. `SECURITY.md:107-109` states the consequence
without flinching: *"a default install carries no capability-level mitigation"*
against the project's own named primary risk.

**This audit does not contest that decision.** It is the maintainer's call, the
reasoning is sound on its own terms, and the security-is-the-second-word-in-our-name
instinct shows plainly in how openly it is recorded.

What the audit does contest is the *consequences left unswept*. A deliberate
decision to ship open is compatible with good security posture only if
everything that describes the posture is moved with it. Here, three model-facing
tool descriptions, five source docstrings, the living threat model's §1 control
narrative, three of its threat statuses, the README's competitive claim, and the
startup warning's capability line were not moved. The gap matters in one
direction specifically: **every stale statement understates what a default
install permits.** A reader, an operator, and — most consequentially — the model
itself are all told the posture is narrower than it is.

The single highest-value fix in this audit is not a code change. It is
`ISSUES.md` #1: sweep the descriptions to match the decision that was already
made, and add the one test that makes the sweep hold.

## Provenance and handoff

Findings were produced by a seven-agent parallel read and then **individually
re-verified by the auditing session against the pinned tree**; nothing in
`FINDINGS.md` rests on an agent report alone. One agent claim was refuted in
that pass and is recorded as refuted rather than dropped.

Per the audit-corpus convention, this directory is the only thing the audit
committed. Adopting the re-scored `THREAT_MODEL.md` at root, sweeping the stale
documentation, and correcting `REMEDIATION.md` are filed as issues in
[`ISSUES.md`](ISSUES.md) and left for a separate remediation session, so the
flaw trail and the fix trail stay independently reviewable.
