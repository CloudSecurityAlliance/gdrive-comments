# TODO / backlog

The feature roadmap (comments · content read/write · Sheets cell-mapping · Docs
suggestions read) is **complete and live-verified** — see `CHANGELOG.md`. This file
is the post-roadmap backlog: the phase-2 delivery layer (below), plus enhancements and
polish to the library itself (comments + content on Google Docs/Sheets/Slides), none of
the latter blocking.

Ordered by leverage-to-effort. Nothing here is committed to — it's a menu. Each item,
when picked up, follows the plan-then-execute rhythm (spec/plan under
`docs/superpowers/`, then TDD via `FakeBackend`). `CHANGELOG.md` is the shipped-work
ledger; the phase plans in `docs/superpowers/plans/` are the per-phase detail.

## Near-term objective: phase 2 — the built-in MCP server

The **audit → cleanup → PyPI** milestone that used to head this file is **done** (Tiers 0–2
below, plus the release-process hardening — all ✅). The library is published and the
pipeline is hardened, so the next milestone is the **delivery layer**:

**Ship `csa_google_workspace.mcp`** — a built-in MCP server so an AI client can review
comments, read content, and edit Docs/Sheets/Slides through the library. The spec is
**approved for planning**:
[`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](docs/superpowers/specs/2026-07-23-mcp-server-design.md).

Locked decisions: local single-user **stdio** first (structured so Streamable HTTP can be
added later), the official `mcp` SDK's bundled **FastMCP**, **read + write on by default**
(hedged with tool annotations + a `CSA_GW_READ_ONLY=1` flag, not gated), and v1 primitives
= tools + one Resource (document text) + one Prompt (comment triage).

- [ ] **Write the implementation plan** (via writing-plans) — the spec's §10 phasing is the
  outline: (a) `[mcp]` extra + package skeleton + `create_server` + config; (b) read tools +
  structured schemas; (c) write tools + annotations; (d) Resource + Prompt; (e) entry point
  + docs + a gated live smoke. This is the actual next action.
- [ ] **Then execute it** TDD, per task, against `FakeBackend` + FastMCP's in-memory client.

Note the scope shift: everything *below* this section is library-internal, but phase 2 is a
**delivery layer over** the library — it adds no document logic, only maps MCP primitives
onto the existing `Workspace` API.

## Publish — ✅ DONE

- [x] **Release automation** — `.github/workflows/release.yml` (Trusted Publishing / OIDC);
  steps in `RELEASING.md`.
- [x] **Published to PyPI** — `0.1.0`, `0.1.1` (docs patch), and `0.1.2` (first release
  through the hardened pipeline — attestations + env gate) all cut via `gh release create`
  → CI-built, tagged, GitHub-Released, uploaded over OIDC. Page:
  <https://pypi.org/project/csa-google-workspace/>. Current `__version__`: **0.1.2**.

## Release-process / supply-chain hardening — ✅ DONE

From a 2026-07-23 release-process review (re-verified). Fixed in PR #69 (code) + repo-admin
settings, worst-first:

- [x] **⚙️ `main` is protected.** Branch protection via API: required status checks (`lint`,
  `test (3.10–3.13)`, `security`), PRs required, direct + force pushes blocked, **enforced for
  admins**. `required_approving_review_count = 0` so the solo/AI PR flow still merges (checks
  gate, no human-approval bottleneck). *Residual (optional):* also require the CodeQL contexts,
  and/or raise the review count if a second reviewer is ever available.
- [x] **🔧 Actions pinned to commit SHAs** (PR #69) — `checkout` v4, `setup-python` v5,
  `gh-action-pypi-publish` v1.14.1, across `tests.yml` + `release.yml`; Dependabot keeps them current.
- [x] **🔧+⚙️ Environment gate on publish** — protected `pypi` GitHub Environment (required
  reviewer: repo owner) + `environment: pypi` on the publish job (PR #69). *Residual (optional):*
  tighten the PyPI trusted-publisher binding to require environment `pypi` (works without today).
- [x] **🔧 PEP 740 attestations** — `attestations: true` on the pinned publisher (PR #69),
  **✅ verified** against PyPI's **Integrity API**: `0.1.0`, `0.1.1`, and `0.1.2` all return
  `200` on `/integrity/csa-google-workspace/<ver>/<file>/provenance` — every release is
  attested. *Correction:* the earlier "no provenance" reading was a **measurement error** —
  the legacy `/pypi/<pkg>/<ver>/json` `urls[].provenance` field is unreliable (reads `false`
  even when attestations exist); use the Integrity API. Attestations have shipped since
  `0.1.0` (Trusted Publishing default), so there was never a gap to fix — the explicit
  `attestations: true` just makes it intentional.
- [x] **🔧 Security gate at release time** — `pip-audit` + `bandit` run before publish in
  `release.yml` (PR #69).
- [x] **🔧 Dependency automation + pinned build** — `.github/dependabot.yml` (`pip` +
  `github-actions`); `build`/`twine` pinned in the release job (PR #69). *(Full CI lockfile
  still optional/deferred.)*
- [x] **🔧 Polish** — `SECURITY.md` disclosure text completed; sdist-contents guard added
  (PR #69). *Deferred (optional):* SBOM publication; a post-publish "install from PyPI + import"
  smoke step.

## Tier 0 — audit findings (correctness) — ✅ DONE

Confirmed by an external review (2026-07-21), re-verified against the code, and fixed:

- [x] **`Workspace.open()` leaks a raw `HttpError`.** ✅ Fixed in PR #26. `ApiBackend.get_file_metadata`
  (`backend.py:190`) is the *only* data method that calls `.execute()` without
  `_errors.call(...)`, so the first call a consumer makes raises a raw
  `googleapiclient.errors.HttpError` on a missing/forbidden/service-disabled file
  instead of the typed `NotFoundError`/`PermissionError`/`ServiceDisabledError` the spec
  promises. **Fix:** wrap in `_errors.call`, **and** add an `ApiBackend`-level test that
  feeds a stub service raising `HttpError` and asserts typed translation — no
  `FakeBackend` test can catch this class of bug, because the fake raises typed errors
  directly (the one blind spot of the fake/real seam).
- [x] **Cell-map degrade is spec-noncompliant (no recorded warning).** ✅ Fixed in PR #26
  (stdlib `logging` WARNING on degrade; genuine no-match stays quiet). The spec
  (`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md:334`) requires
  `_cellmap` to degrade to `location=None` **plus a recorded warning**. `sheet.py:63`
  does the `location=None` half but records nothing, so export-cap-exceeded,
  access-denied, malformed XLSX, and genuine no-match are indistinguishable to callers.
  Shares a root cause with the tracked "10 MB export cap silently degrades" item:
  **there is no logging/warnings story.** **Fix (shared, minimal):** adopt stdlib
  `logging` + `warnings.warn`; closes both. Resist anything heavier.

## Tier 1 — make the "embeddable, typed" promise real (small, high leverage)

Both items below were independently flagged by the same external review — good signal
they're the right release-readiness priorities.

- [x] **`py.typed` marker (PEP 561).** ✅ Shipped in PR #27 (marker + `package-data`;
  verified present in a built wheel + a packaging test guards it).
- [x] **Package metadata.** ✅ Done: `readme`, SPDX `license = "Apache-2.0"` +
  `license-files`, `authors`/`maintainers`, `keywords`, trove `classifiers`
  (incl. `Typing :: Typed`), `[project.urls]`, and a single-sourced dynamic version.
  Bumped to `0.1.0`; `build` + `twine check` green for sdist + wheel.
- [x] **CI that runs the test suite.** ✅ Added in PR #28 — GitHub Actions runs
  `pytest -q` across Python 3.10–3.13 on push + PR (offline; live suite stays gated).

## Tier 2 — formalize the guarantees — ✅ DONE

- [x] **ruff + mypy in dev deps and CI.** ✅ ruff (lint; E/F/W/I/B/UP, ignoring the
  deliberate `E702` semicolon style, no auto-formatter) + mypy (`check_untyped_defs`,
  google stack marked untyped) now run as a dedicated `lint` CI job. Fixed the findings
  (mostly test cleanups + typing the injected `_backend`/`_file_id` fields and the
  `CommentsMixin` attributes).
- [x] **Coverage reporting** (`pytest-cov`). ✅ Wired into the CI matrix with
  `fail_under = 85` (total ~87%; the shortfall is the integration-only ApiBackend +
  interactive OAuth paths).

## Tier 3 — real API-surface gaps — ✅ DONE

- [x] **Sheets `append_rows`** (`spreadsheets.values.append`, `INSERT_ROWS`). ✅ Added;
  non-idempotent so never auto-retried on 5xx.
- [x] **Slides write symmetry.** ✅ Added `Slides.insert_text(object_id, text, index=0)`
  (shape-addressed, symmetric to `Doc.insert_text`) + `Slide.shape_ids` to discover
  targetable shapes. Decision: a fuller shape model (bulk shape CRUD) stays out — raw
  `batch_update` remains the escape hatch; the asymmetry with Docs is inherent (Slides is
  shape-addressed, Docs is a linear index).
- [x] **`Sheet.as_text(tab=…)`** ✅ now renders **all** tabs by default (each with a
  `# <tab>` header when >1), fixing the silent first-tab-only data loss; `tab=` selects one.

### Tier 3 minor / polish — ✅ already resolved (verified in code)

- [x] `replace_text` returns `occurrencesChanged` + `match_case` kwarg (Doc + Slides) —
  fixed in an earlier batch; a no-match (`0`) is distinguishable from a match.
- [x] `Sheet.batch_update` invalidates the cell-map cache (`self._cell_map_cache = None`).
- [x] `Doc.suggestions` is typed `list[Suggestion]`.

## Tier 4 — prove the pitch (scope-adjacent)

- [ ] **`examples/` reference consumer** — ~~a small MCP server or~~ a comment-triage bot
  built on the library. **Mostly superseded by phase 2:** the earlier "stays out of the
  *core* per the design" framing was reversed when the built-in MCP server was approved, and
  that server is now the reference consumer + the proof of the "embed in MCP/plugins"
  positioning. What's left of this item is only a *non-MCP* example (e.g. a plain triage
  bot), if one is still wanted after phase 2 ships.
