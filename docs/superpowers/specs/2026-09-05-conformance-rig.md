# The conformance rig — a dedicated machine that runs everything CI cannot

**Status:** design, 2026-09-05. Nothing here is built yet; §9 says what exists and what does not.

## 1. Why, and the argument is one bug

On 2026-09-05 we found that **every comment write had been broken since v0.47.0** — five
releases. `create_comment`, `edit_comment`, `reply`, `resolve`, `reopen` all returned
`400 Invalid field selection mentioned_email_addresses` against real Google. Reads were fine, so
nothing looked wrong.

CI was green throughout, because `FakeBackend` does not validate field masks. The unit suite
exercised a double that accepts anything.

**The existing live suite would have caught it on its first test.** `tests/integration/
test_all_types_live.py::_assert_comment_lifecycle` does exactly `create_comment → reply →
resolve → reopen → delete` — all four broken calls. It had not been run in five releases,
because running it needs a browser login, a real Drive and a human to opt in.

That is the gap this rig closes: **a machine whose whole job is to run the things a
GitHub-hosted runner cannot**, and to file an issue when they fail.

It was found by *using* the library, not by testing it. A rig is how you make "using it" happen
on a schedule.

## 2. What is under test: the published wheel, not the working tree

**Default: the latest version on PyPI.** Not `main`, not a checkout.

The reasoning is not just "users install from PyPI", though they do. It is that the artifact and
the source can differ in ways only the artifact shows: a packaging error, a file missing from the
wheel, a dependency floor that resolves differently on a clean machine, a `TypedDict` that only
fails below Python 3.12. Testing the tree cannot see any of those.

It also decouples cadence. The rig runs nightly against whatever is current, regardless of what
is being merged that day, and a failure means *"a released version is broken for users right
now"* — which is a different and more urgent statement than "main is broken".

### Version selection

```
--version latest      # DEFAULT: resolve from PyPI, install that
--version 0.50.0      # a specific released version, for bisecting a regression
--version tree        # the working checkout — for validating a fix BEFORE release
```

`latest` resolves from `https://pypi.org/pypi/csa-google-workspace/json` → `info.version`.

`tree` exists because the natural use of the rig, once it finds something, is to fix it and
re-run before cutting a release. It must be an explicit choice, never a fallback: a rig that
silently tests the tree when PyPI is unreachable would report success about a version nobody can
install.

## 3. THE TRAP — and it would make the rig lie

**`pyproject.toml` sets `pythonpath = ["src"]` for pytest.** So running the repo's tests from the
repo root imports the **working tree**, even with a wheel installed in the venv. Measured
2026-09-05:

| how it is run | what `csa_google_workspace.__file__` resolves to |
|---|---|
| `pytest tests/…` (default) | `…/csa-google-workspace/src/…` — **the tree** |
| `pytest -o pythonpath= tests/…` | `…/site-packages/…` — **the wheel** |

A rig built the obvious way would print *"tested 0.51.1 from PyPI: PASS"* having tested whatever
was checked out. That is the same failure as the bug it exists to catch — a green run exercising
the wrong thing.

**Two rules follow, and neither is optional:**

1. Every pytest invocation passes `-o pythonpath=`.
2. **The rig asserts what it imported before running anything**, and aborts if wrong:

```python
import csa_google_workspace as w
assert "site-packages" in w.__file__, f"shadowed by the tree: {w.__file__}"
assert w.__version__ == version_under_test
```

Print both lines in the run log. Every report the rig files quotes them, so a reader can tell
what was actually exercised.

**This is not a new idea here — it is an existing one that never spread.** `scripts/mcp_smoke.py`
already says so in its own docstring: *"It deliberately depends on nothing from this repository:
no pytest, no fixtures, no `src/` on the path. It imports the package the way a user's client
would … so running it in a clean environment tests the published artifact rather than the working
tree."* That script was written for RR-004 to close exactly this gap for the `[mcp]` extra. The
rig generalises it to every layer.

## 4. Where the tests come from — NOT from PyPI

Measured 2026-09-05 against the published 0.51.1 sdist:

