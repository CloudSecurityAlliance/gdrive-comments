# Design spec — built-in MCP server (`csa_google_workspace.mcp`)

**Date:** 2026-07-23 · **Revised:** 2026-08-05 (auth model — §3, §5, §6, §7, §9, §10, §11)
**Status:** **Implemented** — shipped v0.2.0 (2026-08-24). Deviations from this document
are marked *[as-built]* where they matter; deferred items are listed in `TODO.md`.
**Phase:** 2 — a delivery layer over the shipped `csa-google-workspace` library (v0.1.2, on PyPI).

> **2026-08-05 revision.** The original §5 had `main()` perform browser OAuth consent on first
> run. That is unsafe under stdio and contradicts the MCP spec; §5 is rewritten around a separate
> `login` subcommand, with the rationale in §5.1. Knock-on changes: one small addition to the
> shipped library (`auth.load_cached_credentials`, §5) so "never interactive" is structural rather
> than a convention; a recorded sync-handler trade-off verified against the SDK source (§3); two
> new test guards (§9); and §11, which collects the open questions and deferrals.

## 1. Goal & context

Ship a **built-in Model Context Protocol server** so an AI client (Claude Desktop/CLI) can
review comments, read content, and edit Google Docs/Sheets/Slides through the library. The
server is a thin **delivery method** for the library — it adds no document logic, only
maps MCP tools/resources/prompts onto the existing `Workspace` API.

**Self-hosted by design.** The server runs on infrastructure the user controls (their own
machine for v1); it never routes Google credentials through a third-party SaaS host. This
matches the project's standing constraint on sensitive-Drive access.

Decisions locked in the brainstorm:
- **Transport:** local single-user **stdio** first; structured so Streamable HTTP can be
  added later without reworking the tools.
- **Framework:** the official **`mcp` SDK**, class `MCPServer` (`from mcp.server import
  MCPServer`) — first-party, spec-tracking. Target spec revision **`2026-07-28`** (current).
  *`mcp.server.fastmcp` was removed in SDK 2.0 — FastMCP became `MCPServer`.*
- **Write posture:** **full read + write, on by default**, mirroring the library. Hedged
  (not gated) with MCP tool annotations and an optional read-only launch flag (§7).
- **v1 primitives:** tools + one Resource (document text) + one Prompt (comment triage).

## 2. Scope

**In (v1):** stdio server; full read/write tool surface; a document-text Resource; a
comment-triage Prompt; `[mcp]` optional-dependency extra; a console entry point with a `login`
subcommand (the only interactive code path, §5); typed-error → tool-error mapping; unit tests via
`FakeBackend` driven through the server's in-process `call_tool`.

**Out (v1, designed-for not built):** Streamable HTTP / remote transport; multi-user OAuth
2.1 (resource-server model) + per-user token custody; MCP Sampling/Elicitation; a raw
`batch_update` escape-hatch tool; document discovery (`files.list`) — every tool takes a file
id/URL. *[Noted 2026-08-25: that was justified here only by "the library is document-scoped",
which restates the decision rather than supporting it. `files.list` is fully available; this is
a scope choice, and an open one — see `TODO.md`. It bites hardest exactly here, since an MCP
client has no host application to supply a file id.]*

## 3. Architecture

Mirrors the library's own composition — a factory/DI seam plus per-axis **tool producers** —
so the delivery layer never re-derives what the library already owns. `create_server` parallels
`Workspace`; the producers parallel the library's two axes (uniform comments ~ `CommentsMixin`;
variant content ~ `documents/`).

```
src/csa_google_workspace/mcp/
  __init__.py        # re-exports Settings/WorkspaceProvider/settings_from_env + main
  cli.py             # argv -> run the stdio server, or `login`
  server.py          # create_server(get_workspace) -> MCPServer; holds both tool producers:
                     #   register_comment_tools  — UNIFORM axis (all file types) ~ CommentsMixin
                     #   register_content_tools  — VARIANT axis; via open() + typed methods
  _config.py         # env -> Settings; WorkspaceProvider (cached token only, thread-local)
  _login.py          # the `login` subcommand — the ONLY interactive-consent code path
  _schemas.py        # TypedDict output shapes (bare `dict` is not serializable in SDK 2.x)

Deferred until they earn their own files: `_resources.py` (document-text resource) and
`_prompts.py` (comment-triage prompt). The two producers live in `server.py` while it is
small; split them along the same axis boundary when it stops being.
```

