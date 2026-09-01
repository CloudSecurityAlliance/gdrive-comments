---
audit_id: 2026-09-01-01
date_started: 2026-09-01T07:10Z
date_completed: 2026-09-01T07:40Z
target: csa-google-workspace
target_commit: d33034b2e5452acc4730f3a56a7640fdba590873
main_at_record_commit: d33034b
commits_landed_during_audit: 0
target_version: 0.38.0

tool: codex
tool_harness: chatgpt-codex-local-repository
tool_workflow: "plan-then-execute: automated Python security checks, dependency and secret scanning, then targeted trust-boundary review"
model: gpt-5
subagents: "none"

human_interaction: light
automation: assisted
review_depth: standard

scope_covered:
  - "src/csa_google_workspace/ through ruff, mypy, pytest coverage, Bandit, and targeted manual review of auth, MCP, policy, allowlist, local file I/O, Drive permissions, access proposals, backend calls, demo flows, logging, and schemas"
  - "scripts/ through Bandit and manual review of subprocess, URL-fetching, generated-index, release-history, doc-claims, and smoke-test paths"
  - ".github/workflows/, Dependabot, lockfiles, packaging metadata, and secret-scanning config through manual supply-chain review"
  - "tests/ as executed verification: full suite passed in the project virtualenv; targeted tests for policy/tool-description/default-posture claims were read"
  - "dependency inventory for base runtime and optional MCP extra through clean pip-audit virtualenvs"
  - "working tree and git history secret scanning through gitleaks and trufflehog verified-only"
scope_excluded:
  - "No live Google Workspace endpoint was contacted and no OAuth token was read."
  - "No source remediation was made in this audit context."
  - "No dynamic prompt-injection exercise was run against a live LLM client."
  - "CodeQL and Semgrep were not run because they were not installed in the local environment."
  - "GitHub branch-protection status could not be verified locally without an admin-capable CONTROLS_TOKEN; the public release-control checks did pass."
  - "Most test files were execution targets, not line-by-line static-review targets; only the test files listed in modules_covered were read as code."
inputs:
  - "docs/security-audits/SCHEMA.md and docs/security-audits/README.md"
  - "README.md, SECURITY.md, THREAT_MODEL.md"
  - "prior audit record docs/security-audits/2026-08-27-defending-code-reference-harness-claude/"
  - "pyproject.toml, requirements/*.txt, .gitleaks.toml"
  - ".github/workflows/*.yml and .github/dependabot.yml"
  - "raw scanner artifacts in artifacts/"

findings_total: 3
findings_exploitable: 0
findings_hardening: 2
findings_informational: 1

remediation_status: not-started
remediation_context: "separate session recommended"
supersedes: null

