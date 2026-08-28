# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this repository is

`csa-google-workspace` — a **Python library** (import name `csa_google_workspace`) for managing **comments** and **content** on Google **Docs, Sheets, and Slides**. It is **feature-complete for its scoped roadmap** and live-verified end-to-end against real Google (the gated suite in `tests/integration/`); remaining work is tracked polish + explicit deferrals.

It is meant to be **embedded in AI tooling** — MCP servers, agent/LLM plugins, review bots, automation services — that read, triage, and write back Google Workspace comments/content. The `Workspace(backend=…)` seam + `Backend` protocol (run-as-a-service / DI) exist for exactly that.

- **Shipped (all live-verified; the six phase plans are in `docs/superpowers/plans/`):** comment management (list/filter/create/reply/resolve/reopen/edit/soft-delete); content read (`as_text`/`export`, `Doc.paragraphs`, `Sheet.values`/`tabs`, `Slides.slides`/notes); content write (Docs `replace_text`/`insert_text`/`append_text`/`delete_range`; Sheets `update`/`append_rows`/`clear`; Slides `replace_text`/`insert_text` + `Slide.shape_ids`; `batch_update` on each; all `read_only`-gated); Sheets comment→cell mapping (`Comment.location`, `sheet.comments_by_cell`, `create_comment(cell=)` deep-link); Docs suggestions read (`Doc.suggestions`, `as_text(suggestions="accepted"|"rejected"|"inline")`).
- **Deferred (tracked, not bugs):** `Location.tab` resolution (multi-tab cell disambiguation via `workbook.xml`+rels); a caching pass (accessors re-fetch per call, by design); accept/reject of suggestions & true cell-anchored comment creation — API-impossible, reserved for a future `PlaywrightBackend`.

**Phase 2 — the built-in MCP server (`csa_google_workspace.mcp`) — shipped in v0.2.2.** A local stdio server: **34 tools** as of v0.30.6 (it shipped with nine), each with structured output and read-only/destructive annotations, per-user OAuth, an `[mcp]` optional extra, and the `csa-google-workspace-mcp` console script. Spec: [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](docs/superpowers/specs/2026-07-23-mcp-server-design.md) — read it before touching the module; its architecture deliberately **mirrors the library's own composition** (`create_server(get_workspace)` parallels `Workspace`; per-axis `register_*` tool producers parallel `CommentsMixin` / `documents/`).

Five SDK facts that cost time to find, all verified against `mcp` 2.1.0 rather than docs: **`mcp.server.fastmcp` no longer exists** (`FastMCP` became `MCPServer` in SDK 2.0); **sync tool handlers run on worker threads** (`anyio.to_thread.run_sync`), which is why the `Workspace` provider is thread-local — a shared one would put a non-thread-safe `googleapiclient` client on several threads; **a plain exception becomes `UnexpectedToolError` with the message suppressed**, so user-facing text must be raised as the SDK's `ToolError`; and **a bare `dict` return is not serializable for structured output**, hence the `TypedDict`s in `_schemas.py` (which must come from `typing_extensions` below Python 3.12, or pydantic silently emits no schema); and **a pydantic `Field(alias=…)` on a tool parameter is a trap** — the published schema shows the alias and then every call fails, because the SDK dumps the validated model *by alias* and calls `fn(**kwargs)`, so the handler receives `fileId=`, raises `TypeError`, and surfaces as a message-suppressed `UnexpectedToolError`. A camelCase wire name must be the **literal** Python parameter name. (Also: `Tool.input_schema`, not `inputSchema` — renamed in 2.x.)

The MCP server also **describes itself**: `mcp/_resources.py` renders `csa-gw://config` (the live effective policy) and `csa-gw://help/configuration` (the reference), and `_tools/config.py` is the same information as a tool. All three omit allowlist *reasons* — those are for whoever reviews the config, not for the model's context.

**Still not exposed through MCP:** the document-text Resource and the comment-triage Prompt — both conveniences, neither a capability. **Docs suggestions landed in v0.20.0** (`list_suggestions` + `read_file_content(suggestions=)`), which closed gate B2 and with it the last functional gap between the library and the server. Content-write tools landed in v0.13.0 and the file lifecycle in v0.15.0, so **every tool Google's Drive MCP server or the claude.ai Drive connector offers is now here**, under the same names — with the three Google declines to ship (`update_file`, `share_file`, `trash_file`) off unless an operator names each capability. **File allowlisting (#82) shipped its first control** in v0.7.0–v0.10.0 (capability gating + two fail-closed URL lists + named profiles); what remains of it — folders, per-capability scope, expiry, dead-entry detection, dry-run — is in `TODO.md` under A4.

