---
report_id: 2026-09-01-release-readiness-02
date_started: 2026-09-01
date_completed: 2026-09-01
target: csa-google-workspace
target_version: 0.37.0
target_commit: 5cf8d4e010e9603eeef29e296284596a922e0440
target_branch: main
target_worktree: "product tree clean; this report is the only intended working-tree change"
scope: correctness-release-readiness
security_scope: deferred
artifact_policy: public-report-only-no-product-remediation
producer: codex-gpt5
primary_consumer: ai-remediation-agent
consumer_contract: stable-finding-ids-with-evidence-and-done-criteria
release_verdict: not-ready-for-1.0.0
findings_total_open: 6
findings_p0: 1
findings_p1: 3
findings_p2: 2
resolved_since_previous_pass: 2
---

# Release Readiness Report - 2026-09-01

This is a public, report-only correctness and release-readiness review for the
`csa-google-workspace` MCP server and surrounding project. It deliberately does
not remediate product code. A security audit remains deferred until the public
correctness contract is stable.

## Consumer Contract

This report is written for downstream AI agents first and humans second.
Consumers should treat finding IDs as stable work items. Do not reinterpret a
finding from the title alone; use the evidence and "Done when" criteria.

Severity:

| severity | meaning |
|---|---|
| P0 | Blocks a credible 1.0.0 release candidate. |
| P1 | Should be fixed before 1.0.0 unless explicitly accepted. |
| P2 | Worth fixing or documenting before 1.0.0; not a hard blocker alone. |
| P3 | Informational or process improvement. |

Status values are report status, not remediation status. A finding remains
open until a later report or explicit tracking artifact marks it closed.

## Scope

Included:

- MCP stdio behavior and public protocol shape, checked against the official
  2026-07-28 MCP specification.
- MCP tool, resource, configuration, and client-consumed reporting surfaces.
- Public documentation and source-level documentation that describes the
  server contract.
- Test, typing, lint, coverage, release-history, packaging, and CI readiness
  signals.
- The current repository state at `5cf8d4e010e9603eeef29e296284596a922e0440`.

Excluded:

- Security exploit testing, adversarial prompt-injection testing, and
  dependency vulnerability triage. Those belong to the next security audit.
- Live Google integration tests. This report used offline tests and direct
  stdio probes.
- Real-client UI behavior in Claude, ChatGPT, Cursor, VS Code, or other MCP
  clients. This report checked the server-side protocol surface those clients
  consume.

External standards sources used:

- MCP base protocol 2026-07-28:
  https://modelcontextprotocol.io/specification/2026-07-28/basic/index
- MCP `server/discover` 2026-07-28:
  https://modelcontextprotocol.io/specification/2026-07-28/server/discover
- MCP stdio transport 2026-07-28:
  https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio
- MCP tools 2026-07-28:
  https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- PyPI project page:
  https://pypi.org/project/csa-google-workspace/

## Executive Verdict

Not ready for 1.0.0 today.

The cleanup since the prior pass materially improved the project. The earlier
runtime blockers are gone: the tab/range MCP expansion is fully wired into the
capability model, the full test suite is green, and MCP `serverInfo.version`
now reports `0.37.0` on both modern and legacy protocol paths.

The remaining blocker is the public contract around configuration and defaults.
Runtime behavior, updated security prose, CLI help, README guidance, and
source-level comments do not yet tell one consistent story. For this project
that is release-critical: the human maintainer delegates implementation and
operation to AI agents, so stale prose becomes executable guidance.

No product-code correctness failure was found in this pass. The codebase is in
good shape for a 0.x release train: lint, typing, docs-claims, audit-index,
release-history, PyPI version, direct MCP stdio probes, and the full offline
suite all pass. The 1.0.0 bar is higher because it freezes the public
expectation for operators and clients.

## Evidence Commands

Commands were run from the repository root.

