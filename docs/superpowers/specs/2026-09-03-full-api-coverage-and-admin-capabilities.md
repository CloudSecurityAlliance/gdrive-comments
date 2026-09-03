# Full API coverage, and a capability class that is OFF by default

**Status: proposed, 2026-09-03 (CINO ask).** Not started. Written before code because it
**reverses four recorded decisions** and **widens the OAuth token**, and both should happen
deliberately.

## The governing principle this serves

**"The MCP server cannot do that" must never be a technical answer.** The answer should be
*"that is extremely risky, so we gated it off and disabled it by default — and if you absolutely
want those administrative functions on, we can turn them on."*

Whether to let an AI do a given thing is a **business and risk decision**. A missing
implementation makes that decision silently and disguises it as a technical fact, so the operator
never gets to weigh it. That is what this programme is for — not completeness for its own sake.

**The one place the principle has a real, ongoing cost is scope**, and §2 is about that. The
resolution proposed here is **incremental authorization**: request an additional OAuth scope at
the moment an operator *enables* the capability that needs it, rather than at install. A default
install then holds a narrow token, the answer *"we can enable that"* stays true, and the token
never carries authority for a capability nobody switched on. Without that, "no technical
blockers" would mean permanently widening the token for capabilities that are off — which the
capability system cannot protect, because a stolen token never reaches it.

## The ask

1. 100% API coverage.
2. A new capability category, **disabled by default**, for admin actions — the examples given
   were *"allow sharing outside of drive membership"* and *"creating a new shared drive"*.

The second is the right instinct and this spec adopts it with a change: **one category is too
few**, and the reason it must be off by default is **not** the reason the existing eleven are on.

## 1. What "100%" actually costs — measured, not estimated

Enumerated from the live discovery documents, 2026-09-03:

| API | methods | `batchUpdate` request types |
|---|---|---|
| Drive v3 | **64** | — |
| Docs v1 | 3 | **40** |
| Sheets v4 | 17 | **69** |
| Slides v1 | 5 | **44** |
| | **89** | **153** |

**~242 distinct operations. `Backend` has 43.** So literal 100% is roughly a sixfold expansion,
and **153 of the 242 are `batchUpdate` request types.**

### Most of those request types are a different product

`addSlicer`, `createSheetsChart`, `addDataSource`, `cancelDataSourceRefresh`, `addBanding`,
`createVideo`, `addDimensionGroup`, `createFootnote`. That is a **spreadsheet and presentation
authoring** library. This one is scoped to *comments and content on Docs, Sheets and Slides, for
embedding in AI tooling* — and the scope statement is the reason it has stayed coherent.

**Recommendation: reject literal 100% and adopt a stated boundary instead.** "Everything in the
API" is not a scope, it is the absence of one, and the cost is not the code — it is that every
future question ("should this library do charts?") loses its answer.

### The boundary worth committing to

- **All of Drive v3**, minus four that should never be implemented (below). Drive is the axis
  this library *is* — comments are a Drive concern, and the uniform axis is the whole design.
- **Docs / Sheets / Slides request types that serve comments-and-content**: text, structure,
  tables, tabs, notes, protected ranges. Not charts, not data sources, not video.