- the sdist **does** ship `tests/` — 128 files;
- the sdist does **not** ship `tests/integration/` or `tests/oauth/`;
- it does not ship `scripts/` or `experiments/` either.

So the live suites, the zoo builders and the helper scripts exist **only in git**. The rig
therefore needs both halves, version-matched:

- **package under test** — the wheel from PyPI, at the selected version;
- **test code** — a git checkout at tag `v<version>`.

Pairing them is what keeps the result meaningful. Running today's tests against last month's
wheel produces failures that are the *tests'* fault, and a rig that cries wolf gets ignored.

For `--version tree`, both halves are the checkout, and the import assertion in §3 is inverted:
assert it is **not** site-packages.

## 5. The layers

Ordered cheapest-first so a broken install fails in seconds rather than after an hour of browser
work. **A layer that fails does not stop the ones after it** unless it is L0 — the point is one
report per night listing everything wrong, not a bisect.

| # | layer | needs | ~time |
|---|---|---|---|
| **L0** | install the wheel into a fresh venv; assert version + import path (§3) | network | 30s |
| **L1** | the offline unit suite from the matching checkout | — | 1min |
| **L2** | **`tests/integration/`** — real Google, throwaway files, **full read/write** | RW token, Drive | 2–5min |
| **L2-RO** | **prove read-only IS read-only** — see §5a. A *negative* layer | RO token, Drive | 1min |
| **L3** | `scripts/mcp_smoke.py` — the MCP server starts and answers | — | 30s |
| **L4** | `experiments/zoo/verify.py` — the specimens still say what the repo claims | token, Drive | 1–2min |
| **L5** | `csa-google-workspace-mcp demo --auto` — the guided end-to-end | token, Drive | 3–5min |
| **L6** | `tests/oauth/` — interactive browser login | **a human**, browser | 2min |
| **L7** | editor conformance — place comments in the browser, read anchors back | browser, **idle machine** | 10–20min |

**L0 is the only hard gate.** If the wheel does not install or the version is wrong, everything
after it is meaningless.

**L6 needs a human** and so cannot run nightly. It runs when the token is being refreshed anyway,
or on demand. Do not let it block the rest.

**L7 is the new and expensive one**, and it has a constraint nothing else has: *the machine must
be left alone.* Measured 2026-09-03 — a person using the keyboard while the automation runs
steals focus mid-sequence and every keystroke lands somewhere else. This is the single strongest
argument for the machine being dedicated rather than borrowed.

**L5 is already safe to run unattended**, and deliberately so: `--auto` sets `confirm=None`, so
an environment-configured share is *refused* rather than performed without a human. An existing
unattended run keeps working and simply stops sharing. That is the behaviour a rig wants, and it
means L5 needs no special handling.

## 5a. L2-RO — proving read-only is *in fact* read-only

**The default posture is full read/write** (L2), because that is what most callers run and where
the bugs are. But read-only is a **claimed security property**, and a claimed property that is
never adversarially tested is a claim.

### There are three layers of read-only, and they are not equally strong

| # | control | what it proves | survives |
|---|---|---|---|
| 1 | **client guard** — `_require_writable()` raises `ReadOnlyError` | *our code declined to try* | nothing; it is our own code |
| 2 | **token scope** — `CSA_GW_READ_ONLY=1` requests only `.readonly` | **Google refuses the call** | a bug in 1, a bypassed policy, a stolen token |
| 3 | capability/policy gating | an operator's configured ceiling | — |

**Only #2 is proof.** This is the same asymmetry `restrictions.py` already records: *"Google will
refuse this" is categorically stronger than "our policy is configured not to."*

### What exists today, and what does not

`tests/oauth/test_oauth_flow.py::test_read_only_oauth_session_reads_but_refuses_writes` covers
this, and its own docstring is precise about how far: *"blocks writes **at the client guard**."*
Thirteen offline test files assert `ReadOnlyError` similarly.

**Nothing anywhere has ever confirmed that the read-only token cannot write.** That is layer #2,
it is the one that matters, and it is untested.

