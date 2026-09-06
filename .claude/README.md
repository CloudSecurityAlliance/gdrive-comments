# `.claude/settings.json` — why the claude.ai Google Drive connector is denied here

**Committed on purpose. It applies to anyone working in this repository, not just the test
machine.**

claude.ai ships its own hosted **Google Drive** connector. When it is live in the same session
as `csa-google-workspace`, two things go wrong, and neither announces itself:

1. **You stop testing this project.** A model asked to read a comment or a file has two tools
   that can do it. If it reaches for the hosted connector, the run is green and this library
   was never exercised — the exact "a passing suite exercising the wrong thing" failure the
   conformance rig exists to catch, one level up.

2. **It defeats the policy ceiling.** `README.md` already concedes this: the capability gates
   and the allowlist bind *this library's* calls, not another Drive client's. A second Drive
   client in the same session can do what this one was configured to refuse, so a test that
   proves "the allowlist refused it" proves nothing about the session as a whole.

`Gmail` and `Google Calendar` connectors are left alone — they do not touch Drive files, so
they cannot answer a question meant for this server. Deny them yourself if you want a stricter
machine; nothing here depends on it.

## This is a session-level control, not an account-level one

It stops a Claude Code session **in this directory** from calling those tools. It does not
disable the connector on your claude.ai account, and it does nothing about a browser tab. For
the dedicated test machine, `Setup-test-machine.sh` also checks for a live Drive connector and
says so, because a control you cannot see is one you cannot trust.
