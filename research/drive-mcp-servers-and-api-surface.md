# Drive MCP servers, and what the Drive/Docs APIs actually offer

**Date:** 2026-08-25 · **Method:** tool schemas read from the live claude.ai connector in a
running session; Google's tool docs fetched from `developers.google.com`; API surfaces
enumerated from the **discovery documents** (`https://www.googleapis.com/discovery/v1/apis/…`)
rather than from prose. Probe beats docs.

## Why this exists

A roadmap note assumed the claude.ai connector's `update_file` edited document content, on the
strength of its name. It does not. That one wrong assumption had already produced a "feature
parity" plan pointed in the wrong direction, so every tool in both servers was read from its
actual schema. **Two of the conclusions below reverse what the name implies.**

---

## 1. The claude.ai Google Drive connector — 11 tools, as they actually behave

### Read (6)

| Tool | What it actually does |
|---|---|
| `search_files` | Drive query syntax: `title`, `fullText`, `mimeType`, `modifiedTime`, `viewedByMeTime`, `createdTime`, `parentId`, `owner`, `sharedWithMe`, combined with `and`/`or`/`not`. Paginated. Returns content snippets unless suppressed. |
| `list_recent_files` | `orderBy` ∈ `recency` \| `lastModified` \| `lastModifiedByMe`. Page size 10 by default. |
| `get_file_metadata` | File metadata, plus a content snippet unless suppressed. |
| `get_file_permissions` | Lists the file's permissions. Read-only, but reveals who a document is shared with. |
| `read_file_content` | **Natural-language text representation**, and *optionally comments inlined* with thread mappings. Supports 13 mime types: Docs/Sheets/Slides, **PDF**, Word/Excel/PowerPoint, ODT/ODS/ODP, and **PNG/JPEG**. |
| `download_file_content` | Raw bytes as base64, with `exportMimeType` for Google-native files. |

### Write (5)

| Tool | What it actually does |
|---|---|
| `create_file` | Creates or uploads. `textContent` or `base64Content` + `contentMimeType`; can create an *empty* Doc/Sheet/Slides or a folder; converts to Google types unless `disableConversionToGoogleType`. |
| **`update_file`** | **Metadata only.** Its own schema says *"currently only title and parent_id are supported"* — so: **rename and move. It does not touch content.** |
| `copy_file` | Duplicate, optional new title/parent. Defaults to `Copy of {title}`. |
| `share_file` | Grants an **arbitrary `emailAddress`** a role of `writer` \| `commenter` \| `reader`. Upgrades an existing role if the new one is higher. |
| `trash_file` | Moves to trash. **Not** a permanent delete. |

## 2. Google's own server — the same implementation, minus three

