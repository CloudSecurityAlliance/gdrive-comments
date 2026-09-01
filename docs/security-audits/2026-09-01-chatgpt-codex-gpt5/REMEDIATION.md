---
audit_id: 2026-09-01-01
remediation_started: 2026-09-01T08:00Z
remediation_status: complete
fixed_in_version: unreleased at time of writing
---

# Remediation — audit 2026-09-01-01

The fix trail, kept separate from the flaw trail by design: this file carries the reasoning that
produced each fix, written after the audit and in a different session, so neither can quietly
reshape the other.

All three findings are dealt with. One threat-model action from each hardening finding is
**deliberately deferred** — see the last section.

---

## CODX-2026-09-01-01 — stale default-posture text

**Status:** fixed · **Landed:** `security/codx-2026-09-01` → #305

### What the audit found, and what the sweep added

The audit listed **13** surfaces still saying destructive or sharing capabilities are off by
default, eleven releases after v0.31.0 reversed it. All 13 were confirmed by reading them.

Sweeping by **phrase** rather than by the audit's table found a **14th**, in `CLAUDE.md` — the
agent-facing guide — describing the three tools Google declines to ship as *"off unless an operator
names each capability"*. Neither this audit nor the correctness review of the same morning had
caught it.

The concentration is the part worth keeping: most were in **source docstrings and MCP tool
descriptions**, not Markdown. A model reads those as operational context, so understating which
destructive tools are reachable is a misleading authority statement on the surface that most
affects behaviour. `PolicyBackend` was never involved — the gate always enforced the real policy,
which is why this was hardening rather than a bypass.

### The test that was pinning the stale claim

`tests/test_file_lifecycle.py` asserted the descriptions **contain** `"off unless an operator"`.
So the wrong text was not merely un-caught: it was **protected by a passing test**. Anybody
correcting a description would have been stopped by CI, and could reasonably have concluded the
description was right.

The same file already knew — `test_share_is_on_by_default_and_off_below_organizer` opens its
docstring with *"REVERSED in v0.31.0."* One test was updated; its neighbour was not.

It now derives from `DEFAULT_ENABLED` rather than pinning a form of words, and its original purpose
is kept as a second test, because removing the false claim must not remove the guidance a model
needs to explain a refusal.

**The replacement then made the same mistake**: it required the literal word `"allowlist"` and
failed on `share_file`, which says *"the file must be listed for modify"* — the same guidance in
different words. Fixed to accept any wording that conveys the bound. Recorded because pinning a
phrase is exactly what the other test exists to undo.

### The check that stops it recurring

`scripts/check_doc_claims.py` gained a default-posture check, scanning **source as well as
Markdown**.

Tuning it was the real work. The bare phrase matched 13 places and **12 were correct** — negations
(*"nothing is off by default"*), past tense (*"capabilities that **were** off by default"*), and
three about **caching**, which genuinely is off by default. A checker with a 92% false-positive
rate is one nobody runs, so two filters narrow it: the claim must sit near a capability or
lifecycle tool name, and must not be negated or in the past tense.

Verified it still catches all three real shapes — a guide claim, a tool description, and prose in
`SECURITY.md` — and stays silent on every legitimate use.

---

## CODX-2026-09-01-02 — unattended demo sharing

**Status:** fixed · **Landed:** `security/codx-2026-09-01` → #305

### What made it a finding

Three separately-reasonable behaviours, none wrong alone: the recipient comes from
`CSA_GW_DEMO_SHARE` when `--share` is absent; `--auto` sets `confirm=None`; and `file.share` has
been on by default since v0.31.0, so the step is reachable on an unconfigured install — with the
Drive notification suppressed.

A fourth made it stickier, and this is the connection the audit drew that is worth keeping:
`configure` carried every `CSA_GW_*` variable into the Desktop config, which is *where policy state
persists*, so a value meant for one run became ambient state that outlived it.

### The three fixes, and why each is shaped as it is

**`NOT_CARRIED` gains `CSA_GW_DEMO_SHARE` and `CSA_GW_DEMO_REPO`.** The second is not dangerous.
It is included because *"demo-only"* is the category that should not persist, and drawing the line
per-variable invites the next one to be missed.