| command | result |
|---|---|
| `git rev-parse HEAD` | `5cf8d4e010e9603eeef29e296284596a922e0440` |
| `git status --short` | before rewriting this report, only `?? docs/RELEASE-READINESS-REPORT-2026-08-31.md` was present |
| `.venv/bin/python -c 'from csa_google_workspace import __version__; print(__version__)'` | `0.37.0` |
| `python3 -m pip index versions csa-google-workspace` | latest published package is `0.37.0` |
| `.venv/bin/python scripts/check_release_history.py` | changelog, git tags, and PyPI agree: 72 version entries, 58 claimed released, 58 tags, 58 PyPI releases |
| `.venv/bin/ruff check src tests` | passed |
| `.venv/bin/mypy src` | passed: 57 source files |
| `.venv/bin/python scripts/check_doc_claims.py --strict` | passed: 19 documents checked, no mechanical contradictions found |
| `.venv/bin/python scripts/gen_audit_index.py --check` | passed: index current with 3 audit records |
| `.venv/bin/python -m pytest -q --cov --cov-report=term-missing` | passed: 1631 passed, 14 skipped, 89.05% coverage; 85% required |

Direct stdio probes:

| probe | result |
|---|---|
| `server/discover` with `io.modelcontextprotocol/protocolVersion=2026-07-28` | `resultType: "complete"`, `supportedVersions: ["2026-07-28"]`, `ttlMs: 0`, `cacheScope: "private"`, `_meta.io.modelcontextprotocol/serverInfo.version: "0.37.0"` |
| legacy `initialize` with `protocolVersion=2025-11-25` | `protocolVersion: "2025-11-25"`, `serverInfo.version: "0.37.0"` |

Current tool counts from `create_server(...).list_tools()`:

| flavour | tools registered | hidden |
|---|---:|---:|
| default | 50 | 0 |
| full | 50 | 0 |
| google | 11 | 39 |
| claude | 14 | 36 |

New tab/range tool capability mapping is now present:

| tool | capability |
|---|---|
| `list_tabs` | none |
| `add_tab` | `content.write` |
| `delete_tab` | `content.delete` |
| `list_document_tabs` | none |
| `add_document_tab` | `content.write` |
| `delete_document_tab` | `content.delete` |
| `read_range` | none |
| `clear_cells` | `content.delete` |
| `insert_text` | `content.write` |
| `delete_range` | `content.delete` |

Important limitation: `scripts/check_doc_claims.py --strict` explicitly says
it checks mechanically verifiable claims only. A clean result means no counted
or enumerated contradiction was found; it does not mean the prose is correct.

## Resolved Since Prior Pass

### RR-001 - Tab/Range MCP Expansion Was Partially Landed

Status: resolved in this pass
Former severity: P0

The prior pass observed 50 tools registered but red tests and missing
capability mappings for the new tab/range tools. Current state:

- Full suite passes: 1631 passed, 14 skipped.
- Current tool counts are coherent: 50 default/full, 11 google, 14 claude.
- The new tools are mapped in `TOOL_CAPABILITIES`.
- `content.delete` is no longer reported as unexpectedly unreachable under
  the full profile.

No further action is carried under RR-001.

### RR-002 - MCP `serverInfo.version` Was Empty

Status: resolved in this pass
Former severity: P0

The prior pass observed an empty `serverInfo.version` in direct MCP protocol
responses. Current direct stdio probes return `0.37.0` for both
`server/discover` and legacy `initialize`.

No further action is carried under RR-002.

## Open Findings

### RR-003 - Public Configuration Documentation Still Describes the Old Default Model

Status: open
Severity: P0
Confidence: high
Area: public docs, CLI help, source-level documentation

Evidence:

- `README.md:31-32` says every destructive capability is off until an operator
  names it and that the file allowlists fail closed.
- `README.md:40-48` says the project is behind 963 offline tests and that the
  MCP server exposes 34 tools. Current evidence is 1631 passed, 14 skipped,
  and a 50-tool default/full surface.
- `README.md:440-451` says unset allowlists permit nothing and that unset,
  empty, or bad allowlist values fail closed. Current behavior is different:
  unset or blank read/modify allowlists mean every file; malformed attempted
  lists fail closed.