[`drivemcp.googleapis.com`](https://developers.google.com/workspace/drive/api/reference/mcp)
exposes **8** tools, identical in name and behaviour to the connector's, omitting
`update_file`, `share_file` and `trash_file`. It is **remote/hosted** (endpoint
`https://drivemcp.googleapis.com/mcp/v1`), authorized with **`drive.file` /
`drive.readonly`** — never full `drive`.

**Verified: the shared tools are the same tools.** Names, parameters and — for `search_files`
— the full list of supported query terms match exactly. The one difference is in the
*descriptions*: the claude.ai connector's carry extra model-facing guidance that Google's
reference does not, such as *"do not put document-type words inside `title`/`fullText` clauses;
map them to `mimeType`"*. Same capability, wording better tuned for a model. Worth copying that
guidance rather than reinventing it — it exists because models get this wrong.

Two inferences worth holding onto:

- **The three it omits are the three highest-risk ones** — the exfiltration primitive, the
  destructive one, and the mutating one. Google controls this API and could expose anything.
- **`drive.file` is allowlisting enforced by Google.** An app sees only files it created or the
  user explicitly picked. That is why their server can be relaxed about everything else: it
  physically cannot reach a document the user did not choose.

## 3. The headline finding: **neither server can edit an existing file's content**

`create_file` uploads content to a *new* file. `update_file` changes *metadata*. Nothing in
either server modifies the body of a document that already exists — confirmed by Google's own
documentation for `create_file`: *"it cannot modify an existing file's content."*

So the framing "we need parity with them" was wrong in both directions.

| Capability | Google MCP (8) | claude.ai connector (11) | `csa-google-workspace` |
|---|---|---|---|
| Search / discovery | ✅ | ✅ | ❌ |
| List recent | ✅ | ✅ | ❌ |
| File metadata | ✅ | ✅ | partial (`open()` → id/name/type/url) |
| Read permissions | ✅ | ✅ | ❌ |
| Text of a document | ✅ | ✅ | ✅ `as_text()` |
| Read PDF / Office / ODF / **images** | ✅ | ✅ | ❌ Docs/Sheets/Slides only |
| Raw export | ✅ | ✅ | ✅ `export()` |
| Read comments | inline text | inline text | ✅ **structured objects** |
| Create file / folder | ✅ | ✅ | ❌ |
| Copy | ✅ | ✅ | ❌ |
| Rename / move | ❌ | ✅ | ❌ |
| Share (grant access) | ❌ | ✅ | ❌ |
| Trash | ❌ | ✅ | ❌ |
| **Edit existing content** | ❌ | ❌ | ✅ **only here** |
| **Comment lifecycle** (create/reply/resolve/reopen/edit/delete) | ❌ | ❌ | ✅ **only here** |
| **Sheets comment → cell mapping** | ❌ | ❌ | ✅ **only here** |
| **Docs suggestions read + accept/reject preview** | ❌ | ❌ | ✅ **only here** |

### Neither of them is the wrong choice

Worth stating plainly, since a table of ticks invites the opposite reading. For a lot of people
those servers are simply **better**: Google's is hosted, so it works with any MCP client with no
install, no OAuth client to create, and `drive.file` scope — which means it can reach only files
the user explicitly picked, a stronger safety property than this library can offer itself. The
claude.ai connector is built in, so setup is zero. This one asks for an install, your own OAuth
client, and full-Drive scope.

**These are complementary, not competing.** They do Drive *file management* and broad-format
*reading*. This project does deep document *editing* and *comment workflow*. The genuine gaps
here are discovery, file lifecycle, permissions, and format breadth — not "catching up".

---

## 4. What the APIs actually offer

Enumerated from the discovery documents. **Docs v1 has exactly three methods** —
`documents.get`, `documents.create`, `documents.batchUpdate` — so all its power lives in
`batchUpdate` request types. Drive v3 is far larger than the part anyone uses.

### Drive v3 surface nobody above exposes

| Resource | Methods | Why it matters here |
|---|---|---|
| **`approvals`** | `start`, `list`, `get`, `approve`, `decline`, `reassign`, `cancel`, `comment` | A **full document review workflow**, in the API. Directly on-mission for a comment-triage tool, and *neither MCP server touches it.* The most interesting thing in this document. |
| **`revisions`** | `list`, `get`, `update`, `delete` | **Version history.** Read prior versions, diff them, pin `keepForever`. Nobody exposes it. |
| **`changes`** | `getStartPageToken`, `list`, `watch` | Incremental sync. The correct answer to "sweep my documents" instead of re-reading everything. |
| **`files.watch`** | + `changes.watch` | **Push notifications.** A review bot could react to a new comment instead of polling. |
| `files.modifyLabels`, `files.listLabels` | | Drive **labels** — classification and data governance. Obvious CSA relevance. |
| **`accessproposals`** | `list`, `get`, `resolve` — **no `create`** | Answering "can I have access?" requests. **Shipped** — see §accessproposals below. |
| `permissions` | `list`, `create`, `get`, `update`, `delete` | Full permission management; the connector exposes only a share-shaped slice of it. |
| `drives` | `create`, `list`, `get`, `update`, `hide`, `unhide`, `delete` | Shared drive administration. |
| `files.delete`, `files.emptyTrash` | | **Permanent** deletion. Note the connector deliberately stops at `trash_file`. |
| `about.get` | | Quota, import/export formats, capabilities. **Now probed** — [`experiments/export-formats/RESULTS.md`](../experiments/export-formats/RESULTS.md) has the full conversion matrix. |
| `files.generateIds`, `files.download`, `files.generateCseToken` | | Batch id pre-allocation; client-side encryption. |

Already used here: `files.get`/`export`, `comments.*`, `replies.*`.

### Corrections to our own understanding

- `files.update` **can** change content (Drive-level media upload) — it is only the *connector's*
  `update_file` that is metadata-only. Do not carry that limit into our own naming.
- `revisions` and `approvals` were absent from earlier research notes entirely. `research/`
  covered comments and suggestions in depth and treated the rest of Drive as out of frame.
- **Export formats differ by document type, and roadmap #6's "images" was wrong.** Probed
  2026-08-25: a Doc exports Markdown, HTML, EPUB, RTF, PDF, DOCX, ODT, `text/plain` and zip; a
  **deck exports only PDF, PPTX, ODP and `text/plain`** — no Markdown, no HTML; a sheet exports
  CSV/TSV/XLSX/ODS/PDF/zip. Only **drawings** export PNG/JPEG/SVG, and the library cannot open a
  drawing. Full matrix: [`experiments/export-formats/RESULTS.md`](../experiments/export-formats/RESULTS.md).
- **How the connector reads PDFs and images, probably.** Its `read_file_content` covers 13 mime
  types including PDF and PNG/JPEG. Drive's *import* table converts `application/pdf` and
  `image/*` **into a Doc** — i.e. OCR. If that is the mechanism, note what it costs: reading a
  PDF that way **creates a file**, so it is not a read operation and does not belong behind a
  `readOnlyHint`. Matching those 13 types honestly needs local extraction instead.

## 5. Consequences for the roadmap

1. **Drop "parity" as the goal.** The overlap is small and the differentiator is already ours.
   Adopt their *names and query syntax* where we implement the same thing, so users transfer —
   but the target is coverage of what users need, not a tool count.
2. **Discovery (`search_files`, `list_recent_files`) is the highest-value gap** and the one that
   currently forces every MCP interaction to start with a pasted URL.
3. **`approvals` deserves its own look.** A review-workflow API that no one exposes, adjacent to
   the comment workflow this project already owns, is a stronger differentiator than matching
   `copy_file`.
4. **Format breadth (PDF/Office/images) is a real gap** and is mostly `files.export` plumbing.
5. **`share_file` and anything from `permissions` stay blocked on file allowlisting
   ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82))** — with
   full `drive` scope and attacker-influenceable document text, granting access to an arbitrary
   email address is an exfiltration path. Google avoids this by never taking full scope; we
   took full scope for a real reason and must buy the property back in software.


