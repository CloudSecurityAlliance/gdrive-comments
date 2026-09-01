# Findings · audit 2026-09-01-01

Target `csa-google-workspace` @ `d33034b` (v0.38.0).
Prior audit: `2026-08-27-01` @ `95c6afa` (v0.28.0).

All line numbers are exact at `d33034b`, and are **deliberately not rewritten**
to match later commits — a citation pinned to `target_commit` is checkable, one
chased forward is not.

`origin/main` did not move while the audit ran (07:32–08:05Z). It moved
immediately afterwards: `f8acda6` (#305) landed between this record's commit and
its merge, processing two findings from the **concurrent** `2026-09-01-01` audit
of the same commit. One finding here (**F2**) was fixed by it; two more (**F3**,
**F5**) were partially addressed; the rest, including the headline **F1**, are
live on `f8acda6`. Per-finding status and line-number drift are noted inline
below, and the overlap is tabulated in [`README.md`](README.md#concurrent-audit--and-one-finding-fixed-before-this-record-merged).

---

## 1. Verification standard

Seven parallel research agents produced the raw material. **Every finding below
was then re-verified by the auditing session directly against the pinned tree**
before it was written down. Where an agent's claim did not survive that pass it
is recorded in §5 as refuted, not deleted — a refuted claim is evidence about
the codebase too.

The `confidence` values follow `SCHEMA.md`:

- `confirmed-by-read` — the auditing session read the cited lines and the claim
  follows from them. Every finding here is at least this.
- `confirmed-empirically` — additionally reproduced by execution. **Nothing this
  round.** The prior audit had one (T35, openpyxl cell typing, reproduced in an
  isolated scratch directory); this audit executed no code at all.
- `plausible` / `refuted` — see §5.

Two consequences worth stating. First, no finding here depends on running the
target, so all of them are reviewable by reading. Second, the absence of any
empirical confirmation is a real limit: F1 in particular predicts a runtime
behaviour (a `writer` successfully clearing cells) that this audit reasoned to
rather than observed. The proof is a three-line test, and it is the first thing
the remediation session should write — see F1's *Fix* note.

---

## 2. Prior audit re-verification

All 19 remediated findings from `2026-08-27-01` were re-checked against
`d33034b`. **All 19 hold. None was reverted.** Several were fixed more
thoroughly than the audit recommended; those are credited in `README.md`.

Three items, however, were *cleared against a control that v0.31.0 then
removed*. The fix is intact; the environment it was verified in changed:

| prior item | cleared because | at `d33034b` |
|---|---|---|
| T4 (share reachability) | *"doubly gated — `file.share` is `DEFAULT_DISABLED` **and** the file must be in the modify allowlist"* | Neither gate holds by default: `file.share` is in `DEFAULT_ENABLED`, modify scope is `all_files=True` |
| T20 (comment mutation) | *"`comment.edit` and `comment.delete` are both `DEFAULT_DISABLED`"* | `DEFAULT_DISABLED = frozenset()`; both are default-enabled |
| T29 (`CSA_GW_DEMO_SHARE`) | *"sharing still requires `file.share`, which is `DEFAULT_DISABLED`, so the setting is inert on a default install"* | Live on a default install |

This is the cleanest illustration of the audit's central point. Nobody broke
these fixes. The fixes were verified against a default posture, the default
posture was deliberately inverted eight days later, and no process existed to
re-open items whose clearance rested on it. See F3.

Two prior findings were **over-** or **under-**stated by the living model and
should be corrected in the register:

- **T15 is fully closed**, not `partially_mitigated`. `valueInputOption` was
  deleted from the tool surface in v0.30.13 (`8716274`); `content_write.py:34-53`
  writes `RAW` unconditionally. The living model still carries a residual
  subsection arguing the risk is reachable. It is not, by eight releases.
- **T18's evidence is falsified.** It states `oauthlib` *"is not declared at all
  and arrives transitively, so this repo pins no floor on it."* `pyproject.toml`
  declares `oauthlib>=3.2.2` with a comment naming CVE-2022-36087. There are
  five runtime dependencies, not four.

And one prior audit **error of my own**, for the record: the 2026-08-27 audit
claimed `google-auth-oauthlib` needed PKCE enabled explicitly. It defaults
`autogenerate_code_verifier=True` at 1.0.0. That finding was wrong when written.

---

## 3. Findings

### 3.1 F1 — FLAW · `clear_cells` enforces `content.write` while four artefacts and two tests say `content.delete`

**Confidence:** confirmed-by-read.
**Threats:** T20-class (irreversible content mutation), new register row T37.
**Impact:** high. **Likelihood:** likely (no attacker sophistication required;
the profile is a documented, recommended configuration).

`content.delete` was added in v0.36.0 for exactly one purpose: to separate
*writing* content from *destroying* it, so a profile could be granted the first
and refused the second. Four sheet/doc destruction tools were placed behind it.
Three were wired correctly. One was not.

```python
# src/csa_google_workspace/policy.py   (at d33034b; `f8acda6` shifts these +1, gate unchanged)
403:    "sheets_delete_tab":    Gate(CONTENT_DELETE, MODIFY),
404:    "docs_delete_tab":      Gate(CONTENT_DELETE, MODIFY),
408:    "docs_delete_range":    Gate(CONTENT_DELETE, MODIFY),
420:    "sheets_values_clear":  Gate(CONTENT_WRITE,  MODIFY),   # <-- the divergence
```

`TOOL_GATES` is the only table that gates. Four other artefacts state the
opposite, and because three of them derive from a single wrong source they agree
with each other:

| artefact | says | why it says it |
|---|---|---|
| `mcp/_capabilities.py:111` | `"clear_cells": CONTENT_DELETE` | hand-written; the origin of the error |
| `mcp/_tools/content_write.py:303` | *"Requires content.delete, not content.write"* | model-facing tool description |
| `demo/_plan.py` (`requires`) | predicts a refusal under `editor` | derived from `TOOL_CAPABILITIES` |
| `policy.py:194` (comment) | *"A writer may therefore edit … never destroy part of one"* | hand-written; false |

**Consequences, in order of severity.**

1. **A `writer` or `editor` profile can blank any range of any reachable
   sheet.** `CONTENT_WRITE` is in both profiles. Sheets `values.clear` has no
   trash and no API undo; recovery depends on Drive revision history, which is
   a different control with a different retention policy. The profile exists
   precisely to permit editing and refuse destruction, and it does not.
2. **`demonstration_plan` actively misinforms the operator.** Its whole purpose
   is to say up front what will be skipped. Because it derives `requires` from
   `TOOL_CAPABILITIES`, it reports that `clear_cells` will be refused under
   `editor`. It will not be.
3. **The model is told the same thing** by `content_write.py:303`. See F2 for
   why text in a tool description is a different class of problem from a stale
   comment.

**Two tests certify the defect rather than catching it.**

`tests/test_policy_matrix.py:50` — this test drives the *real* enforcement path
(it calls through `PolicyBackend` and catches the refusal), which is exactly
right. But its expected-value table hand-lists the tool under the wrong row:

```python
49:    "content.write": {"docs_batch_update", "sheets_values_update", "sheets_values_append",
50:                      "sheets_values_clear", "sheets_batch_update", "slides_batch_update",
```

A test that exercises the correct code path and takes its oracle from the wrong
source does not merely miss the bug — it **ratifies** it, converting an open
question into a settled one. This is worse than no test.

`tests/test_demo.py:360-370` — a shipped test asserting a security property the
code does not have:

```python
        assert {s["tool"] for s in blocked} == {
            "edit_comment", "delete_comment",
            ...
            # And every DELETE, added in v0.36.0 with `content.delete`. This row is the clearest
            # statement of why that capability exists: an `editor` writes cells, appends rows,
            # inserts text and adds tabs, and is refused all four ways of destroying content.
            "clear_cells", "delete_range", "delete_tab", "delete_document_tab"}
```

The comment states the security property in the clearest terms anywhere in the
repository, and the assertion passes — because `demonstration_plan` derives from
the same wrong table the assertion is implicitly checking. Both sides of the
comparison come from `TOOL_CAPABILITIES`, so the test is self-consistent and
tells you nothing about `TOOL_GATES`.

**A coverage hole hides it further.** `EXPECTED` in `test_policy_matrix.py` has
**no `content.delete` key at all** (`grep -c content.delete` → 0). The
parametrised one-capability-at-a-time check therefore skips the entire
capability added in v0.36.0, and the superset assertion never sees it either.

**And no test reads the enforcing table.** `grep -rln TOOL_GATES tests/` returns
nothing.

**Fix.** Two changes, in this order.

1. Decide which is correct. On the stated design intent — and on the plain
   reading of `policy.py:194` and `test_demo.py:365-370` — `clear_cells` should
   be `CONTENT_DELETE`. Change `policy.py:420`, then fix
   `test_policy_matrix.py:50` (move it to a new `content.delete` row) and
   re-run `test_demo.py` unchanged; it should still pass, now for the right
   reason.
2. Add the one guard that could not have gone stale:

```python
def test_the_reporting_table_agrees_with_the_enforcing_table():
    """TOOL_CAPABILITIES is documentation; TOOL_GATES is enforcement. Nothing compared them,
    so clear_cells said content.delete in four places and enforced content.write."""
    from csa_google_workspace.policy import TOOL_GATES
    from csa_google_workspace.mcp._capabilities import TOOL_CAPABILITIES
    # map Backend method -> MCP tool name via the existing registry, then:
    assert {t: g.capability for t, g in TOOL_GATES.items()} == expected_from(TOOL_CAPABILITIES)
```

Also add a `content.delete` row to `EXPECTED`, and consider asserting that
`set(EXPECTED) == set(ALL_CAPABILITIES)` so the next new capability cannot be
silently omitted.

---

### 3.2 F2 — FLAW · Three model-facing tool descriptions tell the model a capability is off that is on

> **FIXED in `f8acda6` (#305), after this audit's read and before this record
> merged.** Found independently and concurrently by audit `2026-09-01-01` as
> `CODX-2026-09-01-01`; all four `files.py` sites and the `policy.py` comment are
> corrected on current `main`. Retained here because a record is point-in-time,
> and the evidence of what the tree looked like at `d33034b` is what makes the
> fix reviewable. **`ISSUES.md` #1 is marked already-done.**
>
> Two independent tools ranked this the most urgent finding for the same stated
> reason. That convergence is the strongest signal either audit produced.

**Confidence:** confirmed-by-read.
**Threats:** T8 (hand-maintained description vs code), attacking asset A3.
**Impact:** high. **Likelihood:** almost_certain (it is in every session).

```
src/csa_google_workspace/mcp/_tools/files.py
149:  "All three are OFF by default and refuse unless an operator names the capability
       AND lists the file for modify"
174:  "Requires the `file.update` capability, which is off unless an operator enables it."
201:  "Requires the `file.trash` capability, which is off unless an operator enables it."
224:  "Requires the `file.share` capability, which is off unless an operator enables it,
       AND the file must be listed for modify."
```

All three capabilities are in `DEFAULT_ENABLED` (`policy.py:101`), and the modify
allowlist `:224` additionally invokes defaults to every file
(`mcp/_config.py:229-232`). `policy.py:369-374` carries the same false claim as a
source comment: *"all three are OFF by default (DEFAULT_DISABLED)."*

**Why this is a different class of problem from a stale README.** These strings
are delivered to the model as its description of its own constraints, on the one
asset the entire threat model is built around. A model that has been told
"trash is off unless an operator enables it" will reason about a trash attempt
as something the server will safely refuse — and will therefore weigh it as
low-risk when a document or comment suggests it. That is the confused-deputy
mechanism being handed a false premise about its own guardrails, in the
guardrail documentation itself.

The prior audit found this defect class in `mcp/server.py`'s INSTRUCTIONS and §8
recommended the general fix: *"the server INSTRUCTIONS string may contain no
capability claim absent from `ALL_CAPABILITIES`."* That was implemented for
INSTRUCTIONS and for annotations. It was not extended to **"off by default"
claims in tool descriptions**, which is where the claims moved.

**Fix.** Delete the default-state claims from all four sites; a tool description
should name the capability it requires and stop. If the current state is worth
telling the model, derive it — `describe_configuration` already computes it, and
a derived string cannot drift. Then extend the existing docstring guard to fail
on the regex `off (unless|by default)|OFF by default|DEFAULT_DISABLED` anywhere
under `mcp/_tools/`.

---

### 3.3 F3 — FLAW · The living threat model's control narrative and three statuses describe a posture that ended at v0.31.0

**Confidence:** confirmed-by-read.
**Impact:** medium (it is documentation) but **it is the document every other
document now delegates to**, which is why it is ranked here.

`SECURITY.md:8-19` restructured itself deliberately: *"Two documents, and the
split is deliberate. This one is the framing … `THREAT_MODEL.md` is the register
… **It changes as the code does.**"* That delegation is what makes the register's
drift consequential rather than cosmetic.

**§1's posture paragraph** (`THREAT_MODEL.md:126-135`) is presented as the
controls *"observable in the tree,"* i.e. the stated basis for every rating in
§4. Clause by clause at `d33034b`:

| claim | reality |
|---|---|
| *"defaults are chosen to be safe: an operator who configures nothing gets the narrow posture, not the convenient one"* | An operator who configures nothing gets the **widest** posture |
| *"both file allowlists fail closed when unset"* | Both permit **every file** when unset (`_config.py:229-232`) |
| *"`*` must be typed literally and logs a warning on every parse"* | Only a literally-typed `*` warns (`_config.py:243-246`); *unset* yields the same access silently — so the **more careful** operator is the one who gets warned |
| *"the three irreversible operations are disabled by default"* | Four irreversible operations (`policy.py:107` adds `CONTENT_DELETE`), all enabled |

Two clauses survive: a typo'd profile is a hard error, and there is no permanent
delete.

Also in §1: `:124` says *"Ten named capabilities with the three irreversible
operations disabled by default … four ascending profiles; separate fail-closed
read and modify file allowlists"* → 11 capabilities, none disabled, five
profiles, allowlists fail open. `:112` says *"exposing 34 tools, and it fails
closed"* → 50, fails open.

**Three statuses are invalid**, and this is not covered by the frozen-text
argument. The document's own header says *"the `status` column is current."*

- **T20 — `mitigated`.** Its sole cited control (`:233`) is
  *"`comment.edit` and `comment.delete` are both `DEFAULT_DISABLED`."*
  `policy.py:115` is `frozenset()`. **The only control cited no longer exists,
  and the threat is marked mitigated.**
- **T29 — `partially_mitigated`** on *"`file.share` is `DEFAULT_DISABLED`, so the
  setting is inert on a default install."* It is live.
- **T4 — `partially_mitigated`** on a doubly-gated claim; neither gate holds.

None of the three appears in §0's delta table.

**The project has partially catalogued this itself** (`TODO.md:361-397`, from
RR-003), naming three lines and deferring them to *"the follow-on security
audit"* — this one. That catalogue has two defects of its own:

1. **Two of its three cited lines are in §1, not §3/§4.** `:112` and `:131` sit
   in *System context* and in the posture paragraph. The freeze covers *threat
   text*; nothing declares §1 frozen. So they could have been fixed under the
   project's own rule and were not.
2. **The `status` column is not covered by the freeze at all**, and all three
   invalid statuses are absent from the catalogue.

Missing from the catalogue beyond those: §1:124, §1:133, §2:172 (A6), §3:187,
§3:190, §3:191, §3:193, §3:200, §3:202, §4:212/215/233/242, §6's `full`-profile
question, §6's T1 bullet, T15's residual subsection, and §7.

**§6 contradicts §0 inside one document.** §6's first bullet still reads
*"~~Is `ALLOWLIST_READ='*'` permanent?~~ **Answered:** a migration state. The
1.0.0 plan has operators set the value at install time"* — while §0 rescores T1
on the basis that it is permanent by design.

**§7 describes only the audit, not the living document.** There is no
`last_reviewed: <commit>/<version>` line, so a reader cannot tell that the model
has been maintained to v0.37.0 on a v0.38.0 tree. §0's own heading says
`(v0.28.0 → v0.37.0)`, one release behind.

**Fix.** Five edits, none of which is a rewrite of frozen text: move the three
statuses and add §0 rows; rewrite §1's posture paragraph (not frozen); delete
T15's residual subsection; add `last_reviewed:` to §7; move T36's row into §4
(see F11). The re-scored register in this directory's `THREAT_MODEL.md` does all
five and can be adopted wholesale instead — see `ISSUES.md` #2.

---

### 3.4 F4 — FLAW · The startup warning is silent about the one axis that changed

**Confidence:** confirmed-by-read. **Impact:** medium. **Likelihood:** almost_certain.

`mcp/_config.py:378-400` builds the startup warnings. It prints the read and
modify scopes unconditionally when they are unrestricted:

```
READ: UNRESTRICTED — every file your Google account can reach. Set … to narrow it.
MODIFY: UNRESTRICTED — every file your Google account can reach. Set … to narrow it.
```

Capabilities are announced only in two branches: `capability_source == "profile"`
(names the profile's set), or a profile that is being overridden by an explicit
list (RR-005's fix). **On a default install `capability_source == "default"`, and
neither branch fires.** Nothing is printed about the capability set at all.

So the operator starting a default server is warned about the two axes that were
*always* documented as unrestricted-by-choice, and told nothing about
`file.share`, `comment.edit`, `comment.delete`, and `content.delete` being live —
the axis that actually changed in v0.31.0, and the one carrying all four
irreversible operations.

**Fix.** Add a third branch: when `capability_source == "default"`, emit the
enabled set with the same shape as the scope warnings, naming the irreversible
members explicitly. One line, and it closes the operator-facing half of the
defaults sweep permanently — a derived string cannot go stale.

---

### 3.5 F5 — FLAW · The README's competitive security claim is false on a default install

**Confidence:** confirmed-by-read. **Impact:** medium. **Likelihood:** almost_certain.

```
README.md:263  "the difference is that each is off until an operator names it, and refuses…"
README.md:704  "each is off until an operator turns it on by name"
```

*(Both live on `f8acda6`. #305 fixed a third instance of the same claim at
`README.md:37` — annotating it "This bullet said the opposite" — and left these
two, which are the ones in the competitive-comparison passages.)*

Both appear in passages contrasting this server with the read-only claude.ai
Drive connector — i.e. they are the project's stated security advantage over an
alternative a reader might otherwise choose. Neither is true at `d33034b`.

This is ranked above the other documentation drift because of who reads it: a
prospective operator deciding whether this server is safe enough to install,
using a claim about capability defaults to make that decision.

**Fix.** Rewrite both to the true and still-favourable claim: every capability
*can* be named and narrowed, per-file allowlists exist on both axes, and a
profile or explicit list makes the posture as narrow as the operator wants —
while a default install is open and `SECURITY.md:107-109` says so. The honest
version is a better argument anyway, because it is checkable.

---

### 3.6 F6 — FLAW · A `writer` can change who has access to a file, by reparenting it

**Confidence:** confirmed-by-read.
**Threats:** T4-adjacent; new register row T38.
**Impact:** high. **Likelihood:** possible.

The capability model's organising claim is that it mirrors Drive's ladder, and
that below `Manager` nothing can change who has access. The spec states the
mechanism plainly:

```
docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md:107
    'our "move" is a rename'
```

That is false. `update_file` forwards parent mutations to the Drive API:

```python
# src/csa_google_workspace/backend.py
716:    if add_parent:    kw["addParents"] = add_parent
719:    if remove_parent: kw["removeParents"] = remove_parent
```

gated as:

```python
policy.py:375       "update_file_metadata": Gate(FILE_UPDATE, MODIFY)
policy.py:184-185   "writer": frozenset({… FILE_UPDATE …})
```

Moving a file into or out of a folder changes which folder ACL it inherits. On a
Shared Drive, moving a file into a folder with broader membership grants every
member of that folder access to it; moving it out of a restricted folder removes
access from the people who had it only by inheritance. Neither requires
`file.share`, and neither is visible as a permission change on the file.

**This is the only path below `Manager` that changes who has access**, which
makes it the one counterexample to the design's central claim — and to the
Drive-mirroring argument that replaced the prior audit's rejected §5 proposal.
It is worth saying that the replacement design was the better one; this finding
exists *because* that design made a falsifiable claim, which is what good design
documents do.

**Fix.** Two options, and the choice is the maintainer's:

- **Gate parent mutation separately.** Split `addParents`/`removeParents` out of
  `file.update` into `file.share` (they are a sharing operation in effect), or
  into a new narrow capability. This preserves the ladder claim.
- **Withdraw the claim.** Correct `spec:107` and the ladder documentation to say
  that `writer` can relocate a file and therefore can alter inherited access,
  and let Drive's own folder ACLs be the control.

Either is defensible. Leaving `spec:107` as written is not, because the rest of
the model is reasoned from it.

---

### 3.7 F7 — FLAW · Exception messages carry the content that `__repr__` redaction was built to withhold

**Confidence:** confirmed-by-read. **Impact:** medium. **Likelihood:** possible.

The prior audit verified that redacting `__repr__`s exist and omit message
bodies and cell values, and `mcp/_logging.py:32-37` states the governing rule:
log detail is about *the operation, never the content*. `_base.py:39-47` honours
it — tool name, file id, outcome.

The bypass is not `__repr__`. It is exception text:

```
src/csa_google_workspace/sheet.py:89,127,218   — messages embedding the full tab-title list
src/csa_google_workspace/_base.py:84           — logs at ERROR
```

Three compounding facts:

1. **ERROR ≥ the default threshold.** The default level is WARNING, so these are
   emitted on a default install, not only in debug.
2. **The destination is outside the server's control.** `mcp/_logging.py:1-21`
   documents that Claude Code captures stderr verbatim into
   `~/Library/Caches/claude-cli-nodejs/<project>/mcp-logs-<server>/*.jsonl`, and
   Desktop logs the whole JSON-RPC exchange. The server cannot see, rotate, or
   purge either.
3. **`ConflictError` is not in the translated ladder**, so its raw text — the
   least controlled of the three — is what reaches the log.

Tab titles are document content and frequently meaningful (client names,
project codenames, `Q3 layoffs`). This is a narrow confidentiality leak into a
persistent, uncontrolled location, and it defeats a control the repository built
deliberately and documented well.

**Why the test did not catch it.** `tests/test_logging_level.py` asserts the
no-content property against `FakeBackend`, which cannot produce the failing
values — the tab-title list comes from a real API response shape. The test is
correct and passes and covers nothing.

**Fix.** Bound the message at the raise site: replace embedded title lists with
a count plus at most one example, or use the existing `one_line()` plus a length
cap. Add `ConflictError` to the translated ladder. Then re-point
`test_logging_level.py` at a fixture that actually carries titles — the test's
shape is right, its input is inert.

---

### 3.8 F8 — FLAW · `request_message` reaches the model with none of the three defences ordinary comment bodies get

**Confidence:** confirmed-by-read.
**Threats:** T36 (already in the living model, and correctly reasoned there).
**Impact:** high. **Likelihood:** possible.

`access_proposals.py:37-45` carries `requester_email` (Google-vouched) and
`request_message` — **free text written by someone who has no access to the
file, delivered to a model that is deciding whether to grant them some.** That
is the highest-leverage injection position in the whole surface: the payload and
the desired outcome are the same request.

The feature shipped with real mitigations, which deserve credit: `owner` is
refused (`:155`), `accept()` defaults to `reader` rather than the requested role
(`:145-148`), deny is gated as `file.share` too (`policy.py:389-397`), and
`__repr__` omits both fields (`:113-120`).

The gap is the fence. `_inline.py` gives ordinary comment bodies three defences —
`one_line()` collapsing all 11 break characters (`:43-61`), an untrusted-content
fence, and a length cap. `request_message` gets **none of the three** on the way
to the model.

So the one field authored by an unauthenticated third party is the one field
rendered rawest. A message containing newlines and fence-shaped text can
therefore restructure the surrounding prompt in a way a comment body cannot.

**Fix.** Route `request_message` through the same path as comment bodies:
`one_line()`, the untrusted-content fence, and a cap. This is a small change and
it uses machinery that already exists and is already tested. The reason to rank
it high anyway is position, not size.

---

### 3.9 F9 — FLAW · A local-path existence oracle inside the control added to remove local exposure

**Confidence:** confirmed-by-read. **Impact:** low. **Likelihood:** possible.

```python
# src/csa_google_workspace/mcp/_tools/comments.py
353:        source = Path(path).expanduser()
354:        if not source.is_file():
355:            raise ValueError(f"{source} is not a file. Pass the .csv or .xlsx that …")
356:        if not local_read:
357:            raise ValueError("reading a register from this machine is switched off …")
```

The order is wrong. With `CSA_GW_LOCAL_READ` switched **off**, the two branches
still return distinguishable errors, so a model steered by injected content can
probe the operator's filesystem one path at a time:

- path exists as a file → *"reading a register … is switched off"*
- path does not exist → *"… is not a file"*

`expanduser()` means `~/...` works, so `~/.ssh/id_rsa`, `~/.aws/credentials`, and
`~/.csa_google_workspace/token.json` are all probeable for existence. No content
is disclosed and the oracle is one bit per call, which is why this is ranked
low — but it exists specifically inside the switch whose stated purpose is to
remove local exposure, and it is switched off when the leak happens.

**Fix.** Swap lines 354-355 with 356-357. Check the switch first; a refusal
that precedes any filesystem access cannot be an oracle. One-line change,
and worth a test asserting the refusal message is identical for an existing and
a non-existing path when the switch is off.

---

### 3.10 The guards that cannot fail

Grouped because they share one cause and one fix pattern. Each was written to
prevent exactly the drift that then occurred.

**F10 — `check_doc_claims.py` never reads `THREAT_MODEL.md`.** *(Live on
`f8acda6`; #305 edited this file, so the lines shift 58/60/214 → 65/67/293. The
defect is unchanged.)*
The surveyor built to *"enumerate reality and compare against it"* excludes its
most important subject. `THREAT_MODEL.md` is absent from `DOCS` (`:52-55`) and
from `DOC_GLOBS` (`:56`), so `FROZEN_COUNTS = {"THREAT_MODEL.md"}` (`:60`),
consulted at `:214`, is **dead code** — the file never enters the loop it would
filter. The explanatory comment at `:58` — *"excluded from the COUNT checks but
not the name checks"* — is false in both halves. The script's own docstring
(`:26-33`) records this exact failure class: *"Two guards in this repo passed
while the thing they guarded rotted … they looked for a string somewhere in a
file, or iterated a collection that had become empty."*
**Fix:** add `THREAT_MODEL.md` to `DOCS`, keep it in `FROZEN_COUNTS` so the
frozen-text exemption becomes real rather than vacuous, and correct `:58`.

**F11 — `test_threat_model.py`'s "§4 only" filter is a shape filter.**
Its docstring claims it reads *"the §4 threat table only"* and explains it skips
§0 *"by requiring the ten-column shape."* Column count is not section
membership. T36's row is 12 fields at **line 47, inside §0** (§0 begins at 15;
§4 begins at 206), so it is parsed as a §4 threat. The test sees 36 rows, of
which exactly one — T36 — is above §4. This is also why `SECURITY.md:12`'s
*"36 enumerated threats"* agrees with the test: **both count a row from the
delta table**, while §4 itself holds 35.
**Fix:** bound the parse to the span between the `## 4.` and `## 5.` headings,
then move T36's row into §4 where it belongs. The count claim becomes true
automatically.

**F12 — the weekly controls drift detector cannot fail.**
```yaml
.github/workflows/controls.yml:49   python scripts/check_controls.py | tee controls.txt
```
No `set -o pipefail`, so the step's exit status is `tee`'s, which is always 0.
The scheduled job that exists to notice externally-enforced controls drifting
away reports success unconditionally. `release.yml:48` runs the same script
unpiped and does propagate, so a release would still catch it — the *weekly*
detector is the one that is dead, which is the one whose whole point is to catch
drift between releases.
**Fix:** `set -o pipefail` in the step, or drop the pipe and `tee` from a
separate read of the file. Then break the script deliberately once and confirm
the job goes red.

**F13 — nothing reads the enforcing table.** See F1. `grep -rln TOOL_GATES
tests/` is empty; `test_policy_matrix.py`'s oracle is the reporting table;
`EXPECTED` has no `content.delete` row.

**F14 — `TOUCHES_STORAGE` hand-lists 16 of 50 tools.**
`tests/test_annotations_and_claims.py:43-50`. Absent: `clear_cells`,
`delete_range`, `delete_tab`, `delete_document_tab`, `resolve_access_proposal`,
`add_tab`, `add_document_tab`, `insert_text`, `unshare_file`,
`update_file_permission`. Its anti-staleness guard fires on a name that no
longer exists and never on a mutating tool that was never added — so every tool
in that list could be re-annotated `read_only_hint=True` and the suite stays
green. That is precisely the defect class issue #184 was filed about.
**Fix:** derive the set. A tool reaching a `MODIFY`-gated `Backend` method
touches storage by definition; `TOOL_GATES` already knows. Replace the literal
with a comprehension and the guard cannot fall behind again.

**F15 — three guards from the prior remediation went dark.**
Removing the defect emptied the guard's input, so the guard now asserts nothing:
- `test_every_capability_named_in_the_instructions_exists` — `server.py` no
  longer contains dotted capability tokens, so the input set is empty and the
  assertion is vacuous.
- `test_no_capability_miscounts` — 0 regex matches across all three target docs.
- Two tests in `test_config_text_agrees_with_policy.py` skip when
  `not DEFAULT_DISABLED`, which is now permanently true — **permanently skipped**.

The author named this exact failure mode in `check_doc_claims.py:26-33` and
defended against it there. It happened in three other places.
**Fix:** assert non-emptiness before asserting the property —
`assert tokens, "guard found nothing to check; it has gone stale"`. For the
skipped pair, invert them: assert the *current* invariant (that every capability
in `DEFAULT_ENABLED` is documented as enabled) rather than skipping when the old
one is unreachable.

**F16 — `test_docs_do_not_drift.py` is phrase-specific.**
`:479-491` matches three literals — `"unset means nothing is permitted"`,
`"both allowlists fail closed"`, `"both fail closed"` — across exactly three
files (README, SECURITY, TODO). Every surviving drift site uses different
wording (`"off unless an operator enables it"`, `"OFF by default"`,
`"fails closed when nothing is configured"`) in a file not on the list
(`policy.py`, `files.py`, `THREAT_MODEL.md`).
**Fix:** widen to a regex over `src/**/*.py` plus the docs set, and assert the
match count is zero rather than that three specific strings are absent.

**F17 — the coverage table's unit is the file path, not the content.**
Roughly 3,400 of the 4,061 new `src/` lines sit inside files marked "fully
covered," because coverage was recorded per file at a point when those files
were smaller. A file does not stop being listed when it triples in size.
**Fix:** record coverage against line counts or against the module's public
surface, and re-derive rather than hand-maintain.

**F21 — `test_all_writes_are_non_idempotent` covers 15 of 26 writes**, omitting
`create_permission` — the sharing write, i.e. the one whose repetition matters
most. Same hand-list cause, same derivation fix.

---

### 3.11 Latent gaps and hardening

**F18 — the release-workflow guard never reads the workflow-level
`permissions:` block.** *(This is the narrowed, surviving form of a claim that
was refuted in its original form — see §5.)*
`release.yml` is correct today: `:27-28` sets `contents: read` at workflow level,
`:121-122` puts `id-token: write` on `publish` alone, and `:33` documents the
build job's deliberate absence. The guard checks per-job permissions
(`test_release_workflow_shape.py:60`, `:67`) and never the top-level block. A
future edit adding `id-token: write` at workflow scope would grant it to
`build` — the job that runs `pip install` and the test suite — with both
assertions still green.
**Fix:** assert `"id-token" not in workflow.get("permissions", {})` as well.

**F19 — the MCP conformance test is asymmetric**, checking protocol →
implementation but not the reverse, so an implementation-side addition with no
protocol counterpart passes. Currently latent: no divergence exists at
`d33034b`. Same shape as a finding in the sibling `csa-skilljar` audit, which
suggests a shared habit worth fixing in both.

**F20 — `has_write_scope` has no test and recognises only this project's four
write scopes.** `auth.py:54`, used at `:130` to decide whether a granted token
exceeds read-only. `grep -rln has_write_scope tests/` is empty. A token carrying
`drive.file` — a write scope this project does not request — passes the
read-only check.
**Fix:** invert the logic. Test that the granted set is a subset of the
read-only set, rather than that it excludes four known write scopes; an
allowlist cannot be outflanked by an unlisted scope. Add the test.

**F22 — `openWorldHint` is set nowhere.** Zero hits in `src/`. `_base.py:24-26`
declares three annotation fields and not this one, on a server whose **entire
read surface returns third-party content**. It is the annotation whose meaning
is "scrutinise this output for untrusted content," and §8 of the prior model
recommended it.
**Fix:** set `openWorldHint=True` on every tool returning Drive-sourced content.
It costs nothing and it is the one annotation that speaks directly to this
server's primary risk.

---

### 3.12 Housekeeping

**F23 — `REMEDIATION.md` is stale.** Still `status: in-progress`, versions
`0.30.0…0.30.4`, no entries for #190–#194. It is the document a reader uses to
check whether an audit's findings were addressed, so staleness here reads as
"unfinished" for work that is done.

**F24 — count drift.**
- *"ten capabilities"* → 11 since v0.36.0: `CLAUDE.md:82`,
  `docs/DECISIONS.md:34`, and three sites in
  `docs/superpowers/specs/2026-08-28-capability-model-mirrors-drive.md`
  (`:64`, `:201`, `:214`).
- `INTERFACE-RESOURCES.md:104` says *"current release v0.36.1"* while `:3` and
  `:33` in the same file say v0.38.0.
- `docs/superpowers/specs/2026-08-27-multi-account…:42,369` still says *"34
  tools"* and *"31 of today's 34"*, in a spec claiming re-verification on
  2026-08-31.
- `mcp/_flavours.py:9,139` says *"a model shown 36 tools"* / *"8 published, 28
  hidden"* → 50 / 42. Illustrative, but in the module that implements the count.

`CLAUDE.md` is otherwise **broadly current** and should be credited: it names
`access_proposals.py`, `labels.py`, `preview_allowlist`, 50 tools, and the
v0.31.0 defaults reversal as invariant #7. Two gaps: the capability miscount at
`:82`, and `mcp/_flavours.py`, `mcp/_logging.py`, and `mcp/_capabilities.py` are
absent from the module inventory despite being three of the four new modules.

**F25 — three Drive-shaped id constants are hardcoded across 18 test files.**
Reported by shape and location only; the values are not reproduced here.

| shape | spread |
|---|---|
| 44 chars, `1`-prefixed, mixed case + digits (Drive **file** id shape) | 15 test files |
| 44 chars, same shape | 7 test files |
| 33 chars, `1`-prefixed (Drive **folder** id shape) | `tests/test_allowlist.py` |

None carries a placeholder marker (`test`, `fake`, `example`, repeated
characters), and all three match Google's id grammar exactly, which is what
distinguishes them from ordinary fixtures.

**A Drive id is not a credential** — the file remains ACL-gated, so this is not
an access disclosure. What it would disclose, if these are real ids from the
maintainer's Drive, is the *existence* of specific documents, plus a precise
target for a directed access request in a public repository. The 15-file spread
also means any replacement is a mechanical sweep rather than a one-line fix.

**Action:** determine whether they are real. If they are, replace with
obviously-synthetic ids of the same shape (a `1` prefix plus a fixed
`AAAA…`-style body keeps any format validation passing) and note it in the
commit without restating the values. If they are already synthetic, add a
comment saying so at the definition site — the finding then costs one line and
never recurs.

---

## 4. The structural finding

Three audits of two repositories have now produced the same shape: **a
hand-maintained description of a policy drifting from the policy.** This audit
sharpens it into something more useful, because the sharper form explains why
the drift survived a repository that had already built anti-drift machinery.

> **Derivation protects against incompleteness, not against incorrectness.**

`demo/_plan.py:496-514` is the clearest statement of the right instinct anywhere
in the tree:

> *"Derived rather than hand-annotated because 22 of the 36 steps are gated and
> a table somebody has to remember is a table that goes stale.
> `TOOL_CAPABILITIES` is already the single source of truth —
> `tests/test_mcp_capabilities.py` fails if a tool is missing from it — so
> reading it here means a new gated tool arrives correctly annotated for free."*

Every step of that reasoning is correct except the premise. What
`test_mcp_capabilities.py` actually proves is: every registered tool has a row
(`:32`), no row names a dead tool (`:39`), and every capability named is a real
enum member (`:45`). Those are **completeness and well-formedness** properties.
Nothing in the repository compares `TOOL_CAPABILITIES` to `TOOL_GATES`.

So "single source of truth" names a table that no test ties to the enforcement
it claims to describe — and because three artefacts derive from it, the wrong
value **propagates consistently** rather than surfacing as a contradiction. Four
artefacts agree with each other; all four disagree with the enforcer; and the
agreement is what made it look verified.

The corollary is the practical guidance:

1. **Derive from the thing that enforces**, not from the thing that describes.
   `TOOL_GATES` is load-bearing; `TOOL_CAPABILITIES` is a projection of it and
   should be computed, not maintained.
2. **A guard must assert its input is non-empty.** Four of this audit's findings
   (F10, F12, F15) are guards that pass because they check nothing.
3. **A test's oracle must not share a source with its subject.** F1's two tests
   both compare the wrong table to itself.
4. **Prefer removal to configuration.** The two strongest fixes in this
   codebase — deleting `valueInputOption`, and never requesting the label write
   scope — removed the possibility rather than gating it. Neither can drift,
   because there is nothing left to describe.

---

## 5. Refuted and adjusted

Recorded rather than dropped, because a refuted claim is evidence too — and
because the next audit should not spend the same effort.

**REFUTED — the release workflow does not leak `id-token: write` to the build
job.** An agent reported that workflow-level `id-token: write` inherits to every
job while both shape tests still pass. `release.yml:27-28` sets
`permissions: contents: read` at workflow level and nothing else; `:121-122`
scopes `id-token: write` to `publish`; `:33` documents the build job's
deliberate absence. **The workflow is correct today.** What survives is the
narrower guard gap recorded as F18: the test never reads the top-level block, so
the correctness is not protected.

**ADJUSTED — the unset-vs-`*` warning asymmetry is deliberate, not a bug.**
`_config.py:228-235` reasons about it explicitly: an unset variable is an
operator who has not narrowed anything, a malformed one is an operator who tried
and failed, and silently widening the latter would hand them the opposite of
what they wrote. That reasoning is sound. The finding that survives is not the
asymmetry but F4: the *startup* warning covers both scopes and is silent about
capabilities, which is a gap in what the operator is told rather than in how the
value is parsed.

**ADJUSTED — `THREAT_MODEL.md` is not a neglected document.** The brief
anticipated one. It has a maintained §0 delta table, a test that makes the delta
load-bearing, and a §7 provenance block. The drift in F3 is real and it is
concentrated in exactly the places the project's own freeze rule left ambiguous
(§1's posture paragraph and the `status` column) — which is a different and more
interesting failure than neglect.

**NOT RE-TESTED — the stdio wire boundary.** The prior audit's most instructive
miss was that it never crossed the stdio boundary, and `serverInfo.version`
shipped empty from day one through a well-formed response (found later as
RR-002). This audit also did not probe the wire; the scope excluded executing
the server. That blind spot is therefore **unverified, not cleared** — the fix
landed, but this audit did not re-confirm it end to end. A wire-level probe is
the single highest-value addition to the next audit's scope, and it is cheap.