Earlier drafts called this a *TypeScript* MCP server and *comments-only* — both obsolete; ignore that framing wherever it survives in older docs.

## Where things live

- **`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`** — the authoritative **library** design spec (scope, architecture, API surface, error model, phasing). Start here.
- **`docs/superpowers/specs/2026-07-23-mcp-server-design.md`** — the authoritative **MCP server** spec (phase 2). Supersedes `research/mcp-server-design.md`.
- **`docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md`** — a **shape review before growth**: the library today has one axis (per-file) and the roadmap adds a second (account-scoped — search, create, changes). Read it before starting anything from `TODO.md`'s roadmap; it says where each item lands and what must not happen.
- **`docs/superpowers/plans/`** — the six phased, bite-sized TDD implementation plans (foundations, comments, …). Each shipped phase was built from its plan; phase 2 still needs its plan written.
- **`src/csa_google_workspace/`** — the library (see layout below).
- **`TODO.md`** — the post-roadmap backlog: a *menu*, ordered by leverage-to-effort, with the explicit deferrals and their rationale. Check it before proposing "missing" features — most are already recorded decisions.
- **`SECURITY.md`** — the threat model. **Prompt injection through document/comment content is the named primary risk**, and it constrains any change that surfaces content to a model (all of phase 2). Also: token custody, scope breadth, per-user isolation.
- **`research/`** — canonical API-behavior references: `google-drive-comments-reference.md` (Drive comments), `docs-suggestions-reference.md` (Docs suggestions), `server-landscape.md` (prior art), `drive-mcp-servers-and-api-surface.md` (what the two Drive MCP servers actually do, read from live schemas — their `update_file` is metadata-only and neither can edit existing content — plus the full Drive v3 / Docs v1 method inventory). `mcp-server-design.md` / `mcp-protocol-notes.md` are **earlier** MCP notes, kept for reference only — the `docs/superpowers/specs/` one above is authoritative.
- **`experiments/`** — runnable empirical probes, each with a dated `RESULTS.md`. **Probe beats docs:** when Google's documentation and a probe disagree, the probe wins, and the finding is folded back into `research/`.

**This file is the single guide for agents working here.** A duplicate `AGENTS.md` was removed in favour of keeping one file correct — it had drifted into stating the opposite of reality on tooling. If another harness needs an `AGENTS.md`, make it a pointer to this file rather than a second copy.

## Code layout (`src/csa_google_workspace/`)

- `workspace.py` — `Workspace` entry point + `open()`/`open_by_url()` (MIME-sniff → typed subclass).
- `auth.py` — OAuth installed-app flow, scope selection, re-consent detection.
- `backend.py` — `Backend` protocol; `ApiBackend` (real Google APIs) + `FakeBackend` (in-memory, powers all unit tests).
- `_services.py` — lazy Google API client registry. `_errors.py` — `HttpError`→typed translator + retry.
- `base.py` — `Document` base + `CommentsMixin`. `documents/` — `Doc`/`Sheet`/`Slides` (per-type content read/write).
- `comments.py` — `Author`/`Reply`/`Comment`/`Location`/`CommentCollection` + in-place mutation.
- `policy.py` — **#82**: capability names, `Policy` (capabilities **and** the file allowlist), and `PolicyBackend` (a `Backend` wrapper). `_GATES` must name every `Backend` method with a `Gate(capability, file_scoped)` — an unlisted one is *refused*, not delegated, and `tests/test_policy.py` fails in CI if the protocol grows past it.
- `allowlist.py` — the write allowlist: parse/validate a plain-text list of document URLs. **Folder URLs are a loud error**, and a bare file id is rejected (unlike `Workspace.open()`) because it cannot be told apart from a typo. See `TODO.md` → "Folders in the allowlist" before touching this.
- `permissions.py` — `Permission` + `PermissionsMixin` (`doc.permissions`). A uniform Drive concern, so a mixin — the same shape as `CommentsMixin`.
- `files.py` — **the account axis**: `FileCollection` (`workspace.files`) + `FileRef`. The one place that is *not* reached through `open(file_id)`, because you cannot open a file you are searching for.
- `suggestions.py` — `Suggestion` + read-only suggestion extraction (grouped by suggestion id).
- `_cellmap.py` — Sheets comment→cell mapping: XLSX-export → parse `threadedComments` (defusedxml) → A1.
- `_content.py` — plain-text extraction walkers for Docs/Slides.
- `exceptions.py` — typed error hierarchy.