It is not hypothetical. **#327 was exactly this bug**: `has_write_scope` was an allowlist of four
known write scopes, so a token carrying `drive.file` — a real write scope this project never
requests — answered `False` and was accepted as read-only. A token that could write, treated as
one that could not, in the check whose entire job is preventing that. It is now an inverted
subset check, which is right, and which no live test verifies.

### The test, and it must bypass our own guard on purpose

1. Acquire read-only credentials (`read_only=True`, its own token cache).
2. **Assert the granted scopes** — `has_write_scope(granted)` is `False`, and every granted scope
   ends `.readonly`. This is the *configuration* check.
3. **Read something.** Read-only must still work; a posture that refuses everything is not a
   passing read-only, it is a broken credential.
4. **Attempt a real write, going around the client guard deliberately** — straight to the Drive
   service with those credentials, because `_require_writable()` would otherwise raise first and
   the call would never reach Google. Going around our own guard is the entire point: the guard
   is what is *not* being tested here.
5. **Assert Google refused it** — a 403 on insufficient scopes, not a `ReadOnlyError`. If the
   exception type is `ReadOnlyError`, the test did not do what it claims and must fail as
   inconclusive rather than pass.
6. **Assert nothing was created.** Re-read with the read-write credentials and confirm absence. A
   403 does not by itself prove no side effect landed, and "the write was refused" and "nothing
   changed" are different statements.

Step 5's distinction is the one that makes this layer worth having. A test that accepts *either*
`ReadOnlyError` or a 403 as success silently degrades into layer #1 the moment the guard fires
first — which is precisely how this property came to be untested in the first place.

### If the write SUCCEEDS

That is a **security finding, not a test failure.** The rig must:

- file at once, labelled as security, and say plainly that a read-only credential performed a
  write;
- **not** continue to later layers on that posture;
- record which scope was granted, since that is the evidence.

It should also clean up what it just wrote — the write succeeding does not make the artefact
wanted.

### Target

The same throwaway discipline as everywhere else, and stated because this layer is the one
deliberately *trying* to write: **it attempts its write against a file the rig created for the
purpose**, never the zoo, never anything cited by id. A read-only conformance check that scribbles
on the corpus while proving it cannot is the worst possible outcome.

### L7 must not touch the zoo

The zoo specimens are **shared, cited, public state**. Files are referenced by id from this
repository and from the comments reference. A nightly job that places comments on them would
corrupt the corpus within a week.

So the split is:

- **L4 verifies the zoo** — read-only, asserts the specimens still match what the repo says.
- **L7 mutates throwaway files it creates itself**, exactly as `tests/integration/` already does.

The one exception is a deliberate, human-initiated corpus rebuild, which is not a rig run.

## 6. The machine

**A Mac.** Not preference: the editor-automation recipe is written in `⌘`-based shortcuts
(`⌘+Option+M`, `⌘+F`, `Alt+Shift+ArrowRight`), and Google Docs' key handling differs by
platform. Porting to Linux is possible and is a project, not a config change.

**Dedicated, and left alone.** See L7 above. A laptop someone is using is not a rig.

**Logged in as the account under test.** The browser needs a real, already-authenticated Google
session; the API needs a token for the same account.

### What to install

