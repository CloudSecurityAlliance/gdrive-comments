# INTERFACE-RESOURCES.md — csa-google-workspace

**Last verified:** 2026-08-27 (v0.30.12)
**Scope:** Interfaces this repo exposes to callers, and first-party interfaces it
consumes. Third-party Python dependencies live in `pyproject.toml`; the Google
API surfaces this library wraps are third-party and are not listed here.

---

## Provides

### `csa-google-workspace` — library

A published Python library. Its interface is an **import surface**, not a URL —
there is no endpoint to curl and no deployed instance to health-check. Verifying
it means installing it and importing it.

- **Package:** `csa-google-workspace` on PyPI — `pip install csa-google-workspace`
- **Import surface:** `from csa_google_workspace import Workspace`
  - Construction: `Workspace.from_credentials(creds)`, `Workspace.from_oauth("client_secret.json")`
  - Extension seam: the `Backend` protocol + `Workspace(backend=…)` dependency
    injection, provided specifically so delivery layers (MCP servers, bots,
    services) can be built on top without forking
- **Capabilities:** comment management, content read/write, and Sheets
  comment→cell mapping across Google Docs, Sheets, and Slides; Docs suggestions
  read
- **Requires:** Python >=3.10. Ships `py.typed`, so downstream `mypy`/`pyright`
  consume its type hints.
- **Auth:** none at the library boundary — callers bring their own Google
  credentials (BYO `google.oauth2` credentials, or the bundled OAuth helper)
- **Code:** [`src/`](src/)
- **Status:** production — feature-complete for its scoped roadmap and
  live-verified end-to-end against real Google. Current release **v0.2.3**
  (2026-08-25); the MCP server below arrived in v0.2.0. Classifier still reads
  `Development Status :: 4 - Beta`.
- **Health check:**
  ```bash
  pip install csa-google-workspace && python -c "from csa_google_workspace import Workspace; print(Workspace)"
  ```
- **Owner:** Kurt Seifried
- **Notes:** Changelog at [`CHANGELOG.md`](./CHANGELOG.md); release process in
  [`RELEASING.md`](./RELEASING.md).

### `csa_google_workspace.mcp` — mcp

- **Transport:** stdio (local) — an AI client spawns the server as a subprocess.
  No hostname, no route, no Cloudflare Worker; this is the first local-transport
  interface in the portfolio.
- **Install / run:**
  ```bash
  pip install "csa-google-workspace[mcp]"
  csa-google-workspace-mcp login          # once, interactive: browser consent
  claude mcp add csa-google-workspace -- csa-google-workspace-mcp
  ```
- **Surface:** 34 tools, each with structured output (`outputSchema`) and
  read-only/destructive annotations, across five groups — discovery and file
  lifecycle (`search_files`, `list_recent_files`, `get_file_metadata`,
  `get_file_permissions`, `create_file`, `copy_file`, `update_file`,
  `share_file`, `trash_file`), content read (`read_file_content`,
  `download_file_content`, `list_slides`, `list_suggestions`), **content write**
  (`replace_text`, `append_text`, `insert_slide_text`, `update_cells`,
  `append_rows`), comments (`list_comments`, `get_comment`, `comments_by_cell`,
  `create_comment`, `reply_comment`, `resolve_comment`, `reopen_comment`,
  `edit_comment`, `delete_comment`, `export_comments`,
  `apply_comment_actions`), and the server describing itself
  (`describe_configuration`, `read_server_resource`, `report_a_problem`,
  `demonstration_plan`, `authenticate`).

  Content writes shipped in **v0.13.0** and Docs suggestions in **v0.20.0**, so
  the server now reaches everything the library does. An earlier version of this
  file said content writes were not exposed; that was true at v0.2.3 and wrong
  for roughly fifteen releases after.
- **Auth:** per-user Google OAuth, inheriting the library's BYO-credentials
  model. Requires an **installed/desktop-app** OAuth client and the Drive, Docs,
  Sheets, and Slides APIs enabled. Each user authorizes as themselves; there is
  no shared token. `login` is a separate subcommand because it is the only code
  path that may open a browser — under stdio, stdout is the JSON-RPC channel.
- **Config:** `CSA_GW_TOKEN` (token cache, default
  `~/.csa_google_workspace/token.json`), `CSA_GW_READ_ONLY=1` (refuse writes),
  `CSA_GW_CLIENT_SECRETS` (needed by `login` only — a cached token carries its
  own client id and secret).
- **Protocol:** MCP revision `2026-07-28`; requires SDK `mcp>=2.1`.
- **Status:** **shipped**, v0.2.0 onward (2026-08-24); current release v0.30.12.
- **Design:** [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](./docs/superpowers/specs/2026-07-23-mcp-server-design.md)
- **Health check** — no credentials needed; lists the tool surface over real stdio.
  The request must be on **one line**: stdio framing is newline-delimited, so a
  pretty-printed body is read as several truncated messages.
  ```bash
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"healthcheck","version":"0"}}}}' | csa-google-workspace-mcp
  ```
  Expect a JSON-RPC result listing 34 tools.
- **Owner:** Kurt Seifried
- **Notes:** A missing or expired token does **not** stop the server starting —
  it starts and reports the remedy through a tool error. So "the process is
  running" is not evidence that anyone is authenticated; the health check above
  deliberately exercises only the unauthenticated path.

### CSA-internal distribution

Not an interface this repo exposes, but the deployment path worth recording
alongside it: CSA members get this via
[`DesktopSetup`](https://github.com/CloudSecurityAlliance/desktopSetup), which
gh-probes `CloudSecurityAlliance-Internal/CSA-Plugins` and runs
`internal-setup/csa-google-workspace-setup.sh` from there. That private repo
carries CSA's Internal OAuth client, which cannot live in a public repo (Google's
API ToS forbid embedding developer credentials in open source). Non-members get a
404 from the probe and see nothing.

---

## Uses

None. This library sits at the bottom of the dependency graph — it wraps
third-party Google APIs and consumes no first-party CSA interface.

---

## Not listed here

| Thing | Where it lives |
|---|---|
| Python dependencies | `pyproject.toml` |
| Google Docs/Sheets/Slides/Drive APIs | third-party — out of scope by the first-party-only rule |
| Release and versioning process | [`RELEASING.md`](./RELEASING.md) |
