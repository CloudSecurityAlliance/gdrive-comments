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

## Phase 2 — the built-in MCP server — ✅ SHIPPED (v0.2.0–v0.2.3, 2026-08-24/25)

`csa_google_workspace.mcp` is on PyPI: a local stdio server on MCP revision `2026-07-28`
(SDK `mcp>=2.1`), with **nine tools** carrying structured output and read-only/destructive
annotations, per-user OAuth via a separate `login` subcommand, and a CSA-branded consent page.
Spec: [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](docs/superpowers/specs/2026-07-23-mcp-server-design.md).

Built directly from the spec without a separate plan file — the spec's §10 phasing served as
the task list.

**Deferred from v1, deliberately:**

- [ ] **Content-write tools through MCP** — Docs `replace_text`/`insert_text`/`append_text`/
  `delete_range`, Sheets `update`/`append_rows`/`clear`, Slides `insert_text`. The library API
  has them; the MCP layer exposes comment writes only. **Blocked on file allowlisting below** —
  exposing document mutation to a model over a full-Drive token, with no per-file scope, is the
  confused-deputy scenario #82 describes.
- [ ] **Docs suggestions** (`list_suggestions`) and the `as_text(suggestions=…)` preview.
- [ ] **The document-text Resource and comment-triage Prompt** — both in the spec, neither built.
- [ ] **A launcher shim for Claude Desktop on macOS.** GUI apps inherit a minimal `PATH` where
  `python3` is the system 3.9, below the 3.10 floor — so Desktop fails where Claude Code works.
  Documented in the README's troubleshooting table; no fix yet.
- [ ] **Verify the PowerShell setup scripts.** `CSA-Plugins/internal-setup/*.ps1` and the
  `DesktopSetup` Windows hook have never been executed — they were written on a machine with no
  `pwsh`. A Windows colleague should not be the first to find out.

- [ ] **File allowlisting — scope a `Workspace` to specific files and operations.**
  ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) Listed here
  rather than in the library-internal section below because **it is arguably a phase-2
  dependency, not a parallel nicety.** The locked phase-2 decision is *read + write on by
  default*, hedged with tool annotations and `CSA_GW_READ_ONLY=1`. That hedge is all-or-nothing:
  the only choices an operator gets are "this agent may write to everything you can reach" or
  "nothing". An allowlist is the missing middle, and it is what makes write-on-by-default
  defensible rather than merely convenient.
  **Shape settled 2026-08-21**: an explicit **write-allowlist of Drive URLs** — read stays as broad
  as the credentials allow, only mutation is gated. The goal is damage containment rather than
  confidentiality: the agent already sees whatever the user sees, so what must be bounded is what
  it can *break*. Keyed on URLs because that is what people paste (`parse_file_id` normalises to
  IDs internally). And the list is **curated, not per-user** — e.g. the CSA WG document URLs —
  which means a volunteer installs the tooling and it is physically incapable of damaging anything
  outside the list, whether or not they understand why. That is a better story than per-user config,
  because it does not depend on the least-equipped person making a good decision.
  **Cheap to build**: every one of the 25 `Backend` Protocol methods takes `file_id` first, so a
  wrapping `AllowlistBackend` enforces uniformly with no changes to existing methods, composed
  through the documented `Workspace(backend=…)` seam. `read_only` is the precedent — the
  allowlist is its fine-grained sibling and the two should be one mechanism, not two.
  **The MCP server also answers the hard half.** #82 notes that session scoping only means
  something if it is monotonically narrowing *and* set by the host rather than callable by the
  guest — otherwise an agent just widens its own scope. **An MCP server session is exactly that
  boundary**: the server constructs the scoped `Workspace` per session, and the client has no
  in-band way to broaden it. So "session-level allowlisting" has a concrete home in phase 2
  rather than being an open question.
  **Requirement surface is captured in full on #82** so nothing is rediscovered mid-build. Summary
  of what must be considered: **two independent dimensions** — capability gating *at all* (write /
  create-comment / update / delete / resolve / accept-suggestion, each on-or-off globally) and
  **per-URL scope** for each capability that is enabled — with the composition rule that **global
  is a ceiling and per-file grants narrow, never widen**. Plus the parts that decide whether it is
  actually usable: **obtaining the URLs** (folder enumeration as a *generator* producing a
  reviewable committed list, never as a live rule — folder-as-rule reintroduces TOCTOU when someone
  drops a file in), **config ergonomics** (plain-text and diffable so it reviews like code, a
  reason field per entry so "why is this writable" is answerable in six months, URL forms accepted
  as pasted, validation on load), **fail-closed behaviour** for every failure mode including the
  no-policy-configured default, **operational lifecycle** (immediate revocation, optional expiry,
  dead-entry detection, and new-file creation which probably sits outside the list since it cannot
  damage anything existing), and **observability** — log allowed *and* denied with the matching
  rule, since denials are the security signal, plus a dry-run mode answering "what would this run
  touch" before it touches anything.
  **Driver**: CSA-Plugins#27 wants agentic read/edit/comment on live Google Docs authored by
  volunteers. The blocker there is not capability — this library already has it — it is that
  handing volunteers unscoped write access to their own Drive is not defensible. Prevention has
  to carry the weight, because Docs has no selective undo.

