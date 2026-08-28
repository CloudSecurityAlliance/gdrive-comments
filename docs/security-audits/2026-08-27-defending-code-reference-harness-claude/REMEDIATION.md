---
audit_id: 2026-08-27-01
remediation_started: 2026-08-27T19:20Z
remediation_status: in-progress
fixed_in_version: 0.30.0, 0.30.1, 0.30.2, 0.30.3, 0.30.4
---

# Remediation — audit 2026-08-27-01

The fix trail, kept separate from the flaw trail by design: this file carries the reasoning that
produced each fix, written after the audit and in a different session, so neither can quietly
reshape the other.

One entry per finding, in the order fixed. A finding is only recorded here once its fix has
landed on `main`.

---

## T15 / #181 — `update_cells` and `append_rows` defaulted to `USER_ENTERED`

**Status:** fixed · **Landed:** `fix/raw-is-the-default-at-the-boundary` → 0.30.0
**Rated:** the audit's only exploitable flaw

### What was verified before fixing

Both halves of the finding were reproduced rather than taken on trust:

- `mcp/_tools/content_write.py:63` and `:83` defaulted to `USER_ENTERED`, against **eight**
  library declarations all defaulting to `RAW` — `Backend` (`:54,56`), `FakeBackend`
  (`:370,375`), `ApiBackend` (`:639,645`), `Sheet` (`:116,121`). Confirmed by reading all ten.
- The reachability claim holds in the **deployed** configuration, which was checked rather than
  assumed. `claude mcp get csa-google-workspace` on the maintainer's machine reports
  `CSA_GW_ALLOWLIST_READ=*`, `CSA_GW_ALLOWLIST_MODIFY=*`,
  `CSA_GW_CAPABILITIES=default,file.update,file.trash,file.share`, and **no per-tool
  enablement** — so the second of the two facts the audit said would gate its ratings resolves
  in the worse direction: configuration removed nothing.

### The fix

Both defaults changed to `RAW`. `USER_ENTERED` remains available as an explicit argument,
because the feature is legitimate — only the default was wrong. A fix that removed the ability
to write a real formula would have been a different regression, and there is a test asserting
it still works.

The docstrings were rewritten. The old one taught the unsafe value as the norm
(*"`USER_ENTERED` (the default …)"*), which mattered more than the signature: for an MCP tool the
description is the only interface documentation a model gets. The new text states the default,
and states plainly that `USER_ENTERED` must not be passed for anything derived from document or
comment content, with the server-side-evaluation reason given rather than implied.

### One correction to the finding

The issue says `_export.py:200`'s premise — *"NOT applied to `to_grid`: a Sheets write uses
RAW"* — is **"true of the library, false at the MCP boundary."**

Traced during remediation: `destination="sheet"` calls `sheet.update("A1", to_grid(...))`, the
**library** method, passing no `value_input_option`, so it inherited `RAW`. **`to_grid` was
already safe.** A test written before the fix confirmed this by passing.

So the premise was not false. It was a **global claim that was only locally true** — it held for
the one call path `to_grid` happens to use, and nothing tied it to the eight declarations it
depended on. That is a materially different defect from the one described: not an incorrect
statement, but load-bearing prose with no enforcement.

The comment now says which path it means, notes that `#181` made the claim true everywhere, and
points at the tests that hold it. It also records why the escape sets **must stay different per
format** — Excel-on-CSV acts on `= + - @`, openpyxl infers a formula from `=` alone, and a `RAW`
Sheets write needs no escaping — so nobody later unifies them into one helper that is wrong in
two directions.

### An existing test asserted the vulnerable behaviour

`tests/test_mcp_write_tools.py::test_update_cells_defaults_to_user_entered_so_formulas_work`
encoded the unsafe default as intent. Rewritten in place rather than deleted: its legitimate
half — *a formula is writable* — is kept and now asserted through the explicit argument, and the
docstring records what changed and why. Deleting it would have removed the only assertion in the
write-tools suite that formulas work at all.

### Tests

`tests/test_raw_is_the_default.py`, 21 assertions, **10 failing before the fix**:

- the option the backend was **called with**, for `update_cells` and `append_rows` — behavioural,
  not a signature check
- seven payload shapes including `IMPORTXML`, `IMPORTRANGE` and `IMAGE`, plus `+ - @`, asserting
  the guard is **unconditional**: a default that inspected the value for `=` would miss the
  shapes each downstream reader treats differently
