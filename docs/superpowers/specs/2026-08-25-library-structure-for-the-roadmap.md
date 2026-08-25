# Structure for what comes next — a shape review before roadmap #1

**Status:** accepted architecture direction. Not a plan; the plan for #1+#6 is
[`../plans/2026-08-25-tool-alignment-and-format-breadth.md`](../plans/2026-08-25-tool-alignment-and-format-breadth.md).

**Why now.** The library is 2,354 lines and does one thing cleanly. `TODO.md` lists nine
subsystems that will roughly triple it. The question this document answers is not "what should
we build" — that is the roadmap — but **"does the current shape absorb it, or does it have to
bend?"** Answering before #1 rather than during #4 is the whole point: the expensive mistakes
here are the ones that look free while there is only one kind of operation.

## 1. The library today has exactly one axis, and it is per-file

Everything is reached by opening a file:

```
Workspace(backend, read_only)
    .open(url_or_id) -> Document            # MIME sniff -> typed subclass
                          .comments         # uniform  (Drive API, all three types)
                          .export(mime)     # uniform
                          Doc/Sheet/Slides  # variant  (Docs v1 / Sheets v4 / Slides v1)
```

`CLAUDE.md` already names the two axes *inside* a document — **uniform** (comments: one API
for all three types) and **variant** (content: three APIs). That distinction is sound and is
not what changes. What changes is that both of those axes live *below* `open()`, and half the
roadmap does not.

**The 22 `Backend` methods all take `file_id` first.** That is not a coincidence; it is what
"one axis" means expressed in the seam.

## 2. What the roadmap actually adds: a second, account-scoped axis

Sorting the nine subsystems by *what they are scoped to* — rather than by feature area — the
split is clean and it is not the split the roadmap table implies:

| Roadmap item | Scope | Fits today's shape? |
|---|---|---|
| #1 tool alignment | — | Yes. MCP layer only. |
| #6 format breadth | per-file | **Yes** — `Document.export()` already exists. |
| #5 permissions | per-file, uniform | Yes, as a mixin beside `CommentsMixin`. |
| #7 revisions | per-file, uniform | Yes, as a mixin. |
| #7 approvals | per-file, uniform | Yes, as a mixin. |
| #8 Docs `batchUpdate` | per-file, variant | Yes — `Doc`/`Sheet`/`Slides` grow methods. |
| **#3 discovery** | **account** | **No.** `search_files(query)` has no file. |
| **#4 lifecycle (create)** | **account** | **No.** It *produces* a file id. |
| **#7 changes feed** | **account** | **No.** Drive-wide, not file-wide. |
| #2 allowlist | cross-cutting | A `Backend` decorator — see §5. |
| #9 hosted server | deployment | Transport + auth; no document logic. |

Six of eleven fit as-is. The three that do not are all the same shape: **operations about the
Drive, not about a document.** They need a home, and `Document` is the wrong one — you cannot
`open()` a file you are trying to find, and you cannot `open()` a file that does not exist yet.

## 3. The direction: `Workspace` grows collections, `Document` grows mixins

```
Workspace                          # credentials + read_only + backend; the DI seam
    .open(url_or_id) -> Document   # existing per-file axis, unchanged
    .files                         # NEW  account axis: search, recent, create, copy
    .changes                       # NEW  account axis: the change feed  (#7)

Document                           # per-file; uniform Drive concerns compose as mixins
    .comments        CommentsMixin       exists
    .permissions     PermissionsMixin    #5
    .revisions       RevisionsMixin      #7
    .approvals       ApprovalsMixin      #7
    .export(mime)                        exists  (#6 exposes it)
  Doc | Sheet | Slides             # the variant content axis, unchanged  (#8 grows it)
```

Three properties of this that are worth stating as commitments, because each has a tempting
cheaper alternative:

**`Workspace` gains collections, not methods.** `ws.files.search(...)`, not
`ws.search_files(...)`. `CommentCollection` is the precedent and it earns its keep: the
collection is where filtering, pagination and lazy fetch live without cluttering the thing that
holds credentials. `Workspace` is 53 lines and should stay roughly that size — it is the DI
seam embedders implement against, and a fat entry point is the thing `Workspace(backend=…)`
exists to avoid.

**Uniform Drive concerns arrive as mixins, one per concern, never as `Document` methods.**
`CommentsMixin` is already the pattern. Permissions, revisions and approvals are *the same
shape* as comments — one Drive API, identical across Docs/Sheets/Slides — so they get the same
treatment. This keeps the per-concern module (`comments.py`, later `permissions.py`) as the
single place a concern lives, models and all.

**`base.py` becomes composition only.** It is 71 lines holding `Document`, `CommentsMixin`,
`MIME_TO_TYPE`, `subclass_for_mime` and a batch-reply helper. With four mixins the mixins must
not live there. Target: `base.py` holds `Document`, the MIME map, and the dispatch function;
each mixin lives with its models in its own module.

## 4. What must not happen

Each of these is cheap once and expensive four times.

- **No `if doc.type == …` ladders.** `MIME_TO_TYPE` / `subclass_for_mime` is the single
  dispatch point (`CLAUDE.md` invariant 5), and the MCP layer already has the right tool for
  the delivery side: `_require(doc, attr, what)` asks the object rather than its label. Every
  new per-type capability uses one of those two.
- **No account-scoped operation hung off `Document`.** A `doc.search_siblings()` would be the
  moment the shape breaks.