## `accessproposals`, read from the discovery document

`[probed]` — 2026-08-30, against the discovery document the installed `googleapiclient` resolves,
not against Google's prose. Shipped in the library and as two MCP tools.

### The name misleads, and the shape is the opposite of what it suggests

| method | HTTP | scopes |
|---|---|---|
| `list` | `GET files/{fileId}/accessproposals` | incl. `drive.readonly`, `drive.metadata.readonly` |
| `get` | `GET files/{fileId}/accessproposals/{proposalId}` | incl. the `.readonly` pair |
| `resolve` | `POST files/{fileId}/accessproposals/{proposalId}:resolve` | **`drive` or `drive.file` only** |

**There is no `create`.** This API cannot request access to a file you cannot reach; it lets an
owner see and answer requests other people made through Drive's UI. That is the *other side* of
the interaction the name suggests — and the better side for a triage tool.

**The scope table settles the capability question empirically.** `list`/`get` accept the
`.readonly` scopes; `resolve` demands a write scope. Google itself classifies resolving as a
write, which is why `resolve_access_proposal` is gated as `file.share` rather than as something
gentler — approving *grants a permission*.

It is a **file sub-resource**, so it fits the `file_id`-first `Backend` shape directly, unlike
search and create (which forced the account axis in `files.py`).

### Schemas

```
AccessProposal:  createTime  fileId  proposalId  recipientEmailAddress
                 requestMessage  requesterEmailAddress  rolesAndViews[]
AccessProposalRoleAndView:      role  view
ResolveAccessProposalRequest:   action  role[]  sendNotification  view
ListAccessProposalsResponse:    accessProposals[]  nextPageToken
```

Three things worth knowing before using it:

1. **`action` is `ACTION_UNSPECIFIED | ACCEPT | DENY`** — a three-state whose third member means
   "you did not decide". `src/csa_google_workspace/access_proposals.py` therefore exposes
   `accept()` and `deny()` and keeps the raw string at the `Backend` seam, so "undecided" is
   unrepresentable rather than merely invalid. See `CLAUDE.md` invariants 9 and 10 for the two
   times this repository was bitten by exactly that shape.
2. **`role` on the resolve body is a LIST**, despite granting a single role.
3. **`requesterEmailAddress` is a plain, always-present string** — a genuine exception to this
   API's reluctance to identify people. `User.emailAddress` elsewhere in Drive is conditional
   ("may not be present … if the user has not made their email address visible"), and comment
   authors usually have none. A request for access is unactionable without it.

### `requestMessage` is the sharpest untrusted input this project has

Every other untrusted string here — document text, comment bodies — was written by somebody who
**already had access** to the file. `requestMessage` is free text from somebody with **no access
at all**, and it reaches a model being asked to decide whether to **give them some**. The barrier
to injecting it is clicking "Request access" on a link.

That does not make the capability unsafe to ship, but it does set the rules: decide on
`requesterEmailAddress`, never on the message or a display name; report the message rather than
acting on it; and keep it out of `__repr__`, because a log line is where injected text gets read
later by something that has forgotten where it came from.