index_label: "2026-09-01 · ChatGPT Codex / GPT-5"
modules_covered:
  - ".github/dependabot.yml"
  - ".github/workflows/controls.yml"
  - ".github/workflows/dependabot-auto-merge.yml"
  - ".github/workflows/doc-claims.yml"
  - ".github/workflows/release.yml"
  - ".github/workflows/relock.yml"
  - ".github/workflows/tests.yml"
  - ".gitleaks.toml"
  - "README.md"
  - "SECURITY.md"
  - "THREAT_MODEL.md"
  - "pyproject.toml"
  - "requirements/README.md"
  - "requirements/build-backend.txt"
  - "requirements/build.txt"
  - "requirements/dev.txt"
  - "requirements/uv.txt"
  - "scripts/check_controls.py"
  - "scripts/check_doc_claims.py"
  - "scripts/check_release_history.py"
  - "scripts/gen_audit_index.py"
  - "scripts/lock.sh"
  - "scripts/mcp_smoke.py"
  - "src/csa_google_workspace/__init__.py"
  - "src/csa_google_workspace/_apply.py"
  - "src/csa_google_workspace/_cellmap.py"
  - "src/csa_google_workspace/_content.py"
  - "src/csa_google_workspace/_environment.py"
  - "src/csa_google_workspace/_errors.py"
  - "src/csa_google_workspace/_export.py"
  - "src/csa_google_workspace/_formats.py"
  - "src/csa_google_workspace/_services.py"
  - "src/csa_google_workspace/access_proposals.py"
  - "src/csa_google_workspace/allowlist.py"
  - "src/csa_google_workspace/auth.py"
  - "src/csa_google_workspace/backend.py"
  - "src/csa_google_workspace/base.py"
  - "src/csa_google_workspace/comments.py"
  - "src/csa_google_workspace/demo/__init__.py"
  - "src/csa_google_workspace/demo/_cli.py"
  - "src/csa_google_workspace/demo/_feedback.py"
  - "src/csa_google_workspace/demo/_plan.py"
  - "src/csa_google_workspace/demo/_runner.py"
  - "src/csa_google_workspace/documents/__init__.py"
  - "src/csa_google_workspace/documents/doc.py"
  - "src/csa_google_workspace/documents/sheet.py"
  - "src/csa_google_workspace/documents/slides.py"
  - "src/csa_google_workspace/exceptions.py"
  - "src/csa_google_workspace/files.py"
  - "src/csa_google_workspace/labels.py"
  - "src/csa_google_workspace/mcp/__init__.py"
  - "src/csa_google_workspace/mcp/__main__.py"
  - "src/csa_google_workspace/mcp/_auth_flow.py"
  - "src/csa_google_workspace/mcp/_capabilities.py"
  - "src/csa_google_workspace/mcp/_config.py"
  - "src/csa_google_workspace/mcp/_desktop.py"
  - "src/csa_google_workspace/mcp/_flavours.py"
  - "src/csa_google_workspace/mcp/_inline.py"
  - "src/csa_google_workspace/mcp/_logging.py"
  - "src/csa_google_workspace/mcp/_login.py"
  - "src/csa_google_workspace/mcp/_resources.py"
  - "src/csa_google_workspace/mcp/_schemas.py"
  - "src/csa_google_workspace/mcp/_success_page.py"
  - "src/csa_google_workspace/mcp/_tools/__init__.py"
  - "src/csa_google_workspace/mcp/_tools/_base.py"
  - "src/csa_google_workspace/mcp/_tools/auth.py"
  - "src/csa_google_workspace/mcp/_tools/comments.py"
  - "src/csa_google_workspace/mcp/_tools/config.py"
  - "src/csa_google_workspace/mcp/_tools/content.py"
  - "src/csa_google_workspace/mcp/_tools/content_write.py"
  - "src/csa_google_workspace/mcp/_tools/demo.py"
  - "src/csa_google_workspace/mcp/_tools/feedback.py"
  - "src/csa_google_workspace/mcp/_tools/files.py"
  - "src/csa_google_workspace/mcp/_tools/suggestions.py"
  - "src/csa_google_workspace/mcp/cli.py"
  - "src/csa_google_workspace/mcp/server.py"
  - "src/csa_google_workspace/permissions.py"
  - "src/csa_google_workspace/policy.py"
  - "src/csa_google_workspace/suggestions.py"
  - "src/csa_google_workspace/workspace.py"
  - "tests/test_config_text_agrees_with_policy.py"
  - "tests/test_demo.py"
  - "tests/test_desktop_config.py"
  - "tests/test_desktop_config_permissions.py"
  - "tests/test_file_lifecycle.py"
  - "tests/test_mcp_capabilities.py"

findings_summary: "3 total · 0 exploitable · 2 hardening"
remediation_summary: "not started — audit record only"
---

# ChatGPT Codex security audit, 2026-09-01

## 1. Summary

This audit reviewed the current `main` tree at commit
`d33034b2e5452acc4730f3a56a7640fdba590873` with the explicit goal of turning a
ChatGPT Codex security-audit approach into a repository-local plan and then
executing it.