- **No second entry point.** Not `DriveClient` alongside `Workspace`. One object holds
  credentials, or per-user isolation (§6) becomes something you have to remember rather than
  something the type system gives you.
- **No caching retrofit.** Caching is off by default *by design* — live multi-reviewer
  sessions make a self-invalidated cache actively wrong (`CLAUDE.md` fact 6). Discovery will
  make this tempting, because search feels like it should be cheap. It is a deliberate
  deferral, not an oversight.

## 5. `Backend` is where the roadmap's one real schema decision lives

This is recorded in `TODO.md` and repeated here because it is a *structural* fact, not a
security preference: **all 22 `Backend` methods take `file_id` first**, which is exactly why
#82's `AllowlistBackend` can be a wrapper — `policy.check(file_id, op)`, delegate, done, with
no change to any existing method.

The account-axis methods break that uniformity, and each breaks it differently:

| New method | Shape | What the policy must decide |
|---|---|---|
| `search_files(query)` | no id | Filter results? Refuse? Titles and snippets leak either way. |
| `list_recent_files()` | no id | Same. |
| `create_file(...)` | *produces* an id | Is a newly created file automatically allowed? |
| `copy_file(id, …)` | consumes **and** produces | Both questions at once. |

So #82 is **a schema decision with a deadline**, and the deadline is #3. Design the policy
while the 22 methods are uniform and the four exceptions are deliberate; add discovery first
and the policy gets retrofitted around whatever those four happened to do.

The seam also has a rule that is easy to violence by accident: `Backend`, `ApiBackend` and
`FakeBackend` move together, guarded by `tests/test_backend_conformance.py`. Every method added
to the protocol needs all three plus — for `ApiBackend`-only behaviour like pagination — a
stub-service test (`CLAUDE.md` invariants 3 and 4). Budget that per method, not per feature.

## 6. What the hosted server (#9) demands of the structure

Nothing new, which is the useful finding — but it *hardens* two existing rules from advice into
requirements:

- **One `Workspace` per user, never shared, never across threads.** Today `SECURITY.md` says
  this and the stdio server's thread-local provider honours it. Multi-tenant, violating it is a
  cross-user data leak rather than a `googleapiclient` thread-safety bug.
- **`from_credentials` is the real entry point.** `from_oauth` and the token file are the local
  convenience. Anything that assumes a token *file* — rather than a `Credentials` object handed
  in — becomes a thing to unpick later.

Concretely: keep credential acquisition out of the library's core objects. `auth.py` already
separates `load_cached_credentials` (no interactive branch) from `load_credentials`, which is
the same instinct applied at the function level.

## 7. The MCP layer needs the same split, one release earlier

`server.py` is 265 lines and registers 10 tools through three `register_*` producers. The
producers are the right seam — but the file cannot hold thirty tools.

```
mcp/
  server.py        create_server() — composition only
  _tools/
    content.py     read_file_content, download_file_content, get_file_metadata
    comments.py    the seven comment tools
    files.py       search_files, list_recent_files, create_file, …   (#3, #4)
    permissions.py get_file_permissions, share_file                  (#5)
    auth.py        authenticate
  _schemas.py      -> split alongside, same axes
```

Two things this shape buys that are worth doing it for:

**The flavour switch becomes a registration-time predicate.** `TODO.md` wants a switch limiting
this server to Google's or the claude.ai connector's surface. With per-axis producers that is
a filter over *which tools get registered* — the tool simply is not there — rather than a
runtime check inside each handler. A tool that exists and refuses is worse than absent: it
still occupies the model's attention and its own description has to explain the refusal.

**`_errors` and the annotation constants stay shared.** They are already module-level in
`server.py`; they move to a `_tools/_base.py` and every producer imports them. The invariant
worth guarding is that `_errors` must raise the SDK's `ToolError` — anything else becomes an
`UnexpectedToolError` with the message suppressed, and the user sees nothing useful.

## 8. One SDK fact found while checking this, because it changes the naming plan

Aligning tool names with Google's and Anthropic's servers means matching their **wire
parameter names**, which are camelCase (`fileId`, `includeComments`, `exportMimeType`).

`Annotated[str, Field(alias="fileId")]` on a snake_case parameter **publishes the right schema
and then fails every call.** The SDK validates into a model, dumps it *by alias*, and calls
`fn(**kwargs)` — so the handler receives `fileId=` and raises `TypeError`, which surfaces as
`UnexpectedToolError` with the message suppressed. Verified against `mcp` 2.1.0:
`list_tools` shows `{"fileId": …}`, and `call_tool` dies.

So a wire-aligned parameter must be *literally named* `fileId` in the Python signature. That is
un-Pythonic, and it is fine here for a reason that is structural rather than a concession: the
tool handlers are a **wire adapter**, translating one external contract (Google's tool schema)
into another (the library's Pythonic API). Adapters are named after the thing they adapt. The
library API does not follow suit and must not.

## 9. Sequencing consequence

The recommended first step is unchanged — **#1 + #6 together** — and this review adds one
reason: it is the only item that delivers the `_tools/` split, and every later subsystem lands
in it. Doing #3 first would mean adding an account axis to a 265-line single file *and*
designing the allowlist policy under time pressure.

Order: **#1+#6** (structure + naming, no library change) → **#2** (policy, while the seam is
uniform) → **#3** → **#4/#5** → **#7/#8** → **#9**.