- `src/csa_google_workspace/mcp/cli.py:40-56` still advertises profile names
  `reader | commenter | editor | full`, default `editor`, and a safe default
  capability set. Current profile names mirror Drive roles
  `reader | commenter | writer | fileOrganizer | organizer`, and the default
  is everything on.
- `src/csa_google_workspace/mcp/cli.py:147-149` says Claude Desktop defaults
  leave both allowlists fail closed and nothing reachable until
  `CSA_GW_ALLOWLIST_READ`.
- `src/csa_google_workspace/mcp/_config.py:159-163` still has an internal
  docstring saying both allowlists fail closed and unset means nothing is
  permitted, while `_scope_from_env` documents and implements unset as every
  file.
- `THREAT_MODEL.md:112`, `THREAT_MODEL.md:131`, and
  `THREAT_MODEL.md:197` still describe the bundled MCP server as a 34-tool,
  fail-closed artifact. The next security audit can replace the threat model,
  but until then this is still public repository text.
- `SECURITY.md:120-123` has the newer correct statement: unset allowlists mean
  every file, while malformed attempted lists fail closed. The repository now
  contains both the old and new models.

Impact:

- Operators and AI agents can configure the server under the wrong assumption
  that an unconfigured install refuses access. It does not.
- AI remediation agents reading source comments may preserve the stale
  docstring because nearby code still carries both historical and current
  statements.
- Docs-claims CI cannot catch this class because it is reasoning drift, not a
  simple count or inventory mismatch.
- The 1.0.0 release would publish contradictory public guidance about the
  server's most important operational boundary.

Consumer action:

- Rewrite the README introduction and capability-boundaries section to match
  the current model: default capabilities on, unset/blank allowlists mean every
  file, malformed attempted lists fail closed.
- Rewrite CLI help and `configure` output so a newly generated MCP client
  config does not tell the user the opposite of runtime behavior.
- Update stale source-level comments/docstrings in `_config.py`.
- Either refresh `THREAT_MODEL.md` during the follow-on security audit or
  clearly mark stale statements as historical until that audit is complete.
- Add specific regression tests for the sentences that have already drifted:
  default tool count, profile vocabulary, default capability posture, and
  unset allowlist semantics.

Done when:

- A repository-wide search for current-doc claims about `fail closed`, `34
  tools`, `963 offline tests`, `editor`, `full`, and unset allowlists returns
  only accurate current statements or explicitly historical text.
- `csa-google-workspace-mcp --help`, `csa-google-workspace-mcp configure
  --print`, README, `SECURITY.md`, and `THREAT_MODEL.md` no longer contradict
  runtime behavior.
- At least one automated docs-drift test fails if README or CLI help reverts
  to "unset allowlists permit nothing".

### RR-004 - The Published `[mcp]` Extra Is Not Exercised Under Free Resolution

Status: open
Severity: P1
Confidence: medium-high
Area: packaging, MCP optional dependency, CI

Evidence:

- `pyproject.toml:65-69` defines the user-facing MCP extra as
  `mcp = ["mcp>=2.1", ...]`.
- `pyproject.toml:79-84` includes `mcp>=2.1` in the dev extra, so pinned dev
  CI covers one known-good MCP SDK resolution.
- `.github/workflows/tests.yml:101-111` intentionally free-resolves the runtime
  package for `pip-audit`, but installs `pip install -e . pip-audit bandit`,
  not `pip install -e .[mcp] ...`.
- `.github/workflows/release.yml:50-56` does the same on the release security
  gate.
- Direct runtime probes in this report used the local pinned development
  environment, not a fresh install of the published optional extra.

Impact:

- A future MCP SDK release satisfying `mcp>=2.1` could break the shipped MCP
  server while the pinned suite remains green.
- The project intentionally distinguishes pinned CI from real-user free
  resolution, but the same reasoning is not applied to the optional extra that
  provides the primary server artifact.
- This is especially important before 1.0.0 because MCP protocol compatibility
  is part of the public promise.

Consumer action:

- Add a release or scheduled job that creates a clean environment, installs the
  package as users do with `pip install .[mcp]` or the published wheel plus
  `[mcp]`, and runs MCP smoke probes.
