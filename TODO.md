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

## Roadmap — nine subsystems, in order

Everything below this line was one item called "feature parity" until a code review showed it
is nine independent pieces with real dependencies between them. Each is its own spec → plan →
implement cycle; **do not try to plan them together.** At the granularity this project uses
(every task a failing test, a run, an implementation, a run, a commit) a combined plan runs to
several hundred steps and nobody executes it.

| # | Subsystem | Touches | Blocked on | Notes |
|---|---|---|---|---|
| **1** | **Tool alignment** — their names, argument shapes, and Claude's model-facing guidance | MCP layer only | — | **Start here.** No library change. |
| **2** | **File allowlisting** ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) | `Backend` wrapper | — | Do it **before** 4 and 5. See below. |
| **3** | **Discovery** — `search_files`, `list_recent_files` | library: new axis on `Workspace` | 2 | Biggest usability win. |
| **4** | **File lifecycle** — `create_file`, `copy_file`, `update_file`, `trash_file` | library: new axis | 2, 3 | |
| **5** | **Permissions** — `get_file_permissions`, `share_file` | library | **2** | `share_file` is an exfiltration primitive. |
| **6** | **Format breadth** — PDF, Office, ODF, images | `export` plumbing | — | Nearly free; `Document.export()` exists, just unexposed. Can ride with 1. |
| **7** | **Differentiators** — `approvals`, `revisions`, `changes`+`watch` | 3 new API surfaces | — | Own brainstorm each. `approvals` is the most on-mission thing found. |
| **8** | **Docs `batchUpdate` breadth** — 37 unused request types | library | — | A programme, not a plan. Tables first. |
| **9** | **Hosted server** — unlocks `files.watch` push, and removes install/OAuth-client/login for everyone | new transport + auth + custody | **2**, and a CASA decision | Largest item here, and almost all of it is security rather than features. Own section below. |

### Why #2 must come before #4 and #5 — and it is not only the security argument

