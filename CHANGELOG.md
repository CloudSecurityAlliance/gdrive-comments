# Changelog

> **Headings marked "not released" were never published.** Those versions were bumped in code
> as each change landed, but no tag was cut and nothing reached PyPI — they shipped together as
> `v0.11.0`. The entries are kept because they accurately record *what changed and why*; they
> are not a record of what was released.
>
> **On PyPI:** 0.1.0, 0.1.1, 0.1.2, 0.2.0, 0.2.1, 0.2.2, 0.2.3, 0.2.4, 0.2.5, 0.3.1, 0.11.0,
> 0.11.1, 0.12.0. `tests/test_release_history.py`
> keeps this file honest; `scripts/check_release_history.py` reconciles it against git tags and
> PyPI itself.

## 2026-08-25 — v0.12.0 (named security profiles)

`CSA_GW_PROFILE` gives the capability set a name, so "what may this install do?" has an answer
shorter than a list — and so an installer can write one line instead of reasoning about ten
capabilities.

### Added

- **`CSA_GW_PROFILE`** — `reader` · `commenter` · `editor` · `full`.

  | Profile | May |
  |---|---|
  | `reader` | nothing — read and report only, whatever the allowlists say |
  | `commenter` | comment, reply, resolve. **Not** edit content, delete a thread, or touch the file |
  | `editor` | the above, plus edit content, tidy comments, create new files |
  | `full` | everything, including rename/move, trash and share |

  `editor` is exactly the historical default set, so an install that sets nothing behaves as
  before. A test holds the two together rather than a module-level `assert`, which bandit
  rightly flags and `python -O` strips.
- The profile is reported in the startup warnings, in `csa-gw://config`, and in
  `describe_configuration`'s output.

### Design

**Profiles cover capabilities only.** The file allowlists are deliberately not profiled, and
will not be: which documents a deployment may touch is specific to that deployment, and a named
default for it would be a named default for *"which of your files an agent may change"*. That is
the one thing nobody else gets to decide.

**A typo'd profile is an error**, not a fall back to the default — falling back would give a
*wider* policy than the operator asked for. The message lists the real names with their
capability counts.

**An explicit `CSA_GW_CAPABILITIES` wins over a profile** — it is the more specific statement —
but it logs a warning, because an operator who set both plainly believed the profile was doing
something.

**Profiles ascend**, and a test enforces it: each is a strict superset of the one before, or
"pick the next one up" stops being sound advice.

### Why now

The CSA install scripts registered the server with **no environment at all**, which since 0.9.0
meant a fresh install refused every operation, reads included — safe, but indistinguishable from
a broken install. Fixed in `CSA-Plugins`: both Claude Code and Claude Desktop now get
`CSA_GW_ALLOWLIST_READ=*` and `CSA_GW_PROFILE=commenter`, with `CSA_GW_ALLOWLIST_MODIFY` left
unset so nothing can be changed until somebody lists documents. Two independent limits, so
filling in the allowlist later does not silently grant editing too.

Claude Desktop needed it most: it has no shell, so whatever is in its JSON *is* the server's
entire environment — there is nowhere else for these to come from.

## 2026-08-25 — v0.11.1 (provenance, and a check that the changelog tells the truth)

No library changes. Release hygiene, prompted by asking whether there was a plan for auditing
past versions — there was not, and looking turned up a documentation error.

### Fixed

- **The changelog claimed versions nobody could install.** Eleven entries — `v0.3.0` and
  `v0.4.0`–`v0.10.1` — were development versions: bumped in code as work landed, never tagged,
  never published, all shipped together in `v0.11.0`. Each heading now says so.
- **`v0.1.0`'s heading did not use the versioned format**, so it read as unpublished when it is
  on PyPI. Found by the new script on its first run.

### Added

- **`PROVENANCE.md`** — who built this, how to verify a release's PEP 740 attestation *yourself*,
  the yank policy, and what the secret scanners say about the history.
  The authorship section says the unusual thing plainly: every non-bot commit is authored by Kurt
  Seifried, a large share of the content was drafted by an AI assistant under his direction and
  review, and **review is single-person**. That last part is the one that carries weight, so it is
  named rather than implied. If it disqualifies the library for someone's purposes, that is a
  legitimate call and this document exists so they can make it early.
- **`docs/DECISIONS.md`** — an index of decisions: when each was settled, what evidence settled
  it, and which earlier belief it replaced. Corrections are rows of their own rather than edits,
  because being able to see that we believed something wrong is more useful than a clean record.
  Five rows are corrections to documented or widely-believed Google behaviour.
- **`tests/test_release_history.py`** — offline, runs in CI: every version heading is marked
  released or not, `__version__` has an entry and is the newest one, versions and dates descend.
- **`scripts/check_release_history.py`** — the three-way reconcile against git tags and PyPI,
  needing network and a full clone. Now in `RELEASING.md`'s pre-tag checklist, alongside both
  secret scanners.
- **`.gitleaks.toml`** — one allowlist entry for one triaged false positive, *with the
  reasoning*. A scanner that reports a known non-finding trains people to skim its output, which
  is how a real finding gets missed.

### Verified

Across 177 commits: **trufflehog reports 0 verified and 0 unverified secrets**, gitleaks reports
none after the documented allowlist, and no `client_secret*`, `credentials.json`, `token*.json`,
`.pem` or transcript path has ever been committed. Attestations confirmed present on published
artifacts, naming publisher `GitHub` and this repository.

### The general point

A file that records *intent* and a registry that records *fact* will drift, and the file is the
one people read. The fix is not discipline, it is a check — which is why this ships as a test and
a script rather than as a resolution to be careful.

## 2026-08-25 — v0.11.0 (the server explains itself)

Configuration this specific deserves somewhere to read about it. Two MCP **resources** and one
tool, so neither the user nor the model has to guess what the server may touch — and so a
refusal produces an explanation rather than a retry.

### Added

- **`csa-gw://config`** — the *effective* policy, as Markdown: what may be read, what may be
  changed, which mutation kinds are on and which are off, whether read-only mode is set, and —
  when something permits nothing — the specific diagnosis of why. Computed from the same
  `Settings` the tools enforce, so it cannot drift from what actually happens.
- **`csa-gw://help/configuration`** — the reference. Every variable, the accepted forms, the
  three outcomes, a table of what each kind of mistake looks like, and the limits worth knowing
  *before* hitting them: folders unsupported and why, matching by file id so a copy is not
  included, per-capability file scope not expressible.
- **`describe_configuration`** — the same facts as structured output, for clients that do not
  surface resources, and because a tool is what the model can reach on its own. It **needs no
  credentials and calls no Google API**, so it answers even when the server is unauthorized —
  which is exactly when someone is most likely to ask.
- `INSTRUCTIONS` now points at all of it, and says plainly: **do not retry a refused
  operation** — the policy cannot be changed from inside a session, so a retry fails
  identically. A resource the model never learns about is a resource nobody reads.

### Deliberately absent

**Allowlist reasons.** An entry's trailing comment is written for whoever reviews the
configuration and may name people or unannounced work — the same reasoning that keeps it out of
`Entry.__repr__`. File ids *are* included: those are exactly the files the agent may already
touch.

Also absent without `Settings`: a server built by a library embedder wiring its own `Workspace`
gets the document tools and none of this, because there is no server configuration to describe.

### Docs

The tool-by-tool comparison was one table with six columns, and the *Google API* column made it
too wide to read — one row ran to nearly 400 characters. It is now **two** tables: capability ·
what it does · Google · Claude · ours, followed by capability · underlying Google API. Nothing
is lost and the API mapping gets to be as wide as it needs to be.

Splitting it also made two things visible that the wide version buried: **`drive.files.list`
does the work of two tools** (discovery is one method with different parameters), and
**`drive.replies.create` is both replying and resolving**, because resolve is an *action reply*
rather than a state change — which is exactly why its capability gate has to inspect the call's
arguments rather than its name.

### Notes for the next person