- **`create_server(get_workspace: Callable[[], Workspace]) -> MCPServer`** builds the app and
  calls each `register_*` producer. The seam is a **provider, not an instance**, and that is
  load-bearing twice over: credentials resolve on first tool use (so a server with no token
  still starts and reports the remedy in chat rather than dying at startup, where an MCP client
  renders the failure as an opaque "server failed to start"), and it lets each worker thread
  hold its own `Workspace`. Tests pass `lambda: Workspace(FakeBackend(...))`; the CLI passes a
  `WorkspaceProvider`.
- **`main()`** (entry point) reads config (§5), constructs the `Workspace` from **cached
  credentials only** (never `from_oauth` — see §5), calls `create_server`, and runs it over stdio
  (`app.run()`). **All logging goes to stderr** —
  under stdio, stdout is the JSON-RPC channel and must never be written to (no `print`, no
  stdout log handler; the library's own `logging` warnings must land on stderr).
- **Tool handlers are synchronous; the SDK runs them on worker threads.** Verified against
  `mcp` 2.1.0: `FuncMetadata.call_fn` does
  `await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))` for a sync tool, and says
  so — *"A sync function runs on a worker thread."* **This reverses the finding recorded here
  on 2026-08-05**, which was measured against `mcp` 1.27.0, where sync tools ran inline on the
  event loop. Consequences flip with it: Google calls no longer block the event loop (good),
  but concurrent tool calls now execute on *different threads*, so a single shared `Workspace`
  would be touched concurrently — which `SECURITY.md` forbids and `googleapiclient` does not
  survive. Hence the provider seam below, which hands each thread its own `Workspace`.
- **Factory-based dispatch (not a type ladder).** Content tools use `ws.open(file)` — the
  library's MIME-sniffing producer — and call the returned typed `Document`'s method directly,
  leaning on the library's polymorphism. A capability the type lacks (e.g. `replace_text` on a
  `Sheet`) is translated into a clean tool error, rather than re-derived with an
  `if doc.type == …` ladder in the MCP layer. Stateless: a fresh `open()` per call (matches the
  library's point-in-time read model; no caching).

## 4. Tool / resource / prompt surface

Structured output (`structuredContent` + `outputSchema`, JSON Schema 2020-12) for anything
list-shaped, so the client gets typed data, not prose. `file` is an id or share URL.

> ***[as-built]*** **Shipped in v0.2.0:** `open_document`, `read_text`, `list_comments`,
> `get_comment`, `comments_by_cell`, `create_comment`, `reply_comment`, `resolve_comment`,
> `reopen_comment` — nine tools. **Not built:** `list_suggestions`, every content-write tool,
> `edit_comment`/`delete_comment`, the Resource, and the Prompt. Content writes are blocked on
> file allowlisting (#82); the rest are simply deferred. See `TODO.md`.

### Reads — `readOnlyHint: true`
| Tool | Maps to | Returns |
|------|---------|---------|
| `open_document(file)` | `ws.open` | `{id, name, type, url}` |
| `list_comments(file, resolved?, author?, since?, include_deleted=False)` | `doc.comments.filter/all` | `list[CommentOut]` |
| `get_comment(file, comment_id)` | `comments.get` | `CommentOut` |
| `read_text(file, tab?, suggestions?)` | `doc.as_text(...)` | `{text}` |
| `list_suggestions(file)` | `Doc.suggestions` | `list[SuggestionOut]` (Docs only) |
| `comments_by_cell(file, cell)` | `Sheet.comments_by_cell` | `list[CommentOut]` (Sheets only) |

### Writes — annotated `destructiveHint`/`idempotentHint` as appropriate
`reply_comment`, `resolve_comment`, `reopen_comment`, `create_comment(…, cell?)`,
`edit_comment`, `delete_comment` *(destructive)*; `replace_text(find, replace, match_case=True)`
*(Doc/Slides)*, `append_text`, `insert_text(text, index)`, `delete_range(start, end)` *(destructive)*;
`update_cells(range, values, value_input_option="RAW")`, `append_rows`, `clear_cells` *(destructive)*
*(Sheets)*; `slides_insert_text(object_id, text, index=0)`.
A tool whose capability the opened document lacks translates the library's absence /
`UnsupportedOperation` into a clear tool error (e.g. `replace_text` on a spreadsheet →
"not supported for spreadsheets; use update_cells") — via the factory dispatch in §3, not a
hand-rolled type ladder.

### `CommentOut` (structured)
`{id, author, content, resolved, created_time, cell|null, replies: [{id, author, content}]}`
— `author` is display name (email is usually absent and not surfaced). Content **is**
returned (the agent needs it); the library's redacted `__repr__` protects *logs*, not tool output.

### Resource
- `document://{file_id}/text` — a read resource returning the document's plain text
  (`as_text`). Keyed by **bare file id** (not a share URL) to keep the URI clean; the tools
  still accept id-or-URL.

### Prompt
- `triage_open_comments(file)` — a prompt template that instructs the model to list open
  comments and propose replies/resolutions, **explicitly framing comment/document text as
  untrusted data, not instructions** (see §7).

## 5. Configuration & authentication (local single-user)

Env vars (no secrets in argv):
- `CSA_GW_CLIENT_SECRETS` — path to the installed-app OAuth client secrets (required).
- `CSA_GW_TOKEN` — token cache path (default `~/.csa_google_workspace/token.json`).
- `CSA_GW_READ_ONLY=1` — build a read-only `Workspace` (writes then error at the library guard).

**Two entry points, and only one of them may ever be interactive.**

```
# Once, by the human, in a real terminal:
$ csa-google-workspace-mcp login
  → browser consent → writes $CSA_GW_TOKEN (0600)

# Thereafter, launched by the MCP client (Claude Desktop, etc.):
$ csa-google-workspace-mcp
  → loads the cached token, refreshes it if stale, never prompts
  → no usable token? exit non-zero with a stderr message naming `login`
```

- **`login()`** (`_login.py`) is the **only** code path that may run `InstalledAppFlow`. It calls
  `Workspace.from_oauth(client_secrets, token_path, read_only=…)`, the flow already proven in
  `tests/oauth/`. It runs in the user's own terminal, where a browser and stdout are both fine.
- **`main()`** (the server) **must never** reach interactive consent. It loads the cached token
  and refreshes it — `creds.refresh(Request())` is pure HTTP with no stdout writes and no
  blocking on user action — and if no usable token exists it **exits non-zero with the remedy on
  stderr**. It does not attempt consent, and it does not fall back to it.
**This needs one small library addition.** Today `auth.py` exposes only `load_credentials()`,
whose `else` branch runs `InstalledAppFlow` — there is no way to say "load the cache, refresh it,
but never prompt." Two ways to get one, and the second is better:

- ✗ *Re-implement the cached-load in `_config.py`* using `google.oauth2` directly. Rejected: it
  would duplicate `auth.py`'s hardened token handling (`O_NOFOLLOW`, `fchmod 0600`, scope
  re-consent detection, non-interpolating `AuthError`) in a second place, where it will drift.
- ✓ **Split the interactive branch out in `auth.py`.** Add
  `load_cached_credentials(token_path, read_only) -> Credentials`, containing everything
  `load_credentials` does *except* the `InstalledAppFlow` call — where that branch would be
  reached, it raises `AuthError` instead. Then `load_credentials` becomes the thin interactive
  wrapper that falls back to the flow, and `_config.py` calls the cached-only variant and hands
  the result to **`Workspace.from_credentials(creds)`** — the library's documented production
  entry point, which takes ready credentials and never authenticates.

The consequence worth stating plainly: **`main()` cannot reach `InstalledAppFlow` even by
mistake**, because the function it calls does not contain that code path. That is a structural
guarantee rather than a discipline, which is why it is preferred over "remember not to prompt."
This is a genuine (small) change to the shipped library, so it belongs in phase-2 task (a) with
its own unit tests, not smuggled into the MCP layer.

- `read_only` note inherited from `auth.py`: a cached **read-write** token satisfies a required
  read-only scope set, so `CSA_GW_READ_ONLY=1` is a *client-side* guard, not a scope-level
  guarantee, whenever an RW token is already cached. For a scope-level guarantee, use a separate
  `CSA_GW_TOKEN` path for the read-only server so it consents to `.readonly` scopes on its own.

### 5.1 Why consent cannot live in the server

Two independent reasons, one normative and one mechanical.

**The MCP spec forbids it.** Authorization, §Protocol Requirements (unchanged through the
current `2026-07-28` revision; quoted here from `2025-11-25`):

> "Implementations using an STDIO transport **SHOULD NOT** follow this specification, and instead
> **retrieve credentials from the environment**."

Credentials-from-the-environment is the blessed design for stdio, not a workaround. Note also
that the SDK offers nothing here either way: its auth support is inbound (authenticating MCP
*clients*) and HTTP-only — "a pipe has no `Authorization` header, so `token_verifier` is never
consulted there" — and it has no facility for authenticating a server *outbound* to a
third-party API. That remains `auth.py`'s job.

**`run_local_server()` would corrupt the JSON-RPC stream.** Verified in the installed
`google_auth_oauthlib` source, `InstalledAppFlow.run_local_server`:

```python
if authorization_prompt_message:
    _LOGGER.info(authorization_prompt_message.format(url=auth_url))
    print(authorization_prompt_message.format(url=auth_url))   # ← bare print → stdout
...
local_server.timeout = timeout_seconds      # None by default; auth.py passes none
local_server.handle_request()               # ← blocks until the browser redirect
```

Under stdio, stdout **is** the JSON-RPC channel (§3). So in-server consent would inject
`"Please visit this URL to authorize this application: …"` into the protocol stream *and* block
startup indefinitely while the client's init timeout expires. §3's stdout-purity rule already
covers logging; this records that the OAuth flow is itself a stdout writer, which is the
non-obvious case.

**Generalize it:** under stdio, any dependency on the startup path that assumes a human terminal
is a protocol-corruption bug. `print`, progress bars, `input()`. Anything writing to *stderr*
(the `logging` default, `warnings`) is fine.

### 5.2 Credential provenance — users supply their own OAuth client

The user brings `CSA_GW_CLIENT_SECRETS` from their own Google Cloud project (Desktop-app OAuth
client). This is friction we investigated and could not remove; it is the ecosystem norm, not a
shortcoming:

- **Google's own Drive Python quickstart** requires a Cloud project, the Drive API enabled, a
  consent screen, and a downloaded Desktop-app `credentials.json`. Our `auth.py` *is* that
  quickstart, hardened.
- **Full `.../auth/drive` is a restricted scope** (required by design — the library opens
  arbitrary files the user names, which `drive.file` cannot reach). For a public app, restricted
  scope means Google app verification **plus** an annual CASA third-party security assessment.
  Unverified alternatives are capped at 100 users with 7-day refresh-token expiry.
- **We cannot ship credentials to remove the step.** Google's API ToS: *"Developer credentials
  may not be embedded in open source projects."* This holds even though Google separately notes
  an installed-app secret "is obviously not treated as a secret" — technically harmless,
  contractually forbidden.
- **Prior art agrees.** `workspace-mcp`, the closest analogue, likewise requires the user's own
  Cloud project and OAuth client, passes them by env var, caches the token, and ships a separate
  CLI for the authenticate-once step.

The design is insensitive to where the file comes from: `main()` reads `CSA_GW_CLIENT_SECRETS`
whether it is a user's own client or a future verified CSA-owned one. See §11.

## 6. Error handling

Tool bodies translate the library's typed exceptions into MCP tool errors (`isError`) with a
short, safe message: `NotFoundError`→"file/comment not found", `AccessError`→"permission
denied", `ReadOnlyError`→"server is read-only", `UnsupportedOperation`→the library's message,
`ValueError`→bad-argument message. Messages never interpolate token material (consistent with
the auth hardening). Unexpected exceptions surface as a generic tool error, logged server-side.

**Startup failures are not tool errors** — they happen before a session exists, so they exit the
process with a non-zero status and a one-line remedy on **stderr**:

| Condition | Exit message (stderr) |
|---|---|
| `CSA_GW_CLIENT_SECRETS` unset | "CSA_GW_CLIENT_SECRETS is not set — point it at your OAuth client secrets JSON" |
| No cached token | "no cached credentials — run 'csa-google-workspace-mcp login' first" |
| Token present but unusable (`AuthError`) | "cached credentials are invalid or revoked — run 'csa-google-workspace-mcp login' again" |

Never the raw exception: `auth.py` deliberately avoids interpolating the cause because it can
echo token material (`AuthError("could not load cached credentials") from e`). Preserve that.

## 7. Security posture

Writes are on by default, so the containment from `SECURITY.md` is applied as **hedges, not
gates**:
- **Tool annotations** — `readOnlyHint` on reads; `destructiveHint` on delete/clear/delete_range;
  `idempotentHint` where true. Clients can surface confirmations on destructive tools.
- **Optional `CSA_GW_READ_ONLY=1`** — a one-flag path to a read-only server.
- **Prompt-injection framing** — the triage Prompt and tool docstrings state that document/
  comment content is untrusted input, never instructions; steer edits toward the surgical
  `replace_text` over raw index edits.
- No credential material in tool output, errors, or logs.
- **Token at rest stays `0600` plaintext JSON**, as `auth.py` already writes it (`O_NOFOLLOW`
  against symlink/TOCTOU, `fchmod` to defeat `O_TRUNC` mode retention). Considered and rejected:
  Fernet-encrypting the token file, as `workspace-mcp` does — a key stored on the same disk as
  its ciphertext protects against very little while adding a dependency and a key-management
  problem. If stronger custody is wanted, the OS keychain is the honest answer; that is a
  separate, larger decision (§11), not a v1 requirement.
- **The persisted refresh token is the crown jewel** — a full-Drive token means read/write/delete
  across the user's entire Drive (`SECURITY.md`). It never leaves the user's machine: the server
  sends data nowhere except Google's APIs. This is why the local, self-hosted model is the whole
  v1 scope, and why a hosted variant is a separate design rather than a config flag (§11).

## 8. Packaging

- Optional extra in `pyproject.toml`: `[project.optional-dependencies] mcp = ["mcp>=2.1"]`
  plus `typing_extensions` below Python 3.12. Core library dependencies are unchanged.
  *[as-built]* The floor moved `>=1.2` → `>=1.27` → **`>=2.1`** as the target revision moved to
  `2026-07-28`; SDK 1.x is maintenance-only, and `mcp.server.fastmcp` does not exist in 2.x.
- Entry point: `[project.scripts] csa-google-workspace-mcp = "csa_google_workspace.mcp:main"`,
  plus `python -m csa_google_workspace.mcp`. **One console script, two modes:** a bare invocation
  runs the server; the single subcommand `login` runs interactive consent (§5). Argument parsing
  stays deliberately minimal — no argparse subparser tree for one verb.
- README: a "Use as an MCP server" section with the `login`-then-configure sequence and the Claude
  Desktop config snippet. The README is the frozen PyPI long description, so it must not describe
  the server as available before the release that ships it.

## 9. Testing

- **Unit (gates CI):** `create_server(lambda: Workspace(FakeBackend(...)))` driven in-process
  through `await server.call_tool(...)` — call each tool, assert structured output and error
  mapping. *[as-built]* A provider, not an instance (§3), and `call_tool` directly rather than a
  client object; note it **raises** `ToolError` rather than returning an error result. No network,
  no credentials — the same `FakeBackend` strategy as the rest of the suite. The `mcp` extra is
  added to the `dev` install so CI can import it.
- **Stdout purity (the regression guard for §5.1).** Run the server's startup path with
  `contextlib.redirect_stdout` (or a captured pipe) and assert **nothing** is written to stdout —
  including on the failure paths (missing client secrets, missing token, invalid token), which is
  where a stray `print` or a library prompt is most likely to appear. This is the test that would
  have caught the original design, so it is not optional.
- **`main()` never prompts.** Point `CSA_GW_TOKEN` at a nonexistent path and assert the process
  exits non-zero with the `login` remedy on stderr — and that `InstalledAppFlow` was never
  constructed (patch it to raise if called). Asserting the *absence* of interactive consent is
  the actual invariant; asserting the error text alone would pass even if consent ran first.
- **`login` is covered by the existing gated tier, not the unit suite.** It is interactive by
  nature; `tests/oauth/` already exercises `from_oauth`, token-file permissions, and the
  `read_only` contract behind `CSA_GW_OAUTH=1`. Extend that suite rather than mocking a browser.
- **Gated live smoke (optional):** one `CSA_GW_MCP_LIVE`-gated test that starts the server against
  a real token produced by `login` (at `CSA_GW_TOKEN`) and lists comments on a throwaway doc. The
  original draft named a token borrowed from another project; use this project's own token path
  instead, so the smoke exercises the documented flow rather than a side channel.
- ruff/mypy/coverage/bandit gates apply to the new module as to the rest of `src`.

## 10. Phasing

One implementation plan (via writing-plans), TDD, bite-sized tasks:

- **(a) Skeleton + auth.** The `auth.load_cached_credentials()` split in the **library** (§5, with
  its own unit tests), then the `[mcp]` extra, package skeleton, `create_server`, `_config.py`
  (cached-only load + the §6 startup errors), `_login.py`, and the two §9 guards (stdout purity,
  `main()` never prompts). **Auth lands first**, because it is the part the original spec got wrong
  and the part every later task runs on top of. Note this task touches shipped library code, not
  just the new module — the only task in phase 2 that does.
- **(b)** read tools + structured schemas + tests.
- **(c)** write tools + annotations + tests.
- **(d)** Resource + Prompt + tests.
- **(e)** entry point wiring + README section + a gated live smoke.

Each task: `FakeBackend` tests, then commit; PR at the end.

## 11. Open questions and explicit deferrals

Recorded decisions, not oversights. None blocks the plan.

- **Credential provenance for public users.** Users supply their own OAuth client today (§5.2).
  Removing that step requires Google app verification + an annual CASA assessment for a
  CSA-owned client — a cost/ownership decision, not an engineering one. The design is
  insensitive to the outcome: `main()` reads `CSA_GW_CLIENT_SECRETS` either way. Tracked in
  `TODO.md`.
- **Hosted / server-side login.** A remote, multi-user server (Streamable HTTP + the MCP OAuth
  2.1 resource-server model, per-user token custody in a real secret store) is a **separate
  design**, deliberately not a config flag on this one — it inverts the token-custody model that
  `SECURITY.md` is built around. v1 is local, self-hosted, single-user. Tracked in `TODO.md`.
- **Async / responsiveness.** Resolved by the SDK rather than by us: `mcp` 2.x already runs
  sync handlers on worker threads (§3), so no `anyio.to_thread` work is needed and the event
  loop is not blocked. What it *created* is the thread-safety requirement, met by the
  thread-local provider. An async-native facade over `google-api-python-client` remains out of
  scope (that library is synchronous).
- **Token custody beyond `0600`.** OS-keychain storage instead of a plaintext file (§7). A real
  improvement, a real amount of work, and cross-platform. Not v1.
- **Elicitation for re-consent.** MCP Elicitation could let the server ask the client to prompt
  the user when a token goes stale, avoiding the exit-and-rerun-`login` cycle. Out for v1 (as the
  original §2 already had it), but it is the natural way to soften the one rough edge in §5.
