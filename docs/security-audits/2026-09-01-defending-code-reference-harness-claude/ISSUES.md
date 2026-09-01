# Issues to file · audit 2026-09-01-01

Every issue below links back to a finding in [`FINDINGS.md`](FINDINGS.md). The
audit itself committed **only this directory**; all code, doc, and threat-model
changes are filed here and left for a separate remediation session.

Ranked by what I would fix first. Suggested labels in brackets.

**Before filing:** `f8acda6` (#305) landed after this audit's read, fixing #1
entirely and #3 partially — both are annotated below. Everything else is live on
current `main`, including #2, the headline. #25 and #26 arise from the
reconciliation itself.

---

## Tier 1 — the model is being told the wrong thing

### 1. ~~Three tool descriptions tell the model a capability is off that is on~~ — ALREADY FIXED
`[security] [mcp] [docs-drift] [P1]` · **F2** · **DO NOT FILE**

> Fixed in `f8acda6` (#305) as `CODX-2026-09-01-01`, found independently by the
> concurrent `2026-09-01-01` audit. All four `files.py` sites corrected. Kept in
> this list so the numbering matches `FINDINGS.md` and so a reader can see the
> convergence. **The acceptance test below was not added** — see #26.

`mcp/_tools/files.py:149,174,201,224` assert `file.update`, `file.trash`, and
`file.share` are *"off unless an operator enables it"* (and `:224` adds the
modify allowlist). All three are in `DEFAULT_ENABLED`; the modify allowlist
defaults to every file. `policy.py:369-374` carries the same false claim as a
comment.

These are strings delivered to the model as its description of its own
constraints. A model told trash is switched off will treat a trash attempt as
safely refusable — exactly the premise a confused deputy should not be handed.

**Fix.** Delete the default-state claims; a tool description should name the
capability it requires and stop. If current state is worth telling the model,
derive it from `describe_configuration`.
**Acceptance.** A test fails on `off (unless|by default)|OFF by default|DEFAULT_DISABLED`
anywhere under `mcp/_tools/`. Extends the guard that already covers INSTRUCTIONS
and annotations to where the claims moved.

### 2. `clear_cells` enforces `content.write`, and two tests certify the wrong wiring
`[security] [policy] [tests] [P1]` · **F1, F13**

`policy.py:420` gates `sheets_values_clear` as `Gate(CONTENT_WRITE, MODIFY)`
while its three siblings at `:403,404,408` are `CONTENT_DELETE`. Four artefacts
say `content.delete`: `_capabilities.py:111`, `content_write.py:303` (model-facing),
`demo/_plan.py`'s derived `requires`, and `policy.py:194`'s comment.

Consequence: a `writer`/`editor` — granted precisely so it can edit but not
destroy — can blank any range of any reachable sheet, with no trash and no API
undo. `demonstration_plan` tells the operator this will be refused.

Two tests hold it in place. `tests/test_policy_matrix.py:50` drives the real
enforcement path but lists the tool under `content.write`. `tests/test_demo.py:360-370`
asserts `clear_cells` **is** blocked under `editor` and passes, because both
sides of its comparison derive from `TOOL_CAPABILITIES`. `EXPECTED` has no
`content.delete` key at all, so the capability added in v0.36.0 has zero
one-at-a-time coverage.

**Fix.** Change `policy.py:420` to `CONTENT_DELETE`; add a `content.delete` row
to `EXPECTED` and move the tool into it; `test_demo.py` should then pass for the
right reason.
**Acceptance.** A new test asserts `TOOL_CAPABILITIES` agrees with
`{t: g.capability for t, g in TOOL_GATES.items()}`, and that
`set(EXPECTED) == set(ALL_CAPABILITIES)`. `grep -rln TOOL_GATES tests/` is
currently empty; it should not be.

### 3. Sweep the v0.31.0 defaults reversal through every description of the posture
`[docs-drift] [security] [P1]` · **F3, F5, F24** · **PARTIALLY DONE**

> `f8acda6` (#305) fixed the three `policy.py` docstrings (`:264-266`,
> `:369-374`, `:445-448`) and one README instance (`:37`). Still open: all
> `THREAT_MODEL.md` sites, `README.md:263` and `:704`, `TODO.md:588-591`, and the
> capability count. File it with those and only those.

`f481733` inverted the default posture deliberately and correctly recorded the
decision. Nothing swept the descriptions, and **every stale statement understates
what a default install permits.**

Sites, all verified at `d33034b`:

- `THREAT_MODEL.md:126-135` — §1's posture paragraph, presented as the controls
  *"observable in the tree"* and therefore the stated basis for every §4 rating.
  Four of its six clauses are now false. **Not frozen text**; the freeze covers
  threat prose.
- `THREAT_MODEL.md:112` (*"34 tools, and it fails closed"*), `:124`
  (*"ten capabilities … three irreversible operations disabled by default …
  four ascending profiles; separate fail-closed read and modify allowlists"*).
- `policy.py:264-266`, `:369-374`, `:445-448` — source docstrings asserting the
  pre-v0.31.0 model. `mcp/_config.py:177-181` is the one site already fixed, and
  says why it matters: *"an internal docstring is the version an AI remediation
  agent is most likely to preserve while changing the code around it."*
- `README.md:263`, `:704` — the claimed security advantage over the read-only
  claude.ai connector. Rewrite to the true and still-favourable claim.
- `TODO.md:588-591` — *"a default install cannot reach any of them."*
- Capability count: `CLAUDE.md:82`, `docs/DECISIONS.md:34`, and spec `:64,201,214`
  say ten; there are 11.

**Acceptance.** `test_docs_do_not_drift.py` widened per issue #10 finds zero
matches, and `check_doc_claims.py` reads `THREAT_MODEL.md` per issue #9.

### 4. Adopt the re-scored threat model at root
`[threat-model] [docs] [P1]` · **F3, F11**

`docs/security-audits/2026-09-01-defending-code-reference-harness-claude/THREAT_MODEL.md`
is a frozen snapshot re-scored against v0.38.0. It fixes, in one edit: the three
invalid statuses (T4, T20, T29), §1's posture paragraph, T15's residual
subsection (closed since v0.30.13), T18's falsified evidence, §6's contradiction
of §0, T36's misplaced row, and adds `last_reviewed:` to §7. It also adds the
new surfaces §3 was missing — the flavour control, the local-I/O switches, the
client-log destination, access proposals, labels, and the `content.delete`
tab/range surface.

Adopting it is a docs change and was deliberately not made by the audit.
**Note the freeze convention:** the *audit* copy stays frozen; the root copy is
the living one.

---

## Tier 2 — live defects, smaller blast radius

### 5. A `writer` can change who has access, by reparenting
`[security] [policy] [P2]` · **F6**

`backend.py:716-719` forwards `addParents`/`removeParents`;
`policy.py:375` gates it as `Gate(FILE_UPDATE, MODIFY)`; `policy.py:184-185` puts
`FILE_UPDATE` in `writer`. Moving a file between folders changes which folder
ACL it inherits, so it grants or revokes access without `file.share` and without
a visible permission change.

`docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md:107` says
*'our "move" is a rename'*. That is false, and it is the one counterexample to
the ladder claim the rest of the model is reasoned from.

**Fix — pick one.** (a) Split parent mutation into `file.share` or a new narrow
capability, preserving the ladder claim. (b) Correct `spec:107` and the ladder
docs to say `writer` can alter inherited access, and let Drive's folder ACLs be
the control. Either is defensible; leaving `:107` as written is not.

### 6. `request_message` reaches the model with no fence, no `one_line()`, no cap
`[security] [prompt-injection] [P2]` · **F8**

`access_proposals.py:37-45`. The field is free text from someone with **no
access to the file**, delivered to a model deciding whether to grant them some —
the highest-leverage injection position on the surface, because the payload and
the desired outcome coincide. Ordinary comment bodies get all three defences
from `_inline.py:43-61`; this field gets none.

Credit where due: the feature shipped with `owner` refused, `accept()` defaulting
to `reader`, deny gated as `file.share`, and `__repr__` redaction. Only the fence
is missing.

**Fix.** Route it through the same path as comment bodies. Small change, existing
tested machinery; ranked here for position, not size.

### 7. Exception messages leak tab titles into the client's uncontrolled log
`[security] [logging] [P2]` · **F7**

`sheet.py:89,127,218` embed full tab-title lists in exception messages;
`_base.py:84` logs at ERROR, which is above the default WARNING threshold;
`ConflictError` is not in the translated ladder. Destination is
`~/Library/Caches/claude-cli-nodejs/.../mcp-logs-*/`, which the server cannot
rotate or purge (`mcp/_logging.py:1-21` documents this).

Tab titles are document content and often meaningful. This defeats the
*"operation, never content"* rule the repo states at `_logging.py:32-37` and
honours everywhere else.

`tests/test_logging_level.py` asserts the property against `FakeBackend`, which
cannot produce the failing values — correct shape, inert input.

**Fix.** Bound the message at the raise site (count plus one example, or
`one_line()` plus a cap); add `ConflictError` to the ladder; re-point the test at
a fixture that carries titles.

### 8. `apply_comment_actions` leaves a filesystem existence oracle when local reads are off
`[security] [P2]` · **F9**

`mcp/_tools/comments.py:353-357` checks `source.is_file()` **before** the
`local_read` switch, so with local reads disabled the two error strings still
separate "exists" from "does not exist". `expanduser()` means `~/.ssh/id_rsa`
and `~/.csa_google_workspace/token.json` are probeable for existence, one bit per
call.

**Fix.** Swap the two checks — refuse on the switch first. Add a test asserting
the refusal message is byte-identical for an existing and a non-existing path
when the switch is off.

### 9. Announce the capability set at startup on a default install
`[security] [usability] [P2]` · **F4**

`mcp/_config.py:378-400` prints `READ: UNRESTRICTED` and `MODIFY: UNRESTRICTED`,
and announces capabilities only when `capability_source == "profile"`. On a
default install neither capability branch fires, so the operator is warned about
the two axes that were always open by choice and told nothing about
`file.share`, `comment.edit`, `comment.delete`, and `content.delete` being live —
the axis that actually changed, carrying all four irreversible operations.

**Fix.** Add a `capability_source == "default"` branch emitting the enabled set,
naming the irreversible members. A derived string cannot go stale, so this closes
the operator-facing half of issue #3 permanently.

---

## Tier 3 — guards that cannot fail

These share one cause: each was written to prevent the drift that then occurred.

### 10. The weekly controls drift detector always exits 0
`[ci] [P2]` · **F12**

`.github/workflows/controls.yml:49` — `python scripts/check_controls.py | tee controls.txt`
with no `set -o pipefail`, so the step reports `tee`'s status. `release.yml:48`
runs it unpiped and does propagate, so the *scheduled between-release* detector
is the dead one — the one whose entire purpose is catching drift between
releases.

**Fix.** `set -o pipefail`, or drop the pipe. **Acceptance:** break the script
deliberately once and confirm the job goes red.

### 11. `check_doc_claims.py` never reads `THREAT_MODEL.md`
`[ci] [docs-drift] [P2]` · **F10**

`THREAT_MODEL.md` is absent from `DOCS` (`:52-55`) and `DOC_GLOBS` (`:56`), so
`FROZEN_COUNTS` (`:60`, used at `:214`) is dead code and the comment at `:58`
(*"excluded from the COUNT checks but not the name checks"*) is false in both
halves. The script's own docstring (`:26-33`) describes this failure class.

**Fix.** Add it to `DOCS`; keep it in `FROZEN_COUNTS` so the frozen-text
exemption becomes real rather than vacuous; correct `:58`.

### 12. `test_threat_model.py` bounds §4 by column count, not by section
`[tests] [threat-model] [P2]` · **F11**

The docstring claims *"the §4 threat table only"*; the mechanism is
`len(fields) >= 11`. T36's row is 12 fields at **line 47, inside §0** (§4 begins
at 206), so it is parsed as a §4 threat. The test sees 36 rows, one of them above
§4 — which is also why `SECURITY.md:12`'s *"36 enumerated threats"* agrees with
it while §4 holds 35.

**Fix.** Bound the parse between the `## 4.` and `## 5.` headings, and move
T36's row into §4. The count claim then becomes true automatically.

### 13. Derive `TOUCHES_STORAGE` instead of hand-listing it
`[tests] [P2]` · **F14**

`tests/test_annotations_and_claims.py:43-50` lists 16 of 50 tools. Missing:
`clear_cells`, `delete_range`, `delete_tab`, `delete_document_tab`,
`resolve_access_proposal`, `add_tab`, `add_document_tab`, `insert_text`,
`unshare_file`, `update_file_permission`. The anti-staleness guard fires on
removals only, so every one of those could be re-annotated `read_only_hint=True`
and stay green — the defect class #184 was filed about.

**Fix.** A tool reaching a `MODIFY`-gated `Backend` method touches storage by
definition; `TOOL_GATES` already knows. Replace the literal with a comprehension.

### 14. Three guards from the prior remediation now assert nothing
`[tests] [P2]` · **F15**

Removing the defect emptied the guard's input:
- `test_every_capability_named_in_the_instructions_exists` — `server.py` has no
  dotted capability tokens left; the input set is empty and the assertion vacuous.
- `test_no_capability_miscounts` — 0 regex matches across all three docs.
- Two tests in `test_config_text_agrees_with_policy.py` skip when
  `not DEFAULT_DISABLED`, permanently true → **permanently skipped**.

The author named this failure mode in `check_doc_claims.py:26-33` and defended
against it there.

**Fix.** `assert tokens, "guard found nothing to check; it has gone stale"`
before asserting the property. For the skipped pair, invert them: assert the
current invariant (every capability in `DEFAULT_ENABLED` is documented as
enabled) rather than skipping when the old one is unreachable.

### 15. `test_docs_do_not_drift.py` matches three literals across three files
`[tests] [docs-drift] [P3]` · **F16**

`:479-491`. Every surviving drift site uses different wording — *"off unless an
operator enables it"*, *"OFF by default"*, *"fails closed when nothing is
configured"* — in a file not on the list (`policy.py`, `files.py`,
`THREAT_MODEL.md`).

**Fix.** Widen to a regex over `src/**/*.py` plus the docs set; assert the match
count is zero rather than that three strings are absent.

### 16. The coverage table's unit is the file path, not the content
`[docs] [P3]` · **F17**

~3,400 of 4,061 new `src/` lines sit inside files marked "fully covered",
because coverage was recorded per file when those files were smaller.

**Fix.** Record against line counts or the module's public surface, and derive.

### 17. The release-workflow guard never reads the workflow-level `permissions:`
`[ci] [tests] [P3]` · **F18**

`release.yml` is **correct today** — `:27-28` is `contents: read`, `:121-122`
scopes `id-token: write` to `publish`, `:33` documents build's absence. The guard
checks per-job permissions only (`test_release_workflow_shape.py:60,67`), so a
future top-level `id-token: write` would reach `build` (which runs `pip install`
and the test suite) with both assertions green.

**Fix.** Also assert `"id-token" not in workflow.get("permissions", {})`.

### 18. `test_all_writes_are_non_idempotent` covers 15 of 26 writes
`[tests] [P3]` · **F21**

Omits `create_permission` — the sharing write, i.e. the one whose repetition
matters most. Same hand-list cause as #13, same derivation fix.

### 19. The MCP conformance test is asymmetric
`[tests] [P3]` · **F19**

Checks protocol → implementation but not the reverse, so an implementation-side
addition with no protocol counterpart passes. Currently latent — no divergence at
`d33034b`. The same shape appears in the sibling `csa-skilljar` audit, so it is
worth fixing the habit in both.

---

## Tier 4 — hardening and housekeeping

### 20. Set `openWorldHint` on every tool returning Drive content
`[security] [mcp] [P2]` · **F22**

Zero hits in `src/`. `_base.py:24-26` declares three annotation fields and not
this one, on a server whose entire read surface returns third-party content. It
is the annotation that means "scrutinise this output for untrusted content", and
§8 of the prior model recommended it. Costs nothing; speaks directly to the
project's stated primary risk.

### 21. Invert `has_write_scope` to a subset check, and test it
`[security] [auth] [P2]` · **F20**

`auth.py:54`, used at `:130`. `grep -rln has_write_scope tests/` is empty. It
recognises only this project's four write scopes, so a token carrying
`drive.file` — a write scope this project does not request — passes the
read-only check.

**Fix.** Assert the granted set is a **subset of the read-only set** rather than
that it excludes four known write scopes. An allowlist cannot be outflanked by an
unlisted scope. Add the missing test.

### 22. `REMEDIATION.md` is stale
`[docs] [P3]` · **F23**

Still `status: in-progress`, versions `0.30.0…0.30.4`, no entries for #190–#194.
It is the document a reader uses to check whether an audit's findings were
addressed, so staleness reads as "unfinished" for work that is done.

### 23. Version and module-inventory drift
`[docs] [P3]` · **F24**

- `INTERFACE-RESOURCES.md:104` says *"current release v0.36.1"* against `:3`/`:33`
  v0.38.0 in the same file.
- `docs/superpowers/specs/2026-08-27-multi-account…:42,369` says *"34 tools"* /
  *"31 of today's 34"*, in a spec claiming re-verification on 2026-08-31.
- `mcp/_flavours.py:9,139` says *"36 tools"* / *"8 published, 28 hidden"* → 50/42,
  in the module that implements the count.
- `CLAUDE.md`'s module inventory omits `mcp/_flavours.py`, `mcp/_logging.py`, and
  `mcp/_capabilities.py` — three of the four new modules. (`CLAUDE.md` is
  otherwise broadly current and should be credited.)

### 24. Confirm whether three hardcoded Drive-shaped ids are real
`[hygiene] [P2 if real, P4 if not]` · **F25**

Three constants matching Google's id grammar exactly, spread across 18 test
files: one 44-char file-shaped id in 15 files, another in 7, and one 33-char
folder-shaped id in `tests/test_allowlist.py`. None carries a placeholder marker.
Values are deliberately not reproduced in the audit.

A Drive id is **not** a credential — the file stays ACL-gated — so this is not an
access disclosure. If the ids are real it discloses the existence of specific
documents plus a precise target for a directed access request, in a public repo.

**Fix.** If real, replace with obviously-synthetic ids of the same shape (a `1`
prefix plus a fixed `AAAA…` body keeps format validation passing) and note it in
the commit without restating the values. If already synthetic, add a comment
saying so at the definition site — one line, and it never recurs again.

---

### 25. SCHEMA.md: `audit_id` collides when two audits run the same day
`[docs] [process] [P3]`

Two audits of `d33034b` ran concurrently on 2026-09-01 and both front matters
claimed `audit_id: 2026-09-01-01`. Resolved by renumbering this record `-02`
because `2026-09-01-01` completed first (07:40Z vs 08:05Z), but nothing in
`SCHEMA.md` or `tests/test_audit_index.py` prevents or detects it.

The corpus is explicitly designed for parallel audits, so same-day collisions are
expected rather than exceptional, and `audit_id` is the field a `REMEDIATION.md`
and an issue trail point at.

**Fix.** State the tie-break rule in `SCHEMA.md` (completion time, or the
directory name as the real key), and add a test asserting `audit_id` is unique
across records. Cheap, and it stops two records disagreeing about which is which.

### 26. Add the guard that would have caught the F2 class permanently
`[tests] [P2]` · **F2**

#305 fixed the three `files.py` strings but did not add a guard, so the class can
recur — and it already recurred once: the prior audit's §8 recommended asserting
capability claims in the INSTRUCTIONS string, that was implemented, and the
claims then reappeared in tool **descriptions**, which the guard does not read.

**Fix.** Fail on `off (unless|by default)|OFF by default|DEFAULT_DISABLED`
anywhere under `mcp/_tools/`. Better: assert no tool description contains any
default-state claim at all, and derive current state from
`describe_configuration` if it needs to be stated.

## Filing note

Suggested body footer for each issue, so the trail stays navigable:

```
Found by security audit 2026-09-01-01 (claude-opus-5 via
anthropics/defending-code-reference-harness) at d33034b / v0.38.0.
Evidence: docs/security-audits/2026-09-01-defending-code-reference-harness-claude/FINDINGS.md#<anchor>
```

Issues #2, #3 and #4 are the ones I would put in a milestone together (#1 is done): they
are one story — a deliberate posture change whose descriptions were not swept —
and fixing #3 without #1 leaves the model still being misinformed, which is the
half that matters most.

---

## Filed

Added after the record merged — the issue trail, which is the one thing
`SCHEMA.md` expects a completed record to gain. Findings and evidence above are
unchanged.

| # here | GitHub | finding | title |
|---|---|---|---|
| 1 | — **not filed** | F2 | Already fixed in `f8acda6` (#305) as `CODX-2026-09-01-01`, found independently by the concurrent audit |
| 2 | [#308](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/308) | F1, F13 | `clear_cells` enforces `content.write`, and two tests certify the wrong wiring |
| 3 | [#309](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/309) | F3, F5, F24 | Sweep the v0.31.0 defaults reversal through every description of the posture |
| 4 | [#310](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/310) | F3, F11 | Adopt the re-scored threat model at root |
| 5 | [#311](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/311) | F6 | A `writer` can change who has access, by reparenting a file |
| 6 | [#312](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/312) | F8 | `request_message` reaches the model with no fence, no `one_line()`, no cap |
| 7 | [#313](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/313) | F7 | Exception messages leak tab titles into the client's uncontrolled log |
| 8 | [#314](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/314) | F9 | `apply_comment_actions` leaves a filesystem existence oracle when local reads are off |
| 9 | [#315](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/315) | F4 | Announce the capability set at startup on a default install |
| 10 | [#316](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/316) | F12 | The weekly controls drift detector always exits 0 |
| 11 | [#317](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/317) | F10 | `check_doc_claims.py` never reads `THREAT_MODEL.md` |
| 12 | [#318](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/318) | F11 | `test_threat_model.py` bounds §4 by column count, not by section |
| 13 | [#319](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/319) | F14 | Derive `TOUCHES_STORAGE` instead of hand-listing it |
| 14 | [#320](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/320) | F15 | Three guards from the prior remediation now assert nothing |
| 15 | [#321](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/321) | F16 | `test_docs_do_not_drift.py` matches three literals across three files |
| 16 | [#322](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/322) | F17 | The coverage table's unit is the file path, not the content |
| 17 | [#323](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/323) | F18 | The release-workflow guard never reads the workflow-level `permissions:` |
| 18 | [#324](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/324) | F21 | `test_all_writes_are_non_idempotent` covers 15 of 26 writes |
| 19 | [#325](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/325) | F19 | The capability-reachability conformance test is asymmetric |
| 20 | [#326](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/326) | F22 | Set `openWorldHint` on every tool returning Drive content |
| 21 | [#327](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/327) | F20 | Invert `has_write_scope` to a subset check, and test it |
| 22 | [#328](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/328) | F23 | `REMEDIATION.md` is stale |
| 23 | [#329](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/329) | F24 | Version and module-inventory drift |
| 24 | [#330](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/330) | F25 | Confirm whether three hardcoded Drive-shaped ids are real |
| 25 | [#331](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/331) | — | `SCHEMA.md`: `audit_id` collides when two audits run the same day |
| 26 | [#332](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/332) | F2 | Add the guard that would have caught the CODX-01 / F2 class permanently |

**Start with #308.** It is the only live finding in this set that lets a profile
do something the profile exists to prevent, and it ships with a test asserting
the opposite.