- `Resource.mime_type`, not `mimeType` — snake_case in mcp 2.x, same as `Tool.input_schema`.
- Tests assert on **whitespace-flattened** prose. These documents are hard-wrapped, so a
  sentence straddles a newline and a naive substring search fails against text that is
  perfectly correct. Flattening tests the wording rather than the line breaks.

## 2026-08-25 — v0.10.1 (comment parsing: keep the fragment, refuse the silent drop) — not released; shipped in v0.11.0

Whitespace formatting and quoting in reasons already worked; two parsing bugs did not.

### Fixed

- **A URL fragment was eaten as a comment.** `…/edit#gid=0` and `…/edit#heading=h.x` are
  ordinary Drive links, and `#` was splitting on its first occurrence — so the anchor became
  the "reason" and the *real* reason was thrown away. A comment now starts at a `#` that begins
  the line or **follows whitespace**. (The file id extracted correctly throughout, so the
  security behaviour was never wrong; the reason field was.)
- **A second URL after a comment was silently dropped.** `a # one, b # two` looks like two
  entries and parsed as one, because a comment runs to the end of its line. Now an error naming
  the problem — *"the comment contains what looks like another document URL, so that document is
  NOT being allowlisted"* — with the workaround if the mention was deliberate.
- **Two URLs on one line was the same bug in different clothes.** `a, b  # both` splits on
  newlines only once any comment is present, and only the first id would have been taken. Now
  an error saying how many it found and that only the first would be listed.

Both drops fail *closed*, so nothing was over-permitted. But a policy with fewer files than its
author believes is exactly the kind of confusion that gets worked around rather than fixed, so
failing closed quietly is not good enough here.

### Confirmed working, now with tests

- **Indentation, tabs and alignment** are insignificant — reasons can be lined up into a column,
  and whole-line comments can themselves be indented.
- **Blank and whitespace-only lines** are ignored anywhere; CRLF line endings work.
- **The reason is free text**: apostrophes, double quotes, further `#`s, semicolons and commas
  all survive. Whatever holds the value — JSON, a shell — has its own quoting rules, and that is
  a separate layer this parser has no business second-guessing.

## 2026-08-25 — v0.10.0 (the allowlist lives in the configuration, and only there) — not released; shipped in v0.11.0

**Breaking.** `CSA_GW_ALLOWLIST_READ` and `CSA_GW_ALLOWLIST_MODIFY` now hold the lists
themselves. **There is no allowlist file** — no path values, no default location.

### Why

The client configuration is the artifact an operator controls and can *see*: reading it tells
them exactly what the agent may touch. A path adds an indirection whose target can change
without the config changing, puts the real policy somewhere nobody looks, and makes the path
itself something that can be mistyped or redirected.

The cost is real and accepted: a long list is less pleasant in a JSON `env` value than in a
file. In exchange, "what may this agent change?" is answered by looking at one place.

### Removed

- Path values, `~/.csa_google_workspace/allowlist-{read,modify}.txt` defaults, `load_allowlist()`,
  `is_inline()`. `parse_inline()` becomes **`parse_setting(value, variable=…)`**.
- The check for a leftover v0.8.x `allowlist.txt` — there is no longer any file for it to be
  confused with. `CSA_GW_ALLOWLIST` itself is still refused with a message naming both
  replacements.

### Added

- **A path-shaped value is diagnosed, not read.** `/etc/csa/allow.txt`, `~/allow.txt`,
  `./a.list`, `C:\Users\…\a.txt`, `allowlist.yaml` and friends all produce *"that looks like a
  file path. The allowlist is set in the environment, not read from a file — put the document
  URLs in the variable itself, separated by newlines or commas."* Silently ignoring it would be
  worse than either reading it or failing.
- The unset diagnosis no longer names a file to create, because creating one would do nothing.

### A whole class of test fragility went with it

`tests/test_mcp_config.py` had an autouse fixture pointing default paths at nonexistent
locations, because otherwise every "nothing configured" assertion depended on what happened to
be in the developer's home directory — the same machine-dependent trap that once let a `login`
test pass only because CI lacked a `client_secret.json`. With no file support there is no
ambient state to neutralise, and the fixture is gone rather than merely maintained.

### Ordering fix

The path check runs **after** URL extraction and **before** the bare-id check. Before that
order was settled, `allow.cfg` was diagnosed as "a bare file id" — technically reachable, and
useless to whoever wrote it.

## 2026-08-25 — v0.9.1 (say *which* kind of misconfiguration it is) — not released; shipped in v0.11.0

There are exactly three outcomes for an allowlist setting: `*`, a set of document URLs, or
**unusable** — and unusable always means *nothing permitted*. "Unusable" covers a lot of ground,
so the server now says which kind it hit.

### Added

- **`diagnose_url()`** — a ladder of specific cases instead of one "invalid value". Each rung is
  a mistake somebody actually makes:

  | Input | Diagnosis |
  |---|---|
  | `…/document/d/` | the URL stops after `/d/`, so the file id is missing |
  | `…/document/d/AAA…/edit` | contains `…`, so it looks like a placeholder copied from documentation |
  | `…/document/` | a Google URL with no `/d/<id>` segment |
  | a bare file id | needs the full URL — a link can be opened and checked by a reviewer |
  | a folder URL | folders are not supported yet; list the documents inside |
  | `https://example.com/x` | the host is not a Google Docs or Drive address |

- **`diagnose_setting()`** — distinguishes **not set** from **set but empty**. They behave
  identically and have completely different fixes: one means nobody configured it, the other
  usually means a config template or an unexpanded shell variable, and the message says so.
- **`Scope.reason`** — an empty scope carries *why* it is empty, so a refusal can name the
  variable and the cause. "Denied" on its own is not actionable. The text reaches the user twice:
  on stderr at startup, and in the error from any tool that was refused, where the model can
  relay it.

The diagnosis is **deterministic**, not inferred, so it is testable and cannot be wrong about
what it found. The model's job is to relay it, not to guess it.

### Fixed

- **A real file id containing `AAA` could have been diagnosed as a placeholder.** Drive ids are
  random base64url, so a 44-character id will occasionally contain such a run. Id extraction now
  runs *before* the placeholder check — diagnosing a working URL as a mistake would be worse than
  any message it replaced.

### Docs

The comparison table's scoping row is split into three — read scope, modify scope, per-capability
gating — and the other two servers' columns say what is actually true rather than just `✗`:

- **Google's server** reaches the same outcome by a different and arguably better route. It
  authorizes with **`drive.file`**, so Google itself limits it to files the user explicitly
  picked — allowlisting enforced upstream, where it cannot be misconfigured — and its only writes
  *create new files*, so there is nothing to scope. It has no knobs because it does not need any.
- **The claude.ai connector** is the one that differs in substance: full `drive` access plus
  `update_file`, `trash_file` and `share_file`, with no way to narrow any of it.
- **This library** needs full `drive` scope by design, because it opens arbitrary files the user
  names and `drive.file` cannot reach those. Having given up Google's upstream enforcement, it
  owes an equivalent — and these controls are it.

## 2026-08-25 — v0.9.0 (read and modify allowlists, and unset now means nothing) — not released; shipped in v0.11.0

**Breaking.** The single `CSA_GW_ALLOWLIST` becomes two — `CSA_GW_ALLOWLIST_READ` and
`CSA_GW_ALLOWLIST_MODIFY` — and both **fail closed**: unset permits nothing, and unrestricted
access has to be typed as `*`.

Reads and mutations are different risks and want different answers. The intended posture is
`READ=*` with `MODIFY` a short reviewed list: the agent already sees whatever your credentials
see, so **what is worth bounding is what it can break**. `READ=*` is also exactly what Google's
and Anthropic's Drive servers do — they simply have no way to narrow it, which is why *this* is
now a row in the README's comparison table. Neither of them offers anything equivalent.

### Changed (breaking)

