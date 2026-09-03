# Multi-account support — one server, `account` required

**Status:** spec, for review. Not implemented.
**Date:** 2026-08-27
**Claims re-verified against the code:** 2026-08-31, at v0.37.0 — this spec sat open for 88
commits, so every existing mechanism it argues from was re-checked rather than assumed. All six
config names it relies on (`CSA_GW_READ_ONLY`, `CSA_GW_PROFILE`, `CSA_GW_TOKEN`,
`CSA_GW_CLIENT_SECRETS`, `CSA_GW_ALLOWLIST_READ`, `CSA_GW_ALLOWLIST_MODIFY`) still exist;
`editor` is still a valid profile alias (→ `writer`); `read_only` still refuses before the
backend call and still narrows the OAuth request to `.readonly`. **One claim was wrong and is
corrected below** (the "empty modify allowlist"). The suffixed names (`CSA_GW_ACCOUNTS`,
`CSA_GW_*_CSA`) are *proposed* by this document and do not exist yet.
**Decision owner:** CINO
**Related:** [`API-STABILITY.md`](../../../API-STABILITY.md) · [`SECURITY.md`](../../../SECURITY.md) ·
[#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82) (allowlisting)

---

## The problem

One person, several Google accounts — `kseifried@cloudsecurityalliance.org` and a
`seifried.org` one. Today the server authorizes exactly one, because the token cache is a single
path.

Both Google's Drive MCP server and the claude.ai connector have the same limit, structurally:
**one account per OAuth grant**, and connecting a second replaces the first. That makes this a
differentiator, not just a convenience.

## Two designs, and why we are choosing the second

### A — one server instance per account

Register the server twice under different names with different `CSA_GW_TOKEN` values.

**This already works today, with no code changes** — verified 2026-08-27: `CSA_GW_TOKEN` is
env-configurable, `_desktop.carried_env()` already carries it into the client config, and both
OAuth paths bind port 0 (`auth.py:92`, `_auth_flow.py:79`) so two simultaneous logins cannot
collide on the callback port.

| For | Against |
|---|---|
| Zero code. Available now | **Context cost: the whole tool surface × N accounts.** *(Read 34 × N when written; the surface is 52 as of v0.47.0, so two accounts is 104 tools — the argument gets stronger as the server grows, which is why the number is no longer written in.)* |
| **Process isolation** — a *code* bug cannot cross accounts (but see the threat-model section: this does **not** help against injection, and does not isolate tokens at rest) | No fan-out across accounts |
| Per-account policy is free — separate env per instance | The model picks by server prefix, which is easy to get wrong and invisible in the result |

### B — one server, `account` a required parameter — **chosen**

**Rationale, from the CINO:** *"then if they do anything, they did it, not the software."* A
required parameter with no default means every account choice is an explicit act by the caller.
There is no configuration under which the software picks an account on somebody's behalf.

This is the same principle already load-bearing in this codebase, and it is recorded in
`_apply.py` for a reason learned the hard way: **an absence and a value are different things, and
one parameter must not carry both.** An optional `account` would have to default, and a default is
how a model that simply forgot the parameter writes to the wrong Drive.

**What B gives up:** A's *process* separation. B holds N credentials in one process, so account
resolution becomes correctness-critical, and it must be guarded by a test the way `policy._GATES`
is — see *The resolution seam* below. **How much that separation is worth is settled below, and
the answer is: for local stdio, nothing security-relevant.**

### A does not need dynamic tool naming — that worry is unfounded

Worth stating because it is the first objection A attracts. **You do not rename anything.** MCP
clients namespace tools by server automatically — observed in a live session, not inferred:

```
mcp__csa-google-workspace__list_comments
```

Register the server twice under two names and the client yields
`mcp__csa-gw-work__list_comments` and `mcp__csa-gw-personal__list_comments`. `MCPServer(name=…)`
already takes the name from settings, so this costs no code.

A's real problems are different ones:

1. **Both instances ship identical descriptions.** `INSTRUCTIONS` is a module constant, so the
   model distinguishes the accounts *only* by the server-name prefix. Nothing in any description
   says *"this one is the work account."* Fixable by taking the identity from settings — small, but
   work A needs and B does not.
2. **34 × N tool definitions** in every session.
3. **The result never says which account acted.** The tool *name* carried it; the payload does not,
   so a model summarising back to a human can drop it silently.

### Same POSIX user, therefore not a security boundary

**Settled 2026-08-27, by the CINO.** For a local stdio deployment, process separation is a
**reliability** boundary — a crash or a code bug in one instance does not reach the other — and
**not a security boundary at all.**

The proof does not need the interesting part. **Both processes read tokens from
`~/.csa_google_workspace/`, which is readable by that user.** Any code running as the user already
holds *both* tokens, whatever the process count. Signals, debuggers and `/proc/PID/mem` are
additional; the filesystem alone is sufficient and certain.

**Scoping caveat, so this is not misapplied.** The conclusion is about *same-user local stdio*.
In a **hosted, multi-tenant** deployment — Customer360 — tenant isolation genuinely *is* a security
boundary, because the tenants are different principals with different rights. Same word, opposite
weight, and the deciding question is only ever *do these identities share a POSIX user?*

### Weigh that against the actual threat, not the tidy one

**Corrected 2026-08-27**, after the CINO observed that the real attack surface is the model.
An earlier draft of this spec treated process isolation as B's significant cost. It is not, and
the reason matters enough to write down.

[`SECURITY.md`](../../../SECURITY.md) names **prompt injection through document content as the
primary risk**. Measure both designs against *that*:

| | A — process per account | B — one process |
|---|---|---|
| Injection says *"use the personal account"* | Model calls `csa-gw-personal__create_comment` | Model passes `account="personal"` |
| **Exposure** | **identical** | **identical** |

In A the model holds tools for **every registered server simultaneously**. Process isolation
protects against a *software bug* crossing accounts; it does nothing about the *model being
persuaded* to pick the other one — and the model is the attack surface.

**Nor does it isolate the credentials at rest.** Both processes run as the same user with read
access to `~/.csa_google_workspace/`, so a malicious dependency or a code-execution flaw in
*either* process reads *both* tokens. The boundary is a process, not a privilege domain.

**What actually defends here is capability gating and the allowlists** — already built, already
fail-closed. A personal account that is `read_only` cannot be made to write by any injection,
whichever tool the model is talked into calling: `Document._require_writable()` and
`CommentsMixin.create_comment` refuse *before* the backend call, and `read_only` also narrows the
OAuth request to `.readonly` scopes, so the token itself cannot carry the authority.

**Not "an empty modify allowlist"** — an earlier draft of this section said that, and it is not a
configurable state. `allowlist.py` **refuses to start** on one: *"Refusing to run with an empty
allowlist, because that is indistinguishable from a typo."* That is deliberate, and it makes the
point above stronger rather than weaker — the config cannot silently degrade to permitting
nothing, so "this account may not write" has to be said out loud (`read_only`, or a profile that
excludes writes) rather than achieved by leaving something blank. A control you can enable by
accident is one you can disable by accident.

Per-account policy (§2) is that control extended to several identities, and it is the real
security argument for this work.

Two ways **B is better** against the primary risk:

- **`acted_as` on every response (§7).** Attribution after the fact is the main way a *successful*
  injection gets detected. An echoed field is far harder for a summarising model to drop than a
  tool-name prefix is.
- **One policy declaration** instead of two client entries that can silently drift apart.

### The property A really has is reachability, and B subsumes it

Not isolation — **reachability**. Under A you can register only the personal server for a session,
and the work account is *absent*: no injection can reach a tool that does not exist. That is
stronger than any gate, because it is not a decision anything makes at runtime.

**B gets the same property for free**, because `CSA_GW_ACCOUNTS` is per client entry. Register the
same server twice with different account lists and the accounts are as unreachable from each other
as two processes would make them:

```
csa-gw-work      CSA_GW_ACCOUNTS=csa                 # this session cannot see the personal account
csa-gw-personal  CSA_GW_ACCOUNTS=personal
csa-gw-both      CSA_GW_ACCOUNTS=csa,personal        # convenience, when you want both
```

So **reachability is a deployment decision, not an architecture decision**, and one codebase spans
the whole range. That is the argument that settles A vs B: B is a superset.

**The general principle, worth carrying beyond this feature:** the strongest protection for a
capability against prompt injection is for its tools **not to be present in the session at all**.
Gating is the fallback for when they must be.

## Design

### 1. Configuration — env only, by suffix

**A correction to how this rule is usually justified here.** "Env, not a file" does *not* buy
tamper-resistance: the MCP client config that carries the env (`claude_desktop_config.json`,
`.mcp.json`) is itself a user-writable file, and per *Same POSIX user* above, anything running as
the user can rewrite it. What env-only actually buys is **provenance and reviewability** — one
place to look, visible in `claude mcp get`, travelling with the client entry, and **never written
by the server itself**. Those are the real reasons; integrity is not one of them.

So the rule is a split rather than a prohibition:

| | Where | Why |
|---|---|---|
| Which accounts exist, and each one's **policy** | **env** | declarative, reviewable, server never writes it |
| The **tokens** | files, one per account | already true today; only the naming changes |

`gmail-mcp-multi` puts both in `~/.gmail-mcp/` (`config.json` for aliases, `accounts/{alias}/credentials.json`
for tokens, and `oauth-keys.json` for the OAuth **client secret**). We deliberately do not follow
that on either count: per-account **policy** in a server-managed file is the worst version of the
alias-swap problem — an attacker rewriting `personal` from `read_only` to `editor` is worse than
swapping which account is used — and the client secret stays out of the token tree, which is why
`_desktop.carried_env()` already excludes `CSA_GW_CLIENT_SECRETS`.

With that settled:

```
CSA_GW_ACCOUNTS=csa,personal
```

That declares the aliases and is the only new variable. **Any existing `CSA_GW_*` variable may
then be suffixed with `_<ALIAS>` to override it for that account**, falling back to the unsuffixed
form as a shared default:

```
CSA_GW_ACCOUNTS=csa,personal

CSA_GW_PROFILE=read_only                  # shared default: both accounts read-only…
CSA_GW_PROFILE_CSA=editor                 # …except the work one

CSA_GW_ALLOWLIST_READ_CSA=https://docs.google.com/document/d/…
CSA_GW_ALLOWLIST_MODIFY_CSA=https://docs.google.com/document/d/…
CSA_GW_ALLOWLIST_READ_PERSONAL=*
```

Chosen because it introduces one concept rather than a parallel configuration language, reuses
every variable name that already exists and is already documented, and extends to variables not
yet invented.

**Token paths default from the alias** — `~/.csa_google_workspace/token-csa.json` — so the common
case needs no path configuration at all. `CSA_GW_TOKEN_CSA` overrides.

**Aliases are case-insensitive on the wire, upper-cased in variable names.** `[a-z0-9_-]{1,32}`,
validated at startup; an alias that cannot be turned into a valid variable suffix is a loud
configuration error, not a silent skip.

### 1a. Identity: the alias is the handle, the verified email is the truth

Two identifiers, and which is which is forced by *when each is knowable*.

Configuration must name an account **before any token exists**, and an unauthorized account has no
email yet. So the email can be neither the configured identifier nor the published enum:

| | Role | Known when | Direction |
|---|---|---|---|
| **alias** | the **local handle** — declared in config, taken by the parameter, listed in the enum | always, from config | **input** |
| **email** | the **authoritative identity** — what a reply asserts | after authorization, from Google | **output only** |

So an account always has a **handle**. What is optional is whether the handle means anything to a
human.

**Both are accepted as input** (`gmail-mcp-multi` does this and it costs nothing):

- `account="csa"` — the configured handle
- `account="kseifried@cloudsecurityalliance.org"` — the verified email, once known

**Nobody is forced to invent an alias.** A handle may simply *be* an email address —
`CSA_GW_ACCOUNTS=kseifried@cloudsecurityalliance.org,kurt@seifried.org` is a valid configuration,
and for one account `CSA_GW_ACCOUNTS` may be omitted entirely, giving a single account whose handle
is `default` until authorization supplies its email, after which the email works too.

Validation: a handle that collides with a *different* account's verified email is a startup error.
Rare, but it is the one way this ambiguity bites.

**Obtaining the email — verified 2026-08-27.** `drive.about.get` returns `user.emailAddress` and
is authorized by the `drive` and `drive.readonly` scopes **already requested**. So: no new scope,
**no re-consent for existing users**, one call per token, cacheable because an account's email does
not change.

Costs a new `Backend` method and therefore a `policy._GATES` entry — and it is the first gate that
is **account-scoped rather than file-scoped**: `Gate(capability=None, file_scoped=False)`.

### 2. Per-account policy is the point, not a side effect

Different accounts genuinely warrant different capability sets: the work account editing shared
review documents while the personal one is read-only, or the reverse. Because policy is per
account, **a compromised prompt cannot use the personal account's laxer allowlist to touch a work
document** — the two never share a `Policy` object.

This is the strongest security argument *for* B over A-with-two-configs, since it makes the
distinction enforceable in one auditable place rather than dependent on two client entries staying
correct.

### 3. The resolution seam — fail closed

`get_workspace()` becomes `get_workspace(account: str)`. It is the **only** place an alias becomes
credentials, and it is the account analogue of `PolicyBackend`:

```python
def __call__(self, account: str) -> Workspace:
    key = account.strip().lower()
    if key not in self._accounts:               # refused, never defaulted
        raise ToolError(
            f"unknown account {account!r}. Configured: {', '.join(sorted(self._accounts))}. "
            f"Accounts are declared with CSA_GW_ACCOUNTS.")
    ...                                          # thread-local cache keyed by (thread, key)
```

Non-negotiables:

- **An unknown alias is refused**, and the error names the configured ones so a model can recover
  in one turn rather than guessing.
- **No fallback, no "the only one", no first-in-list.** If resolution cannot name the account, it
  fails.
- The thread-local `Workspace` cache is **keyed by account**. A shared one would hand account A's
  client to a call for account B — the same non-thread-safety trap `googleapiclient` already
  forced us to solve once, in a form that would be a data-crossing bug rather than a crash.
- **A test in the shape of `test_policy.py::test_every_backend_method_has_a_declared_gate`** —
  reflect over the registered tools and fail CI if any tool reaches a `Workspace` without an
  account having been resolved for it.

### 4. `account` is required in the published schema — always

Even for somebody with one account.

A schema that changes shape based on configuration is a schema that lies to every client that
cached it, and *"there is only one, so it cannot be wrong"* is the exact reasoning that produced
the `FALSE`-means-two-things defect. One rule, no modes.

**And it is an `enum` of the configured aliases, not a free string.** With one account the schema
offers exactly one legal value, so there is nothing to get wrong; with two, the model must name one
and cannot invent a third.

This refines the paragraph above rather than contradicting it: the parameter **existing** is the
schema's *shape* and never varies; the **allowed values** are a *constraint*, and clients re-fetch
tool lists on connect. It is strictly safer — an invalid alias cannot be sent at all, so the
fail-closed seam becomes the second line of defence rather than the first. Aliases are always
knowable at startup (§1a), so the enum is never empty or stale.

**Migration** for existing single-account users is therefore a breaking change, and a one-line
one:

```
CSA_GW_ACCOUNTS=default
mv ~/.csa_google_workspace/token.json ~/.csa_google_workspace/token-default.json
```

Pre-1.0.0 is precisely when to take this. `configure` should perform the rename itself and say so.

### 4a. The limit of a required parameter — and the sentence that has to carry it

**`account` required stops the *software* from choosing. It does not stop the *model* from choosing
badly.**

A user says *"check my comments"* with two accounts configured. The model must supply a value, so
it will **pick one** rather than ask, unless something tells it otherwise. A JSON schema cannot
express *"ask the human"*; only a description can.

So the load-bearing sentence lives in the tool descriptions, not the signature:

> **If the user has not said which account, ask. Do not choose.**

That gives a clean division of labour, worth stating because only the first half is enforceable:

| Mechanism | Moves the decision |
|---|---|
| `account` required + enum | from **software** to **model** — enforceable |
| the description above | from **model** to **human** — *not* enforceable |
| `acted_as` echoed (§7) | detection, after the fact |

Nothing here closes the gap fully. `acted_as` is what makes it *visible*, which is why it is not
optional.

### 5. Which tools take `account`

**Required on every tool that touches Google**: all file, content, comment, permission, export and
apply tools, plus `search_files`, `list_recent_files`, `create_file`, `demonstration_plan`, and
`authenticate`.

**No `account`** — these are about the server, not an account:

| Tool | Why |
|---|---|
| `list_accounts` | It is the discovery mechanism; requiring an account would be circular |
| `report_a_problem` | Diagnostics about the install. Must keep working when **no** account is authorized |
| `describe_configuration` | Takes an **optional** `account`: without one, the server-wide config plus the alias list; with one, that account's effective policy |
| `read_server_resource` | Same treatment — it renders `csa-gw://config`, which becomes per-account. Optional `account` |

Counted against the live registry rather than by hand: of the **34 tools present when this was written** (52 as of v0.47.0), **31 would take a
required `account`**, and the three above would not.

### 6. `list_accounts` — because a required parameter must be discoverable

A model cannot supply a required parameter it has no way to learn. Read-only, needs no credentials:

```
list_accounts() -> [{alias, authorized, email?, profile, read_only}, …]
```

`email` only when a token exists and Google returned one — it is usually absent
(`research/google-drive-comments-reference.md`), so it is a convenience, never the key. `alias` is
the identifier.

### 7. Echo the acting account — address first, alias second

**A required input proves intent; an echoed output proves what happened.** Every tool that acts on
Google returns `acted_as: {email, alias}`, and the human-readable form leads with the **address**:

> *"Replied to 3 comments on **kseifried@cloudsecurityalliance.org**, which you also call
> `work`."*

**The ordering is the point, not politeness.** An alias is user-chosen and can be wrong — somebody
can alias their personal account `work` by mistake. Leading with the alias would let a mis-assigned
alias misattribute silently, forever. Leading with the address **Google verified** means a
misleading alias cannot hide anything: the ground truth is always on screen, and the alias is there
only so the reader recognises which one they meant.

It detects **two** distinct failures, not one:

1. **The model chose an account the human did not intend** — the risk §4a cannot prevent.
2. **The human's own configuration is wrong.** Swapping the `work` and `personal` aliases by
   accident is an easy mistake, silent forever otherwise, and *only* visible by comparing the
   handle you asked for against the address that actually acted. This is the case that makes the
   echo worth it even in a single-user, non-adversarial setting.

**And the cost is a few tokens.** There is no competing consideration — no privacy cost (it is the
user's own identity, shown to their own model), no failure mode, no ambiguity introduced. When a
control is this cheap and detects a class of silent error, it is not optional.

#### The 1Password precedent, and why a conversation is harder than a GUI

The CINO's example, and it is the right one. Corporate 1Password accounts sit alongside personal
ones, and people routinely put personal items in the work vault — because it is one machine, or
they never set the personal account up, or they simply picked the wrong store at save time. **It
happens constantly, to careful people.**

Two things follow.

**1Password shows the destination vault in the UI at save time, and people still get it wrong.** So
an echo is *not sufficient*. But note what we do not have: a GUI has a **persistent visual
indicator** of the active account, always on screen, glanceable. A conversation has no such
surface. **The reply is the only place the identity can appear at all** — which makes the echo more
important here than in 1Password, not less, and means the design cannot lean on the user "just
checking" somewhere else.

**The consequence is a governance failure, not a mis-attribution nuisance** — and it is asymmetric,
so both directions need naming:

| Slip | Where the action is recorded | Why it matters |
|---|---|---|
| Personal document, **work** account | CSA's Admin Console Drive audit log | Personal activity inside corporate retention and discovery scope. The 1Password personal-in-work-vault problem, offboarding included |
| CSA document, **personal** account | **no CSA audit log at all** | Corporate work happening off the corporate trail, invisible to the people accountable for it |

The second is the one an organisation should fear more, and it is the one nobody notices, because
nothing is *missing* from the user's point of view — the comment posted, the thread resolved, the
work got done. Only the record is gone.

This is the strongest argument for `acted_as`: it is the sole mechanism by which either slip becomes
visible at the moment it happens, rather than during an audit that will not find what was never
logged.

### 8. `authenticate(account)`

One consent flow per account, into that account's token path. Google permits the same OAuth client
across accounts; only the token differs. Port 0 already prevents callback collisions.

`configure --account <alias>` writes the client entry, and should be able to add an alias to an
existing entry rather than replacing it.

## Logging and the audit trail — local logs are for debugging, not for security

**Raised by the CINO, and it changes the design of C4 ([#145](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/145)), not just this feature.**

An attacker who has compromised the MCP client is running as the user. So a local log file is
writable by them, and cleaning it up is among the first things they would do. **By the argument in
*Same POSIX user* above, a local log cannot be evidence against a local attacker.** It is a
debugging aid, and #145 should say so rather than implying an audit property it cannot have.

**The real record is server-side, at Google.** Every action here is taken with the user's own
token, so Drive logs it as that user — and for a Workspace account those events reach the **Admin
Console Drive audit log**, which the user cannot delete and the compromised machine cannot reach.
That is the tamper-resistant trail, and it exists already without us building anything.

Three consequences:

- **Do not oversell local logging.** Ship it for diagnostics — the ring buffer and opt-in JSONL in
  #145 are right — and state plainly in `SECURITY.md` that the durable record is Google's.
- **Default the level to genuinely-bad-only**, per the CINO, with opt-in verbosity and a full debug
  mode for troubleshooting. That is not merely about noise: verbose logging of a tool that reads
  documents risks **writing document and comment content to disk**, which `SECURITY.md` explicitly
  rules out ("no persistent storage of comment content"). So default-minimal is a *privacy*
  control, and full debug needs a loud statement of what it may capture — not a quiet flag.
- **Multi-account makes Google's trail *more* useful**, because the acting identity determines
  *which* audit log the action lands in. A work-account action is visible to CSA admins; a personal
  one is not. That is another reason the acting identity must be explicit and echoed.
- **Answered 2026-08-27: they do.** Drive log events carry **App ID** (*"OAuth client ID of the
  third-party app that performed the action"*), **App name** and **API method**, so actions through
  this server are already distinguishable from the same user's manual edits — unforgeably, because
  Google derives it server-side. Full findings and the four things the trail *cannot* record in
  [`research/audit-trail-and-agent-attribution.md`](../../../research/audit-trail-and-agent-attribution.md).
  The one that matters here: **an audit trail whose coverage depends on an unlogged runtime decision
  is not a trail**, which makes `account` required-and-echoed an audit argument, not a usability
  one.

## Consequences

- **`API-STABILITY.md`**: `account` becomes a stable, required parameter name on the listed tools.
  **Alias *values* are user-chosen configuration and explicitly not contract** — the same
  distinction already drawn between capability names (contract) and profile membership (not).
- **`SECURITY.md`**: a new paragraph. The server now holds credentials for several identities, so
  *"acted as the wrong identity"* joins the threat model — and it belongs under the **prompt
  injection** heading, not token custody, because that is where it will actually come from. State
  the three mitigations honestly: the required parameter (intent), `acted_as` (detection),
  per-account policy (containment). And state plainly that **a session which does not need an
  account should not be configured with it** — reachability beats gating.
- **Context cost**: one extra required parameter on 31 tools, versus A's 34-tools-per-account.
  Strictly better beyond one account.
- **A stays available and is worth documenting anyway** — for anyone who wants process isolation
  badly enough to pay the context cost, it needs no code and it is a legitimate choice.

## Open questions

1. **Fan-out.** `mcp-google-multi` offers "one call across all accounts". Deliberately **out of
   scope here**: a fan-out write is exactly the un-attributable action this design exists to
   prevent. A fan-out *read* (`search_files` across both) is genuinely useful and could be a
   separate, explicitly-named tool later — never a magic value of `account`.
2. **Does `export_comments`' register need an account column?** A register exported from one
   account and applied under another would post as the wrong person. The document-identity check
   catches a *different file*; it would not catch the *same file, different identity*. Probably
   yes, and it is the same class of bug the register's existing `wrong_file` guard exists for.
3. **`CSA_GW_READ_ONLY` interaction.** It narrows OAuth scopes at token-acquisition time, so it is
   a property of the *token*, not of a runtime call. Per-account it is coherent; a shared default
   with a per-account override may mean a token has to be re-acquired when it changes. Needs a
   check that changing it does not silently keep using a broader token.
4. **Does the alias belong in `report_a_problem`?** The alias is user-chosen and could contain
   anything, including a name. Report the *count* of configured accounts and which one was acting
   by index, not by alias.

## Not doing

- Automatic account inference from a file id — trying each account until one resolves. It leaks
  which accounts can see a file, is slow, and picks for the user, which is the whole thing being
  avoided.
- A `switch_account` tool. Ambient state a model can forget it set is the worst version of this
  feature.
- Encrypted token storage at rest (as `mcp-google-multi` does with AES-256-GCM). Worth considering
  separately, but it is orthogonal — the current 0600 + `O_NOFOLLOW` handling is unchanged by
  account count.
