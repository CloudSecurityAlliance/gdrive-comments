# Findings

## 4. Actionable Findings

### CODX-2026-09-01-01: Stale default-posture text remains in model-facing and operator-facing surfaces

Severity: medium  
Type: hardening  
Confidence: confirmed-by-read  
Status: open

The current policy default is permissive: `DEFAULT_ENABLED =
frozenset(ALL_CAPABILITIES)` at `src/csa_google_workspace/policy.py:101`, and
`DEFAULT_DISABLED` is empty at `src/csa_google_workspace/policy.py:115`.
The MCP allowlist parser also treats unset or blank read/modify allowlists as
all files: `_scope_from_env()` returns `Listing(all_files=True)` at
`src/csa_google_workspace/mcp/_config.py:237-240`.

Several active source and documentation surfaces still describe the old posture:

| location | stale claim |
|---|---|
| `src/csa_google_workspace/policy.py:369-374` | file lifecycle capabilities are "OFF by default" and must be named explicitly |
| `src/csa_google_workspace/policy.py:444-448` | `Policy.default()` is permissive, but the MCP server "fails closed when nothing is configured" |
| `src/csa_google_workspace/mcp/_tools/files.py:149-150` | update, trash, and share are "OFF by default" |
| `src/csa_google_workspace/mcp/_tools/files.py:174` | `file.update` is off unless enabled |
| `src/csa_google_workspace/mcp/_tools/files.py:201` | `file.trash` is off unless enabled |
| `src/csa_google_workspace/mcp/_tools/files.py:224-225` | `file.share` is off unless enabled |
| `src/csa_google_workspace/permissions.py:7-12` | `file.share` is off unless named explicitly |
| `src/csa_google_workspace/backend.py:733-735` | create-permission path is off by default |
| `src/csa_google_workspace/_export.py:52-54` | `comment.delete` is off in every profile but full |
| `src/csa_google_workspace/demo/_plan.py:388-391` | sharing is off unless somebody enabled it |
| `src/csa_google_workspace/mcp/_tools/demo.py:15-18` | a default editor profile cannot trash anything |
| `README.md:599` | `delete_comment` is off unless the operator enables `comment.delete` |
| `SECURITY.md:159-162` | the MCP server fails closed as a configured artifact |

The suite currently preserves at least part of the stale behavior:
`tests/test_file_lifecycle.py:192-197` asserts that the registered MCP tool
descriptions contain "off unless an operator" for `update_file`, `trash_file`,
and `share_file`, even though `tests/test_file_lifecycle.py:93-105` correctly
asserts that sharing is now on by default.

Impact: an LLM client reads MCP tool descriptions and resources as part of its
operational context. If those descriptions understate which destructive or
sharing tools are currently reachable, the model and the operator can make a
wrong safety decision before any Python policy gate is reached. The code gate
still enforces configured capabilities and file scope, so this is not a bypass
of `PolicyBackend`; it is a misleading authority statement on a model-facing
surface.

Recommended remediation:

1. Sweep active source docstrings, README, SECURITY.md, and demo narration for
   "off by default", "off unless enabled", and "fails closed when unset" claims.
2. Replace stale claims with the current posture: capabilities are enabled by
   default unless narrowed; Drive ACLs still decide; malformed allowlists fail
   closed; `describe_configuration` is the runtime source of truth.
3. Replace `tests/test_file_lifecycle.py:192-197` with a regression test that
   fails when tool descriptions contradict `DEFAULT_ENABLED`,
   `DEFAULT_DISABLED`, or `_scope_from_env()`.
4. Treat the root `THREAT_MODEL.md` stale rows as a living-model update to file
   after this audit merges; frozen prior audit snapshots should remain frozen.

### CODX-2026-09-01-02: Demo share recipient can be reused silently in unattended mode

Severity: medium  
Type: hardening  
Confidence: confirmed-by-read  
Status: open

The CLI demo takes a share recipient from the ambient environment:
`share_with = env.get("CSA_GW_DEMO_SHARE", "")` at
`src/csa_google_workspace/demo/_cli.py:60-62`. `--share` can override it, but an
environment value is otherwise enough.

When `--auto` is passed, confirmation is disabled: the runner is constructed
with `confirm=None if auto else _ask` at `src/csa_google_workspace/demo/_cli.py:90-91`.
The runner skips a gated step only when the capability is absent at
`src/csa_google_workspace/demo/_runner.py:73-77`. Since the current default
capability set includes `file.share`, the share step is reachable on a default
install.