- Smoke probes should include at least `server/discover`, `tools/list`, and a
  minimal resource/tool call that imports the optional dependencies.
- Keep the existing pinned dev closure. This finding is about adding a
  free-resolution MCP-extra check, not replacing the reproducible suite.

Done when:

- CI proves the current published `[mcp]` dependency range can start the stdio
  server and list tools under a fresh free-resolved install.
- A future incompatible `mcp` SDK release would fail CI before a release is
  cut.

### RR-005 - Explicit Capability Overrides Still Report the Ignored Profile as Active

Status: open
Severity: P1
Confidence: high
Area: effective configuration reporting

Evidence:

- `src/csa_google_workspace/mcp/_config.py:168-174` correctly logs that when
  both `CSA_GW_PROFILE` and `CSA_GW_CAPABILITIES` are set, the explicit
  capability list wins and the profile is ignored.
- `src/csa_google_workspace/mcp/_config.py:299-307` still stores the raw
  parsed profile on `Settings.profile`.
- `src/csa_google_workspace/mcp/_config.py:354-356` emits startup warnings from
  `Settings.profile`, not from the effective capability source.
- `src/csa_google_workspace/mcp/_resources.py:173-177` renders
  `Profile: **{settings.profile}**` whenever `settings.profile` is set.
- `src/csa_google_workspace/mcp/_tools/config.py:57-65` returns
  `"profile": settings.profile` in `describe_configuration`.
- Runtime proof with `CSA_GW_PROFILE=reader` and
  `CSA_GW_CAPABILITIES=comment.create`:
  - log: explicit capability list wins and the profile is ignored.
  - effective capabilities: only `comment.create`.
  - startup warning: `profile: reader - no mutations at all`.
  - config resource: `Profile: **reader**` and `Available here:
    comment.create`.

Impact:

- The effective configuration payload is internally contradictory in exactly
  the case where an operator supplied two controls and needs a clear answer.
- AI clients can summarize the profile as active even though it was ignored.
- Debug reports generated through `describe_configuration` can mislead
  maintainers during support.

Consumer action:

- Track the effective capability source separately from the raw environment
  variable, for example `capability_source=profile:<name>` or
  `capability_source=explicit`.
- Keep the warning that both variables were set.
- Render ignored profile data as ignored, not active.

Done when:

- With `CSA_GW_PROFILE=reader` and `CSA_GW_CAPABILITIES=comment.create`,
  `describe_configuration`, startup warnings, and `csa-gw://config` all say
  the profile was ignored and the effective source is explicit capabilities.
- No effective configuration surface reports `reader` as the active profile in
  that scenario.

### RR-006 - Modern MCP Wire Behavior Is Manually Probed but Not Locked in CI

Status: open
Severity: P1
Confidence: medium
Area: MCP protocol compatibility, regression testing

Evidence:

- Direct subprocess probes in this report show good current behavior for
  `server/discover` and legacy `initialize`.
- `rg -n "server/discover|resultType|ttlMs|cacheScope|protocolVersion|serverInfo" tests src/csa_google_workspace/mcp`
  returned no matches in the current tree.
- The full suite can pass without asserting the exact stdio JSON-RPC envelope
  that standards-compliant MCP clients consume.

Impact:

- A future SDK migration or server wrapper change could drop `resultType`,
  `serverInfo.version`, `supportedVersions`, or legacy `initialize` behavior
  without failing CI.
- These are not implementation details. MCP clients use them for protocol
  parsing, display, logging, debugging, and compatibility decisions.

Consumer action:

- Add subprocess-level MCP smoke tests that launch
  `.venv/bin/python -m csa_google_workspace.mcp`, send JSON-RPC on stdin, and
  parse stdout as a client would.
- Cover `server/discover`, `tools/list`, and legacy `initialize`.
- Assert protocol-version behavior, `resultType`, server version identity,
  list-result fields, and stderr/stdout separation.

Done when:

- The direct stdio probes from this report are represented in committed tests.
- Removing `version=__version__`, dropping `resultType`, or writing logs to
  stdout causes CI to fail.