- `USER_ENTERED` still honoured when passed explicitly, on both tools
- all **eight** library declarations still default to `RAW`, by reflection — a single drifted
  default reopens this, since a tool passing no option inherits whatever the layer beneath chose
- the `to_grid` premise, enforced rather than asserted

### What this does not fix

The seam. The audit's sharpest observation is that this and T35 are the **fourth and fifth**
instances of *"a capability the library had and the server did not"*, and that fixing instances
without the seam invites a sixth. That is #195, which blocks nothing and is not attempted here.

Worth recording alongside it: the same shape was independently hit during ordinary development
on 2026-08-27 and written into `CLAUDE.md` as invariant #10 — *a guard at one layer does not
protect the layers above or below it* — after #161/#162, where a three-state type was undermined
once beneath it and once above it. T15 is the same structure with a security consequence: the
library chose `RAW` in eight places, the MCP layer above overrode it, and a comment in a third
file documented the library's choice as though it were the system's.

### Not decided here

Whether T15 warrants disclosure beyond a release note. The audit records the precedent without
applying it: 0.24.0 was yanked for the CSV variant of the same class, which required a human to
open a file and click through a warning, where this required neither. That decision is the
maintainer's and is not taken in this file.

---

## T35 / #182 — the `.xlsx` export wrote untrusted content as a live formula

**Status:** fixed · **Landed:** 0.30.1

### Mechanism, chosen empirically as the issue asked

The finding said to verify the mechanism against openpyxl 3.1.5 rather than trusting
documentation, *"because the behaviour here is inference, not configuration."* Probed:

| approach | result |
|---|---|
| plain assignment (today) | `data_type='f'` — a formula |
| assign, then `cell.data_type = 's'` | `data_type='s'`, value intact |
| `set_explicit_value(v, 's')` | **`AttributeError`** — does not exist in 3.1.5 |

And verified one level deeper, at the XLSX XML, because *"openpyxl reads it back as a string"* is
a different claim from *"Excel treats it as text"*:

    before   <c r="A2"><f>IMPORTXML(...)</f><v /></c>
    after    <c r="A2" t="inlineStr"><is><t>=IMPORTXML(...)</t></is></c>

The first is a formula element, with the `=` stripped because XLSX formulas do not carry it. The
second is an inline string with the `=` inside `<t>`.

### Why not an apostrophe

The CSV sibling prefixes `'`. Here that would be gratuitous: forcing the type already works and
leaves the value **byte-identical**, and a register that mangles what a reviewer wrote is wrong
about the record it exists to be. Asserted by a test.

The escape sets stay **per-format**, and a test asserts `+ - @` are left alone in `.xlsx`: openpyxl
infers from `=` alone, Excel reading a *CSV* also acts on the other three, a `RAW` Sheets write
needs none. One shared helper would under-escape the CSV or mangle the other two.

### The docstring read as an assurance

`to_xlsx` said *"No formulas, deliberately"* — which was about the register having no computed
columns of its own, and about cached values being blank for thumbnail previewers. It never
contemplated untrusted content being *inferred* as a formula, and as written it read as a promise
the path was formula-free. Rewritten to give both reasons and to point at the enforcement.

---

## T34 / #183 — attribution inside the untrusted-content fence was forgeable

**Status:** fixed · **Landed:** 0.30.1

Bodies were interpolated raw into a layout where a line is `    author: content`, so a newline
plus `    Someone Trusted: approved` was byte-identical to a real reply from that person. The
display name had the same hole, since the commenter controls it.

`one_line()` now collapses every character `str.splitlines()` treats as a break — `\r` alone and
the Unicode separators included — into a visible `⏎`. **Not dropped and not joined:** a model has
to report on this text, so "first line" and "second line" must not become "first linesecond
line". The quoted-text anchor description gets the same treatment, being document text.

The author field additionally has `:` neutralised to `∶` and is capped at 80 characters. Both are
structural rather than cosmetic: a colon in the author field fakes the delimiter, and an unbounded
name pushes the content off the end of whatever renders the line — the same forgery by other
routes.

**The no-footer property is preserved and now asserted.** Everything after `HEADER` is untrusted
to end-of-string, which is stronger than a paired delimiter an attacker can close early. The issue
asked for this explicitly and a test now enforces it.

### Where the achievable line is, having asserted the impossible twice

Two versions of one test asserted something unattainable, and the corrections are worth recording
because the distinction is the finding's real boundary:

1. *"the forged name must not appear in the block"* — wrong. A comment may legitimately mention
   any name; nothing can or should stop somebody writing "Kurt said X" in a comment.
2. *"the author field must not contain the forged name"* — also wrong. If somebody's Google
   display name genuinely is `Trusted Person: approved`, reporting it is **correct**. That is a
   display-name problem at Google, not here.

What is achievable, and is what the tests now assert: the line **cannot be split**, and the author
field **cannot contain a `: ` delimiter**. Together those make the content unambiguously
attributable to exactly one field, however that field reads.

An earlier version of the same test also passed while the forgery worked — counting attributed
lines missed it, because splitting the real author line leaves the first half unmatched and the
total stays at one.

---

## T7 / #184 — `export_comments` was annotated read-only, and the server invented a control

**Status:** fixed · **Landed:** 0.30.1

`READ` is `read_only_hint=True, destructive_hint=False, idempotent_hint=True`. All three were
false: the tool writes a file to a model-chosen absolute path, creates Drive files on
`destination="sheet"`, and appends `-TIMESTAMP` rather than overwriting, so a retry makes a second
file. Now `WRITE`.

The annotation is not cosmetic — the MCP spec maps `readOnlyHint` to *"skip the confirmation
dialog"* for a trusted server, which a locally-installed stdio server is.

And `INSTRUCTIONS` claimed `destination="file"` works *"only if the operator enabled it"*. No such
enablement exists. **An imaginary control is worse than an absent one**, because it stops both a
model and an operator looking for the real gap. Replaced with where the file actually goes.

Adding an `export.file` capability is explicitly **not** this fix — it is #195's territory, and
the annotation was wrong independently of whether a gate ever exists.

### Guarded structurally, because both were claims that drifted from behaviour

`tests/test_annotations_and_claims.py`: nothing touching storage may be annotated read-only or
idempotent, and every capability named in `INSTRUCTIONS` must exist. **Verified to fail against
the pre-fix tree** — four of its seven assertions do — so they are guards and not decoration.

Two counterweights in the same file, because a guard that can be satisfied by over-broadening is
not a guard: a genuinely read-only tool must still be annotated read-only, and the
storage-touching list must still name tools that exist, or a rename silently empties it.

### A pattern worth naming across all three fixes in this batch

**Two more existing tests asserted the vulnerable behaviour** — one required `export_comments` to
be read-only, and 0.30.0's required `USER_ENTERED` as the default. Both were rewritten rather than
deleted, keeping the legitimate half of each. Three of the four findings fixed so far had a test
defending them, which is the concrete reason a green suite proved nothing here.

---

## T9 / #185 — `read_only=True` was satisfied by a cached read-write token

**Status:** fixed · **Landed:** 0.30.2 · the audit's load-bearing item

`CSA_GW_READ_ONLY=1` installed an empty `Policy` over a full-write credential. Any path reaching
the credential without passing the `Policy` gates had full write, and both prior audits name a
read-only posture as the primary bound on prompt injection — so the top risk's main mitigation
could fail open.

### Two changes, because either alone is a half-measure

**A separate cache**, `token.readonly.json`, derived from `CSA_GW_TOKEN` rather than configured
separately: an operator asked for two paths will set one, and the forgotten one is the posture
that silently falls back. Idempotent, so configuring the derived path is harmless.

**Write scopes refused outright** in a read-only posture. File separation alone is a *filename*
guarantee — a token copied across, or a broad grant at the consent screen, reopens the hole.

### What was deliberately not changed

`needs_reconsent` says a granted write scope satisfies a required read scope. **That is true of
OAuth**, `tests/test_auth.py` is right to assert it, and changing it would have made a true thing
false. The defect was never the predicate; it was the *policy* of accepting its answer for a
posture whose entire purpose is a narrower credential. The fix is a layer above it, and a test
asserts both: the predicate still says yes, the posture still says no.

The old comment cited **headless refresh** as the reason for sharing one cache. That reason
survives the separation — each file refreshes on its own, with no browser — so nothing was traded
away for this.

### A gap the fix nearly introduced

`mcp/_tools/auth.py` wrote tokens to `settings.token_path` directly. With the separation in place
and nothing else changed, `authenticate` would have written a valid read-only token to
`token.json` while the server read `token.readonly.json`, leaving `CSA_GW_READ_ONLY=1`
**permanently unsatisfiable with no error explaining why** — a worse failure than the one being
fixed, because it looks like the feature is broken rather than insecure.

