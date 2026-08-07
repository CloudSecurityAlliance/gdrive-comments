# INTERFACE-RESOURCES.md — csa-google-workspace

**Last verified:** 2026-08-07
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
  live-verified end-to-end against real Google. Classifier still reads
  `Development Status :: 4 - Beta`.
- **Health check:**
  ```bash
  pip install csa-google-workspace && python -c "from csa_google_workspace import Workspace; print(Workspace)"
  ```
- **Owner:** Kurt Seifried
- **Notes:** Changelog at [`CHANGELOG.md`](./CHANGELOG.md); release process in
  [`RELEASING.md`](./RELEASING.md).

### `csa_google_workspace.mcp` — mcp *(planned)*

- **Transport:** stdio (local) — an AI client spawns the server as a subprocess.
  No hostname, no route, no Cloudflare Worker; this is the first local-transport
  interface in the portfolio.
- **Surface:** review comments, read content, and edit Docs/Sheets/Slides through
  the library
- **Auth:** inherits the library's BYO-credentials model
- **Status:** **planned** — spec approved, implementation not started. It is
  **not** in the released package. Nothing in the README's API applies to it yet.
- **Design:** [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](./docs/superpowers/specs/2026-07-23-mcp-server-design.md)
- **Owner:** Kurt Seifried
- **Notes:** Listed while unbuilt on purpose. A planned interface with an
  approved spec is exactly the thing that otherwise gets forgotten, or gets
  built twice because nobody knew it was already designed.

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
