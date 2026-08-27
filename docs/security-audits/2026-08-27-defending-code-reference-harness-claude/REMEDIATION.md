---
audit_id: 2026-08-27-01
remediation_started: 2026-08-27T19:20Z
remediation_status: in-progress
fixed_in_version: 0.30.0
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