| | |
|---|---|
| Python | 3.10–3.14 (CI's matrix). Pick one as the rig default; 3.12 or 3.13 is sensible |
| git | for the version-matched checkout |
| `gh` | authenticated, for filing issues |
| Playwright | plus its browser download, for L7 |
| the repo | cloned; the rig checks out tags, so a plain clone is enough |

### Credentials, and one gotcha

- **The OAuth client** — an *installed/desktop-app* client secrets JSON. Google's API ToS forbid
  embedding developer credentials in an open-source project, so this lives in the private
  `CloudSecurityAlliance-Internal/CSA-Plugins` repo. It is the only credential-bearing artifact
  in this whole system.
- **`CSA_GW_CLIENT_SECRETS`** points at it.
- **The token cache** — first run opens a browser for consent; after that it is cached and
  unattended runs work.
- **Two token caches, and BOTH are required.** `CSA_GW_READ_ONLY=1` uses its **own** cache file,
  and a read-write token elsewhere does not satisfy it (hit on 2026-09-05; the error says so
  plainly, which is why it cost minutes rather than hours). Since the rig runs L2 read-write
  *and* L2-RO read-only, **the consent dance happens twice during setup** — once per posture.
  This is not a gotcha to work around, it is the mechanism that makes L2-RO meaningful: two
  separate tokens carrying different scopes is exactly the property being tested.

  Setting up read-only deliberately requires a *fresh* consent, not a downgrade of the existing
  token. If the rig ever finds itself able to satisfy the read-only posture from the read-write
  cache, that is itself the #327 failure and should be reported, not accommodated.

Never commit any of these. `.gitignore` covers the known shapes (`credentials.json`,
`token*.json`); the rig's own config should live outside the checkout entirely.

## 7. Blast radius — state it plainly

**The rig runs as Kurt, so its credentials can reach everything Kurt can reach.** There is no way
around that while the requirement is "logged in as me". Pretending otherwise would be the
dishonest kind of security note.

What actually bounds it:

- **The suites only touch files they create.** `tests/integration/` uses a `_throwaway`
  contextmanager that creates a file and trashes it in a `finally`. L7 must follow the same
  pattern.
- **Trash, never delete.** Everything the rig removes goes to Drive's trash, recoverable for 30
  days. Nothing calls `files.delete`.
- **A dedicated folder** for anything the rig creates, so a human can see and empty it.
  Implemented 2026-09-05: `CSA_GW_TEST_FOLDER` (or `--folder <id|url>`) puts every throwaway
  inside a folder you choose, and **a run never trashes a folder it did not create**. With it
  unset the suite makes a dated folder per run — `csa-google-workspace conformance
  YYYY-MM-DD HHMMSSZ` — and removes it at the end. Loose files in My Drive root, which is what
  it used to do, are unauditable and indistinguishable from a person's own work.
  *(The ordering works because each throwaway trashes itself on exit, so the folder is empty
  by teardown — Drive leaves a trashed folder's children loose in My Drive otherwise.)*
- **The READ side can point at the public zoo.** The specimens are synthetic, public and cited
  by id, so they are the right corpus for anything that only reads — L4 already does this, and
  L2-RO's read half should too rather than touching a private document.
- **The allowlist and capabilities** narrow what the *library* will do, and should be set as
  tightly as the layers allow. Note the honest limit already recorded in `README.md`: this is a
  ceiling below Drive's, and it binds our calls, not another client's.

**What the rig must never be pointed at:** a Drive containing real work, a shared drive the rest
of CSA depends on, or any document cited by id from this repo other than read-only in L4.

A dedicated Google account would shrink the blast radius to nothing and is worth considering
later; it is not compatible with "logged in as me" today, and the browser session is the reason.

## 8. Filing issues

The rig's output is **an issue, not a log nobody reads** — the same principle as
`CLAUDE.md`'s rule that an audit notifies by filing an issue.

### One issue per distinct failure, not one per night

Dedup by a **stable fingerprint**: `(layer, test id, first line of the assertion)`. Before
filing, search open issues for that fingerprint; if one exists, add a comment saying it
reproduced on version X rather than opening a second. A rig that opens an issue a night trains
everyone to ignore it.

Label them so they are findable and so a human can tell rig output from human reports.

### What goes in

- **version under test**, and the `__file__` assertion from §3 — proof of what ran;
- **which layer**, the test id, and the exact command to reproduce;
- the environment block from **`_environment.describe_environment()`**, which already exists and
  is already written to be safe for a public tracker;
- the failure output — **redacted, see below**.

### What must NOT go in, and this needs code

`_environment` is careful. **pytest output is not.** A failing live test's traceback can contain
a Drive **file id**, a document title, or comment text — and a file id in a public issue is a
working link to the document.

So the rig needs a redaction pass over captured output before it reaches `gh`. At minimum: Drive
file ids (the long base64-ish tokens), `docs.google.com/...` URLs, and email addresses. This is
not optional and it is the one place the rig can do real harm.

`mcp/_untrusted.py` is the precedent for doing this at a boundary rather than per field.

## 9. What exists, and what has to be built

**Built 2026-09-05: [`Run-full-test-suite.sh`](../../../Run-full-test-suite.sh)** — the runner,
in the same shape as the CSA Cloudflare backup script (`--check` / `--ai` / prereqs with install
hints / verify credentials are *live* rather than merely present). It resolves the version,
installs it, **asserts the import path**, checks MCP registration, probes both tokens with a real
API call, runs the layers, and can hand the results to Claude Code to triage.

It also detects the OS and points at **CSA DesktopSetup** when tooling is missing, because a new
person should get one instruction rather than six:

```bash
./Run-full-test-suite.sh --check              # prerequisites only
./Run-full-test-suite.sh --setup              # install/upgrade + register with Claude Code
./Run-full-test-suite.sh                      # latest PyPI release, unattended layers
./Run-full-test-suite.sh --version 0.50.0     # bisect a regression
./Run-full-test-suite.sh --claude             # triage failures and file issues
```

**It found a real bug on its first run** — see #433: the live integration suite cannot create its
throwaway files, because it reaches through `ws._backend._services`, which `PolicyBackend`
refuses. That is the suite that would have caught the v0.51.1 P0.

**The underlying commands, if you would rather run them directly:**

```bash
# L1 — offline
pytest -q

# L2 — the live suite (this is the one that would have caught the P0)
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json \
    pytest -o pythonpath= tests/integration/ -v

# L3
python scripts/mcp_smoke.py

# L4
python experiments/zoo/verify.py

# L5
csa-google-workspace-mcp demo --auto

# L6 — needs a human
CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=... pytest -o pythonpath= tests/oauth/
```

**L2-RO has no command yet.** Nothing in the repository attempts a write with a read-only
credential and asserts that *Google* refused it — today's coverage stops at the client guard
(§5a). It is the layer with the least existing code and the most security value, and it is small:
one test file.

The nearest thing that runs today only demonstrates the gap:

```bash
# Proves the CLIENT GUARD refuses. Says nothing about whether the TOKEN could write.
CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=... \
    pytest -o pythonpath= tests/oauth/test_oauth_flow.py \
    -k read_only_oauth_session_reads_but_refuses_writes
```

Kurt can start running these on the new machine immediately; they are useful before any
orchestrator exists.

**Has to be built:**

1. **`scripts/conformance.py`** — the orchestrator: resolve the version, make the venv, install,
   **assert the import path**, check out the matching tag, run L0–L5, collect results.
2. **The redaction pass** (§8) — before anything reaches a public issue.
3. **The issue filer** — fingerprint, dedup against open issues, `gh issue create`/`comment`.
4. **L2-RO** (§5a) — the read-only conformance test. Smallest item here and the highest
   security value: no existing code proves the read-only *token* cannot write, only that our
   client guard declines to try. Belongs in `tests/integration/` so it runs unattended, not in
   `tests/oauth/` which needs a human.
5. **L7 itself** — the editor-conformance layer. The recipe is written
   (`experiments/zoo/AUTOMATING-THE-EDITOR.md`) and proven on ten placements, but there is no
   runner, and it needs the throwaway-file discipline of §5.
6. **Scheduling** — `launchd` on macOS. Nightly for L0–L5; L7 less often; L6 on demand.

**Open questions, flagged rather than decided:**

- Should a rig failure on the *latest release* also open a PR reverting, or just an issue? An
  issue, initially — automatic reverts need more trust in the rig than it has earned on day one.
- Should the rig test **more than one Python**? CI already covers 3.10–3.14 offline. The live
  layers are where version differences would show as network/API behaviour, which is unlikely.
  One Python to start.
- Does L7 belong on the same schedule as the rest at all, given it is 10–20 minutes and the
  flakiest? Probably its own weekly run.

## 10. The one-line summary

A dedicated Mac, logged in as the account under test, that every night installs **the current
PyPI release** into a clean venv, proves it is testing that wheel and not a checkout, runs the
live suites the GitHub runners cannot at **full read/write**, then separately proves the
**read-only posture is refused by Google and not merely by our own guard**, and files **one
deduplicated, redacted issue** per genuine failure.