**An env-derived recipient is not used under `--auto`.** Interactive runs still honour it, because
there the confirmation prompt **is** the check, and removing a working convenience to fix an
unattended hazard would be the wrong trade. **Dropped rather than refused:** the share step already
skips cleanly on an empty address, so an existing scheduled demo keeps working and simply stops
sharing. Exiting non-zero would break the run in order to protect it. It says what it ignored and
names the flag that would have worked, because silently dropping a configured value reads as the
feature being broken.

**`sendNotification` is now `True`.** The library's own `share()` documents `notify=True`
*"deliberately: a share the recipient is told about is one somebody can notice and question"* — and
the demo overrode it. A silent grant in a demonstration is the same defect as a silent grant
anywhere; the demo is not a special case.

### Two test drafts thrown away

Both are shapes this repository keeps finding, so they are recorded rather than quietly fixed:

- The first **mirrored** the share-resolution logic into the test file, which passes whether or not
  `_cli` still does the same thing. It now drives the real `_cli.main` with a probe `Runner` that
  captures what it was handed, and asserts the run actually reached it.
- The second captured **stdout** for the warning and got an empty string. `_echo` writes to
  **stderr** deliberately, because a `demo` run shares a process image with the server and stdout
  is the JSON-RPC channel.

---

## CODX-INFO-2026-09-01-01 — gitleaks false positive

**Status:** fixed · **Landed:** `security/codx-remaining`

The audit scoped this conditionally — *"if gitleaks is added to CI, add a narrow allowlist"* — and
that under-scoped it. `.gitleaks.toml` already exists and is run by hand, and its own opening
comment gives the reason not to wait: *"a scanner that reports a known non-finding trains people to
skim its output, which is how a real finding gets missed."* So the entry was added now.

**One thing worth knowing for the next entry.** Two `[[rules]]` blocks sharing an `id` do **not**
merge — the second silently *replaces* the first's allowlist. Adding the new entry that way
suppressed the new false positive and brought the original one back, which a local run caught
immediately. The file now uses the plural `[[rules.allowlists]]` form, with a note saying why.

Verified after the change: `gitleaks dir` clean on the working tree, `gitleaks git` clean across
**372 commits** of history.

---

## Also cleared while here — one open CodeQL alert

Not in the audit, because CodeQL was in its excluded scope (*"not installed in the local
environment"*). It **does** run on this repository through GitHub default setup — 1038 analyses,
including one on the pull request that fixed the findings above — so the exclusion is a gap in the
local tooling, not in the repository's coverage. Worth stating so a future reader does not treat it
as uncovered.

It had **one open alert**, at high severity: `py/incomplete-url-substring-sanitization` on
`tests/test_problem_report.py:88`.

Verified as a false positive by reading it. The line is
`assert any("pypi.org" in item for item in out["checklist"])` — it asserts that a **checklist item
string** mentions pypi.org, so the user is told to verify the published version. No URL is being
validated and no decision rests on the result; CodeQL pattern-matches `"host" in string`, and
`CLAUDE.md` already records this rule firing on test assertions.

Dismissed as `false positive` with that reasoning attached, rather than left open — for the same
reason as the gitleaks entry. A known non-finding sitting at high severity is what trains people to
skim the alert list, which is how a real one gets missed.

---

## Deliberately deferred — the threat model

Both hardening findings end with a threat-model action, and neither is done:

- **CODX-01** recommends the living `THREAT_MODEL.md` rows that rely on old default-disabled
  assumptions be updated or marked superseded.
- **CODX-02** names **T29** specifically: its mitigation still says `file.share` is
  default-disabled, which no longer holds.

Deferred on the CINO's instruction (2026-09-01), and tracked in `TODO.md` under *THREAT_MODEL needs
updating*. That entry already carried the same requirement from the correctness review of the same
morning, so **two independent passes now point at it** — which is the argument for doing it as one
deliberate piece of work rather than as a footnote to either.

The constraint that makes it a judgement call rather than an edit is unchanged: §3 and §4 are the
**previous** audit's frozen words, and that immutability is the only real check on a claim of
progress. The options are to supersede in §0 — as T19's row already does — or to let the next
security audit replace the register against the corrected contract.
