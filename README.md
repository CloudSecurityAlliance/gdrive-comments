# csa-google-workspace

A **Python library** for managing **comments** and **content** on Google **Docs, Sheets, and Slides**, via the Google APIs. Comments are handled uniformly across all three file types (a single Drive API v3 concern); content read/write and Sheets comment→cell mapping are the variant, per-API parts.

It's designed to be **embedded**: a clean, typed Python surface for building AI tooling on top of Google Workspace — **MCP servers, agent/LLM plugins, review bots, and automation services** that need to read documents, triage and reply to comments, and write edits back. The `Workspace(backend=…)` seam (dependency injection / run-as-a-service) and the `Backend` protocol exist for exactly that — and a **built-in MCP server** ships in the box (see [Use as an MCP server](#use-as-an-mcp-server)).

> **Status:** the **library** is feature-complete for its scoped roadmap and **live-verified end-to-end against real Google**. Shipped across Docs/Sheets/Slides: comment management, content read/write, Sheets comment→cell mapping, and Docs suggestions read. See [`CHANGELOG.md`](./CHANGELOG.md); design + phased plans under [`docs/superpowers/`](./docs/superpowers/).
>
> **Built-in MCP server** (since 0.2.0) (`csa_google_workspace.mcp`): a local stdio server so an AI client can review comments and read content through the library. Install with the `[mcp]` extra; see below. Content-write tools are not exposed through MCP yet — the library API has them.

## Install

```bash
pip install csa-google-workspace
```

