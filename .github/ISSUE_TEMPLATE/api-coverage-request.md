---
name: API coverage we do not have
about: Ask for an endpoint we cannot reach from our own tenant — especially enterprise-tier
title: "coverage: "
labels: coverage
---

<!--
This project covers 100% of the API endpoints it can SEE AND TEST from its own Google tenant,
which is not an enterprise-tier account. So some endpoints are untested here — and we cannot
honestly say which are edition-gated, which need a domain admin, and which we simply have not
asked consent for, because the first barrier masks the rest: a missing scope refuses with
"insufficient authentication scopes" and hides whatever the next requirement would have been.

The blocker on wider coverage is VERIFICATION, NOT CODE. A single measurement from a tenant we
cannot reach is worth more than any amount of our reasoning — this project has been wrong three
times about what Google's documentation says, and right every time it measured.
-->

## What do you need to do that you cannot?

<!-- The task, not the method name, if you know one. "Which comments are assigned to me across
     a shared drive" tells us more than "we need permissions.list". -->

## Which endpoint, if you know it

<!-- e.g. `drive.files.modifyLabels`, or an Admin SDK / Vault call. Fine to leave blank. -->

## Your reach report

<!-- REQUIRED for anything we cannot test ourselves — it is the whole point of the issue.

     pip install csa-google-workspace
     python scripts/report_api_reach.py

     It reports SHAPES, NEVER CONTENT: method names, HTTP status codes, and boolean edition
     signals. No file ids, no titles, no email addresses, no domain names, no token, no paths.
     Read the output before pasting — that is why it is short. -->

```
paste here
```

## Tier and role

- Workspace edition (if you know it):
- Are you a domain administrator?

## Would untested coverage help?

<!-- We can ship an implementation we have never run against a real account, marked explicitly
     as untested — not working, not broken, UNKNOWN, and never reported as the first. If you
     are willing to be the one who tries it and tells us what happened, say so: that is the
     fastest route, and it makes you the measurement. -->

- [ ] Yes — ship it marked untested and I will report what happens
- [ ] No — I need something verified before I can use it