## Critical architectural facts

1. **Comments are a Google Drive API v3 concern**, uniform across Docs/Sheets/Slides — one API for all three (the "uniform axis"). Content is the "variant axis" (three separate APIs: Docs v1, Sheets v4, Slides v1). Sheets *notes* are a different, out-of-scope thing.
2. **Probe-verified comment quirks the code depends on** (see `experiments/comment-lifecycle/`): `resolved` is **absent** on a never-resolved comment → treat missing as `False`; soft-delete strips **both `content` and `author`** (models are `Optional`); resolve/reopen is an **action-reply** (never a PATCH) and may be **content-less**; `author.email` is usually absent even when requested.
3. **Sheets `anchor` is `workbook-range` — structured but NOT A1-decodable** (opaque range id). You cannot create a cell-anchored comment via the API, and mapping a comment→cell requires an **XLSX-export-and-parse** detour (Phase 4). Earlier "`R1C2`/parse-to-A1" framing was debunked folklore. See `research/google-drive-comments-reference.md` §7.
4. **Docs suggestions are read-only** — the Docs API has **no accept/reject endpoint** (proven by full API enumeration) and exposes no suggestion author. Accept/reject is a future `PlaywrightBackend` concern. See `research/docs-suggestions-reference.md`.
5. **`Backend` seam:** API-first, with UI-automation (`PlaywrightBackend`) reserved for the genuinely API-impossible ops (accept/reject suggestion, true cell-anchored comment). `ApiBackend` raises `UnsupportedOperation` for those today.
6. **Writes are ON by default**, gated by `read_only` (which also narrows to `.readonly` OAuth scopes). **Caching is OFF by default** (the tool is used in live multi-reviewer sessions where a self-only-invalidated cache goes stale). No persistent storage of comment content.
7. **Three entry points:** `Workspace.from_credentials(creds)` (BYOD), `Workspace(backend=…)` (DI / run-as-a-service), `Workspace.from_oauth(...)` (interactive login → delegates to `from_credentials`).

## Invariants that fail silently — check these when editing

These are the things no test will catch for you unless you add one.

