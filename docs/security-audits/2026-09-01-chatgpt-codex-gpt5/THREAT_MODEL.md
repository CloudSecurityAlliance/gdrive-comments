# Audit Threat Model Snapshot

This is the threat-model snapshot produced by audit `2026-09-01-01`. It is not
the living repository threat model. Proposed living-model changes are listed in
[`ISSUES.md`](ISSUES.md).

## Assets

| asset | security property |
|---|---|
| OAuth refresh token and token path | confidentiality, integrity, least privilege |
| Google Drive files, comments, suggestions, labels, and permissions | confidentiality, integrity, availability |
| MCP tool descriptions and configuration resources | model-facing authority and operator decision quality |
| Local export/apply destinations and register files | local confidentiality, integrity, path containment |
| Release artifacts and PyPI Trusted Publisher flow | package integrity and provenance |
| Audit records and generated audit index | traceability and non-overstatement of coverage |

## Trust Boundaries

| boundary | input | control observed |
|---|---|---|
| LLM to MCP tool call | model-selected tool name and arguments | registered tool set, tool annotations, `PolicyBackend` gates, allowlists |
| Environment to policy | `CSA_GW_*` variables | parser rejects malformed allowlists, unknown profiles/capabilities fail, startup warnings describe wide scope |
| OAuth callback to local process | loopback redirect with code/state | state validation, PKCE, local-only listener, hardened token write |
| Drive API to model context | document text, comments, access proposal messages | instructions mark content as untrusted, repr redaction limits accidental logging |
| MCP/local filesystem | export and apply paths | bounded destination logic, no overwrite, zip/XML bounds, local read/write switches |
| GitHub Actions to PyPI | workflow jobs and artifacts | SHA-pinned actions, split build/publish, protected environment, OIDC only in publish |

## Threats And Audit Notes

| id | threat | status in this audit |
|---|---|---|
| TM-1 | Prompt injection in document/comment/access-proposal text induces a read, write, share, or delete. | Partially mitigated. Tool instructions call content untrusted, access-proposal grants default to reader and refuse owner, and policy gates still apply. Wide default capability and file scope make operator-side narrowing important. |
| TM-2 | Arbitrary file exfiltration through `share_file`. | Partially mitigated. `role="owner"` is refused and Drive ACLs/DLP remain authoritative, but `file.share` is enabled in the default capability set. Stale text that says otherwise is finding CODX-2026-09-01-01. |
| TM-3 | OAuth token exposure or accidental write-scope token use in read-only posture. | No finding. Token storage and scope separation were reviewed; read-only posture refuses write-scope tokens. |
| TM-4 | Local file overwrite, path traversal, or spreadsheet formula execution through export/apply/write paths. | No finding. Export avoids overwrite, CSV formula prefixes are escaped, XLSX text cell typing is enforced, and apply paths use dry-run defaults and bounded zip/XML parsing. |
| TM-5 | Supply-chain compromise through CI release token exposure or dependency vulnerability. | No finding. Base and MCP-extra pip-audit results were clean; release publish is split from build and OIDC is isolated to the protected publish job. |
| TM-6 | Model-facing descriptions understate reachable destructive or sharing authority after the default changed. | Open. CODX-2026-09-01-01. This affects operator and model decision quality, not the Python gate itself. |
| TM-7 | Demo run shares real files with a stale or ambient recipient. | Open. CODX-2026-09-01-02. Blast radius is demo-created files, but unattended and silent sharing should require stronger explicitness. |
| TM-8 | Secret committed in repository history. | Refuted for this run. Gitleaks hits were false positives in a test fixture; trufflehog verified-only found zero secrets. |

## Residual Risk

The largest residual risk is not missing Python input validation; it is alignment
between current defaults and the text an operator or model reads before taking
action. This codebase intentionally relies on Google Drive ACLs and operator
configuration as the outer controls. That design can be coherent, but it makes
stale capability/default descriptions security-relevant because those
descriptions are part of how a model chooses whether to act.
