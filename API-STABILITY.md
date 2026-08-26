# API stability and deprecation

What this project promises not to break, what it does not promise, and what you are owed when
something changes anyway.

**In one line:** the **MCP tool surface is the contract**; the Python API is best-effort but
taken seriously; both follow [SemVer](https://semver.org/); pre-1.0.0 nothing is frozen.

## Why the MCP surface ranks above the Python API

Not because the library matters less, but because of who is holding it and what breaking it
costs them.

A Python embedder breaks **loudly**, at import or at a call, in their own test suite, with a
traceback naming the thing that moved. They pinned a version. They can read a CHANGELOG.

An MCP tool is called by a **model** reading a schema, from a prompt somebody wrote weeks ago,
in a session where the failure surfaces as *"I couldn't do that"* — and, because of how the SDK
handles unexpected arguments, sometimes as an error whose message is suppressed entirely. Nobody
pinned anything. There is no test suite. The person affected did not know this server existed.

So the surface with the weaker feedback loop gets the stronger promise.

## What is public

### The MCP tool surface — the contract

| Part | Promise |
|---|---|
| **Tool names** | stable. A rename is a breaking change |
| **Parameter names and types** | stable. camelCase on the wire, deliberately — see below |
| **Required vs optional** | making an optional parameter required is breaking. The reverse is not |
| **Result field names and types** | stable. Removing or renaming a field is breaking |
| **Result fields being ADDED** | **not** breaking. Do not assume the set is closed |
| **Read-only / destructive annotations** | stable. Making a read tool destructive is breaking |
| **Capability names** (`comment.create`, `file.trash`, …) | stable. They appear in configuration people wrote |
| **Environment variable names and accepted values** | stable. Same reason |
| **Resource URIs** (`csa-gw://config`, `csa-gw://help/configuration`) | stable |

**Which capability gates which tool is also part of it.** Moving a tool to a different
capability silently changes what an existing configuration permits, so it is a breaking change
even though no name changed. `tests/test_policy_matrix.py` exists to make that visible.

**Profile membership is NOT covered.** `reader` / `commenter` / `editor` / `full` are curated
sets and may be recurated — as they were in v0.21.0, when the line was redrawn on
*recoverability*. A recuration is announced in the CHANGELOG and gets a minor version at
minimum. If you need an exact set, name capabilities explicitly with
`CSA_GW_CAPABILITIES`, which is a complete list rather than a delta precisely so it cannot
drift under you.

### The Python API

`csa_google_workspace.__all__` is the public surface. Anything `_`-prefixed — module, class,
attribute — is internal and may change in any release, including the `_tools/`, `_schemas`,
`_capabilities`, `_content`, `_cellmap` and `_errors` modules.

Also public, because custom backends need them: `Backend`, `Document`, `CommentCollection`,
`DetachedError`. Implementing `Backend` means tracking it — a **protocol gaining a method is a
minor version for us and a required change for you**, which is the price of the seam existing at
all. `tests/test_backend_conformance.py` will tell you what moved.

## What is deliberately not stable

- **Log messages and their levels.** Text and level may change in any release. Do not parse
  them. (If structured fields are introduced — see
  [#145](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/145) — the field
  *names* will join the contract above and be listed here.)
- **Error message text.** The exception *types* in `exceptions.py` are public; the strings are
  written for humans and models and will be improved.
- **Anything Google decides.** Mime types, export formats, comment anchor opacity, the absence
  of an accept-suggestion endpoint. Where Google changes behaviour, this library follows and
  says so; it will not emulate a Google behaviour that has gone away.
- **The demonstration plan's contents.** `demonstration_plan` returns steps; the *shape* is
  contract, the *list* changes every time a tool is added.

## Two shapes that look like bugs and are not

**camelCase parameter names** (`fileId`, `includeComments`) in a Python project. Two reasons,
one of them forced. They match Google's Drive MCP server and the claude.ai Drive connector
exactly, so a prompt written against either works here unchanged. And a pydantic
`Field(alias=…)` cannot bridge Python `snake_case` to a camelCase wire name: it publishes a
correct-looking schema and then fails **every** call, because the SDK dumps the validated model
by alias and calls `fn(**kwargs)`. The wire name must be the literal Python parameter name.

**`create_file(kind=…)` returning `type`.** They are not the same set of values. `kind` accepts
`folder`; `type` is `null` for a folder, because a folder is not a thing this library can open.
Different names because different value sets — reusing `type` on input would promise a symmetry
that does not exist.

## SemVer, as applied here

- **PATCH** — bug fixes, documentation, better descriptions, new *optional* parameters with a
  default that preserves today's behaviour, new result fields.
- **MINOR** — new tools, new capabilities, new environment variables, profile recuration, a new
  `Backend` method.
- **MAJOR** — anything in *What is public* changing incompatibly.

**Before 1.0.0 — where this project is now — nothing above is frozen.** That is the point of
0.x, and it is why the pre-1.0.0 API review happened (v0.21.0): three things were found that
would have been permanent afterwards, including a result field hard-coded to an empty list and
a field name carrying two different vocabularies. If something here looks wrong, **now** is
when to say so.

## What you are owed when something breaks

1. **A CHANGELOG entry that says what changed and why**, not just that it changed. Every entry
   in this project's history is written to be read by whoever hits the problem.
2. **One minor version of overlap wherever overlap is possible.** A renamed tool keeps the old
   name registered and working for one minor release, with the old description saying what to
   call instead. A renamed parameter cannot do this — the SDK matches by name — so a parameter
   rename is avoided rather than deprecated.
3. **A yank, not a silent fix, for anything dangerous.** See [`SECURITY.md`](./SECURITY.md) and
   the yank policy in [`RELEASING.md`](./RELEASING.md). A PyPI version is permanent; it can be
   yanked and never re-uploaded, so a broken release becomes a new version rather than a
   corrected one.
4. **`report_a_problem`.** If a change broke you, that tool assembles the version, OS, Python
   and active policy into something fileable, labelled `assisted-report` so it is read first.

## What is not a promise

This is a 0.x project built and maintained by a small team at CSA, in the open, under
Apache-2.0. It is used in production by CSA and it is offered without warranty. The promises
above describe how it is *maintained*, not a support commitment — if you need one, the honest
answer is to pin a version and read the CHANGELOG before moving.