1. **Every write goes through `_errors.call(..., idempotent=False)`.** Only 429 is retried for non-idempotent calls; 5xx is not, because the mutation may already have landed server-side (`_errors.py:74`). A new `ApiBackend` write method that omits the flag silently gains a retry that can double-apply.
2. **The domain models have hand-written, redacting `__repr__`s** (`comments.py`, `suggestions.py`) — no document text, no quoted content, no author email, because embedders log these objects. Guarded by `tests/test_repr_redaction.py`. Never let `@dataclass` regenerate one.
3. **`tests/test_backend_conformance.py` is a seam guard.** `FakeBackend` powers *every* unit test, so a method added to `Backend`/`ApiBackend` but not the fake would leave the whole suite exercising a stale double. That test reflects over the Protocol and compares signatures; keep the three in lockstep.
4. **Behavior only `ApiBackend` has needs a stub-service test, not a `FakeBackend` test** — see `tests/test_apibackend_contract.py` / `test_apibackend_errors.py` (pagination, non-idempotent wiring, `HttpError` translation). This is the one blind spot of the fake/real seam, and it is exactly how `Workspace.open()` once leaked a raw `HttpError` past a fully green suite.
5. **Dispatch on type happens in exactly one place:** `MIME_TO_TYPE` / `subclass_for_mime` (`base.py`). To let a document type enrich comments, define the optional `_locate_comment(raw)` hook (as `Sheet` does) — `CommentsMixin.comments` picks it up via `getattr`. Don't add `if doc.type == …` ladders; the MCP spec forbids them in the delivery layer too.
6. **Writes are guarded in two layers:** `CommentsMixin.create_comment` and `Document._require_writable()` raise `ReadOnlyError` *before* the backend call. Every new mutating method must call the guard itself — nothing enforces it centrally.
7. **A new `Backend` method needs a `policy._GATES` entry.** `PolicyBackend` fails *closed* — an unlisted method raises rather than delegating — so forgetting one turns the method off rather than leaving it unguarded. `tests/test_policy.py::test_every_backend_method_has_a_declared_gate` catches it, but the decision (which capability? or `None` for a read?) is yours.
8. **A `Comment`/`Reply` built via `from_api()` is detached** and raises `DetachedError` on mutation. Models obtained through a `Workspace` carry the backend; hand-built ones don't.
9. **Never `str(value or "")` on user data that can legitimately be `False` or `0`.** A spreadsheet cell is *typed*: `openpyxl` returns a TRUE/FALSE cell as Python `True`/`False`, and `False or ""` is `""` — so an instruction silently became an absence, and a boolean `FALSE` meant the opposite of a typed one (#161). What hid it for a whole release is the **asymmetry**: `True or ""` is `True`, so the truthy branch worked *by accident* and only half the behaviour was broken — half your tests pass, which reads as "mostly fine". Any three-state field with a falsy member has this shape, and it is not only spreadsheets: JSON `false`, form values, and a `0` from anywhere do it too. `_apply._norm` now handles `bool` **before** `int`, because `bool` subclasses `int` and an `isinstance(x, int)` check catches booleans first otherwise.
10. **A guard at one layer does not protect the layers above or below it.** `_apply.decision()` is deliberately three-state so "not decided" cannot be confused with "no" — the module docstring records why. The hazard then came back **twice anyway**: once *below* it in `_norm`, which discarded the value before `decision()` ever saw it (#161), and once *above* it in the tool docstring, which told a model that `false` meant "leave it" (#162) — inviting through the front door the exact input the type was built to reject. When you defend against something, ask what reads the value **before** your guard, and what tells the caller **what to send**. A type is not a contract with the model; the description is.

## Commands

```bash
pip install -e ".[dev]"        # install (src/ layout, Python >=3.10)
pytest -q                       # unit suite — no network, no credentials (uses FakeBackend).
                                # Currently ~730 passed, 12 skipped, a few seconds. The 12 skips
                                # are the two gated suites below (9 integration + 3 oauth) —
                                # `-rs` shows why. A skip count of 0 means a gate leaked and they
                                # RAN for real, against somebody's actual Drive.
ruff check src tests && mypy    # lint + type-check (the CI `lint` job). mypy needs no args —
                                # pyproject pins files = ["src"].

# A single file / test / pattern:
pytest -q tests/test_cellmap.py
pytest -q tests/test_cellmap.py::test_location_from_ref_computes_row_col
pytest -q -k cellmap

# What CI's `test` job actually runs. NOTE: plain `pytest -q` does NOT enforce the
# fail_under=85 coverage gate — coverage only runs (and only fails) with --cov:
pytest -q --cov --cov-report=term-missing

# Live API suite (real Google; opt-in). Needs a cached token or a first-run browser login:
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/

# Interactive OAuth suite (SEPARATE — needs a human + touches the sensitive cached token):
CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

Three test tiers: **unit** (`tests/`, offline, gates CI) · **integration** (`tests/integration/`,
real Google API, `CSA_GW_INTEGRATION=1`) · **oauth** (`tests/oauth/`, interactive browser
login + token-file handling, `CSA_GW_OAUTH=1`). The latter two skip unless opted in.

## Public by default

**This project is developed in the open.** Code, specs, plans, design rationale, issues,
CHANGELOG, and releases all live in this public repository. That is a deliberate policy, not
an accident of where the repo happened to be created.

**The only thing that goes somewhere private is credential-bearing material.** Today that is
exactly one artifact: the CSA OAuth client, which lives in the private
`CloudSecurityAlliance-Internal/CSA-Plugins` repo because [Google's API
ToS](https://developers.google.com/terms) forbid embedding developer credentials in open
source projects. Nothing else is withheld — not internal rationale, not security findings,
not the deployment path, not the fact that CSA uses this.

**The test is narrow and mechanical:** *does this artifact contain a credential?* If no, it
is public. "It reveals how we work", "it mentions an internal repo", or "it would be
embarrassing" are not reasons to make something private.

Two things follow from that, and both have already come up:

- **Obscurity is not a control.** The public `DesktopSetup` scripts name the private repo and
  the PyPI package openly; what protects the credential is *repo access*, enforced by a `gh
  api` probe that 404s for non-members. Renaming a file to look innocuous would conceal
  nothing from anyone reading the public half, while training people to run vaguely-named
  scripts that fetch credentials — a bad reflex to build anywhere, and a worse one at a
  security organisation.
- **Security findings get written down, publicly.** This repo's history records real ones —
  a stdout write that would corrupt the JSON-RPC channel, a cached token silently bound to
  the wrong OAuth client, a `TypedDict` that fails only below Python 3.12. Each is in a
  commit message and a CHANGELOG entry because someone hitting the same thing should be able
  to find it. `SECURITY.md` states the threat model for the same reason.

If a change genuinely cannot be public, say why explicitly in the PR rather than routing
around it quietly.

## Working in this repo

- **Branch + PR for every change** (never commit to `main`); merge when CI is green. Branch names use conventional prefixes (`feat/`, `fix/`, `docs/`, `chore/`).
- **Commits** use conventional prefixes with short imperative subjects — the set actually in use is `docs:` · `feat:` · `fix:` · `test:` · `ci:` · `chore:` · `security:` · `enh:` · `release:` (e.g. `fix: preserve deleted comment metadata`). A PR body should say what behavior changed, which tests were run, link the related plan/spec, and call out any Google API or credential implications.
- **Public API is the package root.** Anything users are meant to touch is re-exported from `csa_google_workspace/__init__.py` and listed in `__all__` — including the types embedders need for custom backends (`Backend`, `Document`, `CommentCollection`, `DetachedError`). Adding a user-facing type means adding it there. Note that `tests/test_public_api.py` only asserts a required **subset** of `__all__` — it will not catch a new type you forgot to export, so that step is on you.
- **CI** (`.github/workflows/tests.yml`, runs on every PR): a `lint` job (ruff + mypy), a `test` matrix (pytest + coverage, Python 3.10–3.14, `fail_under=85`), and a `security` job (`pip-audit` + `bandit`). GitHub **CodeQL** default-setup also runs. Two gotchas seen: CodeQL flags `"host" in url`-style substring checks (`py/incomplete-url-substring-sanitization`) even in test assertions; and an OAuth **scope grant ≠ API enablement** — a scoped token still 403s `SERVICE_DISABLED` until each API (Docs/Sheets/Slides) is enabled in the Cloud project.
- **New work follows the plan-then-execute rhythm:** write a spec/plan under `docs/superpowers/`, then implement TDD (unit tests via `FakeBackend`). Keep `README.md`'s manifest and `CHANGELOG.md` in sync. (Phase 1 — the library — and phase 2 — the MCP server — are both complete and on PyPI.)
- **Style:** ruff (`E,F,W,I,B,UP`, line-length 120) and mypy both gate CI. `E702` is **deliberately ignored** — one-line `a = …; b = …` is a pervasive house style here, not a defect; match it rather than splitting lines. The google-api/auth stack ships no stubs, so those imports are `ignore_missing_imports`.
- **Dependabot** opens `pip` + `github-actions` bumps and `dependabot-auto-merge.yml` auto-merges patch/minor once tests pass. Actions are **pinned to commit SHAs** — keep new ones pinned (`uses: owner/action@<sha>  # vX.Y.Z`).
- `main` **is branch-protected and enforced for admins**: `lint`, `test (3.10–3.14)`, and `security` must pass; direct and force pushes are blocked. Required approving reviews are set to 0 so the solo/AI PR flow merges on green checks.
- **Never commit** OAuth secrets (`credentials.json`, `token*.json`), probe transcripts, or **extracted document data** — real comment/document content pulled from Drive during probes or live runs. `.gitignore` already covers the known shapes; the last category is a judgement call, so watch for it in probe output. The client secret must be an **installed/desktop-app** OAuth client.

### Cutting a release

Publishing is automated via **PyPI Trusted Publishing (OIDC)** — never `twine upload` by hand. **A version bump means carrying it through to PyPI**, including approving the protected `pypi` environment gate — a staged release helps nobody. And **a security audit opens a new minor** (`x.y.0`), with subsequent batches of fixes from that same audit as patches (`x.y.1`, `x.y.2`), so the version says how far through remediation a release is. Both rules, with the approval command and the CDN-lag gotcha: [`RELEASING.md`](RELEASING.md).

1. **Bump `__version__`** in `src/csa_google_workspace/__init__.py` (the single source of truth; `pyproject.toml` reads it dynamically) and add a dated `CHANGELOG.md` entry — via the normal **branch + PR**, merged to `main` first.
2. **`gh release create vX.Y.Z`** creates the git tag + GitHub Release. **Publishing the Release** triggers `.github/workflows/release.yml`, which runs the suite, builds sdist+wheel, `twine check`s, and uploads to PyPI over OIDC (no token).
3. **Verify:** `https://pypi.org/project/csa-google-workspace/` shows the new version; `pip install csa-google-workspace` in a clean venv.

Invariants: the tag **must** equal the version (`vX.Y.Z` ↔ `__version__`). A PyPI version is **permanent** — yankable, never re-uploadable, so get it right. The README shown on PyPI is the long-description **frozen at that release** — doc fixes only reach PyPI on the next version bump. Full steps + one-time trusted-publisher setup: [`RELEASING.md`](RELEASING.md).
