# The capability model mirrors Drive's roles

**Status:** agreed 2026-08-28 (CINO). Supersedes the three-axis proposal in issue #195 and
[`FINDINGS.md` §5](../../security-audits/2026-08-27-defending-code-reference-harness-claude/FINDINGS.md).
**Closes:** #195.

## The decision in one line

**Use Google Drive's own roles, with nothing added.** Five profiles named exactly as the Drive
API names them, the ten existing capabilities distributed across them the way Drive distributes
authority, and — after working through every candidate — **no orthogonal axes and no
`everything` profile**, because nothing we expose falls outside Drive's categories.

Two switches are added that are explicitly **not** capabilities: `local.read` and `local.write`,
which are data-handling controls. Calling them security controls would promise containment they
cannot deliver, and §4 explains why.

## Why mirror Drive

The operator already has a mental model of who may do what to a Google file, because Google gave
them one and they use it every day. Inventing a parallel vocabulary means every operator holds
two models and maps between them, and the mapping is where mistakes live.

It is also externally validated in a way our own reasoning is not. The v0.21.0 rework drew the
line on *"can this be undone?"* and got a better answer than the verb-alarm ordering it replaced
— but it was one project's reasoning. Drive's roles are the same problem solved at enormous
scale, and they agree with the recoverability ordering on the point that matters: **`writer`
cannot share.** Google withholds sharing from Editor and reserves it for Manager and Owner.

That last fact settles a question the audit got wrong, which is worth recording because the
audit's reasoning was good and its conclusion still did not survive contact with Drive.

## 1. The profiles

Config accepts **only** the API string. The UI label is documentation, and §5 explains why both
are not accepted.

| profile (config value) | Google UI label | adds | Drive rationale |
|---|---|---|---|
| `reader` | Viewer | — | read content and metadata; may obtain copies |
| `commenter` | Commenter | `comment.create` · `comment.reply` · `comment.resolve` | read + comment, no content edit |
| `writer` | Editor · Contributor | + `content.write` · `file.create` · `file.update` · `file.trash` | edit content; **cannot share** |
| `fileOrganizer` | Content manager | + `comment.edit` · `comment.delete` | "contribute **and manage** content" |
| `organizer` | Manager | + `file.share` | files, folders, **people** and settings |

`editor` and `full` remain accepted as aliases of `writer` and `organizer`, so no existing
configuration breaks.

### Where this departs from Drive, deliberately

**`file.update` and `file.trash` stay in `writer`.** A strict reading of Drive would move them up
to `fileOrganizer`: Drive's Writer cannot reorganize a shared drive or delete from it. That
constraint exists because Drive folders have owners and hierarchy; our "move" is a rename and our
"trash" is the user's own bin.

More importantly, moving them would undo a decision made on evidence. v0.21.0 put `file.trash` in
the default profile because **without it an agent that creates a working file cannot clean up
after itself** — the litter accumulates in somebody's Drive and the only tool that could tidy it
is switched off. That was the state before v0.21.0 and it was a worse outcome than the one the
restriction protected against. Following Drive to the letter here would silently narrow the
default profile and reintroduce a known bad outcome. Mirror the shape and the names; do not
import a constraint whose premise we do not share.

**`comment.edit` / `comment.delete` are placed at `fileOrganizer`.** Two reasons, one strong and
one weak, stated separately because they deserve different confidence:

- *Recoverability (strong, verified).* Drive has **no comment-level restore**. The only path is
  restoring a whole document version, and community reports indicate comments are sometimes still
  lost; combined with the API's soft delete stripping content **and** author, `comment.delete` is
  the least recoverable mutation in the surface. It does not belong with ordinary editing.
- *Drive analogy (weak, unverified).* "Content manager" is where Drive puts *managing* content as
  distinct from contributing it. Searches for authoritative Google documentation on exactly who
  may delete whose comments returned only community threads, so this is a reading of the role's
  description, not a documented mapping. It is not load-bearing; the recoverability argument
  carries the placement on its own.

This placement also fixes the audit's actual complaint. §5.3 objected that `full` bundled R1
destruction with R0 disclosure, so *"may destroy comment history, may never share"* was not
expressible. It now is: that is `fileOrganizer`.

## 2. Three candidate axes, and why none of them is one

The audit proposed three orthogonal opt-ins. Each was worked through and each collapsed. The
reasoning is recorded because "we considered it and dropped it" is only useful with the argument
attached.

### Bulk is not an axis