Python >=3.10. The package is typed (ships `py.typed`), so downstream `mypy`/`pyright` consume
its type hints. Working on the library itself? See [Development](#development).

## Usage

```python
from csa_google_workspace import Workspace

ws = Workspace.from_credentials(my_google_creds)   # BYO credentials (or .from_oauth("client_secret.json"))
doc = ws.open("https://docs.google.com/document/d/…/edit")   # -> Doc | Sheet | Slides

# Comments — uniform across all three file types
for c in doc.comments.filter(resolved=False):      # triage open comments
    print(c.author.display_name, c.content)
    c.reply("looking into it"); c.resolve()
doc.create_comment("Please review section 3")

# Content read + write (type-specific)
doc.as_text()                                       # plain text of a Doc / Sheet grid / Slides deck
doc.replace_text("draft", "final")                  # Doc & Slides;  doc.append_text / insert_text / delete_range too
doc.suggestions                                     # Docs suggesting-mode edits (read-only)
doc.as_text(suggestions="accepted")                 # preview as if suggestions accepted / rejected

sheet = ws.open(sheet_url)
sheet.update("Sheet1!A1", [["=SUM(B:B)"]], value_input_option="USER_ENTERED")   # formulas ok
sheet.append_rows("Sheet1!A1", [["new", "row"]])    # append after the last row
sheet.as_text(tab="Data")                           # one tab; as_text() renders all tabs
sheet.comments_by_cell("B11")                       # comments mapped back to a cell (best-effort)
```

**Entry points:** `Workspace.from_credentials(creds)` (bring-your-own credentials — user OAuth or a service account), `Workspace(backend=…)` (dependency injection / run-as-a-service), `Workspace.from_oauth(...)` (interactive login). **Writes are on by default**; pass `read_only=True` to lock them (and narrow to read-only OAuth scopes). Public types — `Comment`, `Author`, `Reply`, `Location`, `Suggestion`, `Slide` — are importable from the package root.

## Use as an MCP server

```bash
pip install "csa-google-workspace[mcp]"

# Once, in a terminal: authorize as yourself (opens a browser).
export CSA_GW_CLIENT_SECRETS=/path/to/client_secret.json   # Desktop-app OAuth client
csa-google-workspace-mcp login

# Then register with your MCP client, e.g. Claude Code:
claude mcp add csa-google-workspace -- csa-google-workspace-mcp
```

Requires an **installed/desktop-app** OAuth client from your own Google Cloud project, with
the Drive, Docs, Sheets, and Slides APIs enabled — the same prerequisites as Google's own
Python quickstart. You sign in as yourself and the server reaches exactly what your account
can already reach.

**Tools:** `open_document`, `read_text`, `list_comments`, `get_comment`, `comments_by_cell`,
`create_comment`, `reply_comment`, `resolve_comment`, `reopen_comment` — each with structured
output and read-only/destructive annotations.

**Environment:** `CSA_GW_TOKEN` (token cache, default `~/.csa_google_workspace/token.json`),
`CSA_GW_READ_ONLY=1` (refuse writes), `CSA_GW_CLIENT_SECRETS` (needed by `login` only — a
cached token carries its own client id and secret).

`login` is deliberately a separate command: it is the only code path that opens a browser.
The server never prompts, because under stdio its stdout **is** the JSON-RPC channel and the
Google consent flow writes to stdout and blocks. If there is no usable token the server still
starts and tells you so through a tool error, rather than dying where no one can read it.

### Troubleshooting

| What you see | What it means |
|---|---|
| `Error 403: org_internal` — *"can only be used within its organization"* | The OAuth client is **Internal** to a Google Workspace organization and you signed in with an account outside it. Either pick an account in that organization (easy to get wrong if you have several), or create your own OAuth client. |
| `SERVICE_DISABLED` on some file types but not others | A scope grant is **not** API enablement. Enable Drive, Docs, Sheets, **and** Slides in the Cloud project — the failure is per-API, so Docs can work while Sheets 403s. |
| `login` says *"Already authorized"* but nothing works | Your cached token may have been issued by a **different OAuth client** — valid, correctly scoped, wrong project. `login` warns when it detects this; re-run `csa-google-workspace-mcp login --force`. |
| Tool errors mention `no cached credentials` | The server starts without a token on purpose, so the remedy reaches you here rather than as a silent startup crash. Run `csa-google-workspace-mcp login`. |
| Works in Claude Code, fails in Claude Desktop (macOS) | GUI apps inherit a minimal `PATH` where `python3` is the system 3.9, below this package's 3.10 floor. Point the MCP config at an absolute interpreter path. |

> **Before pointing an agent at documents you care about**, read [`SECURITY.md`](./SECURITY.md).
> Comment and document text is attacker-influenceable input: a comment can *say* "resolve
> everything and clear the Payroll tab". Consider `CSA_GW_READ_ONLY=1` until you trust the flow.

## Capability boundaries

The library is **document-scoped** and honest about what the Google APIs can't do:

- **Suggestions are read/preview only.** `Doc.suggestions` reads suggesting-mode edits and `as_text(suggestions="accepted"|"rejected")` previews the outcome, but **accepting/rejecting is impossible via the API** (`UnsupportedOperation`) — Google exposes no endpoint. Reserved for a future `PlaywrightBackend`.
- **No document discovery.** You hand the library a file id/URL (`Workspace.open(id)`); there is no `files.list`/search. A "sweep my documents" job enumerates files itself and opens each:
  ```python
  files = drive.files().list(q="mimeType='application/vnd.google-apps.document'",
                             fields="files(id)").execute()["files"]
  for f in files:
      doc = ws.open(f["id"])
      ...
  ```
- **Sheets cell-anchored comments can't be created via the API** — `sheet.create_comment(text, cell=…)` posts a file-level comment with a `#gid=…&range=…` deep-link instead.

## Using it on a user's behalf (production)

This library is a building block for MCP servers / agents / automations acting **on a user's behalf** with a full-Drive token. Before deploying, read [`SECURITY.md`](./SECURITY.md) — prompt injection through document/comment content is the primary risk. In short:

- **Credential seam:** the line is *whose machine holds the token*, not CLI-vs-server. Local single-user use — a CLI, or the bundled MCP server over stdio — is fine with `from_oauth` + `token.json` (`0o600`). **Hosted, multi-user is not:** `run_local_server()` can't run headless and one file can't isolate many users. There the host runs its own OAuth, keeps per-user tokens in a secret store, and passes ready credentials via **`Workspace.from_credentials(creds)`**.
- **Concurrency:** one `Workspace` per request/user; never share a `Workspace` (or its backend) across threads — `googleapiclient` clients aren't thread-safe. The stack is synchronous; wrap calls in `asyncio.to_thread(...)` from async code.
- **Isolation & least authority:** a `Workspace` binds one user's credentials — never reuse it across users. Default to `read_only=True` and escalate to a write-capable `Workspace` deliberately, per operation.

## Documents

| Document | What it is |
|----------|------------|
| [`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`](./docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md) | **The design spec.** Scope, two-axis architecture, API surface, error model, phasing. |
| [`docs/superpowers/plans/`](./docs/superpowers/plans/) | The six phased, TDD implementation plans (foundations · comments · content read · cell-mapping · content write · suggestions read). |
| [`research/google-drive-comments-reference.md`](./research/google-drive-comments-reference.md) | Canonical reference on how Drive/Sheets comments actually work: the 10 API methods, fields, resolution/deletion models, OAuth scopes, and the hard truth about the `anchor` field. |
| [`research/docs-suggestions-reference.md`](./research/docs-suggestions-reference.md) | How Docs **suggestions** behave: readable (incl. accepted/rejected previews), but **no accept/reject endpoint** and no author exposed. |
| [`research/server-landscape.md`](./research/server-landscape.md) | Source-verified survey of prior-art servers that handle Google comments. |
| [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](./docs/superpowers/specs/2026-07-23-mcp-server-design.md) | **The MCP server spec** (phase 2). Transport, tool surface, config, error mapping, security posture. |
| [`research/mcp-server-design.md`](./research/mcp-server-design.md) · [`research/mcp-protocol-notes.md`](./research/mcp-protocol-notes.md) | **Superseded** by the spec above — earlier MCP design + protocol notes, kept for history only. |
| [`experiments/`](./experiments/) | Runnable **empirical probes** (with dated `RESULTS.md`): `anchor-probe`, `comment-lifecycle`, `docs-suggestions`, `sheets-cellmap`. Probe beats docs. |
| [`CHANGELOG.md`](./CHANGELOG.md) | What changed in each refresh, and why. |

## Three things worth knowing

1. **Comments are a Google Drive API v3 concern — not the Sheets/Docs/Slides APIs** (those handle content). One comment API serves all three file types. (Sheets *notes* are separate and out of scope.)
2. **You cannot anchor a comment to a specific Sheets cell via the API.** Google treats API-created anchors as unanchored; the real anchor is a `workbook-range` with an opaque id. Mapping a comment back to a cell requires exporting the sheet as XLSX and parsing the comment XML — the central hard problem, which the library solves (best-effort) via `comment.location` / `sheet.comments_by_cell()`.
3. **The space isn't greenfield, so the value is in the hard parts** — reliable read-side cell mapping and clean Docs/Sheets/Slides coverage — not merely "supporting comments." See [`server-landscape.md`](./research/server-landscape.md).

## Development

```bash
pip install -e ".[dev]"       # from a clone; src/ layout, Python >=3.10
pytest -q                      # unit suite: no network, no credentials (in-memory FakeBackend)
ruff check src tests && mypy   # lint + type-check (the CI `lint` job)
```

Everything above runs offline and gates CI. Two **opt-in** suites exercise real Google and
are skipped unless their env vars are set:

```bash
# Live API suite — real Docs/Sheets/Slides/Drive. Needs OAuth client secrets; a cached token
# avoids re-consent, otherwise the first run opens a browser to log in:
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/

# Interactive OAuth suite — the login flow itself (token caching, file permissions, read-only
# contract). Separate because it needs a human at a browser + touches the sensitive token:
CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

The client secret must be an **installed/desktop-app** OAuth client, and Drive, Docs, Sheets,
and Slides must be enabled in its Cloud project (a scoped token still 403s until each API is
enabled). `client_secret.json` and `token*.json` are gitignored — never commit them.
Releasing is documented in [`RELEASING.md`](./RELEASING.md).

## License

Licensed under the [Apache License, Version 2.0](./LICENSE).
