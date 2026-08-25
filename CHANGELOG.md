# Changelog

## 2026-08-25 — v0.3.1 (the unauthorized message is now actionable)

An unauthorized server starts by design, so its error text is the entire user experience.
That text now carries everything needed to act on it:

- **Offers the no-terminal path first** — call `authenticate` — then the CLI as fallback.
- **Gives a command that can be pasted verbatim**, using the launcher's absolute path from
  `argv[0]`. A bare `csa-google-workspace-mcp` is useless where the launcher is not on PATH,
  which is the normal case on Windows: pipx installs somewhere PATH does not reach until a
  new shell.
- **Says where it looked**, naming the token path.
- **Tells the model to ask the user and wait**, and not to go hunting for credential files.
  Given only "no credentials", a capable model starts searching the filesystem — which is
  exactly what happened on the first real run.

The server's `instructions` now state the same protocol up front, so the model knows it
before the first failure rather than inferring it from an error.

## 2026-08-25 — v0.3.0 (authorize from inside the client)

- **New `authenticate` tool — browser consent without leaving your MCP client.** When a tool
  reports missing credentials, calling `authenticate` sends the Google consent URL to the
  client via **URL-mode elicitation** (MCP revision `2026-07-28`); you sign in, a loopback
  listener catches the redirect, and the token is cached. No terminal step.

  URL mode exists precisely for this: the sensitive exchange happens out-of-band and never
  passes through the model's context. Note this is *not* MCP's OAuth framework, which is
  HTTP-only and runs the other way round (authenticating a client **to** a server); this
  server authorizes **outbound** to Google, which for stdio the spec says to do from the
  environment.

  **Requires a client that supports URL elicitation** — Claude Code does (v2.1.76+); Claude
  Desktop does not yet. Where it is unavailable the tool degrades to the previous behaviour:
  a clear instruction to run `csa-google-workspace-mcp login`. And because both clients read
  the same token file, authorizing once in Claude Code also authorizes Claude Desktop.

- **`Settings.client_secrets`** (new, optional). Never needed to start the server or to
  refresh a cached token — a token carries its own client id and secret. It is used only to
  build a fresh consent URL for `authenticate`, and resolves from `CSA_GW_CLIENT_SECRETS` or
  `~/.csa_google_workspace/client_secret.json`.

- `create_server(get_workspace, settings=…)` — passing `settings` registers `authenticate`.
  Omitting it yields the previous nine-tool surface, so existing embedders are unaffected.

Internal: `_auth_flow.py` drives the loopback flow directly rather than through
`InstalledAppFlow.run_local_server()`, which prints the consent URL to stdout (the JSON-RPC
channel) and blocks the calling thread. The token exchange is given the full redirect URI so
oauthlib validates the `state` parameter.

## 2026-08-25 — v0.2.5 (`login` finds the client secrets by itself)

- **`login` no longer requires `CSA_GW_CLIENT_SECRETS`.** It falls back to
  `~/.csa_google_workspace/client_secret.json`, the path the CSA setup scripts already write
  to. Requiring an environment variable that points at a location this package itself chose
  only made users rediscover our own convention — and in practice it did: the first real run
  ended at `CSA_GW_CLIENT_SECRETS is not set`, with the file sitting exactly where the
  fallback now looks. The variable still wins when set, for anyone keeping the client
  elsewhere.

- **When nothing is found, the error says where it looked** — both the unset variable and the
  default path — rather than naming only the variable.

## 2026-08-25 — v0.2.4 (Python 3.14; install guidance)

- **Python 3.14 is tested and declared.** A `pipx` install picks the newest interpreter
  present, so 3.14 is what actually runs the MCP server in practice — while CI covered
  3.10–3.13 and the classifiers claimed the same. The full suite was run on 3.14 (269 passed)
  before claiming it; 3.14 is now in the CI matrix, in the trove classifiers, and in the
  required status checks so a failure there blocks a merge.

- **`pipx` is now the recommended install for the MCP server.** It is a CLI you run, not a
  library you import, so it wants its own environment: `pip` into a shared virtualenv works
  until another project disagrees about a dependency (`mcp>=2.1` here versus something else
  pinning `mcp<2.0` is a conflict people hit). `pipx` also gives the console script an
  absolute shebang, which is what makes it launchable from a GUI app. `pip` remains documented
  for embedding the *library* in your own application.