The share step itself uses the carried address and suppresses the Drive
notification:
`src/csa_google_workspace/demo/_plan.py:384-391` calls `share_file` with
`role: "reader"` and `sendNotification: False`. `_require_share()` skips only
when the address is empty (`src/csa_google_workspace/demo/_plan.py:50-55`).

This becomes easier to keep around than intended because `configure` carries
every `CSA_GW_*` environment variable except `CSA_GW_CLIENT_SECRETS` into the
Desktop config (`src/csa_google_workspace/mcp/_desktop.py:37-42`,
`src/csa_google_workspace/mcp/_desktop.py:90-92`, and
`src/csa_google_workspace/mcp/_desktop.py:95-103`). The demo CLI is not launched
by the Desktop server path, but the project already treats that config as the
place where CSA_GW policy state persists. Carrying a demo-only share recipient
there increases the chance that a value meant for one run survives as ambient
state.

Impact: an unattended demo can share real demo-created Drive files with a
recipient without a per-run confirmation and without a Drive notification. The
blast radius is bounded to files the demo creates, and cleanup later attempts to
revoke the grant, so this is hardening rather than a direct arbitrary-file
exfiltration. If the run is interrupted after sharing and before cleanup, access
can remain until a human notices.

Recommended remediation:

1. Stop carrying `CSA_GW_DEMO_SHARE` into Desktop config, or maintain an explicit
   denylist of demo-only environment variables in `_desktop.carried_env()`.
2. Require an explicit `--share EMAIL` for unattended sharing, or print and
   require confirmation before using an env-derived recipient even when
   `--auto` is set.
3. Consider using `sendNotification=True` for demo grants, or making silent demo
   sharing a separately named opt-in.
4. Update the T29 entry in the living `THREAT_MODEL.md`; its current mitigation
   says `file.share` is default-disabled, which no longer holds.

## 5. Investigated And Cleared

### CODX-INFO-2026-09-01-01: gitleaks reports a false positive in test history

Severity: informational  
Type: scanner-noise  
Confidence: confirmed-by-read  
Status: false-positive

`gitleaks detect --source . --redact` reported two findings for the same test
fixture line, `tests/test_labels.py:95`, across two historical commits. The
string is a fake activation URL and Google API service name used in a unit test:
`drivelabels.googleapis.com` plus `http://x`. It is not a credential. Trufflehog
verified-only found zero secrets.

Recommended remediation: if gitleaks is added to CI, add a narrow allowlist for
this fixture so the scanner can stay failing-on-real-findings without blocking
on known test prose.

### Script Bandit warnings

Bandit reported 22 findings in `scripts/` and none in `src/`. The script findings
were reviewed and cleared as non-exploitable in this audit context:

- fixed `sys.executable -m pytest` / `git` subprocess invocations in
  `scripts/check_doc_claims.py`, `scripts/check_release_history.py`,
  `scripts/gen_audit_index.py`, and `scripts/mcp_smoke.py`;
- fixed HTTPS `urlopen` calls to PyPI/GitHub APIs in release/control scripts;
- false-positive hardcoded-secret strings in test/doc-claim prose;
- cleanup `try/pass` blocks where best-effort cleanup failure should not mask
  the primary result.

### OAuth and token custody

Manual review did not find a token-custody vulnerability. The token path is
separate for read-only and read-write scopes, write-scope tokens are refused in
read-only posture, token files are written with private permissions and
no-follow semantics, the MCP server path uses only cached credentials, and the
interactive OAuth flow uses loopback, state, and PKCE.

### Spreadsheet formula injection

Manual review did not find a formula-injection path in the current write/export
surfaces. MCP cell writes use `RAW`; caller-supplied `valueInputOption` is not
accepted as a tool parameter. CSV export escapes formula-leading characters and
XLSX export writes values as text cells.

### Supply chain and release

Manual review did not find a release-token broadening issue. The release workflow
separates build and publish, pins actions by SHA, grants `id-token: write` only
in the publish job, uses the protected `pypi` environment, and publishes only
downloaded artifacts without checking out or executing project code in the
publish job. The local branch-protection API check needs an admin-capable token
to verify status checks and returned HTTP 401 in this environment.