`export_comments` and `apply_comment_actions` have no web-UI equivalent — Drive has no bulk
comment operation anywhere. That makes them *convenient*, not *privileged*: every one of them can
be emulated one call at a time with the same capabilities, so bulk confers **no authority a
caller does not already have**. Leverage is an operational concern (rate limits, blast radius of
one mistake), not an authorization one. `export_comments` maps as reading comments;
`apply_comment_actions` maps as writing them.

### `content.active` is not an axis — the parameter goes away instead

The audit proposed a capability governing whether written content may be *evaluated* by a
downstream engine (Sheets formulas, CSV/XLSX formula injection).

It does not survive the mirroring test: **any human with Editor can type `=IMPORTXML(...)` into
Sheets in the browser.** Google calls that `writer`. A capability here would be us inventing a
distinction Drive does not have, and the whole premise of this spec is not doing that.

But the underlying finding (T15) is real, and the residual recorded in `THREAT_MODEL.md` §0 is
that the only thing between an injected agent and server-side formula evaluation is a docstring
saying *"DO NOT pass `USER_ENTERED`"* — an instruction to the model, on a surface whose premise
is that content can instruct the model.

**Resolution: remove `valueInputOption` from the MCP tool surface entirely.** The MCP tools always
send `RAW`; the library keeps the parameter for an embedder who has decided. This is not a new
axis, it is the pattern already used here — raw `batch_update` is deliberately withheld from MCP
while the library exposes it. **Deleting the attack surface beats gating it**, and it needs no
vocabulary Google lacks.

### `export.file` is not an axis — because view ≈ download

The audit proposed a capability for the local-filesystem write, on the grounds that `PROFILE=reader`
can currently write a `.csv` to disk. Measured, and true: all four profiles write to disk today,
because the local-write path is not in the capability model at all.

But under Drive's model that is **correct, not a bug**: a Viewer may obtain a copy — browser
download is a Viewer action. "May export comment data" is a read operation.

The remaining objection was observability: a browser download raises a Drive **download event**
that is audit-loggable and DLP-interceptable, whereas an API read plus a local write raises no
Drive-side event at all (this is T7). That objection does not survive either, for two reasons:

1. **The distinction was already fiction for a motivated human.** View-only documents are defeated
   by screenshots and OCR, which reconstruct the text and formatting without ever raising a
   download event. The event records a ritual, not a boundary.
2. **For our actual adversary it is not even effortful.** The threat is an injected agent, and it
   does not need OCR: `read_file_content` already returned the full text into its context. Writing
   that text to disk gives it nothing it does not have.

**Confidentiality is lost at read, not at write.** A capability on the write would gate the second
copy while the first is already in the model's context — a control that appears to contain
something after containment is spent. That is precisely the shape this project keeps recording as
a failure: a guard placed where it cannot act.

T7 stays `partially_mitigated` and the audit-trail gap stays real. It is an R0 property —
"nothing to recover, it was seen" — and R0 is not something a capability recovers.

## 3. Therefore: no `everything` profile

An `everything` profile earns its place only if something exists outside the ladder for it to
cover. After §2, nothing does. `organizer` grants all ten capabilities, so "everything" and "top
of the ladder" are the same set and one name is enough.

Recording the near-miss, because it was nearly built: the argument *for* it was that once
orthogonal capabilities exist, `full` becomes ambiguous — either it silently absorbs them on
upgrade (a break in the dangerous direction) or it stops meaning "full". That reasoning was sound;
it simply has no premise now. **If a future capability genuinely falls outside Drive's categories,
this question returns**, and the answer then is two names — a stable ladder top plus an explicitly
auto-absorbing `everything` that logs what it resolved to. Not needed today.


## 3a. Defaults: on, not closed

**Decided 2026-08-28 by the CINO.** Out of the box: **all ten capabilities enabled, both
allowlists `*`.** The documentation's job becomes *how to narrow this*, not *how to switch it on*.

This reverses the #82 posture, and the case for reversing it is mostly already written down in
this repository:

- **The README already tells operators to set `CSA_GW_ALLOWLIST_READ="*"`**, and explains why the
  fine-grained alternative is not what anyone wants. The fail-closed default was already
  contradicted by our own documented happy path; the only thing it reliably produced was a
  setup step.
- **`THREAT_MODEL.md` §1 says Drive is the primary control layer** and that this project's layer
  is *"defense in depth, deliberately narrow … not the primary layer and not intended to be."*
  A deliberately-narrow secondary layer that bricks the tool on install is inconsistent with its
  own stated role. For activities on Google Drive, Drive is where policy belongs — that framing
  is the maintainer's and it predates this decision.
- **Somebody installing a Google Workspace MCP server intends to do Google Workspace things.**
  No comparable MCP server ships inoperative. A control that every operator disables during setup
  is not a control; it is a support burden that additionally teaches people to paste `*` without
  reading, which is a worse outcome than defaulting to `*` honestly.