**Every one of `Backend`'s 22 methods takes `file_id` as its first parameter.** That uniformity
is precisely what makes #82's `AllowlistBackend` trivial: wrap the backend, `policy.check(file_id,
op)`, delegate. No changes to existing methods.

The new operations break that shape:

- `search_files(query)` — **no `file_id` at all**, and it discloses titles and content snippets,
  which is information leakage even with nothing opened
- `list_recent_files()` — no `file_id`
- `create_file(title, content, parent_id)` — no `file_id`; it *produces* one
- `copy_file(file_id, …)` — has one, but also produces a new one

So #82 is not a security chore that can be deferred; it is **a schema decision with a
deadline.** Design the policy while 22 methods are uniform and the exceptions are deliberate.
Add discovery and creation first and the policy has to be retrofitted around them.

### Recommended first step

**#1 + #6 together.** One coherent plan, no library changes, ships the naming alignment and the
transferability that makes the flavour switch possible, adds format breadth almost for free, and
leaves `server.py` split into `_comments.py` / `_content.py` / `_files.py` — a shape that can
absorb the rest. `server.py` is 265 lines with 10 tools today; the next dozen tools need that
split regardless.

## Hosted MCP server — wanted, and a large piece of work

Wanted for real, not hypothetically: a hosted server is what unlocks **push notifications**
(`files.watch`), reacting the instant a comment appears rather than sweeping on a timer — and it
removes the install, the per-user OAuth client, and the `login` step for everyone.

It is also the single largest piece of work on this roadmap, and almost all of it is security
rather than features. Recording that honestly now, so nobody later mistakes it for "the same
server, on a box".

### Why it is not just a transport change

The local server has exactly one user, whose credentials live on their own machine. A hosted one
holds **per-user Google refresh tokens for many people** — each of which is full read/write/delete
on that person's entire Drive. `SECURITY.md` calls a single such token the crown jewel; this is
the crown jewels, plural, in one place, reachable from the internet.

### Inbound auth — the part MCP actually specifies

This is where MCP's OAuth framework finally applies: HTTP transports authenticate the *client to
the server*, which the stdio server deliberately skips.

- [ ] OAuth 2.1 **resource server**: validate every bearer token, reject anything not issued for
  us (RFC 8707 audience binding). **Token passthrough is explicitly forbidden** by the spec.
- [ ] Protected Resource Metadata (RFC 9728) + authorization-server discovery, so clients can
  find the AS. `WWW-Authenticate` on 401 with a `scope` hint.
- [ ] Client registration: **Client ID Metadata Documents** preferred; DCR is deprecated as of
  revision `2026-07-28` and kept only for compatibility.
- [ ] PKCE `S256`, mandatory. Refuse to proceed if the AS does not advertise
  `code_challenge_methods_supported`.
- [ ] **RFC 9207 `iss` validation** — new in `2026-07-28`, and required before an authorization
  code is sent to any token endpoint.
- [ ] Insufficient-scope handling: `403` + `WWW-Authenticate` with the scopes needed, so clients
  can step up rather than fail.

### Outbound Google auth — the part nobody specifies

- [ ] **Two token systems, never conflated.** The MCP client's token authenticates them *to us*;
  a separate per-user Google token authorizes *us to Google*. Mixing them is the confused-deputy
  vulnerability the spec names.
- [ ] Per-user Google refresh tokens in a real secret store, encrypted at rest, **isolated per
  user**. `Workspace.from_credentials(creds)` is already the entry point for this; the token file
  is not.
- [ ] Key management and rotation; revocation on offboarding that actually takes effect.
- [ ] **Reject domain-wide delegation** as the shortcut. A DWD service account can impersonate
  anyone in the org — a single key with more authority than every user token combined.

### Multi-tenancy

- [ ] One `Workspace` per request/user, never shared — the rule `SECURITY.md` already states,
  now load-bearing rather than advisory. `googleapiclient` clients are not thread-safe.
- [ ] No cross-user bleed in any cache (the `Sheet` cell-map cache is per-instance today; keep it
  that way).
- [ ] Per-user rate limiting and quota attribution, not global.
- [ ] Audit log of every mutation, attributed to a user, so a hijacked action is detectable after
  the fact.

### The push webhook itself

- [ ] Verified domain + valid certificate — Drive will not deliver otherwise.
- [ ] Validate the channel token on every delivery; treat the endpoint as **unauthenticated and
  hostile** until it is.
- [ ] Channel lifecycle: expiry, renewal, and cleanup of channels for revoked users.
- [ ] A public endpoint is new attack surface on a service holding many people's Drive tokens.
  Rate-limit and monitor it accordingly.

### And the thing that gets worse, not better

- [ ] **File allowlisting ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) matters more here.**
  Prompt injection through document content is the named primary risk; a hosted server runs that
  read→act path for many users continuously and unattended. The mitigation that does not depend
  on a model behaving well is the only one that scales.
- [ ] Public + full `drive` scope means Google **app verification plus an annual CASA
  assessment**. Real recurring cost, and a decision to make before building rather than after.

### Prior art in-house

CSA has already built most of this shape once: `CINO-Customer360` runs a FastMCP server with
Google OAuth, an Internal consent screen, Cloudflare Tunnel, and secrets in AWS Secrets Manager.
Its `docs/IT-SETUP.md` is the runbook to start from — note that it authenticates users *into* the
service with `openid email profile`, which is only the inbound half of what is needed here.

## Flavour switch — restrict this server to Google's or Claude's surface

- [ ] **`CSA_GW_FLAVOUR=google | claude | full`** (default `full`). Registers only the tools the
  chosen server exposes, under **their** names, with **their** descriptions and argument shapes.

  Why it is worth building:
  - **A predictable, smaller surface on request.** `google` is 8 tools with no share, no trash,
    no rename/move — a materially safer profile, chosen by a vendor who could have exposed more.
  - **Drop-in substitution.** Anyone already prompting against those servers keeps working;
    switching costs nothing and can be reverted.
  - **It forces the alignment work anyway.** Same names, same parameters, same descriptions is
    exactly what makes tools transferable between servers, whether or not the switch is used.

  Prerequisite: implement the overlapping tools with matching names and argument shapes
  (see the coverage section below). The verified detail that matters — the tool *names and
  parameters* are identical between Google's and Claude's; only the *descriptions* differ, with
  Claude's carrying extra model-facing guidance (e.g. "do not put document-type words inside
  `title`/`fullText` clauses"). Copy that guidance: it exists because models get it wrong.

- [ ] Decide what `full` says about itself. A flavour that is a superset of both should be
  explicit in its server description that it can edit documents and hold full-Drive scope, so
  nobody arrives from a read-mostly connector and assumes read-mostly behaviour.

## Underlying API capability inventory — what we could build

Enumerated from the discovery documents (see
[`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)).
This is the honest ceiling of the Python client, not a plan — but several items are closer to
"help people get work done" than more file management would be.