- **Claude Desktop guidance made concrete.** Claude Code runs in your shell; Claude Desktop is
  a GUI app inheriting launchd's `PATH`, which contains neither `~/.local/bin` nor Homebrew and
  where `python3` is macOS's 3.9 — below this package's floor. The troubleshooting entry now
  gives the literal `claude_desktop_config.json` snippet with an absolute path.

- **`SECURITY.md` reconciled with what shipped.** It previously called `from_oauth` +
  `token.json` "PoC/CLI scaffolding — not for server use", written before the bundled MCP
  server existed. The real distinction is *whose machine holds the token*: local single-user
  (a CLI, or this server over stdio) is fine; hosted multi-user is not. It also now states that
  the bundled server *is* the prompt-injection risk the threat model describes — untrusted
  document text reaching a model with write tools live — what the server does about it, and
  what it does not (there is no file allowlist yet; #82).

- Docs reconciled with reality throughout: the MCP spec marked implemented with *[as-built]*
  deltas, `research/mcp-protocol-notes.md` corrected (it still said to target `2025-11-25` and
  not to build against the `2026-07-28` release candidate — which was ratified, and which this
  server is built on), `TODO.md` phase 2 marked shipped with its honest deferred list, and the
  PyPI Trusted Publisher constrained to the `pypi` environment.

No library behaviour changes; the `--force` switch shipped in 0.2.1.

## 2026-08-25 — v0.2.3 (docs patch: MCP troubleshooting)

No code changes. The README is the PyPI long description and is frozen at each release, so a
docs fix only reaches users on a version bump — the same reason 0.1.1 existed.

- **Troubleshooting table** for the MCP server, covering five failure modes hit while
  standing it up, each written from the symptom a user actually sees rather than its cause:
  - `Error 403: org_internal` — the OAuth client is **Internal** to a Workspace organization
    and you signed in with an account outside it. Confirmed by observation, not just docs;
    it also settles that Internal genuinely covers **restricted** scopes. The realistic
    victim is not an attacker but someone with several Google accounts who picks the wrong
    one in the chooser.
  - `SERVICE_DISABLED` on some file types but not others — a scope grant is not API
    enablement, and it fails **per-API**, so Docs can work while Sheets 403s.
  - `login` reporting *"Already authorized"* while nothing works — a cached token issued by a
    different OAuth client; `login --force` is the fix.
  - Tool errors mentioning `no cached credentials` — the server starts without a token on
    purpose, so the remedy surfaces where it can be read.
  - Works in Claude Code but not Claude Desktop on macOS — GUI apps inherit a minimal `PATH`
    where `python3` is the system 3.9, below this package's 3.10 floor.

## 2026-08-25 — v0.2.2 (CSA-branded OAuth success page)

- **Branded consent-complete page.** After `login`, the browser now shows a CSA-branded page
  instead of `google_auth_oauthlib`'s plain "The authentication flow has completed." It uses
  the General CSA palette, Azo Sans via the CSA TypeKit with a full fallback stack (it still
  reads correctly offline), the official logo inlined verbatim, and `prefers-color-scheme`
  dark support.

  `success_message=` cannot carry markup — `_RedirectWSGIApp` hardcodes `Content-type:
  text/plain` — so the page is delivered by swapping that class for the duration of the flow.
  The swap changes the response body only and still records `last_request_uri`, which carries
  the authorization code and the `state` oauthlib validates. Every failure path falls back to
  the stock page, including a renamed upstream class: a cosmetic feature must not be able to
  break authorization.

- **Docs:** `CLAUDE.md` now states the project's **public-by-default** policy explicitly —
  everything is developed in the open except credential-bearing material, which is exactly one
  artifact (the CSA OAuth client) and only because Google's API ToS require it.

No library behaviour changes.

## 2026-08-25 — v0.2.1 (`login --force`; wrong-client detection)

Fixes a failure that is invisible by construction: a cached token can be valid, unexpired,
and carry exactly the required scopes while having been issued by a **different OAuth
client**. `login` reused it and reported success, and every subsequent API call ran against
the wrong project's quota and consent screen. Nothing errored — found in real use within an
hour of 0.2.0.

- **`csa-google-workspace-mcp login --force`** (also `-f` / `--reauth`) — bypass the cached
  token and re-consent. It skips the cache *read* rather than deleting anything: the old
  token is replaced only once a new one is in hand, so a cancelled or failed consent leaves
  the previous credentials working.
- **Wrong-client warning** — `login` compares the cached token's `client_id` against the
  configured client secrets and says so when they differ, naming both and the remedy.
  Nothing else surfaces this: OAuth accepts a refresh token from whichever client issued it,
  so provenance is not visible at runtime.
- **Honest messaging** — `login` no longer announces "Opening a browser" before checking
  whether it needs to; it reports `Already authorized` and how to re-authorize.
- **Library (additive, backward-compatible):** `auth.load_credentials(..., force=False)` and
  `Workspace.from_oauth(..., force=False)`. Existing calls are unaffected.

The default remains reuse-if-usable, because the installer path calls `login` and should not
open a browser on every run.

Also in this release: `INTERFACE-RESOURCES.md`, an inventory of the interfaces this repo
provides and consumes.

## 2026-08-24 — v0.2.0 (built-in MCP server)

Phase 2: a **built-in Model Context Protocol server**, so an AI client (Claude Code, Claude
Desktop) can read and triage comments on Google Docs/Sheets/Slides through the library. The
server is a delivery layer only — it adds no document logic.

**Install:** `pip install "csa-google-workspace[mcp]"` · **Run:** `csa-google-workspace-mcp`

- **Nine tools**, all with structured output (`outputSchema`) and read-only/destructive
  annotations: `open_document`, `read_text`, `list_comments`, `get_comment`,
  `comments_by_cell`, `create_comment`, `reply_comment`, `resolve_comment`, `reopen_comment`.
- **`csa-google-workspace-mcp login`** — a separate, interactive subcommand is the *only* path
  that opens a browser. The server itself never prompts: under stdio, stdout is the JSON-RPC
  channel, and `InstalledAppFlow.run_local_server()` both `print()`s the consent URL into it
  and blocks on the redirect. The MCP spec agrees — stdio servers "SHOULD NOT" do protocol
  OAuth and should "retrieve credentials from the environment".
- **`auth.load_cached_credentials(token_path, read_only)`** (new, public) — non-interactive
  credential load: reuse the cache, refresh if stale, raise `AuthError` rather than prompt.
  It deliberately contains no `InstalledAppFlow` branch, so a server cannot reach interactive
  consent even by mistake. `load_credentials()` is unchanged.
- **Credentials resolve on first tool use, not at startup**, so a server with no token still
  starts and reports the remedy as a tool error. An MCP client renders a startup crash as an
  opaque "server failed to start", where nobody would read it.
- **One `Workspace` per thread.** MCP SDK 2.x runs sync tool handlers on worker threads, so a
  shared `Workspace` would put a `googleapiclient` client on several threads at once. The
  provider hands each thread its own.
- Requires **`mcp>=2.1`** and targets protocol revision **`2026-07-28`**. (`mcp.server.fastmcp`
  was removed in SDK 2.0; `FastMCP` is now `MCPServer`.)
- Environment: `CSA_GW_TOKEN`, `CSA_GW_READ_ONLY`, and `CSA_GW_CLIENT_SECRETS` (needed by
  `login` only — a cached token carries its own client id/secret).

Library behaviour is otherwise unchanged; the core package still has no dependency on `mcp`.

## 2026-07-23 — v0.1.2 (hardened release pipeline; no library changes)

First release through the hardened supply-chain pipeline — no changes to the library code
itself. This release exists to exercise and verify the pipeline:

- GitHub Actions **pinned to commit SHAs** (`checkout` v7, `setup-python` v7,
  `gh-action-pypi-publish` v1.14.1); Dependabot keeps them current.
- Release-time **security gate** (`pip-audit` + `bandit`) runs before publish.
- Publish runs through a protected **`pypi` environment** (manual approval).
- **PEP 740 attestations** emitted — this should be the first release whose PyPI files carry
  provenance.
- `main` is now branch-protected (required checks, no direct/force push, admins enforced).

## 2026-07-23 — v0.1.1 (docs patch)

- **README install fix.** Lead with the consumer install `pip install csa-google-workspace`
  (the PyPI page previously showed only the from-source `pip install -e ".[dev]"`); moved the
  editable install + test/lint commands and the live-suite instructions under a new
  **Development** section. No code change.

## 2026-07-22 — Split the interactive OAuth suite out (`tests/oauth/`)

The browser-login tests are now their own suite, separate from the API-integration tests,
because they need a human at a browser and touch the very sensitive cached OAuth token.

- Moved `tests/integration/test_oauth_live.py` → **`tests/oauth/test_oauth_flow.py`**.
- Own opt-in gate **`CSA_GW_OAUTH=1`** (distinct from `CSA_GW_INTEGRATION`), so it never runs
  by accident and is clearly the interactive/sensitive tier. Run: `CSA_GW_OAUTH=1
  CSA_GW_CLIENT_SECRETS=… pytest tests/oauth/`.
- Three tiers now: unit (offline, gates CI) · integration (real API) · oauth (interactive).

## 2026-07-22 — Live-suite coverage for Tier 3 + a dedicated OAuth e2e suite

Test-only; all gated behind `CSA_GW_INTEGRATION` (no runtime change):

- Extended the live suite to exercise the Tier 3 additions against real Google:
  `Sheet.append_rows`, multi-tab `as_text` (`# <tab>` headers + `tab=`), and
  `Slides.insert_text` / `Slide.shape_ids`.
- New **`tests/integration/test_oauth_live.py`** — end-to-end OAuth: a real `from_oauth`
  login that reaches Google, token-file permissions (no group/other access), and the
  `read_only` session contract (reads succeed, writes raise `ReadOnlyError`). Because the
  writable login runs first, the read-only test reuses the cached token without re-prompting.
- Gated integration tests: 6 → 9.

## 2026-07-21 — Tier 3 API-surface additions

Closed the remaining within-scope content-write gaps (all `read_only`-gated, TDD):

- **Sheets `append_rows(a1_range, values, value_input_option="RAW")`** — `values.append`
  with `INSERT_ROWS`. Non-idempotent, so it is never auto-retried on 5xx (a retry could
  duplicate rows). Invalidates the cell-map cache like the other writes.
- **`Sheet.as_text(tab=None)`** now renders **every** tab by default (each prefixed with a
  `# <tab>` header when there's more than one), fixing silent first-tab-only truncation on
  multi-tab sheets. `tab=` selects a single tab (no header); single-tab output is unchanged.
- **Slides `insert_text(object_id, text, index=0)`** — per-shape text insertion, symmetric
  to `Doc.insert_text` but shape-addressed. **`Slide.shape_ids`** lists the text-capable
  shape objectIds to target. (A fuller shape-CRUD model stays out of scope; `batch_update`
  remains the escape hatch.)

## 2026-07-21 — Dev tooling: ruff + mypy + coverage gates

Formalized the quality bar as enforced CI gates (no runtime/API change):

- **ruff** (lint): rule set `E,F,W,I,B,UP`, line-length 120, ignoring `E702` (the
  deliberate one-line `x; y` style). No auto-formatter — the dense style is intentional.
- **mypy**: `check_untyped_defs`, google/defusedxml marked as missing-stubs. Fixed the
  real gaps it surfaced — typed the injected `_backend`/`_file_id`/`_comment_id` fields on
  `Comment`/`Reply` and declared `CommentsMixin`'s subclass-provided attributes.
- **coverage** (`pytest-cov`): enforced on the CI matrix with `fail_under = 85` (total
  ~87%; the gap is the integration-only `ApiBackend` calls + interactive OAuth flow).
- CI now has a dedicated `lint` job (ruff + mypy) alongside the 3.10–3.13 `test` matrix.

## 2026-07-21 — Packaged for PyPI (v0.1.0)

First release-ready packaging pass, alongside the correctness fixes from an external audit.

- **PyPI metadata.** `pyproject.toml` now carries `readme`, an SPDX
  `license = "Apache-2.0"` + `license-files`, `authors`/`maintainers`, `keywords`,
  trove `classifiers` (incl. `Typing :: Typed`), and `[project.urls]`. The version is
  single-sourced from `csa_google_workspace.__version__` via `dynamic`/`attr` (no more
  two-places-to-bump drift). `python -m build` + `twine check` pass for both sdist and wheel.
- **`py.typed` (PEP 561)** ships, so downstream mypy/pyright consume the inline type hints.
- **Typed errors from `open()`.** `ApiBackend.get_file_metadata` now routes through the
  error translator; the first call no longer leaks a raw `HttpError` on a
  missing/forbidden/service-disabled file — it raises the typed `NotFoundError` /
  `AccessError` / `ServiceDisabledError` the spec promises.
- **Cell-map degrade is now a recorded warning** (stdlib `logging`), not silence — so an
  export-cap / access / malformed-XLSX failure is distinguishable from a genuine no-match.
- **CI.** GitHub Actions runs the unit suite on Python 3.10–3.13 for every push and PR
  (the live Google suite stays gated behind `CSA_GW_INTEGRATION`).
- **License consolidated to Apache-2.0.** A single `LICENSE` (the earlier dual
  MIT/Apache `LICENSE-MIT` + `LICENSE-APACHE` files were removed).
- Version bumped `0.0.1 → 0.1.0`.

## 2026-07-20 — Lifecycle & suggestions probes (empirical)

Two new live-API probes under `experiments/`, each with a `RESULTS.md`, plus an
`experiments/README.md` index and shared-setup guide.

- **`experiments/comment-lifecycle/`** — exercised the full comment/reply cycle on a
  self-created, self-trashed throwaway Sheet. **Corrected two things in the reference doc:**
  (1) `resolved` is **absent** on a fresh comment, not `false` — it appears only after a
  resolve/reopen action (treat missing as false); (2) delete is soft and strips **author**
  as well as content, and the comment drops out of `comments.list` unless `includeDeleted=true`.
  Also confirmed: action-replies (`resolve`/`reopen`) can be **content-less**, `author.me`
  exists, and `emailAddress` is withheld even when requested.
- **`experiments/docs-suggestions/`** — settled the Docs "suggesting mode" question against a
  live doc. **Reading suggestions works** (via `suggestionsViewMode`, incl. accepted/rejected
  text previews), but **accepting/rejecting is impossible via the API** — proven by enumerating
  the entire Docs API surface (3 methods, 40 `batchUpdate` request types → zero suggestion ops).
  Suggestion **author/timestamp is not exposed**. Bonus: Docs comments carry `kix.*` anchors
  **and populated `quotedFileContent`**, so Docs comment→location mapping is trivial (unlike Sheets).
- **New reference:** `research/docs-suggestions-reference.md` (suggestions are read-only;
  no accept/reject; author unavailable; UI-automation is the only path to accept/reject).
- **Setup finding:** a correctly-scoped OAuth token still 403s with `SERVICE_DISABLED` until
  each API (Docs/Sheets/Slides) is separately enabled in the Cloud project — scope ≠ enablement.

## 2026-07-09 — Structured comment extractor

Added `experiments/anchor-probe/extract_comments.py`: extracts **all comments from any Drive file type** (Docs/Sheets/Slides/Drawings/blobs) into structured JSON — author, timestamps, content/htmlContent, resolved/deleted, quotedFileContent, raw anchor, and full reply threads (with `resolve`/`reopen` actions). For Sheets it resolves each comment's **A1 cell** best-effort via the XLSX-export join. Verified against the live sheet: correctly mapped the UI comment to B11 and the mislanded API comment to A1, with threads intact. Notes captured: `author.emailAddress` is often absent; @mentions are plain text in `content` but linkified in `htmlContent`. Extractor JSON output is gitignored (may contain real comment data).

## 2026-07-09 — Anchor probe run: empirical correction

Ran `experiments/anchor-probe` against a live sheet. Results captured in `experiments/anchor-probe/RESULTS.md`. This **corrected a conclusion** in the reference doc:

- **"Sheets anchors are opaque" was too strong.** A UI-placed comment's real anchor is `{"type":"workbook-range","uid":0,"range":"1453957822"}` — **structured**, format `workbook-range` (which a prior entry wrongly called folklore). But `range` is an opaque internal id, so the anchor is still **not A1-decodable**. Reworded §7 and the TL;DR accordingly; moved `workbook-range` out of the "folklore" list.
- **Write limitation confirmed empirically:** an API comment anchored to B11 was stored verbatim but landed on A1 in the export — the editor ignores anchor coordinates.
- **XLSX read path confirmed empirically:** comments export to `xl/threadedComments/threadedComment*.xml` (mirrored in `xl/comments*.xml`) with real A1 `ref`s (recovered `ref="B11"`). Sheets comments are *threaded comments*.
- **Resolved the a-bonus discrepancy:** its `{a:[{sht:{rng:{r,c}}}]}` parser shape is not what real UI comments return; the anchor is not an A1 source. Updated `server-landscape.md`.

## 2026-07-09 — Server landscape & anchor probe

Added, without changing existing conclusions:

- **`research/server-landscape.md`** — source-verified survey of MCP servers that handle Google comments (read from actual tool definitions, not READMEs). Ranked for "general Drive server with proper comments": **#1 a-bonus/google-docs-mcp** (only one that engineers around the Sheets limitation — cell-link + native cell note + read-side anchor mapping), **#2 taylorwilsdon/google_workspace_mcp** (broadest & most adopted, but file-level Sheets comments only, no delete/edit), **#3 piotr-agier/google-drive-mcp** (best Docs anchoring, no Sheets comments). Confirmed no server truly anchors Sheets comments — the ceiling is Google's Drive API. Official Google Workspace MCP has no comment tools.
- **`experiments/anchor-probe/`** — runnable Python script to empirically settle how Sheets comment anchors behave (create / dump-raw-anchor / xlsx-export), the one claim currently supported only by documentation.
- **Flagged an open discrepancy to verify:** a-bonus's `commentAnchor.ts` parses a concrete Sheets anchor shape `{a:[{sht:{sid,rng:{r,c}}}]}`. If real, UI-created Sheets comments are anchor-parseable, which would partly revise the reference doc's "anchors are opaque" conclusion. The probe will settle it; the reference doc is left unchanged until then.

## 2026-07-09 — Research refresh & consolidation

Verified the research against current Google Workspace documentation, the MCP specification, and the MCP server ecosystem (all as of July 2026), corrected what was wrong, and consolidated 5 overlapping documents into 3.

### Document structure

Consolidated to reduce duplication:

| Before | After |
|--------|-------|
| `Google Drive API Comment-Related Capabilities.md` + `report-claude.md` + `report-chatgpt.md` | **`google-drive-comments-reference.md`** — one canonical "how it works" reference |
| `Google Sheets Comments MCP Server - Design Document.md` | **`mcp-server-design.md`** — corrected, with a 2026 reality check |
| `llms-full.md` (scraped MCP docs) | **`mcp-protocol-notes.md`** — concise, current |

### Corrections

**Google Drive comments API**
- **Method count: 12 → 10.** 5 on `comments`, 5 on `replies`. There is **no `patch` method** in v3 — `update` uses the PATCH verb; `comments.patch`/`replies.patch` were v2-only.
- **`fields` parameter is REQUIRED** on every comments/replies method except `delete` (was not stated).
- **`resolved` is read-only** — resolve/reopen only via a reply with `action: "resolve" | "reopen"` (clarified).
- **Deletion is soft** for both comments and replies (`deleted: true`, content stripped) — confirmed.
- **Removed a fake OAuth scope.** `https://www.googleapis.com/auth/drive.comments` does not exist; corrected to the real `drive` / `drive.file` / `drive.readonly` scopes.
- **Switched v2 → v3 examples.** `report-claude.md` used deprecated v2 endpoints (`/v2/files/...`, `comments.insert`); v3 is current. (v2 is legacy/migration-encouraged but has no announced sunset date as of July 2026.)

**The `anchor` field (the big one)**
- **Cell-anchored comments cannot be created via the Drive API.** Google Workspace editors treat API-set anchors as *unanchored*; a Sheets comment created via the API lands at file level, not on the target cell. This invalidates the original "spatial index for writes" architecture.
- **Reading a comment's cell requires an XLSX-export-and-parse detour**, not the `anchor` field, which is opaque for Sheets.
- **Debunked folklore anchor formats.** `R1C2`, `sheet_id=...&range=A1`, and the `cell_classifier`/`range_classifier` JSON in the original doc had no primary source and were removed / relabeled as speculative.
- Clarified **notes vs comments**: notes (Sheets API) are genuinely cell-anchored; comments (Drive API) are not.

**Market analysis**
- **"0% of MCP servers support comments / 100% greenfield / first-mover advantage" is false.** At least 5–6 servers now implement Google comment lifecycles (a-bonus, piotr-agier, taylorwilsdon's workspace server, dbuxton, and others). The obsolete "8 servers, 0% support" table was removed. The real unsolved problem — and the defensible differentiator — is reliable UI-visible/cell-mapped anchoring, which competitors document as broken or missing.

**MCP protocol**
- Current stable spec is **`2025-11-25`**, not `2025-06-18`.
- **Streamable HTTP** replaced the old HTTP+SSE transport (as of `2025-03-26`).
- Added notes on Elicitation, the OAuth 2.1 authorization framework, and structured tool output. Flagged the breaking `2026-07-28` release candidate.

### Method
Facts were verified against primary sources (Google's API reference and guides, the official MCP spec, and server source/READMEs). One area remains genuinely uncertain: the exact current status of Google Issue Tracker threads [#292610078](https://issuetracker.google.com/issues/292610078) and [#357985444](https://issuetracker.google.com/issues/357985444) — both are sign-in-gated, so the *behavior* they describe is confirmed but their live status labels could not be scraped.
