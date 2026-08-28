# Decision index

An index, not a record. The reasoning behind this project is already written down — in commit
messages that argue rather than summarise, in dated probe results, and in the specs and plans
under `docs/superpowers/`. What was missing was a way to find *which* decision was made *when*,
what it superseded, and where the evidence sits.

Read a row, then read the thing it points at. Newest first.

## How to read this

| Column | Means |
|---|---|
| **Settled** | when the decision stopped being open, not when the code landed |
| **Evidence** | what makes it more than an opinion — a probe, an API enumeration, a live run |
| **Superseded** | an earlier belief this replaced. Where a row has one, the earlier belief is usually still findable in the history, and that is deliberate |

Where a decision was **corrected**, the correction is a row of its own rather than an edit. Being
able to see that we believed something wrong is more useful than a clean record.

## 2026-08-28 — the capability model mirrors Drive

| Settled | Decision | Evidence | Superseded |
|---|---|---|---|
| 2026-08-28 | **The profiles are Google Drive's roles, named as the Drive API names them** — `reader`, `commenter`, `writer`, `fileOrganizer`, `organizer`. An operator already holds Google's model; a more precise one sharing none of its vocabulary makes them hold two and map between them | [Drive roles reference](https://developers.google.com/workspace/drive/api/guides/ref-roles); the UI labels Viewer / Commenter / Editor / Content manager / Manager | our own four-rung ladder (`reader`/`commenter`/`editor`/`full`), kept as aliases |
| 2026-08-28 | **`file.share` stays on the ladder, at the top.** Drive's `writer` explicitly cannot share; sharing is reserved to Manager and Owner — so disclosure *is* a ladder property | Google's own role definitions | audit `2026-08-27-01` §5.3, which placed it orthogonal |
| 2026-08-28 | **Viewing and downloading are not meaningfully different**, so the local-filesystem write gets no capability. A view-only document is defeated by screenshot + OCR; and for an injected agent it is not even effortful, because `read_file_content` already returned the text into its context. **Confidentiality is lost at read, not at write** | measured: all four profiles write a `.csv` to disk today, and the capability would gate the second copy after the first is already in the model's context | audit §5.2's `export.file` capability |
| 2026-08-28 | **Bulk is not a capability.** `export_comments` and `apply_comment_actions` have no web-UI equivalent, but each can be emulated one call at a time with the same capabilities, so bulk confers no authority. Leverage is operational, not authorization | the tools' own capability requirements | treating "no UI equivalent" as evidence of privilege |
| 2026-08-28 | **`content.active` is not a capability; the parameter is removed instead.** Any human Editor may type a formula in the browser and Google calls that `writer`, so the distinction is not Drive's — but `valueInputOption` comes off the MCP surface entirely, the way raw `batch_update` already is. Deleting an attack surface beats gating it | T15's residual: after 0.30.1 the only thing between an injected agent and formula evaluation was a docstring | audit §5.2's `content.active` capability |
| 2026-08-28 | **`local.read` / `local.write` are data-handling switches, not capabilities.** They cannot contain confidential data, so filing them beside `file.share` would invite an operator to trust them for something they never did. What they are for is keeping review material inside the MCP client rather than on disk | the read-not-write argument above | classing every on/off control as a capability |
| 2026-08-28 | **A code audit under-weights what a human will understand and adopt.** Audit §5 was sound at every step and its conclusion still did not hold, because it optimised for what an attacker can do rather than what an operator will configure correctly. Interface, vocabulary and defaults are security properties | three proposed capabilities dropped, and a fourth thing tightened that the audit had not proposed | reading an audit's recommendations as findings |
| 2026-08-28 | **Expose every capability the API offers.** Withholding one does not prevent the action — the same user can do it in a browser or in fifty lines of their own Python — it only sends them to a client with no policy layer, no allowlist, no annotations and no logging. Capability withheld is utility lost and risk unchanged | every action here is one the authorizing user can already perform; `SECURITY.md`, *Why this exposes everything the API can do* | "document-scoped by choice", and the no-discovery boundary removed in v0.15.0 but still claimed in the README until now |
| 2026-08-28 | **The controls are a privilege simulator, not a fence.** They let an agent act as a *less-privileged user than you are* — you own the document, the agent runs as a commenter. That is a capability, not a restriction, and it is why narrowing gets used at all | the profiles and allowlists cannot bind the operator (they can fork the package or call the API directly), but the agent cannot fork the package | reading the capability model as a security boundary |
| 2026-08-28 | **Defaults are open; the documentation's job is how to narrow.** All ten capabilities on, both allowlists `*` | the README already told operators to set `READ="*"`; `THREAT_MODEL.md` §1 already named Drive as the primary layer and this one as "deliberately narrow, not the primary layer" | #82's fail-closed posture (the `_GATES` fail-closed invariant is unaffected and stays) |
| 2026-08-28 | **Named the gap the whole episode exposes: access control authenticates identity and authorizes actions, and has no concept of intention or of which tool is acting.** Drive cannot see whether a request came from a human keystroke or a model's inference, from the official client or one written this morning. This project is partly a testbed for that | the confused-deputy delta is *who decides*, and no ACL layer can see it | treating the capability model as the answer to the confused-deputy problem rather than a partial mitigation |
| 2026-08-28 | **This capability layer is explicitly interim: "a simulator, a convenience, and a step in the right direction until there is better backend security." When the durable layer can see tool provenance and request intention, this one should **shrink**, not defend its territory** | client-side enforcement never binds the client, and the gap it compensates for is a server-side one | an implicit assumption that a control, once built, is kept |
| 2026-08-28 | **Logging is the same shape as the capability model: a real audit trail is server-side; local logging is a convenience for debugging.** A log written by this process on this machine does not survive the thing it audits - whoever compromises the client deletes it first. It is evidence about accident, not about an adversary | Workspace audit logging records the API method, the acting user and the OAuth client's App ID, outside the reach of anyone who owns the laptop | treating a local log as an audit trail |
| 2026-08-28 | **Raising the log level raises detail about the OPERATION, never about the CONTENT.** Verbose logging is the natural way to defeat the redacting `__repr__`s, and it would do so exactly when somebody is capturing everything to paste into an issue - and a debug log of document text is a persistence step for an injection payload | `tests/test_repr_redaction.py`; the models redact because embedders log them | a verbosity number that turns up everything, content included |


## 2026-08-25 — the MCP server's shape and its limits

| Settled | Decision | Evidence | Superseded |
|---|---|---|---|
| 2026-08-25 | **Release history, tags and PyPI are reconciled by a check, not by discipline.** A changelog records intent; PyPI records fact; they drift, and the changelog is the one people read | `scripts/check_release_history.py` found a real discrepancy on its first run | eleven changelog entries implying installable releases |
| 2026-08-25 | **Authorship and review are stated explicitly**, including that much of the content was AI-drafted under direction, and that review is single-person | `PROVENANCE.md` | inferring it from prose style |
| 2026-08-25 | **The allowlist lives in the environment; there is no file.** The client config is the artifact an operator controls and can see | `allowlist.py` module docstring; a path-shaped value is diagnosed rather than read | v0.8's path support and default file locations |
| 2026-08-25 | **Read and modify are separate scopes**, both fail-closed, with `*` typed rather than defaulted | `policy.py`; live-verified against real Google | one allowlist covering writes only, unset meaning unrestricted |
| 2026-08-25 | **`#82` gates less than the roadmap said.** It is write-narrow, so discovery and permissions reads are not blocked by it | sorting the eight parity tools by whether they can damage an existing file | "#3 and #5 blocked on #2" |
| 2026-08-25 | **A capability gate may need the call's arguments.** `create_reply` is both replying and resolving | probe-verified action-reply behaviour (`experiments/comment-lifecycle/`) | one capability per backend method |
| 2026-08-25 | **Export formats differ by document type, and "images" was wrong** | [`experiments/export-formats/RESULTS.md`](../experiments/export-formats/RESULTS.md) — `drive.about.get` | a shared format enum; "PDF, Office, ODF, images" |
| 2026-08-25 | **The library has one axis (per-file); the roadmap adds a second (account-scoped)** | [`specs/2026-08-25-library-structure-for-the-roadmap.md`](superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md) | treating discovery as "just another tool" |
| 2026-08-25 | **Tool names match Google's and Anthropic's servers**; a camelCase wire name must be the literal Python parameter name | live schema reads; a pydantic alias publishes correctly and then fails every call | `open_document` / `read_text` / `file=` |
| 2026-08-25 | **Neither other server can edit existing content**, and their `update_file` is metadata-only | [`research/drive-mcp-servers-and-api-surface.md`](../research/drive-mcp-servers-and-api-surface.md), read from live schemas | assuming `update_file` wrote content — which had already produced a wrong roadmap |

## 2026-08-24 → 2026-08-25 — the MCP server ships

| Settled | Decision | Evidence | Superseded |
|---|---|---|---|
| 2026-08-25 | **The unauthorized message is the entire UX of an unauthorized server**, so it carries the remedy, the absolute launcher path, and an instruction not to hunt for credential files | a real first run where the model searched the filesystem | "no credentials" |
| 2026-08-24 | **A cached token can be bound to the wrong OAuth client**, silently | two client ids in one account; `login --force` plus mismatch detection | assuming a valid token is the *right* token |
| 2026-08-24 | **`login` is a separate subcommand, not a fallback inside the server.** `run_local_server()` prints to stdout, and stdout is the JSON-RPC channel | the spec's stdio purity requirement | an interactive branch in the credential loader |
| 2026-08-24 | **Local stdio does not use MCP's OAuth.** That framework authenticates a client *to* a server; the need here is the opposite | MCP spec: stdio "SHOULD NOT" do protocol OAuth, "retrieve credentials from the environment" | treating MCP auth as the answer |
| 2026-07-23 | **The MCP server mirrors the library's own composition** — `create_server(get_workspace)` parallels `Workspace`; per-axis `register_*` parallel the mixins | [`specs/2026-07-23-mcp-server-design.md`](superpowers/specs/2026-07-23-mcp-server-design.md) | `research/mcp-server-design.md`, and an earlier plan for a *TypeScript*, comments-only server |

## 2026-07-09 → 2026-07-22 — the library, and what Google actually does

| Settled | Decision | Evidence | Superseded |
|---|---|---|---|
| 2026-07-22 | **Sheets comment→cell mapping requires an XLSX export and an XML parse** | [`experiments/sheets-cellmap/RESULTS.md`](../experiments/sheets-cellmap/RESULTS.md) | "parse the anchor to A1" |
| 2026-07-20 | **Docs suggestions are read-only — there is no accept/reject endpoint** | [`experiments/docs-suggestions/RESULTS.md`](../experiments/docs-suggestions/RESULTS.md) + full API enumeration | assuming a mutation existed and had been missed |
| 2026-07-20 | **`resolved` is absent on a never-resolved comment; soft delete strips content *and* author; resolve is an action-reply** | [`experiments/comment-lifecycle/RESULTS.md`](../experiments/comment-lifecycle/RESULTS.md) | modelling those fields as always present |
| 2026-07-20 | **Two axes: comments are uniform across the three types (one Drive API); content is variant (three APIs)** | [`specs/2026-07-20-csa-google-workspace-design.md`](superpowers/specs/2026-07-20-csa-google-workspace-design.md) | — |
| 2026-07-09 | **The Sheets `anchor` is an opaque `workbook-range` id, not A1-decodable** | [`experiments/anchor-probe/RESULTS.md`](../experiments/anchor-probe/RESULTS.md) | widely-repeated `R1C2`-style folklore, which this project had also believed |

## Standing rules that came out of being wrong

Not dated decisions so much as habits that exist because something bit us:

- **Probe beats docs.** When Google's documentation and an empirical probe disagree, the probe
  wins and the finding goes into `research/`. Three of the rows above are corrections to
  documented or widely-believed behaviour.
- **Prefer a loud failure to an inert one.** A folder URL, a missing value, an empty list, a
  bare id, an ungated `Backend` method: each is refused with a diagnosis rather than ignored.
  A control that looks configured and enforces nothing is the dangerous state, not "denied".
- **Live-verify anything that touches Google.** The unit suite runs on a fake; the fake cannot
  tell you that `permissions.list` omits `emailAddress` by default, or that `supportsAllDrives`
  is required for shared-drive files to have permissions at all.
- **`FakeBackend`-only tests have a known blind spot.** A duplicate method shadowing a real
  `ApiBackend` one passed a fully green suite; ruff and mypy caught it. Behaviour only
  `ApiBackend` has needs a stub-service test.
