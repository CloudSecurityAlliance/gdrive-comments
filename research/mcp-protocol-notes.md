# MCP Protocol Notes (for this project)

> **Refreshed August 2026.** Replaces the scraped `llms-full.md`, which documented spec revision `2025-06-18` and the since-removed HTTP+SSE transport. This is a concise orientation — the [official spec](https://modelcontextprotocol.io/specification) is authoritative; check it before implementing.
>
> **The July 2026 revision of this file is now wrong in its central advice.** It said to target `2025-11-25` and "do not build against" the `2026-07-28` release candidate. That RC was ratified: **`2026-07-28` is the current revision**, and this project's MCP server (v0.2.0) is built on it. Kept as a worked example of why *"probe beats docs"* extends to our own notes — a research file with a date on it ages, and this one aged in under a month.

## Current spec status
- **Current: `2026-07-28`.** Ratified late July 2026 — target this. `mcp` (Python SDK) **2.x** implements it and serves every earlier revision from the same server.
- Superseded: `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`.

### What `2026-07-28` changed (all of it breaking)
- **Stateless protocol core** — the `initialize`/`initialized` handshake and `Mcp-Session-Id` are **gone**. Every request is self-describing: protocol version, client info and capabilities travel in `_meta` on each request.
- **`server/discover`** — a mandatory RPC returning supported versions, capabilities and identity in one call. Optional for a client to use.
- **Roots, Sampling and Logging are deprecated**, under a new formal deprecation policy (≥12 months, or ≥90 days under expedited removal).
- Extensions framework, Tasks, MCP Apps, authorization hardening.

### Python SDK notes (verified against `mcp` 2.1.0, not documentation)
- **`mcp.server.fastmcp` no longer exists.** `FastMCP` became **`MCPServer`** (`from mcp.server import MCPServer`) in SDK 2.0. The decorator API is otherwise familiar.
- **Sync tool handlers run on a worker thread** (`anyio.to_thread.run_sync`). In 1.x they ran inline on the event loop — the opposite. Anything not thread-safe behind a tool must account for it.
- **Raising a plain exception yields `UnexpectedToolError` with the message suppressed.** User-facing text must be raised as the SDK's `ToolError`.
- **A bare `dict` return is not serializable for structured output** — use a `TypedDict` or model. Below Python 3.12 it must come from `typing_extensions`, or pydantic silently emits no schema.
- **v1.x is maintenance-only** (security fixes).

## Message layer
- **JSON-RPC 2.0** over stateful connections with capability negotiation via `initialize` / `initialized`. Unchanged.

## Transports
- **stdio** — primary for local servers (Claude Desktop launches the process; JSON-RPC over stdin/stdout). Current.
- **Streamable HTTP** — the current recommended **remote** transport. Client POSTs JSON-RPC; the server replies with either a single JSON body or an upgraded SSE stream for streaming responses.
- ⚠️ **The old standalone "HTTP+SSE" transport is gone** — replaced by Streamable HTTP in revision `2025-03-26`. Don't design around a separate SSE endpoint.

## Primitives
- **Server → client:** Tools, Resources, Prompts.
- **Client → server:** Sampling, Roots, **Elicitation** (server asks the user for more input mid-flow — added since mid-2025; likely absent from the old doc).

## Notable additions since mid-2025 (relevant to this project)
- **Authorization:** a formal **OAuth 2.1** framework for HTTP-transport servers (resource-server model, RFC 8707 resource indicators). Matters if this server is ever deployed remotely.
- **Structured tool output:** tools can return `structuredContent` with an `outputSchema` — useful for returning comment lists as typed data rather than prose.
- **Tool annotations:** read-only / destructive hints exist, but the spec warns they are **untrusted unless from a trusted server**.
- Tool I/O schemas standardizing on **JSON Schema 2020-12**.

## Coming soon (RC 2026-07-28 — not yet current)
Flagged so the design isn't blindsided: removal of protocol-level sessions (`Mcp-Session-Id`), a move toward stateless operation, required `Mcp-Method`/`Mcp-Name` routing headers, `InputRequiredResult` replacing persistent SSE, and deprecation of Roots/Sampling/Logging with replacements. Treat as future.

## Sources
- <https://modelcontextprotocol.io/specification> (current `2026-07-28`)
- <https://blog.modelcontextprotocol.io/posts/2026-07-28/> (the ratified revision)
- <https://github.com/modelcontextprotocol/python-sdk/releases> (SDK 2.0 breaking changes)
- TypeScript SDK: <https://github.com/modelcontextprotocol/typescript-sdk>