### Drive v3 — exposed by nobody, including us

- [ ] **`approvals`** — a **document review workflow already in the API**, adjacent to the
  comment workflow this project owns. The strongest item on this list. Ships as four tools:
  `list_approvals` (`approvals.list`/`get`), `start_approval` (`approvals.start`),
  `respond_to_approval` (`approve`/`decline`/`comment`), `reassign_approval`
  (`reassign`/`cancel`). Worth its own brainstorm: an approval is a *state machine*, unlike
  every tool shipped so far, and the library has no precedent for modelling one.
- [ ] **`revisions`** — `list`, `get`, `update` (`keepForever`), `delete`. **Version history:**
  read a prior version, diff two revisions, pin one. Obvious pairing with suggestions review.
- [ ] **`changes`** — `getStartPageToken`, `list`, `watch`. Incremental sync: the correct answer
  to "sweep my documents" instead of re-reading everything, and it directly addresses the
  autonomous-sweep cost `SECURITY.md` worries about.
- [ ] **`files.watch` / `changes.watch`** — push notification. **Planned, for the hosted
  server** (see its own section below), not for local stdio: Drive push requires a publicly
  reachable HTTPS endpoint on a *verified domain*, which a process behind NAT cannot be.
  `changes.list` polling covers the same ground locally until then. This is a genuine want —
  reacting the moment a comment lands is a different product from sweeping on a timer.
- [ ] **`files.modifyLabels` / `listLabels`** — Drive labels, i.e. classification and data
  governance. Plainly relevant to CSA's own work.
