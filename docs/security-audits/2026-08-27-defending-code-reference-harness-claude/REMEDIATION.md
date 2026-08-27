---
audit_id: 2026-08-27-01
remediation_started: 2026-08-27T19:20Z
remediation_status: in-progress
fixed_in_version: 0.30.0, 0.30.1
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