- **`CSA_GW_ALLOWLIST` is refused**, not reinterpreted. Its meaning changed, and silently
  treating it as the modify list would leave reads fail-closed and break them for reasons nobody
  could see. The error names both replacements. A leftover
  `~/.csa_google_workspace/allowlist.txt` is likewise an error rather than silently ignored.
- **Unset means nothing is permitted** — for reads too. Previously an unset allowlist meant *no
  restriction*. The server still starts (a startup crash reaches the user as an opaque "server
  failed to start"), prints on **stderr** which variable to set, and every tool error says the
  same.
- **`*` is the escape hatch and must be typed** — as a value, or a line in the file. It logs a
  warning every time it is parsed, because unrestricted access should be visible in review.
- **Reads are now gated.** `get_file_metadata`, `read_file_content`, `list_comments` and the rest
  check the read scope. A refused read raises `AccessError`, not `ReadOnlyError` — nothing about
  writing is involved.
- **`search_files` results are filtered** to the read scope rather than merely unopenable. A file
  outside it must not be *named* either, or search becomes a way to enumerate what the policy
  excludes.

### Added

- **`Scope`** — `everything()` / `nothing()` / `from_listing()`. `all_files` and "an empty set"
  are deliberately different states: empty means nothing is permitted, and collapsing them into
  one representation is how a fail-closed default turns fail-open during a refactor.
- **`Listing`** — a parsed allowlist that is either "everything" or a specific set. An empty file
  stays a configuration error, because it is indistinguishable from a typo; `*` is the way to say
  "no restriction" out loud.
- **`Gate(capability, access, file_scoped)`** — `_GATES` now states three things per `Backend`
  method: what capability it costs, **which allowlist applies**, and whether it is file-scoped.
  A test asserts every entry declares a known access kind.
- **`startup_warnings()`**, printed to stderr by the CLI: says when a scope permits nothing (so
  nothing will work until it is configured) and when one permits everything.
- Default paths `~/.csa_google_workspace/allowlist-read.txt` and `allowlist-modify.txt`.

### Unchanged, deliberately

**The library's default stays permissive.** `Workspace.from_credentials` is called by a developer
writing code, who has already made a decision; the MCP server is configuration handed to a model.
Two artifacts, two threat models — and a fail-closed library default would have broken every
embedder for no gain in the case that matters.

### Scope of the claim

What this is: per-capability gating plus two flat lists of documents. Deliberately simple,
concrete, and honest — a volunteer's install is physically unable to change a document nobody
listed. What it is not: a general authorization model. A broader design is being researched
separately.

Two properties should survive into whatever replaces it, because they are what make it worth
relying on: enforcement lives in a **`Backend` wrapper**, so library embedders and MCP clients
get the same guarantee from one auditable place; and the policy **cannot be widened in-band**,
because no tool changes it.

### Live-verified

Against real Google, with two throwaway Docs: `READ=*` reads both, `MODIFY` permits a comment on
the listed one and refuses it on the other, and narrowing `READ` makes the second file vanish
from `search_files` as well as becoming unreadable.

## 2026-08-25 — v0.8.1 (the allowlist, configurable where you actually configure things) — not released; shipped in v0.11.0

`CSA_GW_ALLOWLIST` was a path to a file, which meant distributing a second artifact. It now
takes whichever of three forms suits the deployment, all through the same plain environment
variable — so it works in a shell, in `.mcp.json`, or in Claude Desktop's config.

### Added

- **URLs inline.** Any value containing `://` is read as URLs rather than a path, so an MCP
  client's JSON `env` block needs no companion file:

  ```json
  "CSA_GW_ALLOWLIST": "https://docs.google.com/document/d/AAA…/edit  # CCM mapping\nhttps://docs.google.com/spreadsheets/d/BBB…/edit  # AICM tracker"
  ```

  Newlines separate entries and keep the `# reason` comments. Commas, semicolons and
  whitespace also separate entries **when the value contains no `#`** — that condition is what
  stops a separator and a comment fighting over one character, and it makes the ambiguous case
  unreachable rather than merely unlikely.
- **A default path: `~/.csa_google_workspace/allowlist.txt`**, used automatically when it
  exists. Same reason `client_secret.json` has one: a **curated list distributed by a setup
  script should need no per-user configuration**, because the people running it did not write
  it. Explicit configuration always wins over it.
- **`CSA_GW_ALLOWLIST=any`** — unrestricted writes, deliberately and case-insensitively. This
  is what makes flipping the no-allowlist default at 1.0.0 a one-line change that leaves
  nobody stuck: choosing unrestricted writes becomes something somebody typed.

### Why `://` and not `os.path.exists`

Detecting a path by checking whether it exists would silently reinterpret a **mistyped path**
as a URL list — turning a typo into a different, wrong configuration instead of an error. `://`
is a property of the value itself: a URL always has it, a filesystem path never does. A path
that does not exist is still read as a path, and reported as one.

### A test trap closed on the way

The new default path made every "no policy configured" assertion depend on whether the
developer happens to have `~/.csa_google_workspace/allowlist.txt` — the same
machine-dependent failure that once let a `login` test pass only because CI lacked a
`client_secret.json`. `tests/test_mcp_config.py` now has an autouse fixture pointing the
default at a nonexistent path, and the tests that *want* the default patch it themselves.

## 2026-08-25 — v0.8.0 (the write allowlist: #82, second dimension) — not released; shipped in v0.11.0

Gate **A4** completed in its basic form. `CSA_GW_ALLOWLIST` points at a plain-text list of
Google document URLs; **writes are refused for any file not listed, and reads are unaffected**.

Deliberately the simplest thing that works: a flat list of direct document URLs. No folders, no
patterns, no wildcards. Folders are the interesting design problem and they are *not* solved
here — `TODO.md` → "Folders in the allowlist" writes out the seven questions they drag in, and
why folder-as-rule is more dangerous than it looks.

### Added

- **`CSA_GW_ALLOWLIST`** — path to the allowlist. Format is one URL per line, `#` starts a
  comment, so the trailing comment gives #82's required *reason per entry* on the same line and
  the whole thing reviews like code in a `git diff`:

  ```
  # CSA WG documents this agent may write to.
  https://docs.google.com/document/d/1oW1BM…/edit?tab=t.0   # CCM v5 mapping, per WG lead
  https://docs.google.com/spreadsheets/d/1abc…/edit          # AICM tracker
  ```

- **`allowlist.py`** — `parse_document_url`, `parse_allowlist`, `load_allowlist`, `Entry`.
- **`Policy.allowed_files` / `Policy.from_entries`**, and `Gate(capability, file_scoped)` so
  `_GATES` states both facts per method: what it costs, and whether the file list applies.

### The properties worth reviewing

**Matched by file id, not URL string.** Every URL form for one document is one entry — a pasted
`/edit?tab=t.0` link, an `#heading=` anchor and a `?usp=sharing` link all normalise together. It
also means a **copy** of an allowlisted document has a different id and is *not* writable, which
is the correct default, and that id-based entries survive renames and moves.

**Fails closed on every failure mode.** Missing file, unreadable file, no usable entries, any
malformed line — all raise. Never a fallback to unrestricted writes. The failure being avoided
is an operator who believes writes are scoped because they set the variable, and mistyped the
path.

**Folder URLs are a loud error.** Treated as an opaque id, a folder URL would match nothing, so
the entry would protect nothing while looking in the file like protection — the silent no-op #82
calls dead-entry detection. The error names the document-URL form and points at the open design
questions.

**A bare file id is rejected**, unlike `Workspace.open()` which accepts one. Drive ids are
unstructured base64url, so a bare id cannot be told apart from a typo — an early version of this
parser happily accepted `nonsense-one` as a file id. A URL in a reviewed config is also
*clickable*: whoever approves the entry can open it and see what they are granting.

**Every bad line is reported, not just the first.** Fixing a curated list of thirty URLs should
not take thirty runs to find thirty typos.

**Denials log at WARNING** with the method and file id. Denials are the security signal.

### Reads stay unrestricted, on purpose

#82 is damage containment, not confidentiality: the agent already sees whatever the user's
credentials see, so bounding what it can *break* is the part that helps. An unlisted file can
still be read, searched and had its comments listed.

### Still open before 1.0.0

An **unset** `CSA_GW_ALLOWLIST` still means no file restriction, because that is what this
library has always done and flipping it silently would break existing users. #82 asks for
fail-closed including the no-policy default; the recommendation, recorded in `TODO.md`, is to
flip it at 1.0.0 with an explicit opt-out, so that choosing unrestricted writes is something
somebody typed. Also open: per-capability scope (needs a structured format — plain text cannot
say "commentable but not editable"), expiry, dead-entry detection, and a dry-run.

## 2026-08-25 — v0.7.0 (capability gating: #82, first dimension) — not released; shipped in v0.11.0

Gate **A4**, half of it. #82's settled requirement surface separates two independent things —
*may this deployment do X at all*, and *to which files* — with the composition rule that
**global is a ceiling and per-file grants narrow, never widen**. This ships the first, which
means the second can only ever subtract from it.

Why that order: it lets the destructive tools land *off*. `update_file`, `trash_file` and
`share_file` are next, and a default install will not be able to reach any of them before the
per-file allowlist exists.

### Added

- **`policy.py`** — ten named capabilities (`comment.create`, `comment.reply`,
  `comment.resolve`, `comment.edit`, `comment.delete`, `content.write`, `file.create`,
  `file.update`, `file.trash`, `file.share`), a `Policy`, and **`PolicyBackend`**: a `Backend`
  wrapper that refuses what the policy does not permit. Both exported from the package root.
- **`CSA_GW_CAPABILITIES`** — the **complete** list of permitted mutations, not a delta,
  because #82 asks for config that *reviews like code*: the line should tell you everything
  allowed without also knowing what the defaults were the day it was written. The entry
  `default` expands to the built-in set, so a delta stays expressible and self-describing —
  `default,file.trash`. Also `all` and `none`. An unknown name **fails loudly**, because a
  typo that reads as "configured" and behaves as "off" is the worst outcome here.
- **`Workspace.from_credentials(..., policy=…)`** and `from_oauth(..., policy=…)`.

### Changed

- **`from_credentials` and `from_oauth` are now safe by default**: the `ApiBackend` arrives
  wrapped in a `PolicyBackend` carrying `Policy.default()`. That permits exactly what this
  library has always permitted — so no behaviour changes today — and refuses the three
  operations that alter or expose an existing file. `read_only=True` collapses the policy to
  permitting nothing.
- **The raw seam stays raw.** `Workspace(backend=…)` is unwrapped and unguarded, as documented.
  An embedder supplying their own backend has already made the decision.

### Design notes

**Enforcement is a `Backend` wrapper, not a check in the tool layer.** Every `Backend` method
takes `file_id` first (or, on the account axis, nothing), which is what makes a uniform wrapper
possible at all — and it means a library embedder gets the same guarantee as an MCP client,
with one place to audit.

**It fails closed.** `_GATES` must name every `Backend` method; an unlisted name is *refused*
rather than delegated, so adding a protocol method without deciding its gate turns the method
off instead of leaving it unguarded. `tests/test_policy.py` asserts the coverage both ways —
missing entries and stale ones — so it fails in CI rather than at a user.

**It cannot be widened in-band.** No tool changes the policy; only whoever starts the server
does. #82 notes that session scoping means nothing unless it is set by the host rather than
callable by the guest, and an MCP server session is exactly that boundary.

**One method, two capabilities.** `create_reply` carries both replies *and* resolve/reopen,
because resolve is an **action-reply**, never a PATCH (probe-verified). A gate keyed only on
the method name would let anyone who may reply also close a thread, so the gate is consulted
with the call's arguments. Live-verified against real Google: reply allowed, resolve refused,
from the same backend method.

### Reads are deliberately not gated

#82 is **damage containment, not confidentiality** — the agent already sees whatever the
user's credentials see, so bounding what it can *break* is the thing that helps. This is why
`search_files`, `list_recent_files` and `get_file_permissions` needed no gate, and why the
roadmap's "discovery is blocked on #82" was wrong.

## 2026-08-25 — v0.6.0 (who else is in this document?) — not released; shipped in v0.11.0

Gate **A2** of the [1.0.0 list](./TODO.md).

### Added

- **`get_file_permissions(fileId)`** — every grant on a file: the person, group, domain or
  `anyone`, and their role. Plus two roll-ups the model would otherwise have to derive and
  could get wrong: **`public`** (anyone with the link can open it) and **`writers`** (how many
  grants can change the document).
- **Library: `doc.permissions`** — a list of `Permission`, with `can_write` (writer and above,
  not commenter) and `is_public`. Exported from the package root.

### Architecture

Permissions are a **per-file, uniform Drive concern** — one API, identical across
Docs/Sheets/Slides — so they arrive exactly as comments did: a mixin composed into `Document`,
with the model beside it. This is the second use of the pattern the
[structure review](./docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md)
settled on, and revisions and approvals will be the third and fourth.

**Read only, deliberately.** `share_file` — *creating* a permission — is a separate and gated
thing: granting an arbitrary address access to a document is an exfiltration primitive, and one
Google's own MCP server declines to expose. Listing who already has access is not.

`Permission.__repr__` is redacted like `Author`: the email is PII and embedders log these
objects. It is still on the attribute and still returned by the tool — the tool is *about* who
has access, so the email is the answer, not a leak. Same rule as comment content.

### Two things the default API response hides

- **`emailAddress` and `displayName` are omitted** from `permissions.list` unless requested,
  and they are the entire point of the call.
- **`supportsAllDrives`** — without it, a file on a shared drive reports *no permissions at
  all*. Both are asserted in `tests/test_apibackend_contract.py`, since `FakeBackend` has no
  `fields` and no pages.

### Caught by the type checker, not the tests

A stray copy of `list_permissions` landed in `ApiBackend`, shadowing the real one. The suite
stayed green — it runs entirely on `FakeBackend`, which is precisely the blind spot
`CLAUDE.md` invariant 4 describes. ruff (`F811`) and mypy (`no-redef`) both caught it. Worth
recording as evidence that the lint job is not decoration.

### Scorecard

**6 of Google's 8, 6 of Claude's 11**, plus 7 they do not have. Remaining: `create_file`,
`copy_file` (ungated), and `update_file`, `share_file`, `trash_file` (gated on #82).

## 2026-08-25 — v0.5.0 (you can find a file now) — not released; shipped in v0.11.0

Gate **A1** of the [1.0.0 list](./TODO.md). `search_files` and `list_recent_files` — the gap
that actually cost users something, because without them every session began with a pasted URL.

### Added

- **`search_files(query, limit, orderBy)`** — Drive's own `q` syntax: `name contains`,
  `fullText contains`, `mimeType =`, `modifiedTime >`, `'me' in owners`, `sharedWithMe`,
  `'<folderId>' in parents`, combined with `and`/`or`/`not`. Excludes trashed files unless the
  query says otherwise (`files.list` returns binned items by default — a real footgun).
- **`list_recent_files(limit, orderBy)`** — `recency`, `lastModified` or `lastModifiedByMe`.
- **Library: `workspace.files`** — a `FileCollection` yielding `FileRef`s, with `.search()` and
  `.recent()`. `FileRef.open()` upgrades a hit to a typed `Doc`/`Sheet`/`Slides`;
  `FileRef.type` is `None` for anything the library cannot open (a PDF, a folder, a Form),
  which search legitimately returns.
- Shared drives are included (`includeItemsFromAllDrives`, `supportsAllDrives`) — omitting
  those silently hides every file that lives in one, which is where collaborative review
  actually happens.

### Fixed

- **A bad argument value produced an unreadable tool error.** The MCP error translator handled
  the library's typed exceptions but not plain `ValueError`, so an unknown `orderBy` — or
  `as_text(suggestions="maybe")` — became an `UnexpectedToolError` with the message dropped:
  the model saw "Error executing tool X" and could not correct itself. Pre-existing; found by
  a test on the new tools, never specific to them.

### Architecture

This is **the account axis**, and the first thing here not reached through `open(file_id)` —
you cannot open a file you are trying to find. It follows the shape settled in
[the structure review](./docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md):
`Workspace` gains *collections*, not methods, with `CommentCollection` as the precedent. This
is also the first `Backend` method that does **not** take `file_id` first, which is exactly the
schema pressure #82's allowlist has to answer — and it answers it: `search_files` is a read, and
#82 is write-narrow, so it is not gated.

`FileRef.__repr__` is redacted like the comment models: a file *title* can be as sensitive as
its contents ("2026 Layoff Plan") and embedders log these objects. The name is an attribute; it
just does not reach a log by accident.

### Recorded

- **An f-string is not a string literal, so it cannot be a docstring.** Using one for a tool's
  description leaves `__doc__` as `None`: the tool registers, the schema looks correct, and the
  model gets *no guidance at all*. This happened to `search_files` during development. There is
  now a test asserting every registered tool has a non-empty description.

### Scorecard

**5 of Google's 8 tools, 5 of Claude's 11**, plus 7 they do not have. Remaining:
`get_file_permissions`, `create_file`, `copy_file` (ungated), and `update_file`, `share_file`,
`trash_file` (gated on #82).

## 2026-08-25 — v0.4.0 (tool names aligned with the other Drive MCP servers; export formats) — not released; shipped in v0.11.0

Roadmap items #1 and #6 from [`TODO.md`](./TODO.md). The content tools now carry the same
names and parameters as Google's Drive MCP server and the claude.ai Drive connector, so a
user's habits transfer between them — and `Document.export()` finally reaches MCP.

### Changed (breaking)

- **Tools renamed:** `open_document` → **`get_file_metadata`**, `read_text` →
  **`read_file_content`**.
- **The `file` parameter is now `fileId`**, and `comment_id` is `commentId`, across every
  tool. One convention for the whole server beats a split where three tools say `fileId` and
  seven say `file`, and the convention worth converging on is the ecosystem's.
- **No aliases were kept.** Two tools whose only job is to redirect to other tools degrade
  exactly what this change improves — a model picking the right tool. The package is one day
  old with a known user base who receive it through `desktopSetup`.
- `fileId` still accepts a **share URL** as well as a bare id, which neither of the other
  servers does. Everything their clients send works here; so does what users actually paste.

### Added

- **`download_file_content(fileId, exportMimeType)`** — a file's bytes, base64, converted.
  Takes a mime type or a short alias (`markdown`, `pdf`, `docx`, `odt`, `html`, `epub`, `csv`,
  `tsv`, `xlsx`, `pptx`, `odp`). Refuses an export the file type cannot produce **locally**,
  naming the ones it can, and caps a single response at 10 MiB.
- **`read_file_content(includeComments=True)`** — folds comment threads into the text with
  `[[Cn]]` markers plus a labelled thread listing. Anchoring is by *unique quoted-text match*:
  the Drive anchor is an opaque range id with no decodable position, so a quote occurring
  twice or not at all is reported unanchored rather than guessed.
- **`get_file_metadata`** returns a content snippet, suppressible with
  `excludeContentSnippets` — matching the connector's behaviour.
- **Library:** `Doc.as_markdown()`, `Document.export_formats`, and `EXPORT_FORMATS` at the
  package root. `Document.export()` now validates the format instead of passing anything
  through to Google.
- **`FakeBackend(comments=…)`** seeds raw comment dicts, so fixtures can set fields
  `create_comment()` cannot — `quotedFileContent` above all.

### Fixed

- **`Document.export()` accepted formats Drive cannot produce**, which surfaced as an opaque
  400. It now resolves against a per-type table.

### Probed, not assumed

`drive.about.get(exportFormats)` — [`experiments/export-formats/RESULTS.md`](./experiments/export-formats/RESULTS.md).
It corrected the roadmap twice: **export formats differ by document type** (a Doc exports
Markdown; a deck exports only PDF/PPTX/ODP/text, so one shared enum would have handed most
callers an unfixable error), and **"images" was wrong** — only *drawings* export PNG/JPEG/SVG,
and the library cannot open a drawing.

It also found the thing that makes format breadth worth more than a few mime types: **Markdown
round-trips.** `text/markdown` exports from a Doc *and* imports back into one, so a Doc becomes
a usable source for a Markdown toolchain — CSA's `document-pipeline` plugin takes Markdown to
tagged PDF/UA-1, and a public version is planned.

### Internal

- `mcp/` split into a `_tools/` package, one module per axis (`content`, `comments`, `auth`,
  shared `_base`). `server.py` went from 265 lines to 49 and is composition only. This is what
  lets the planned flavour switch be a *registration-time* filter — a tool the flavour excludes
  is simply not there, rather than existing and refusing.
- **New SDK trap recorded:** a pydantic `Field(alias="fileId")` on a tool parameter publishes
  the right schema and then **fails every call** — the SDK dumps the validated model by alias
  and calls `fn(**kwargs)`, so the handler receives `fileId=`, raises `TypeError`, and surfaces
  as a message-suppressed `UnexpectedToolError`. A camelCase wire name must be the *literal*
  Python parameter name. (Also: `Tool.input_schema`, not `inputSchema`.)

## 2026-08-25 — v0.3.1 (the unauthorized message is now actionable)

An unauthorized server starts by design, so its error text is the entire user experience.
That text now carries everything needed to act on it:

- **Offers the no-terminal path first** — call `authenticate` — then the CLI as fallback.
- **Gives a command that can be pasted verbatim**, using the launcher's absolute path from
  `argv[0]`. A bare `csa-google-workspace-mcp` is useless where the launcher is not on PATH,
  which is the normal case on Windows: pipx installs somewhere PATH does not reach until a
  new shell.
- **Says where it looked**, naming the token path.
- **Tells the model to ask the user and wait**, and not to go hunting for credential files.
  Given only "no credentials", a capable model starts searching the filesystem — which is
  exactly what happened on the first real run.

The server's `instructions` now state the same protocol up front, so the model knows it
before the first failure rather than inferring it from an error.

## 2026-08-25 — v0.3.0 (authorize from inside the client) — not released; shipped in v0.11.0

- **New `authenticate` tool — browser consent without leaving your MCP client.** When a tool
  reports missing credentials, calling `authenticate` sends the Google consent URL to the
  client via **URL-mode elicitation** (MCP revision `2026-07-28`); you sign in, a loopback
  listener catches the redirect, and the token is cached. No terminal step.

  URL mode exists precisely for this: the sensitive exchange happens out-of-band and never
  passes through the model's context. Note this is *not* MCP's OAuth framework, which is
  HTTP-only and runs the other way round (authenticating a client **to** a server); this
  server authorizes **outbound** to Google, which for stdio the spec says to do from the
  environment.

  **Requires a client that supports URL elicitation** — Claude Code does (v2.1.76+); Claude
  Desktop does not yet. Where it is unavailable the tool degrades to the previous behaviour:
  a clear instruction to run `csa-google-workspace-mcp login`. And because both clients read
  the same token file, authorizing once in Claude Code also authorizes Claude Desktop.

- **`Settings.client_secrets`** (new, optional). Never needed to start the server or to
  refresh a cached token — a token carries its own client id and secret. It is used only to
  build a fresh consent URL for `authenticate`, and resolves from `CSA_GW_CLIENT_SECRETS` or
  `~/.csa_google_workspace/client_secret.json`.

- `create_server(get_workspace, settings=…)` — passing `settings` registers `authenticate`.
  Omitting it yields the previous nine-tool surface, so existing embedders are unaffected.

Internal: `_auth_flow.py` drives the loopback flow directly rather than through
`InstalledAppFlow.run_local_server()`, which prints the consent URL to stdout (the JSON-RPC
channel) and blocks the calling thread. The token exchange is given the full redirect URI so
oauthlib validates the `state` parameter.

## 2026-08-25 — v0.2.5 (`login` finds the client secrets by itself)

- **`login` no longer requires `CSA_GW_CLIENT_SECRETS`.** It falls back to
  `~/.csa_google_workspace/client_secret.json`, the path the CSA setup scripts already write
  to. Requiring an environment variable that points at a location this package itself chose
  only made users rediscover our own convention — and in practice it did: the first real run
  ended at `CSA_GW_CLIENT_SECRETS is not set`, with the file sitting exactly where the
  fallback now looks. The variable still wins when set, for anyone keeping the client
  elsewhere.

- **When nothing is found, the error says where it looked** — both the unset variable and the
  default path — rather than naming only the variable.

## 2026-08-25 — v0.2.4 (Python 3.14; install guidance)

- **Python 3.14 is tested and declared.** A `pipx` install picks the newest interpreter
  present, so 3.14 is what actually runs the MCP server in practice — while CI covered
  3.10–3.13 and the classifiers claimed the same. The full suite was run on 3.14 (269 passed)
  before claiming it; 3.14 is now in the CI matrix, in the trove classifiers, and in the
  required status checks so a failure there blocks a merge.

- **`pipx` is now the recommended install for the MCP server.** It is a CLI you run, not a
  library you import, so it wants its own environment: `pip` into a shared virtualenv works
  until another project disagrees about a dependency (`mcp>=2.1` here versus something else
  pinning `mcp<2.0` is a conflict people hit). `pipx` also gives the console script an
  absolute shebang, which is what makes it launchable from a GUI app. `pip` remains documented
  for embedding the *library* in your own application.

- **Claude Desktop guidance made concrete.** Claude Code runs in your shell; Claude Desktop is
  a GUI app inheriting launchd's `PATH`, which contains neither `~/.local/bin` nor Homebrew and
  where `python3` is macOS's 3.9 — below this package's floor. The troubleshooting entry now
  gives the literal `claude_desktop_config.json` snippet with an absolute path.

- **`SECURITY.md` reconciled with what shipped.** It previously called `from_oauth` +
  `token.json` "PoC/CLI scaffolding — not for server use", written before the bundled MCP
  server existed. The real distinction is *whose machine holds the token*: local single-user
  (a CLI, or this server over stdio) is fine; hosted multi-user is not. It also now states that
  the bundled server *is* the prompt-injection risk the threat model describes — untrusted
  document text reaching a model with write tools live — what the server does about it, and
  what it does not (there is no file allowlist yet; #82).

- Docs reconciled with reality throughout: the MCP spec marked implemented with *[as-built]*
  deltas, `research/mcp-protocol-notes.md` corrected (it still said to target `2025-11-25` and
  not to build against the `2026-07-28` release candidate — which was ratified, and which this
  server is built on), `TODO.md` phase 2 marked shipped with its honest deferred list, and the
  PyPI Trusted Publisher constrained to the `pypi` environment.

No library behaviour changes; the `--force` switch shipped in 0.2.1.

## 2026-08-25 — v0.2.3 (docs patch: MCP troubleshooting)

No code changes. The README is the PyPI long description and is frozen at each release, so a
docs fix only reaches users on a version bump — the same reason 0.1.1 existed.

- **Troubleshooting table** for the MCP server, covering five failure modes hit while
  standing it up, each written from the symptom a user actually sees rather than its cause:
  - `Error 403: org_internal` — the OAuth client is **Internal** to a Workspace organization
    and you signed in with an account outside it. Confirmed by observation, not just docs;
    it also settles that Internal genuinely covers **restricted** scopes. The realistic
    victim is not an attacker but someone with several Google accounts who picks the wrong
    one in the chooser.
  - `SERVICE_DISABLED` on some file types but not others — a scope grant is not API
    enablement, and it fails **per-API**, so Docs can work while Sheets 403s.
  - `login` reporting *"Already authorized"* while nothing works — a cached token issued by a
    different OAuth client; `login --force` is the fix.
  - Tool errors mentioning `no cached credentials` — the server starts without a token on
    purpose, so the remedy surfaces where it can be read.
  - Works in Claude Code but not Claude Desktop on macOS — GUI apps inherit a minimal `PATH`
    where `python3` is the system 3.9, below this package's 3.10 floor.

## 2026-08-25 — v0.2.2 (CSA-branded OAuth success page)

- **Branded consent-complete page.** After `login`, the browser now shows a CSA-branded page
  instead of `google_auth_oauthlib`'s plain "The authentication flow has completed." It uses
  the General CSA palette, Azo Sans via the CSA TypeKit with a full fallback stack (it still
  reads correctly offline), the official logo inlined verbatim, and `prefers-color-scheme`
  dark support.

  `success_message=` cannot carry markup — `_RedirectWSGIApp` hardcodes `Content-type:
  text/plain` — so the page is delivered by swapping that class for the duration of the flow.
  The swap changes the response body only and still records `last_request_uri`, which carries
  the authorization code and the `state` oauthlib validates. Every failure path falls back to
  the stock page, including a renamed upstream class: a cosmetic feature must not be able to
  break authorization.

- **Docs:** `CLAUDE.md` now states the project's **public-by-default** policy explicitly —
  everything is developed in the open except credential-bearing material, which is exactly one
  artifact (the CSA OAuth client) and only because Google's API ToS require it.

No library behaviour changes.

## 2026-08-25 — v0.2.1 (`login --force`; wrong-client detection)

Fixes a failure that is invisible by construction: a cached token can be valid, unexpired,
and carry exactly the required scopes while having been issued by a **different OAuth
client**. `login` reused it and reported success, and every subsequent API call ran against
the wrong project's quota and consent screen. Nothing errored — found in real use within an
hour of 0.2.0.

- **`csa-google-workspace-mcp login --force`** (also `-f` / `--reauth`) — bypass the cached
  token and re-consent. It skips the cache *read* rather than deleting anything: the old
  token is replaced only once a new one is in hand, so a cancelled or failed consent leaves
  the previous credentials working.
- **Wrong-client warning** — `login` compares the cached token's `client_id` against the
  configured client secrets and says so when they differ, naming both and the remedy.
  Nothing else surfaces this: OAuth accepts a refresh token from whichever client issued it,
  so provenance is not visible at runtime.
- **Honest messaging** — `login` no longer announces "Opening a browser" before checking
  whether it needs to; it reports `Already authorized` and how to re-authorize.
- **Library (additive, backward-compatible):** `auth.load_credentials(..., force=False)` and
  `Workspace.from_oauth(..., force=False)`. Existing calls are unaffected.

The default remains reuse-if-usable, because the installer path calls `login` and should not
open a browser on every run.

Also in this release: `INTERFACE-RESOURCES.md`, an inventory of the interfaces this repo
provides and consumes.

## 2026-08-24 — v0.2.0 (built-in MCP server)

Phase 2: a **built-in Model Context Protocol server**, so an AI client (Claude Code, Claude
Desktop) can read and triage comments on Google Docs/Sheets/Slides through the library. The
server is a delivery layer only — it adds no document logic.

**Install:** `pip install "csa-google-workspace[mcp]"` · **Run:** `csa-google-workspace-mcp`

- **Nine tools**, all with structured output (`outputSchema`) and read-only/destructive
  annotations: `open_document`, `read_text`, `list_comments`, `get_comment`,
  `comments_by_cell`, `create_comment`, `reply_comment`, `resolve_comment`, `reopen_comment`.
- **`csa-google-workspace-mcp login`** — a separate, interactive subcommand is the *only* path
  that opens a browser. The server itself never prompts: under stdio, stdout is the JSON-RPC
  channel, and `InstalledAppFlow.run_local_server()` both `print()`s the consent URL into it
  and blocks on the redirect. The MCP spec agrees — stdio servers "SHOULD NOT" do protocol
  OAuth and should "retrieve credentials from the environment".
- **`auth.load_cached_credentials(token_path, read_only)`** (new, public) — non-interactive
  credential load: reuse the cache, refresh if stale, raise `AuthError` rather than prompt.
  It deliberately contains no `InstalledAppFlow` branch, so a server cannot reach interactive
  consent even by mistake. `load_credentials()` is unchanged.
- **Credentials resolve on first tool use, not at startup**, so a server with no token still
  starts and reports the remedy as a tool error. An MCP client renders a startup crash as an
  opaque "server failed to start", where nobody would read it.
- **One `Workspace` per thread.** MCP SDK 2.x runs sync tool handlers on worker threads, so a
  shared `Workspace` would put a `googleapiclient` client on several threads at once. The
  provider hands each thread its own.
- Requires **`mcp>=2.1`** and targets protocol revision **`2026-07-28`**. (`mcp.server.fastmcp`
  was removed in SDK 2.0; `FastMCP` is now `MCPServer`.)
- Environment: `CSA_GW_TOKEN`, `CSA_GW_READ_ONLY`, and `CSA_GW_CLIENT_SECRETS` (needed by
  `login` only — a cached token carries its own client id/secret).

Library behaviour is otherwise unchanged; the core package still has no dependency on `mcp`.

## 2026-07-23 — v0.1.2 (hardened release pipeline; no library changes)

First release through the hardened supply-chain pipeline — no changes to the library code
itself. This release exists to exercise and verify the pipeline:

- GitHub Actions **pinned to commit SHAs** (`checkout` v7, `setup-python` v7,
  `gh-action-pypi-publish` v1.14.1); Dependabot keeps them current.
- Release-time **security gate** (`pip-audit` + `bandit`) runs before publish.
- Publish runs through a protected **`pypi` environment** (manual approval).
- **PEP 740 attestations** emitted — this should be the first release whose PyPI files carry
  provenance.
- `main` is now branch-protected (required checks, no direct/force push, admins enforced).

## 2026-07-23 — v0.1.1 (docs patch)

- **README install fix.** Lead with the consumer install `pip install csa-google-workspace`
  (the PyPI page previously showed only the from-source `pip install -e ".[dev]"`); moved the
  editable install + test/lint commands and the live-suite instructions under a new
  **Development** section. No code change.

## 2026-07-22 — Split the interactive OAuth suite out (`tests/oauth/`)

The browser-login tests are now their own suite, separate from the API-integration tests,
because they need a human at a browser and touch the very sensitive cached OAuth token.

- Moved `tests/integration/test_oauth_live.py` → **`tests/oauth/test_oauth_flow.py`**.
- Own opt-in gate **`CSA_GW_OAUTH=1`** (distinct from `CSA_GW_INTEGRATION`), so it never runs
  by accident and is clearly the interactive/sensitive tier. Run: `CSA_GW_OAUTH=1
  CSA_GW_CLIENT_SECRETS=… pytest tests/oauth/`.
- Three tiers now: unit (offline, gates CI) · integration (real API) · oauth (interactive).

## 2026-07-22 — Live-suite coverage for Tier 3 + a dedicated OAuth e2e suite

Test-only; all gated behind `CSA_GW_INTEGRATION` (no runtime change):

- Extended the live suite to exercise the Tier 3 additions against real Google:
  `Sheet.append_rows`, multi-tab `as_text` (`# <tab>` headers + `tab=`), and
  `Slides.insert_text` / `Slide.shape_ids`.
- New **`tests/integration/test_oauth_live.py`** — end-to-end OAuth: a real `from_oauth`
  login that reaches Google, token-file permissions (no group/other access), and the
  `read_only` session contract (reads succeed, writes raise `ReadOnlyError`). Because the
  writable login runs first, the read-only test reuses the cached token without re-prompting.
- Gated integration tests: 6 → 9.

## 2026-07-21 — Tier 3 API-surface additions

Closed the remaining within-scope content-write gaps (all `read_only`-gated, TDD):

- **Sheets `append_rows(a1_range, values, value_input_option="RAW")`** — `values.append`
  with `INSERT_ROWS`. Non-idempotent, so it is never auto-retried on 5xx (a retry could
  duplicate rows). Invalidates the cell-map cache like the other writes.
- **`Sheet.as_text(tab=None)`** now renders **every** tab by default (each prefixed with a
  `# <tab>` header when there's more than one), fixing silent first-tab-only truncation on
  multi-tab sheets. `tab=` selects a single tab (no header); single-tab output is unchanged.
- **Slides `insert_text(object_id, text, index=0)`** — per-shape text insertion, symmetric
  to `Doc.insert_text` but shape-addressed. **`Slide.shape_ids`** lists the text-capable
  shape objectIds to target. (A fuller shape-CRUD model stays out of scope; `batch_update`
  remains the escape hatch.)

## 2026-07-21 — Dev tooling: ruff + mypy + coverage gates

Formalized the quality bar as enforced CI gates (no runtime/API change):

- **ruff** (lint): rule set `E,F,W,I,B,UP`, line-length 120, ignoring `E702` (the
  deliberate one-line `x; y` style). No auto-formatter — the dense style is intentional.
- **mypy**: `check_untyped_defs`, google/defusedxml marked as missing-stubs. Fixed the
  real gaps it surfaced — typed the injected `_backend`/`_file_id`/`_comment_id` fields on
  `Comment`/`Reply` and declared `CommentsMixin`'s subclass-provided attributes.
- **coverage** (`pytest-cov`): enforced on the CI matrix with `fail_under = 85` (total
  ~87%; the gap is the integration-only `ApiBackend` calls + interactive OAuth flow).
- CI now has a dedicated `lint` job (ruff + mypy) alongside the 3.10–3.13 `test` matrix.

## 2026-07-21 — v0.1.0 (packaged for PyPI)

First release-ready packaging pass, alongside the correctness fixes from an external audit.

- **PyPI metadata.** `pyproject.toml` now carries `readme`, an SPDX
  `license = "Apache-2.0"` + `license-files`, `authors`/`maintainers`, `keywords`,
  trove `classifiers` (incl. `Typing :: Typed`), and `[project.urls]`. The version is
  single-sourced from `csa_google_workspace.__version__` via `dynamic`/`attr` (no more
  two-places-to-bump drift). `python -m build` + `twine check` pass for both sdist and wheel.
- **`py.typed` (PEP 561)** ships, so downstream mypy/pyright consume the inline type hints.
- **Typed errors from `open()`.** `ApiBackend.get_file_metadata` now routes through the
  error translator; the first call no longer leaks a raw `HttpError` on a
  missing/forbidden/service-disabled file — it raises the typed `NotFoundError` /
  `AccessError` / `ServiceDisabledError` the spec promises.
- **Cell-map degrade is now a recorded warning** (stdlib `logging`), not silence — so an
  export-cap / access / malformed-XLSX failure is distinguishable from a genuine no-match.
- **CI.** GitHub Actions runs the unit suite on Python 3.10–3.13 for every push and PR
  (the live Google suite stays gated behind `CSA_GW_INTEGRATION`).
- **License consolidated to Apache-2.0.** A single `LICENSE` (the earlier dual
  MIT/Apache `LICENSE-MIT` + `LICENSE-APACHE` files were removed).
- Version bumped `0.0.1 → 0.1.0`.

## 2026-07-20 — Lifecycle & suggestions probes (empirical)

Two new live-API probes under `experiments/`, each with a `RESULTS.md`, plus an
`experiments/README.md` index and shared-setup guide.

- **`experiments/comment-lifecycle/`** — exercised the full comment/reply cycle on a
  self-created, self-trashed throwaway Sheet. **Corrected two things in the reference doc:**
  (1) `resolved` is **absent** on a fresh comment, not `false` — it appears only after a
  resolve/reopen action (treat missing as false); (2) delete is soft and strips **author**
  as well as content, and the comment drops out of `comments.list` unless `includeDeleted=true`.
  Also confirmed: action-replies (`resolve`/`reopen`) can be **content-less**, `author.me`
  exists, and `emailAddress` is withheld even when requested.
- **`experiments/docs-suggestions/`** — settled the Docs "suggesting mode" question against a
  live doc. **Reading suggestions works** (via `suggestionsViewMode`, incl. accepted/rejected
  text previews), but **accepting/rejecting is impossible via the API** — proven by enumerating
  the entire Docs API surface (3 methods, 40 `batchUpdate` request types → zero suggestion ops).
  Suggestion **author/timestamp is not exposed**. Bonus: Docs comments carry `kix.*` anchors
  **and populated `quotedFileContent`**, so Docs comment→location mapping is trivial (unlike Sheets).
- **New reference:** `research/docs-suggestions-reference.md` (suggestions are read-only;
  no accept/reject; author unavailable; UI-automation is the only path to accept/reject).
- **Setup finding:** a correctly-scoped OAuth token still 403s with `SERVICE_DISABLED` until
  each API (Docs/Sheets/Slides) is separately enabled in the Cloud project — scope ≠ enablement.

## 2026-07-09 — Structured comment extractor

Added `experiments/anchor-probe/extract_comments.py`: extracts **all comments from any Drive file type** (Docs/Sheets/Slides/Drawings/blobs) into structured JSON — author, timestamps, content/htmlContent, resolved/deleted, quotedFileContent, raw anchor, and full reply threads (with `resolve`/`reopen` actions). For Sheets it resolves each comment's **A1 cell** best-effort via the XLSX-export join. Verified against the live sheet: correctly mapped the UI comment to B11 and the mislanded API comment to A1, with threads intact. Notes captured: `author.emailAddress` is often absent; @mentions are plain text in `content` but linkified in `htmlContent`. Extractor JSON output is gitignored (may contain real comment data).

## 2026-07-09 — Anchor probe run: empirical correction

Ran `experiments/anchor-probe` against a live sheet. Results captured in `experiments/anchor-probe/RESULTS.md`. This **corrected a conclusion** in the reference doc:

- **"Sheets anchors are opaque" was too strong.** A UI-placed comment's real anchor is `{"type":"workbook-range","uid":0,"range":"1453957822"}` — **structured**, format `workbook-range` (which a prior entry wrongly called folklore). But `range` is an opaque internal id, so the anchor is still **not A1-decodable**. Reworded §7 and the TL;DR accordingly; moved `workbook-range` out of the "folklore" list.
- **Write limitation confirmed empirically:** an API comment anchored to B11 was stored verbatim but landed on A1 in the export — the editor ignores anchor coordinates.
- **XLSX read path confirmed empirically:** comments export to `xl/threadedComments/threadedComment*.xml` (mirrored in `xl/comments*.xml`) with real A1 `ref`s (recovered `ref="B11"`). Sheets comments are *threaded comments*.
- **Resolved the a-bonus discrepancy:** its `{a:[{sht:{rng:{r,c}}}]}` parser shape is not what real UI comments return; the anchor is not an A1 source. Updated `server-landscape.md`.

## 2026-07-09 — Server landscape & anchor probe

Added, without changing existing conclusions:

- **`research/server-landscape.md`** — source-verified survey of MCP servers that handle Google comments (read from actual tool definitions, not READMEs). Ranked for "general Drive server with proper comments": **#1 a-bonus/google-docs-mcp** (only one that engineers around the Sheets limitation — cell-link + native cell note + read-side anchor mapping), **#2 taylorwilsdon/google_workspace_mcp** (broadest & most adopted, but file-level Sheets comments only, no delete/edit), **#3 piotr-agier/google-drive-mcp** (best Docs anchoring, no Sheets comments). Confirmed no server truly anchors Sheets comments — the ceiling is Google's Drive API. Official Google Workspace MCP has no comment tools.
- **`experiments/anchor-probe/`** — runnable Python script to empirically settle how Sheets comment anchors behave (create / dump-raw-anchor / xlsx-export), the one claim currently supported only by documentation.
- **Flagged an open discrepancy to verify:** a-bonus's `commentAnchor.ts` parses a concrete Sheets anchor shape `{a:[{sht:{sid,rng:{r,c}}}]}`. If real, UI-created Sheets comments are anchor-parseable, which would partly revise the reference doc's "anchors are opaque" conclusion. The probe will settle it; the reference doc is left unchanged until then.

## 2026-07-09 — Research refresh & consolidation

Verified the research against current Google Workspace documentation, the MCP specification, and the MCP server ecosystem (all as of July 2026), corrected what was wrong, and consolidated 5 overlapping documents into 3.

### Document structure

Consolidated to reduce duplication:

| Before | After |
|--------|-------|
| `Google Drive API Comment-Related Capabilities.md` + `report-claude.md` + `report-chatgpt.md` | **`google-drive-comments-reference.md`** — one canonical "how it works" reference |
| `Google Sheets Comments MCP Server - Design Document.md` | **`mcp-server-design.md`** — corrected, with a 2026 reality check |
| `llms-full.md` (scraped MCP docs) | **`mcp-protocol-notes.md`** — concise, current |

### Corrections

**Google Drive comments API**
- **Method count: 12 → 10.** 5 on `comments`, 5 on `replies`. There is **no `patch` method** in v3 — `update` uses the PATCH verb; `comments.patch`/`replies.patch` were v2-only.
- **`fields` parameter is REQUIRED** on every comments/replies method except `delete` (was not stated).
- **`resolved` is read-only** — resolve/reopen only via a reply with `action: "resolve" | "reopen"` (clarified).
- **Deletion is soft** for both comments and replies (`deleted: true`, content stripped) — confirmed.
- **Removed a fake OAuth scope.** `https://www.googleapis.com/auth/drive.comments` does not exist; corrected to the real `drive` / `drive.file` / `drive.readonly` scopes.
- **Switched v2 → v3 examples.** `report-claude.md` used deprecated v2 endpoints (`/v2/files/...`, `comments.insert`); v3 is current. (v2 is legacy/migration-encouraged but has no announced sunset date as of July 2026.)

**The `anchor` field (the big one)**
- **Cell-anchored comments cannot be created via the Drive API.** Google Workspace editors treat API-set anchors as *unanchored*; a Sheets comment created via the API lands at file level, not on the target cell. This invalidates the original "spatial index for writes" architecture.
- **Reading a comment's cell requires an XLSX-export-and-parse detour**, not the `anchor` field, which is opaque for Sheets.
- **Debunked folklore anchor formats.** `R1C2`, `sheet_id=...&range=A1`, and the `cell_classifier`/`range_classifier` JSON in the original doc had no primary source and were removed / relabeled as speculative.
- Clarified **notes vs comments**: notes (Sheets API) are genuinely cell-anchored; comments (Drive API) are not.

**Market analysis**
- **"0% of MCP servers support comments / 100% greenfield / first-mover advantage" is false.** At least 5–6 servers now implement Google comment lifecycles (a-bonus, piotr-agier, taylorwilsdon's workspace server, dbuxton, and others). The obsolete "8 servers, 0% support" table was removed. The real unsolved problem — and the defensible differentiator — is reliable UI-visible/cell-mapped anchoring, which competitors document as broken or missing.

**MCP protocol**
- Current stable spec is **`2025-11-25`**, not `2025-06-18`.
- **Streamable HTTP** replaced the old HTTP+SSE transport (as of `2025-03-26`).
- Added notes on Elicitation, the OAuth 2.1 authorization framework, and structured tool output. Flagged the breaking `2026-07-28` release candidate.

### Method
Facts were verified against primary sources (Google's API reference and guides, the official MCP spec, and server source/READMEs). One area remains genuinely uncertain: the exact current status of Google Issue Tracker threads [#292610078](https://issuetracker.google.com/issues/292610078) and [#357985444](https://issuetracker.google.com/issues/357985444) — both are sign-in-gated, so the *behavior* they describe is confirmed but their live status labels could not be scraped.