- [ ] `permissions.*` (full: list/create/get/update/delete) — **gated on
  [#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)**, see below.
- [ ] `accessproposals` — resolve "can I have access?" requests.
- [ ] ~~`drives.*` — shared drive administration.~~ Out of scope: it does not help anyone
  review a document.
- [ ] ~~`files.delete` / `emptyTrash` — **permanent** deletion.~~ Out of scope for now. Both
  other servers stop at trash. That is a considered line, and an agent holding full-Drive scope
  with attacker-influenceable input in front of it is the worst possible holder of an
  irreversible delete.
- [ ] ~~`files.generateCseToken`~~ — client-side encryption tokens; no reviewer workflow needs it.

### Docs v1 — we use 3 of 40 `batchUpdate` request types

`documents.get` / `create` / `batchUpdate` are the only three methods; everything lives in the
request types. We use `replaceAllText`, `insertText`, `deleteContentRange`. Unused, grouped:

- [ ] **Tables** — `insertTable`, `insertTableRow`/`Column`, `deleteTableRow`/`Column`,
  `mergeTableCells`, `unmergeTableCells`, `pinTableHeaderRows`, `updateTableCellStyle`,
  `updateTableRowStyle`, `updateTableColumnProperties`. The largest single gap.
- [ ] **Styling** — `updateTextStyle`, `updateParagraphStyle`, `updateDocumentStyle`,
  `updateNamedStyle`, `updateSectionStyle`. Needed for anything that formats rather than types.
- [ ] **Structure** — `createHeader`, `createFooter`, `createFootnote`, `insertPageBreak`,
  `insertSectionBreak`, `createParagraphBullets`, `deleteParagraphBullets`.
- [ ] **Images** — `insertInlineImage`, `replaceImage`, `deletePositionedObject`.
- [ ] **Named ranges** — `createNamedRange`, `deleteNamedRange`, `replaceNamedRangeContent`.
  A stable anchor for repeated edits, which is a better primitive than raw indices.
- [ ] **Tabs** — `addDocumentTab`, `deleteTab`, `updateDocumentTabProperties`. Relevant to the
  deferred `Location.tab` work.
- [ ] **Rich inserts** — `insertPerson` (smart chips), `insertRichLink`, `insertDate`.

### Sheets v4 — we use 6 of 17 methods

- [ ] `values.batchGet` / `batchUpdate` / `batchClear` — one round trip instead of N.
- [ ] The `*ByDataFilter` variants — address ranges by developer metadata rather than A1.
- [ ] `developerMetadata.get` / `search` — durable per-range annotation that survives edits.
- [ ] `sheets.copyTo` — copy a tab between spreadsheets.
- [ ] `spreadsheets.create`.

### Slides v1 — we use 2 of 5 methods

- [ ] **`pages.getThumbnail`** — render a slide to an image. The cheapest route to letting a
  model actually *see* a deck.
- [ ] `pages.get`, `presentations.create`.

## Coverage vs the Drive MCP servers  *(was: "feature parity" — premise corrected)*

> **Read [`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)
> before acting on this section.** Reading the actual tool schemas overturned the premise this
> item was written on. In brief: the connector's **`update_file` is metadata-only** (rename and
> move), and **neither server can edit an existing file's content at all**. So "parity" is the
> wrong goal — the overlap is small, the differentiator (content editing, comment lifecycle,
> cell mapping, suggestions) is already ours, and the real gaps are **discovery, file lifecycle,
> permissions and format breadth**. The research note also surfaces `approvals` and `revisions`,
> two Drive APIs neither server exposes, one of which is a document review workflow.

Match the built-in connector's tool surface so anyone moving between it and this server does
not have to relearn anything — same names, same argument shapes, comparable prompt
suggestions and description. **With one deliberate divergence: say plainly that this server
does full read/write and is correspondingly dangerous.** The connector is a read-mostly
convenience; this is a full-authority tool on the user's entire Drive.

Its surface is 11 tools. Names below are the connector's own, taken from its live schemas
rather than screenshots:

**Read-only (6)** — `search_files`, `list_recent_files`, `get_file_metadata`,
`get_file_permissions`, `read_file_content`, `download_file_content`

**Write/delete (5)** — `create_file`, `update_file`, `copy_file`, `share_file`, `trash_file`

### Google's own Drive MCP server is deliberately narrower — and that is the finding

[Google ships one too](https://developers.google.com/workspace/drive/api/reference/mcp)
(`drivemcp.googleapis.com`), and comparing the three is more instructive than either
target on its own:

| | Google's official | claude.ai connector | this server (proposed) |
|---|---|---|---|
| Transport | remote HTTP | remote | **local stdio** |
| OAuth scope | **`drive.file` / `drive.readonly`** | — | **full `drive`** |
| Tools | **8** | 11 | 11 + comments/content |
| `update_file`, `share_file`, `trash_file` | **absent** | present | proposed |

Two things stand out.

**Google omits exactly the three most dangerous tools.** They control the API and could
expose anything; they ship `copy_file` and `create_file` but no update, share or trash. That
is not an oversight, and it is worth treating as informed opinion about which operations are
safe to hand a model.

**Google never uses full-Drive scope.** `drive.file` is the *per-file* scope: an app sees
only files it created or the user explicitly picked. That is **allowlisting, enforced by
Google**, and it is why their server can be relaxed about the rest — it physically cannot
reach the document the user did not choose.

This project needs full `drive` for a real reason: it opens arbitrary files the user names by
URL, which `drive.file` cannot do
([`SECURITY.md`](SECURITY.md) §Scope breadth). That is a defensible trade, but it means **we
gave up the safety property Google gets for free, and file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) is how we
buy it back in software.** Adding this tool surface on full-Drive scope with no allowlist
would make this server strictly more dangerous than either comparator, which is not a
position to ship from.

### This reverses a documented capability boundary — decide that first

`README.md` currently states, as a deliberate design boundary: *"No document discovery. You
hand the library a file id/URL; there is no `files.list`/search."* `search_files` and
`list_recent_files` are exactly that. So this is **a library change, not an MCP-layer
change**: it needs `Backend` methods, `FakeBackend` parity, the conformance guard, and a
decision to widen the library's scope. Not a tool-registration exercise.

**Correction to an earlier note here:** this file previously implied discovery was excluded
for a security reason. It was not. There is **no recorded rationale anywhere** — not in the
design spec, not in `SECURITY.md`, not in either MCP spec. The only justification on record is
circular ("the library is document-scoped, so every tool takes a file id/URL"), and the README
had it filed under *"what the Google APIs can't do"* next to two genuine impossibilities —
while its own workaround calls `files.list()` successfully. A scope choice had hardened into an
apparent constraint.

The honest case *for* keeping it out of the library: Drive query syntax, pagination, shared
drives and corpora are a sizeable surface to own forever, and this library's value is comments
and cell mapping, not Drive browsing. The case against: the documented workaround needs a
Drive client anyway, so the boundary saves a caller nothing but a loop — and for the MCP
server there is no host application to hand us a file id, which makes it the difference
between "ask about a document" and "paste a URL first". Both Google's own server and the
claude.ai connector lead with `search_files`.

Separately worth weighing, but as a *consequence* rather than the reason: `SECURITY.md` names
the **autonomous sweep** as the highest-risk use case because it ingests comments from many
documents, and search is what makes such a sweep easy. That argues for landing discovery
alongside #82, not for leaving it out.

### `share_file` is an exfiltration primitive — gate it behind #82

Worth separating from the other writes. `share_file(fileId, emailAddress, role)` grants an
**arbitrary email address** reader/commenter/writer access. Every other write tool modifies
content the user can see afterwards; this one silently hands an outsider a copy, and the user
may never notice.

Combined with the two things already true of this server — document text is
attacker-influenceable, and there is no file allowlist — an injected comment saying *"share
this with archive-bot@…"* is a working data-exfiltration path that no amount of tool-
annotation hinting prevents. **`share_file` should not ship before file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)), and
arguably wants its own explicit opt-in even then.**

`trash_file` is destructive but recoverable (Drive trash, not permanent delete), so it ranks
below `share_file` despite sounding worse.

### Checklist

- [ ] **Decide the discovery question.** Widen the library to support `files.list`/search, or
  decline parity on those two tools and say why in the README. Everything else waits on this.
- [ ] **Decide how much parity is actually wanted.** Google's 8 tools may be the better
  target than the connector's 11: matching Google means matching a vendor's considered
  judgement about what is safe to expose, and the three it omits are the three this project
  would most need to gate anyway. Full parity with the connector is a choice to be more
  permissive than either existing implementation, on a broader scope than either — worth
  making deliberately rather than by default.
- [ ] `search_files` — reuse the connector's **Drive query syntax** verbatim
  (`title contains`, `fullText contains`, `mimeType`, `modifiedTime`, `parentId`, `owner`,
  `sharedWithMe`, combined with `and`/`or`/`not`). Also copy its hard-won prompt guidance:
  *do not put document-type words inside `title`/`fullText` clauses; map them to `mimeType`
  instead* — that instruction exists because models get it wrong.
- [ ] `list_recent_files` — `orderBy` of `recency` | `lastModified` | `lastModifiedByMe`,
  page size default 10, token pagination.
- [ ] `get_file_metadata`, `read_file_content`, `download_file_content` — largely wrappers
  over what the library already does (`open`, `as_text`, `export`).
- [ ] `get_file_permissions` — new surface (Drive permissions API). Read-only but sensitive:
  it reveals who a document is shared with.
- [ ] `create_file`, `update_file`, `copy_file`, `trash_file` — new surface (Drive files API).
  Note the library is deliberately document-scoped today; file *lifecycle* is a new axis.
- [ ] `share_file` — **blocked on #82.** See above.
- [ ] **Tool descriptions and the server description must state the danger explicitly.**
  Parity of names must not imply parity of risk. A user who has used the connector will
  assume read-mostly; the description has to correct that before their first write.
- [ ] Prompt suggestions, matching the connector's shape.
- [ ] Pagination convention (`pageToken` / `next_page_token`) — the library has no paginated
  accessor today; `ApiBackend.list_comments` paginates internally and returns everything.
  Decide whether tools expose page tokens or keep hiding them.

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
