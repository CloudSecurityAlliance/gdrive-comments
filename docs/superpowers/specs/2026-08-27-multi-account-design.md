# Multi-account support — one server, `account` required

**Status:** spec, for review. Not implemented.
**Date:** 2026-08-27
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
| Zero code. Available now | **Context cost: 34 tools × N accounts.** Two accounts is 68 tools |
| **Process isolation** — each process holds exactly one credential, so a bug *cannot* cross accounts | No fan-out across accounts |
| Per-account policy is free — separate env per instance | The model picks by server prefix, which is easy to get wrong and invisible in the result |

### B — one server, `account` a required parameter — **chosen**

**Rationale, from the CINO:** *"then if they do anything, they did it, not the software."* A
required parameter with no default means every account choice is an explicit act by the caller.
There is no configuration under which the software picks an account on somebody's behalf.

This is the same principle already load-bearing in this codebase, and it is recorded in
`_apply.py` for a reason learned the hard way: **an absence and a value are different things, and
one parameter must not carry both.** An optional `account` would have to default, and a default is
how a model that simply forgot the parameter writes to the wrong Drive.

**What B gives up, stated plainly:** A's *process* isolation. B holds N credentials in one
process, so account resolution becomes correctness-critical. That is an acceptable trade **only**
because the mitigation already exists as a proven pattern here — see *The resolution seam* below —
and it must be guarded by a test the way `policy._GATES` is.

## Design

### 1. Configuration — env only, by suffix

Per the standing rule that policy lives in the client config as environment variables and never in
a local file:

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

**Migration** for existing single-account users is therefore a breaking change, and a one-line
one:

```
CSA_GW_ACCOUNTS=default
mv ~/.csa_google_workspace/token.json ~/.csa_google_workspace/token-default.json
```

Pre-1.0.0 is precisely when to take this. `configure` should perform the rename itself and say so.

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

Counted against the live registry rather than by hand: of today's 34 tools, **31 would take a
required `account`**, and the three above would not.

### 6. `list_accounts` — because a required parameter must be discoverable

A model cannot supply a required parameter it has no way to learn. Read-only, needs no credentials:

```
list_accounts() -> [{alias, authorized, email?, profile, read_only}, …]
```

`email` only when a token exists and Google returned one — it is usually absent
(`research/google-drive-comments-reference.md`), so it is a convenience, never the key. `alias` is
the identifier.

### 7. Echo the acting account in every response

**A required input proves intent; an echoed output proves what happened.** Every tool that acts on
Google returns `acted_as` — the alias, and the email when known.

Cheap, and it is what makes *"they did it, not the software"* verifiable after the fact rather
than only intended beforehand. It also gives the human reviewing a transcript the one fact they
most need and currently cannot see: which of their identities posted that comment.

### 8. `authenticate(account)`

One consent flow per account, into that account's token path. Google permits the same OAuth client
across accounts; only the token differs. Port 0 already prevents callback collisions.

`configure --account <alias>` writes the client entry, and should be able to add an alias to an
existing entry rather than replacing it.

## Consequences

- **`API-STABILITY.md`**: `account` becomes a stable, required parameter name on the listed tools.
  **Alias *values* are user-chosen configuration and explicitly not contract** — the same
  distinction already drawn between capability names (contract) and profile membership (not).
- **`SECURITY.md`**: a new paragraph. The server now holds credentials for several identities, so
  the failure mode *"acted as the wrong identity"* joins the threat model. Note the mitigation is
  the required parameter plus the single resolution seam, and that per-account policy means a
  laxer account cannot lend its scope to a stricter one.
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