Found by reading the call sites, not by a test. So there is now a test asserting that no write
site uses the raw configured path, and a round-trip test that writes where the writer writes and
reads where the reader reads.

Also fixed in the same pass: every message naming the token cache (`_login.py`, the
`authenticate` tool) now shows the file actually in use, or a read-only operator would be told to
look in the wrong place.

### Usability, because a security fix nobody adopts is not one

Consenting read-only leaves an existing read-write token untouched, and the error message says so
explicitly. A fix that appeared to destroy somebody's working login would simply be reverted by
whoever hit it.

### The fourth test found defending a flaw

`test_cached_read_write_token_satisfies_read_only_request` asserted the vulnerable behaviour
outright, with `#13`'s rule cited as justification. Rewritten, with a counterweight asserting a
read-write request still uses the unsuffixed cache.

**Four of the five findings fixed so far had a test holding their behaviour in place** — #181
(`USER_ENTERED` as default), #184 (`export_comments` read-only), #185 (this one), and 0.29.0's
#161/#162 pair before the audit began. That is the clearest available answer to why a green suite
of over a thousand tests said nothing about any of it, and it is worth carrying into the next
audit: **ask what the suite asserts about the behaviour you suspect, before trusting that it
passes.**

---

## T17 / #187 — `setuptools` floor, and the dependency pass around it

**Status:** fixed · **Landed:** 0.30.3

`setuptools>=83` for CVE-2026-59890. Build-time only, so no consumer cost, and it removes the need
to rely on the release job's sdist grep — which the finding correctly called a *partial
compensating control* rather than a fix. Verified 83 and 84 both declare `requires-python >=3.10`,
matching ours.

**Also declared `oauthlib>=3.2.2`**, from #188's observation: it arrives transitively
(`google-auth-oauthlib` → `requests-oauthlib`) and this project named no floor, so CVE-2022-36087
was unbounded here. It parses redirect URIs on the token-acquisition path. **A transitive
dependency you name no floor on is one you cannot bound.**

**Dev floors raised** (`pytest`, `pytest-cov`, `ruff`, `mypy`). No consumer cost, and for the two
that gate CI it is not tidiness: they give materially different answers across majors, so a
contributor was seeing a different verdict from the one that would block their PR.

### What was deliberately not raised, and why it is written into `pyproject.toml`

The runtime ranges stay lower-bound-only. Raising one excludes somebody on a perfectly good older
release for no benefit; GA-#28 settled that in July and #188 says explicitly to leave the
published ranges permissive. The reasoning is now a comment beside them, so the next reader finds
a decision rather than an apparent oversight — the same failure mode as `_export.py`'s premise in
#181, where correct reasoning sat in a comment with nothing tying it to the code it depended on.

### A second correction to the audit, verified