The automated checks were clean for production code: ruff passed, mypy passed in
the project virtualenv, the full pytest suite passed with coverage above the
configured threshold, pip-audit found no known vulnerabilities in either the base
runtime or the optional MCP extra, and trufflehog found no verified secrets.
Bandit reported only script-level findings already explainable as fixed command
or fixed HTTPS URL use. Gitleaks reported a false positive in historical test
commits, documented below.

Two hardening findings remain. Both relate to the current default-open posture:
some model-facing and operator-facing text still says destructive or sharing
capabilities are off by default, and the demo share path can silently reuse an
ambient share recipient in unattended mode.

## 2. Audit Plan Executed

1. Establish baseline: record commit, version, branch state, existing audit
   schema, and available security tools.
2. Run local quality gates in the same virtualenv the project uses for tests:
   ruff, mypy, and pytest with coverage.
3. Run dependency and secret checks: pip-audit for base runtime and MCP extra,
   Bandit over source and scripts, Bandit high-severity scan over tests, gitleaks,
   and trufflehog verified-only.
4. Read high-risk Python trust boundaries: OAuth and token custody, MCP auth and
   policy configuration, allowlist parsing, tool registration, file sharing and
   permissions, access proposals, local export/apply paths, backend API calls,
   desktop config, and demo execution.
5. Read supply-chain controls: GitHub workflows, Dependabot, release split,
   Trusted Publisher checks, lockfile workflow, packaging metadata, and scanner
   config.
6. Write this audit record under `docs/security-audits/`, including findings,
   a frozen threat-model snapshot, issue handoff, and raw scanner JSON.
7. Regenerate and validate the generated security-audit index.

## 3. Command Results

The default shell virtualenv was not the right verification environment for this
repo: mypy and pytest failed there because the ambient MCP package did not match
the project. The project `.venv` was then used for authoritative checks.

| check | result |
|---|---|
| `.venv/bin/ruff check src tests scripts` | passed |
| `.venv/bin/mypy` | passed: `Success: no issues found in 57 source files` |
| `.venv/bin/python -m pytest -q --cov --cov-report=term-missing` | passed: `1661 passed, 14 skipped`; total coverage `89.08%`, above `fail_under = 85` |
| clean runtime `pip-audit --skip-editable` | passed: 50 dependencies, 0 known vulnerabilities |
| clean `.[mcp]` extra `pip-audit --skip-editable` | passed: 72 dependencies, 0 known vulnerabilities |
| Bandit over `src scripts` | 22 findings, all in `scripts/`; 18 low and 4 medium; source package had no findings |
| Bandit high-severity scan over `tests` | passed: 0 findings |
| gitleaks over history | 2 findings, both the same false positive in `tests/test_labels.py:95` |
| trufflehog filesystem `--only-verified` | passed: 0 verified secrets |
| `scripts/check_controls.py` | public release controls passed; branch-protection check returned HTTP 401 without `CONTROLS_TOKEN` |
| `scripts/check_release_history.py` | passed: changelog, tags, and PyPI agreed |
| `scripts/check_doc_claims.py --strict` | passed with the expected `CSA_GW_ALLOWLIST_READ=*` warning |
| `scripts/gen_audit_index.py --check` before this record | passed: existing index current |

Raw scanner outputs are kept in:

- [`artifacts/pip-audit-runtime.json`](artifacts/pip-audit-runtime.json)
- [`artifacts/pip-audit-mcp-extra.json`](artifacts/pip-audit-mcp-extra.json)
- [`artifacts/bandit-src-scripts.json`](artifacts/bandit-src-scripts.json)
- [`artifacts/bandit-tests-high.json`](artifacts/bandit-tests-high.json)
- [`artifacts/gitleaks.json`](artifacts/gitleaks.json)
- [`artifacts/trufflehog-filesystem.json`](artifacts/trufflehog-filesystem.json)

See [`FINDINGS.md`](FINDINGS.md) for the actionable findings and cleared items.