- **Never**: `teamdrives.*` (a deprecated alias for `drives.*` — implementing it would ship a
  second name for one thing), `files.generateCseToken` (client-side encryption needs CSE
  infrastructure we do not have), `channels.stop` + `*.watch` (a webhook endpoint is
  infrastructure, not an API call, and belongs in the embedder), `apps.*` (which third-party
  apps a user has installed is not this library's business).

## 2. THE CAVEAT THAT MATTERS MOST: capability gating does not protect a stolen token

Some coverage requires **new OAuth scopes**:

| coverage | scope | today |
|---|---|---|
| `files.modifyLabels` | `drive.labels` **write** | never requested — `labels.py` documents that this makes mislabelling *impossible rather than merely disabled* |
| attribution / "undo what Bob did" | `drive.activity.readonly` | never requested |
| anything admin-wide | Admin SDK | a different API entirely |

**A capability gate binds this library's own calls. It does nothing whatsoever for a leaked
token.** `SECURITY.md` names scope breadth as a standing risk for exactly this reason: the token
in `~/.csa_google_workspace/token.json` is the asset, and every scope added makes it a larger
prize while the capability system — which lives in the same process the attacker would bypass —
offers no protection at all.

So **"off by default" is not a substitute for "not requested".** Where a capability needs a new
scope, that is a separate and larger decision than adding the capability, and it must be taken
as one. Two of the three categories below need **no** new scope, which is why they are tractable
now; label writing is deliberately not among them.

## 3. Three categories, not one — and they fail differently

The ask proposed one "admin" category. Splitting it matters because an operator will genuinely
want one without the others: somebody publishing a public corpus wants `share.public` and must
not get drive administration with it.

Also, **"admin" is the wrong word.** None of these needs a Workspace super-admin — a drive
organizer does them, as an ordinary user. Calling the category `admin` invites confusion with
`useDomainAdminAccess` and the Admin SDK, which this library deliberately does not touch.

| capability | covers | why it is its own class |
|---|---|---|
| **`drive.admin`** | `drives.create` / `update` / `delete` / `hide` / `unhide`, drive restrictions | Changes a **container and everything in it** — including files other people put there. The blast radius is not the caller's own data. |
| **`share.public`** | `permissions.create` with `type=anyone` or `type=domain` | **Re-restricting is not un-publishing.** Once a document has been world-readable it may be cached, indexed or copied; restoring the permission does not restore confidentiality. |
| **`content.destroy`** | `files.delete` (permanent, bypasses trash), `files.emptyTrash`, `revisions.delete` | The only operations here with **no recovery path at all**. `file.trash` already exists and trash is recoverable; this is not administration, it is destruction. |

## 4. Why they are OFF by default, and why the existing reason does not apply

**This is the part that must be written down, or the next person will switch them on and be
reasoning correctly from the stated principle.**

v0.31.0 turned all eleven capabilities ON, with a good argument: *a capability enabled here is
not a permission granted — every call runs as the authorizing user against Drive's ACLs, so this
is a ceiling **below** Drive's.*

**That argument applies to all three categories above, and is not the point.** The operator can
create a shared drive, publish a document, and permanently delete a file through the Drive UI
today. Authority is not the distinction.

The distinction is **recovery**. Every currently-enabled capability's mistakes are recoverable:
Drive's trash restores a trashed file, Drive's revision history restores content, an unshare
revokes a grant. These three have no recovery:

- a permanently deleted file is **gone** — and measured 2026-09-03, a Google Doc exposes only
  **two** revisions through the API, so even the history is thin;
- a lifted drive restriction has already exposed every file in that drive for the window it was
  off, and nothing records who looked;
- a published document may already have been copied, and `files.copy` **drops comments**, so
  what was copied is not even a faithful record of what leaked.

So the gate on these is not *"can the user do this?"* but ***"can a mistake be undone?"*** —
a different question, deserving a different default. `IRREVERSIBLE` in `policy.py` already names
the operations that warn; this names the ones that must be switched on first.

## 5. Sequencing

1. **The category machinery** — three capability names, the `_GATES` entries, `DEFAULT_ENABLED`
   no longer being every capability, and the guard that `test_annotations_and_claims.py` needs so
   an off-by-default capability cannot be silently re-enabled. *This is the load-bearing change
   and should land alone*: it is the first time this library has had an off-by-default
   capability since v0.31.0, and every count, description and startup notice asserts otherwise.
2. **Reads, no new scope** — `revisions.list` / `get` (#389, honestly scoped to two entries),
   `changes.list` (what changed since), `drives.list`, `about.get`.
3. **`drive.admin`** — drive lifecycle and restrictions. Reverses `restrictions.py`'s
   read-only-by-construction property, which must be rewritten rather than quietly contradicted.
4. **`share.public`** — reverses T4's control that `type="anyone"` is unreachable. **Needs a
   threat-model amendment, filed as an issue**, not an edit.
5. **`content.destroy`** — last, because it is the one with no recovery.
6. **The remaining Docs / Sheets / Slides request types** within the stated boundary.

## 6. Four decisions this reverses, listed so they are reversed deliberately

| decision | where | what changes |
|---|---|---|
| `type="anyone"` is unreachable | T4 mitigation, `permissions.py:99-100` | becomes reachable behind `share.public` |
| drive restrictions are read-only **by construction** | `restrictions.py` module docstring, shipped v0.49.0 | becomes writable behind `drive.admin` |
| everything is ON by default | v0.31.0, `CLAUDE.md` invariant 7 | three capabilities are OFF, for a stated and different reason |
| labels are read-only because the scope is never requested | `labels.py` | **unchanged** — deliberately excluded, because it needs a new scope |

## 7. One discovery from the enumeration, worth its own issue

**Drive v3 has an `approvals` resource** — `start`, `approve`, `decline`, `reassign`, `comment`,
`cancel`, `get`, `list`. A native document-approval workflow, and nothing in this repository
mentions it.

For a library whose purpose is review and triage of documents, that is squarely on-mission and
was not on any roadmap. It deserves measuring before it is designed: whether it is generally
available, what it requires, and whether an approval is visible to the comment surfaces we
already read.