- [ ] **Async story — decide.** Sync-only forces `asyncio.to_thread` on async callers. Lean:
  *document the `to_thread` pattern* (cheap) rather than build an async facade (large, and
  `google-api-python-client` is sync). **Phase 2 forces the call** — the MCP server is the
  first in-tree async-adjacent consumer, so decide it while writing that plan.

## Integration / live testing

Three tiers:

- **unit** — `tests/`, offline (`FakeBackend`), 217 tests; gates every PR.
- **integration** — `tests/integration/`, real Google API, opt-in via `CSA_GW_INTEGRATION=1`
  (needs a cached token or a first-run browser login). Covers the full surface incl. Tier 3.
- **oauth** — `tests/oauth/`, the **interactive browser-login** suite (real `from_oauth`,
  token-file permissions, `read_only` contract). **Separate** because it needs a human at a
  browser and touches the very sensitive cached token; own gate `CSA_GW_OAUTH=1`.

```
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
CSA_GW_OAUTH=1       CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

- [ ] **Optional: a manual `workflow_dispatch` CI job** running the live suite with a stored
  Google credentials secret. **Deferred to the security audit** — putting Google creds in CI
  is a threat-model decision, not a default.

## Deferred — bigger / genuinely out of reach today (already tracked)

These are recorded design decisions, **not bugs**:

- [ ] **`Location.tab` resolution** — multi-tab cell disambiguation via `workbook.xml` +
  rels (part → sheet-name). Real correctness gap for multi-tab sheets; its own task.
- [ ] **Caching pass** — accessors re-fetch per call by design (the tool is used in live
  multi-reviewer sessions where a self-only-invalidated cache goes stale). An *opt-in* /
  request-scoped cache is the biggest runtime win for embedded review sessions.
- [x] **10 MB XLSX export cap** — large sheets degrade the cell-map. ✅ No longer *silent*
  as of PR #26: the shared logging story records a WARNING naming the cause. (Raising the
  cap itself is still out of reach — it's a Google export limit.)
- [ ] **Accept/reject suggestions & true cell-anchored comment creation** — API-impossible
  (proven by probe); reserved for a future `PlaywrightBackend`. `ApiBackend` raises
  `UnsupportedOperation`.