- **Locking it down must stay easy and obvious** — that is the part this spec must not lose. The
  profiles, the two allowlists and `CSA_GW_CAPABILITIES` all keep working exactly as they do now;
  only which end of the range you start from changes.

### The counter-argument, recorded rather than resolved

`file.share` was raised as the one plausible exception: it is not on the get-work-done path for a
comments-and-content tool — nobody installs this in order to grant Drive permissions — so
defaulting it on removes no friction from any real workflow, while it is the single capability
whose effect leaves the organisation and cannot be recalled once a copy is taken.

**Overruled deliberately**, and the reasoning is coherent: Drive is the layer that owns sharing
policy, and an organisation that cares has sharing restrictions, target audiences and DLP for
Drive available there. Recorded here because a default that was argued about is worth being able
to find later, not because the decision is unsettled.

What follows from it: `file.share` must be **named prominently** in the "how to narrow this"
documentation as the action whose effect leaves the organisation, and `describe_configuration`
and `csa-gw://config` must show it as enabled rather than leaving an operator to infer it.

### What does NOT change

**`PolicyBackend` still fails closed on an unlisted `Backend` method.** That is a different
property from a permissive default and must not be simplified away with it: a method added to the
protocol without a `_GATES` entry is *refused*, not delegated, so forgetting one turns the method
off rather than leaving it silently ungoverned. `tests/test_policy.py` keeps enforcing it. The
default set is a policy decision; the gate table is a code-safety invariant.

### Consequences to carry out with this change

- **T1 must be rescored in `THREAT_MODEL.md`.** #197 required that the model carry T1 forward on
  the basis that `CSA_GW_ALLOWLIST_READ="*"` is *"a deliberate interim posture with a documented
  1.0.0 path, not a defect"*, and that it be rescored if that changed. It has changed: this is now
  the permanent default rather than an interim posture. §0 must record the move, and
  `tests/test_threat_model.py` will fail until it does.
- **The v0.30.7 reversibility invariant is retired.**
  `test_the_irreversible_three_are_exactly_the_ones_off_by_default` has no meaning once nothing is
  off by default. It is replaced by an assertion that every capability is *named* with its
  reversibility in `CAPABILITY_NOTES` and surfaced in the narrowing documentation — the
  information survives, the enforcement point moves.
- **`csa-gw://config`'s "fail closed" diagnosis text** currently explains why an unset allowlist
  permits nothing. That path becomes unreachable for a default install and the wording must stop
  presenting it as the expected state.

## 4. Two data-handling switches, which are not capabilities

`local.read` and `local.write`. Default **on** — they are not a boundary, and off would break
every existing export workflow.

| switch | governs |
|---|---|
| `local.read` | `apply_comment_actions` reading a filled-in register from disk |
| `local.write` | `export_comments` → `.csv`/`.xlsx`, and `apply_comment_actions` writing completion markers back in place |

**They are deliberately not in `ALL_CAPABILITIES` and no profile grants or withholds them.** The
reason is the §2 argument: they cannot contain confidential data, because the data is already in
the model's context by the time either runs. Presenting them as capabilities would put them beside
`file.share` and invite an operator to believe switching them off prevents disclosure. It does not.

What they are actually for, stated as the reason to reach for them: **keeping review material
inside the MCP client rather than landing it on disk**, where it persists, is outside the client's
retention policy, and can be re-read later by anything with filesystem access. That is a data
governance concern and a real one; it is simply not the same concern as authorization.

`apply_comment_actions` needs both, and must say which one is off when it refuses.

## 5. One accepted spelling, and a refusal that teaches

Config accepts the **API** string only. Accepting both spellings would mean two ways to write
every value, two things to grep for, and a config whose meaning depends on which vocabulary the
author happened to know.

The API string wins over the UI label because it is the one that appears in `get_file_permissions`
output — so an operator reading a tool result and an operator writing a config see the same word.

The UI label is carried as **documentation** everywhere the profiles are described (README, the
`csa-gw://help/configuration` resource, `describe_configuration`), so a user who says *"give it
Content manager access"* is understood, and the model can map it without guessing.

A wrong-but-recognisable value must fail with the mapping, not a bare rejection:

    CSA_GW_PROFILE=manager
    → `manager` is Google's UI label for the `organizer` role. Use `organizer`.

Values to recognise and redirect: `viewer`→`reader`, `contributor`→`writer`,
`content manager`/`contentmanager`→`fileOrganizer`, `manager`→`organizer`, `owner`→`organizer`
(with a note that this library has no permanent delete, so `organizer` is the ceiling). Matching
is case- and space-insensitive; `editor` and `full` stay silent aliases rather than redirects,
since they are our own prior vocabulary and not a mistake.