T28 (#191) states the `google-auth-oauthlib>=1.0` floor *"admits releases where the [PKCE] default
is off."* Downloaded the sdists: **1.0.0 already defaults `autogenerate_code_verifier=True`**, as
do 1.2.0 and 1.4.1. The floor does not admit a PKCE-off release, so raising it was not done.

The substantive half of T28 stands — PKCE is *inherited rather than requested*, and no test covers
it — and is fixed by passing it explicitly, which constrains what the code **does** rather than
what may be **installed**. Recorded on the issue.

---

## T3 / #186 — the publish credential was held while third-party code ran

**Status:** fixed · **Landed:** 0.30.4

One job held `id-token: write` while `pip install` (lower-bound-only ranges), `pip-audit`,
`bandit`, `pytest` and `python -m build` all executed. Any of it could mint a PyPI-audience token
from the job environment and publish as us.

Split exactly as the finding proposed: `build` runs all of it with no credential; `publish` holds
the credential and downloads artifacts. **`publish` does not check out the repository**, so our
code is not merely unexecuted there — it is absent.

### The approval got better as a side effect

The finding notes that the environment gate *"protects job start, so the human approves before the
untrusted code runs."* Moving the gate to `publish` means it now waits **after** the suite and the
sdist guard have passed: a reviewer approves a build they can see succeeded, rather than one about
to begin. That was not the goal and is worth keeping.

### Guarded structurally, because the property is one reasonable-looking step from gone

`actions/checkout` added to `publish` "to read the version", or a `pip install` "to check
something first", restores the whole exposure and would pass review. So
`tests/test_release_workflow_shape.py` asserts it as shape rather than as a list of banned
strings: the credential-holding job may not check out, may not run shell, and may use only actions
on a named allowlist that a new entry has to join deliberately.

**Verified to fail against the pre-split workflow — 14 of 17 assertions do.** It also asserts the
split dropped no gate, that every action is still SHA-pinned, and that `if-no-files-found: error`
is set, without which an empty `dist/` uploads cleanly and a green publish ships nothing.

---

## #196 — configuration options undocumented, and counts stale (v0.30.7)

The issue reads as housekeeping. One item in it is not.

### `csa-gw://help/configuration` was giving out a wrong profile table

The reference's profile table was hand-written and had drifted from `policy.PROFILES` in **both**
directions:

| It said | Actually |
|---|---|
| `editor` may "tidy comments" | `comment.edit` and `comment.delete` are `full`; `editor` has neither |
| `full` adds rename/move, trash, share | rename/move (`file.update`) and trash (`file.trash`) are **`editor`** |

Why this outranks a stale README: the server's own instructions tell the model to read this
resource **to explain a refusal**. So the wrong copy is not sitting in a file nobody opens — it is
delivered to a user as an answer, with the server's authority behind it. And an operator picking a
profile from it reads `editor` as more dangerous than it is and `full` as the only route to trash,
which is precisely the inversion the v0.21.0 "can this be undone?" rework existed to remove. Both
of those push a deployment toward `full`.

**Fixed by removing the copy, not correcting it.** The table renders from `PROFILES`; the
per-capability meanings and reversibility live in `policy.CAPABILITY_NOTES`, beside the constants,
because four surfaces (README, this resource, `describe_configuration`, the module docstrings) were
each restating them from memory. The generator checks the nesting it relies on rather than assuming
it, so a future non-nested profile renders its own full list instead of quietly claiming to inherit
a capability it dropped.

The values of `CSA_GW_CAPABILITIES` were, separately, **documented nowhere**: the reference called
it "an explicit capability list" and left the ten names to be guessed from an error message.

### The reference claimed to be complete and named half the variables

It opens with *"Every variable"* and described five of the ten `CSA_GW_*` the code reads. Missing:
`CSA_GW_TOKEN` (points at the cached credential), `CSA_GW_CLIENT_SECRETS`, `CSA_GW_EXPORT_DIR`
(decides where an authorized `.csv` lands **on the host**), and the two demonstration variables.

A partial list under a completeness claim is worse than no list: the omissions read as *there are
no others*. All ten are documented now, and separated into the three bounds and the settings that
are **not** ceilings — so the "three independent bounds" framing stays true while the count stops
being a lie.

### Guarded by discovery, not by a hand-maintained list

`tests/test_docs_do_not_drift.py` finds the variables by scanning `src/**/*.py` for
`CSA_GW_[A-Z_]+`, so a new one documented nowhere fails in CI rather than in somebody's
configuration. It caught a real mistake within minutes of being written: shortening a table row to
`CSA_GW_DEMO_REPO / _SHARE` to satisfy the 120-column limit removed the only full occurrence of
`CSA_GW_DEMO_SHARE`, and the test failed on it.

It also asserts:

* no profile row advertises a capability that profile lacks — the specific defect above;
* the capabilities described as irreversible are **exactly** `DEFAULT_DISABLED`, tying the prose
  "the line is drawn on: can this be undone?" to the data it claims to describe;
* only *mechanical* claims (tool count, capability count, version). Comparative claims about
  Google's server or the claude.ai connector are deliberately **not** asserted — they cannot be
  computed from here, and they carry a verification date instead. The first draft of the test
  flagged the README's "8 tools" for *Google's* server as our own drift, which is the failure mode
  a test like this has.

### The counts it was actually filed about

`CLAUDE.md` said 32 tools; `INTERFACE-RESOURCES.md` said nine and reported itself verified at
v0.2.3; the README said 34, which was right. `INTERFACE-RESOURCES.md` also still stated content
writes were *"not exposed through MCP yet"* — false since **v0.13.0**, fifteen releases earlier,
and it understated the server by an entire capability axis.

That claim survived the first version of the guard, which searched for the literal string while the
file carried it as `are **not** exposed through MCP yet`. Markdown emphasis defeated it. The test
now strips emphasis and collapses whitespace before matching — a guard an ordinary edit can slip
past is not a guard.

### What is not claimed

Nothing here changes an enforcement path. `PolicyBackend` was correct throughout; it was the
*description* of it that was wrong. The exposure is that operators and models were making decisions
from that description.

---

## #188 — T18 · hash-pinned lockfile for CI and release (v0.30.8)

Fixed as scoped: **CI and release only**, published ranges untouched. The issue was explicit that
GA-#28's "benign and standard for a library" verdict on permissive ranges stands for the package
and does not answer the reproducibility question, and that split is now physical — `pyproject.toml`
for consumers, `requirements/` for our automation.

`requirements/dev.txt` · `build.txt` · `build-backend.txt`, generated by `scripts/lock.sh`.
Dependabot covers `/requirements` **explicitly**, because it does not recurse and a frozen
lockfile is the failure mode a lockfile invites. That is also how the "did the new version break
us?" signal survives pinning CI: the bump arrives as a PR and the five-Python matrix runs against
it before auto-merge.

### The part the finding did not name, and which mattered most

A lockfile pins what the *outer* environment installs. It does not reach `python -m build`, which
creates **its own isolated venv** and installs `build-system.requires` into it from PyPI. So the
code that literally writes the wheel was the last thing resolving freely, inside the job whose
only output is the published artifact — the exact place the finding was about.

`PIP_CONSTRAINT` reaches it. **Verified by falsification rather than assumed**: pointed at a file
pinning `setuptools==82.0.0`, contradicting our `build-system.requires = ["setuptools>=83"]`, the
build fails with a resolver conflict. A silently-ignored constraint would have built happily, and
the control would have read as present from the outside while doing nothing — which is worse than
not having it.

The same PEP 517 hole exists in `pip install -e .`. Both workflows now install the backend from
`build-backend.txt` and pass `--no-build-isolation`.

### Three things measured, each of which would have broken something

1. **`uv pip compile --universal` ignores `requires-python`.** It resolves against the interpreter
   it runs on, even with that same `pyproject.toml` as input. On a 3.12 machine it pinned
   `rpds-py==2026.6.3`, which requires >=3.11 — a lockfile that installs on four of the five
   matrix legs and fails the fifth, at install time in CI rather than at compile time here.
   `--python-version 3.10` is load-bearing and `tests/test_lockfiles.py` asserts the script keeps
   it, tied to the `requires-python` value rather than hard-coded.

2. **`PIP_CONSTRAINT` cannot be used for the editable installs** — the obvious wiring, and it
   fails. A constraints file *carrying hashes* puts pip in hash-checking mode for the entire
   invocation, and an editable requirement then errors with *"no single file to hash"*. Had this
   been wired the obvious way it would have reddened every job. It now appears on exactly one
   step, with a test asserting it stays there and is not hoisted to job level.

3. **`pip install --upgrade pip` was an unpinned fetch by the verifier.** The tool about to check
   every other hash was itself downloaded unverified, immediately before doing so. Removed from
   both workflows rather than pinned: the runner's pip is used as shipped, which deletes the fetch
   instead of trying to secure it.

### What is deliberately still unpinned

The `security` job, including its editable build. `pip-audit` exists to report on what a **real**
install resolves to; running it against our lockfile would have it audit the one environment
nobody installs, and a CVE in the version users actually get would stop being reported. The
control applied there would remove the signal it was meant to give.

Both carve-outs are asserted **as** carve-outs, so tidying up the apparent inconsistency fails a
test carrying the reason rather than quietly deleting a signal. The scoping of one of them was
found by the test itself: the first draft flagged the security job's `pip install -e . pip-audit
bandit` as an unpinned build, which is when the exemption stopped being an assumption and became
a written-down decision.

### Drift

`tests/test_lockfiles.py` fails when `pyproject.toml` declares a dependency the lock does not
carry — on the PR that introduces it, in the `lint` job, naming the package. Without it, the drift
surfaces as an `ImportError` somewhere in the five-Python matrix: a true failure with a misleading
cause.

24 tests; **7 fail against the pre-fix workflows**, checked by restoring them from `main`.

### Also verified end to end before shipping

The release build step was rehearsed locally with its exact command pair — `pip install
--require-hashes -r requirements/build.txt` then `PIP_CONSTRAINT=... python -m build` — producing
an sdist and wheel that pass `twine check`. A release path is a bad place to discover a wiring
error, since it only runs on a tag.

---

## #189 — T19/T27 · assert the externally-enforced controls (v0.30.9)

The finding was precise: `RELEASING.md:29-38` analyses the self-referential case correctly, and
the residual is that the analysis is prose. `scripts/check_controls.py` turns each of the three
into a check, run weekly and **in the release build**.

### Why the release build and not only the schedule

A weekly run finds drift within a week. A release is the moment drift costs something: if the
`pypi` environment's required reviewers had been removed, **that very run would publish
unattended** — the exact failure the gate exists to prevent, at the exact moment it is load-
bearing. The check therefore sits in `build` (which holds no credential), not in `publish`
(which does, and deliberately runs no project code — a test asserts it stays out).

### The three states, and why the third is the whole design

`OK` / `VIOLATED` / `UNVERIFIABLE`, never collapsed:

* a violation exits non-zero — the setting is wrong, now;
* unverifiable prints as loudly as a failure but does not fail on its own, because the usual
  cause is a token without admin rights, which is a fact about the caller;
* **everything unverifiable exits non-zero**, because a run that verified nothing must not read
  as a clean bill of health.

That last clause is the point. A control check that cannot reach its evidence and exits 0 is
worse than no check — it reads as a control from the outside while asserting nothing, which is
the failure mode this audit and its predecessor keep finding here in other forms: an sdist grep
matching filenames only, a test asserting a default it never set, a configuration reference
restating a policy from memory.

It is also what makes the check safe on a release path. An outage cannot redden a release; only
a genuinely violated control stops one. A check that failed on unreachability would have to be
removed from that path the first time PyPI had a bad minute.

### How each control is actually verified

| Control | Evidence | Credential |
|---|---|---|
| Publisher constrained to `pypi` | the published **PEP 740 provenance**, which carries `publisher.environment` | none |
| `pypi` environment has reviewers | `GET /repos/{o}/{r}/environments` | none — answers unauthenticated for a public repo |
| Branch protection on `main` | `GET /repos/{o}/{r}/branches/main/protection` | **admin** |

The publisher check deserves a caveat stated plainly rather than glossed: PyPI does not expose a
project's publisher *configuration* publicly, so this asserts the **consequence** — what did
publish, not what would be accepted. A binding widened but never abused looks identical to a
constrained one. PyPI's own *"can be made more secure"* email covers the other end, and the two
together bound it; the script says so in its docstring rather than implying more.

Branch protection cannot be read by a workflow's `GITHUB_TOKEN` at all — there is **no
`administration` permission** to grant in a `permissions:` block, so this is not a matter of
asking for more. In CI it reports unverifiable unless an optional read-only `CONTROLS_TOKEN`
(fine-grained, `administration:read`) is configured. Left to the operator on purpose: adding a
long-lived credential to a public repository is a real cost, and it should not be paid silently
to satisfy one check. The workflow runs and checks two of three without it, and says which.

### Two bugs the check had, found by running it rather than reading it

1. **A 406 that read as "unreachable".** GitHub's `Accept: application/vnd.github+json` was
   being sent to PyPI's integrity endpoint, which rejects it. The publisher control degraded to
   `UNVERIFIABLE` and the script exited 0 — a check that had silently stopped checking, which is
   the precise thing it was written to prevent. The header is now per-host, and
   `test_a_406_is_not_read_as_success` pins it.

2. **A GitHub token was sent to PyPI.** The `Authorization` header was attached to every
   request. A credential sent to a host that did not ask for it is a credential leaked to it.
   Now conditional on the request going to GitHub, asserted by a test reading the source.

### Scope, stated so the check is not read as more than it is

It detects **drift**: a setting changed by hand, a reviewer list emptied, a rule dropped during
unrelated repo surgery. It does **not** defend against an attacker who can edit this repository,
because they can edit the check. Same limit `RELEASING.md` already analyses for the publisher
binding, same answer: what survives repo compromise is what PyPI and GitHub enforce, not the
file asserting it. Both the script docstring and the workflow header say this, so a green badge
is not mistaken for a stronger claim.

### Verification

`tests/test_controls_check.py` — 30 tests, exercising the classification offline by substituting
the HTTP layer, because the interesting behaviour is not "can it reach GitHub" but "what does it
conclude, and what does it do when it cannot tell". Each of the four branch-protection
weakenings (no required checks, admins exempt, force pushes, deletions) is asserted on its own:
checking only the first would pass a branch anyone can force-push over.

Run live against the real repository during development — all three controls currently verify.