Deferred out of phase 2, recorded during the 2026-08-05 auth revision (spec §11):

- [ ] **Hosted / server-side login for the MCP server.** A remote, multi-user server (Streamable
  HTTP + the MCP OAuth 2.1 resource-server model, per-user token custody in a real secret store)
  is a **separate design**, not a flag on the local one — it inverts the token-custody model
  `SECURITY.md` is built around. v1 is local, self-hosted, single-user.
- [ ] **Credential provenance — decide whether CSA ships a verified OAuth client.** Users supply
  their own client secrets today, because full `.../auth/drive` is a *restricted* scope: a public
  CSA-owned client would need Google app verification **plus** an annual CASA third-party security
  assessment, and the API ToS forbid embedding credentials in an open-source project. This is a
  cost/ownership call, not an engineering one — `main()` reads `CSA_GW_CLIENT_SECRETS` either way,
  so it can land any time without redesign.

Note the scope shift: everything *below* this section is library-internal, but phase 2 is a
**delivery layer over** the library — it adds no document logic, only maps MCP primitives
onto the existing `Workspace` API.

## Publish — ✅ DONE

- [x] **Release automation** — `.github/workflows/release.yml` (Trusted Publishing / OIDC);
  steps in `RELEASING.md`.
- [x] **Published to PyPI** — `0.1.0`, `0.1.1` (docs patch), and `0.1.2` (first release
  through the hardened pipeline — attestations + env gate) all cut via `gh release create`
  → CI-built, tagged, GitHub-Released, uploaded over OIDC. Page:
  <https://pypi.org/project/csa-google-workspace/>. Since then: `0.2.0`–`0.2.3` (the MCP
  server and its follow-ups). Current `__version__`: **0.2.3**.

## Release-process / supply-chain hardening — ✅ DONE

From a 2026-07-23 release-process review (re-verified). Fixed in PR #69 (code) + repo-admin
settings, worst-first:

- [x] **⚙️ `main` is protected.** Branch protection via API: required status checks (`lint`,
  `test (3.10–3.14)`, `security`), PRs required, direct + force pushes blocked, **enforced for
  admins**. `required_approving_review_count = 0` so the solo/AI PR flow still merges (checks
  gate, no human-approval bottleneck). *Residual (optional):* also require the CodeQL contexts,
  and/or raise the review count if a second reviewer is ever available.
- [x] **🔧 Actions pinned to commit SHAs** (PR #69) — `checkout` v4, `setup-python` v5,
  `gh-action-pypi-publish` v1.14.1, across `tests.yml` + `release.yml`; Dependabot keeps them current.
- [x] **🔧+⚙️ Environment gate on publish** — protected `pypi` GitHub Environment (required
  reviewer: repo owner) + `environment: pypi` on the publish job (PR #69). **Residual now closed
  (2026-08-25):** the PyPI Trusted Publisher is constrained to environment `pypi` (was `(Any)`).

  Worth recording *why* this mattered rather than just that it is done. While the publisher
  accepted any environment, the approval gate was enforced only by a line of YAML **in the repo
  being published** — anyone able to edit `.github/workflows/release.yml` could drop
  `environment: pypi` and PyPI would still accept the upload. The control guarding releases was
  itself guarded by the thing it protects. Constrained at the registry, removing that line now
  *breaks* publishing instead of bypassing review: a convention became an invariant. Same move as
  `auth.load_cached_credentials` simply not containing the interactive branch.

  PyPI had been emailing this recommendation after every publish since 0.1.2 (five times).
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