## 6. What this API/MCP cannot do

Not a limitation list for completeness — a **capability ceiling**, and part of the security
posture. `organizer` is the top of our ladder and is still narrower than Drive's Manager.

| not available | why |
|---|---|
| accept / reject a suggestion | The Docs API has **no endpoint**, proven by full API enumeration. Reserved for a future `PlaywrightBackend`. |
| create a truly cell-anchored comment | The Sheets anchor is an opaque `workbook-range` id that cannot be constructed. `create_comment(cell=)` deep-links instead. |
| permanently delete anything | Deliberate. There is no permanent delete in the library and no capability that empties the trash. The worst an `organizer` install can do to a file is put it in the bin, where its owner can see and restore it. |
| empty the trash | Same. |
| resolve `Location.tab` for a multi-tab spreadsheet | Needs `workbook.xml` + rels parsing; tracked as a deferral. |

This goes in three places, because three different readers need it and only one of them reads the
README:

1. **`README.md`** — for somebody evaluating the tool.
2. **A new `csa-gw://help/capabilities` MCP resource** — so the *model* gets a straight answer.
   This is the one with real value: a model that knows there is no accept-suggestion endpoint stops
   inventing workarounds, and today it can only find out by failing.
3. **`THREAT_MODEL.md`** — "cannot permanently delete" is a security property, not a limitation.

## 7. Compatibility

Everything here is additive or aliased. Nothing an existing configuration says changes meaning:

- `reader` and `commenter` are unchanged.
- `editor` → alias of `writer`, **identical capability set**.
- `full` → alias of `organizer`, **identical capability set** (all ten).
- `fileOrganizer` is a genuinely new rung and grants strictly less than `full`.
- `local.read` / `local.write` default on, matching today's behaviour.
- **The defaults reversal (§3a) is a real behaviour change, not an alias.** An install that
  today refuses everything because neither allowlist is set will, after this, permit everything.
  That is the intent, and it is the one change here that an operator must be *told* rather than
  allowed to discover: the release notes lead with it, and the first run logs the effective
  policy so "everything" is never an abstraction. An existing configuration that *does* set the
  allowlists is unaffected — explicit values still win, and still narrow.
- Removing `valueInputOption` from the MCP tools is the one behaviour change: a caller that
  explicitly passed `USER_ENTERED` now gets `RAW`. That is the fix, and the parameter has been
  documented as dangerous since 0.30.1.

`CSA_GW_CAPABILITIES` is unaffected — it was always orthogonal to profiles.

## 8. Tests

- `PROFILES` matches the table in §1 exactly, keyed by API name.
- Aliases resolve to **identical** frozensets, so `full` and `organizer` cannot drift apart.
- Every UI label in §5 redirects to its API name, and the message names the replacement.
- `CAPABILITY_NOTES` covers `ALL_CAPABILITIES` (existing test, kept).
- **The `DEFAULT_DISABLED` invariant is restated.** `test_the_irreversible_three_are_exactly_the_ones_off_by_default` currently ties "reversibility NO" to `DEFAULT_DISABLED`. Under the Drive mapping the default profile is `writer`, so what must now hold is: *`DEFAULT_ENABLED` is exactly `writer`'s set, and every capability outside it is either irreversible or grants sharing.* The old assertion encoded the one-ladder model and has to change with it — that change is deliberate and is why this line exists.
- No MCP tool accepts `valueInputOption`; every Sheets write from the MCP layer sends `RAW`.
- `local.read` / `local.write` off ⇒ the respective tools refuse, naming which switch, and the
  Drive-side capabilities are unaffected.
- The §6 ceiling list is asserted against the tool registry: nothing named unavailable is exposed
  as a tool.

## 9. Deferred to 1.0.0

**Export-path confinement.** `resolve_export_path` deliberately honours a full path, with recorded
reasoning: a Claude Desktop project may only be able to write inside its own folder, and a Claude
Code user wants the register in the repo they are in. What is safe about it today is not path
validation but that every failure mode is inert — nothing is overwritten, the extension is forced,
directories are never created, and the resolved path is reported back.

The 1.0.0 addition is an **optional** confinement mode refusing paths outside `CSA_GW_EXPORT_DIR`.
Its value is per-project isolation: an MCP server can be declared per project, so a per-project
export directory keeps projects from writing into each other's working files even when they share
one Google account. Most of that already works — `CSA_GW_EXPORT_DIR` is per server definition —
so the missing piece is only the refusal. Filed rather than built here, because turning a
deliberate permission into a restriction deserves its own change.