### RR-007 - Correctness Reports Do Not Yet Have the Same Producer/Consumer Lifecycle as Security Audits

Status: open
Severity: P2
Confidence: high
Area: audit process, AI-consumable project governance

Evidence:

- Security audits have a generated index:
  `scripts/gen_audit_index.py --check` reports 3 audit records.
- This release-readiness report intentionally avoids the security audit index
  contract because it is not a security audit.
- There is no comparable checked index, schema, or status lifecycle for
  correctness/release-readiness reports.
- The user has explicitly asked for a producer/consumer pattern so one AI can
  write public reports consumed by later AI remediation workers.

Impact:

- Future agents can miss this report unless they know the filename convention.
- Finding IDs can drift or be duplicated across correctness reports.
- A later remediation pass has no mechanical way to know which correctness
  findings remain open, superseded, or closed.

Consumer action:

- Create a small correctness-report convention separate from security audits.
  It should define filenames, front matter, status values, stable finding IDs,
  and whether reports are indexed.
- Add a lightweight checker if the project will keep producing these reports.
  It does not need the full security-audit machinery; it only needs to make
  reports discoverable and stable for downstream AI workers.

Done when:

- A future AI agent can discover all release-readiness reports from a single
  documented entry point.
- The repo has a documented rule for marking RR findings closed or superseded.

### RR-008 - `doc-claims.yml` Uses a Pinned Closure but Bypasses the Editable Build-Isolation Guard

Status: open
Severity: P2
Confidence: medium-high
Area: CI consistency, pinned installs

Evidence:

- `.github/workflows/doc-claims.yml:41-46` says it installs the hash-pinned
  closure, then runs:
  - `pip install --require-hashes -r requirements/dev.txt`
  - `pip install --no-deps -e .`
- `tests/test_lockfiles.py:120-139` asserts that pinned editable installs in
  `tests.yml` and `release.yml` also install `requirements/build-backend.txt`
  and use `pip install -e . --no-deps --no-build-isolation`.
- The new doc-claims workflow is not included in that parametrized guard.
- A normal editable PEP 517 build may create an isolated build environment and
  fetch build backend requirements even after the runtime dependency closure
  was installed with hashes.

Impact:

- The workflow comment promises the same pinned-closure posture as the rest of
  CI, but the editable build step is not the same shape.
- The repository has already encoded the reason this matters in tests: without
  `--no-build-isolation`, the editable install can fetch `setuptools` from
  PyPI unpinned.
- The risk is process consistency rather than current runtime breakage, so this
  is P2.

Consumer action:

- Either make `doc-claims.yml` use the same pinned editable install shape as
  `tests.yml` and `release.yml`, or document an intentional carve-out.
- Extend `tests/test_lockfiles.py` so any future pinned editable workflow is
  covered by the same guard or explicitly exempted.

Done when:

- `doc-claims.yml` either installs `requirements/build-backend.txt` and uses
  `--no-build-isolation`, or an explicit tested exemption explains why not.
- `tests/test_lockfiles.py` would fail if this workflow silently regressed.

## Suggested Remediation Order

1. Fix RR-003 first. It is the only P0 and it affects every operator and every
   AI consumer reading the project.
2. Add the MCP wire tests from RR-006 while the protocol probes in this report
   are fresh.
3. Fix RR-005 so support/debug payloads have one effective configuration story.
4. Add the `[mcp]` free-resolution smoke from RR-004.
5. Normalize `doc-claims.yml` per RR-008.
6. Add the correctness-report lifecycle from RR-007 if this report pattern will
   continue.

## 1.0.0 Readiness Gate

Recommended minimum gate before tagging 1.0.0:

- No open P0 findings in this report.
- P1 findings either fixed or explicitly accepted in a public decision record.
- README, CLI help, `SECURITY.md`, and `THREAT_MODEL.md` agree on defaults,
  tool counts, profile names, and allowlist semantics.
- Fresh `[mcp]` install smoke proves the published dependency range can start
  the server and list tools.
- Direct stdio protocol probes are committed tests, not report-only manual
  evidence.
- The follow-on security audit is run against the post-RR-003 public contract.
