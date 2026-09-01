# Issue Handoff

These are draft issues to file after the audit record lands. Links should point
back to the merged `FINDINGS.md` entries.

## 1. Correct stale default-posture text in model-facing tool descriptions and active docs

Labels: `security`, `documentation`, `mcp`

Body:

Audit `2026-09-01-01` found active source and documentation surfaces that still
say lifecycle/share/comment-delete capabilities are off by default or that the
MCP server fails closed when unset. The current runtime default is different:
`DEFAULT_ENABLED = frozenset(ALL_CAPABILITIES)`, `DEFAULT_DISABLED` is empty, and
unset read/modify allowlists mean every file.

See `docs/security-audits/2026-09-01-chatgpt-codex-gpt5/FINDINGS.md#codx-2026-09-01-01-stale-default-posture-text-remains-in-model-facing-and-operator-facing-surfaces`.

Acceptance criteria:

- Active source docstrings, README, SECURITY.md, demo narration, and MCP
  model-facing text no longer say destructive/share capabilities are off by
  default.
- Replacement text distinguishes current default-open posture from the
  still-true fail-closed invariant for unknown backend methods and malformed
  allowlists.
- A regression test fails if registered tool descriptions contradict
  `DEFAULT_ENABLED`, `DEFAULT_DISABLED`, or `_scope_from_env()`.
- The living root `THREAT_MODEL.md` is updated or explicitly marked superseded
  for rows that rely on old default-disabled assumptions.

## 2. Require explicitness for unattended demo sharing

Labels: `security`, `hardening`, `demo`

Body:

Audit `2026-09-01-01` found that `csa-google-workspace-mcp demo --auto` can use
an ambient `CSA_GW_DEMO_SHARE` recipient, call `share_file`, and suppress the
Drive notification. Since `file.share` is now enabled by default, an unattended
demo can share real demo-created files without a per-run confirmation.

See `docs/security-audits/2026-09-01-chatgpt-codex-gpt5/FINDINGS.md#codx-2026-09-01-02-demo-share-recipient-can-be-reused-silently-in-unattended-mode`.

Acceptance criteria:

- `CSA_GW_DEMO_SHARE` is not persisted by Desktop configuration, or demo-only
  variables are explicitly denied in `_desktop.carried_env()`.
- Unattended demo sharing requires explicit `--share EMAIL`, or env-derived
  recipients require an explicit confirmation before use.
- Silent demo sharing is either removed or split into an explicit opt-in.
- The living root `THREAT_MODEL.md` T29 mitigation no longer says `file.share`
  is default-disabled.

## 3. Add a narrow gitleaks allowlist for the Drive labels test fixture

Labels: `security`, `tooling`

Body:

Audit `2026-09-01-01` ran gitleaks over history and received two findings for
the same historical test fixture at `tests/test_labels.py:95`. The flagged value
is not a credential; it is a fake labels-service activation URL fixture. If
gitleaks is added as a required CI gate, add a narrow allowlist for that fixture
so the scanner can still fail on real leaks.

See `docs/security-audits/2026-09-01-chatgpt-codex-gpt5/FINDINGS.md#codx-info-2026-09-01-01-gitleaks-reports-a-false-positive-in-test-history`.
