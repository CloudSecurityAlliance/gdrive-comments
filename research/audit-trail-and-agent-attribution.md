# What Google's audit trail records when an agent acts — and what it cannot

**Date:** 2026-08-27 · **Method:** Google's own admin documentation and Workspace Updates
changelog, read directly. Nothing here is probed yet; the probe is named at the end.
**Status:** research note. Better than expected on attribution, with one gap that is probably
publishable.

---

## Why this exists

`SECURITY.md` frames this project as a **confused deputy**: third-party comment text reaching a
model that holds the user's own write-capable token. The multi-account spec then argued that a
*local* log cannot be evidence against a local attacker, because both run as the same POSIX user —
so the durable record must be **Google's**.

That raised the question this note answers: **when this server acts, what does Google actually
record?** Specifically, can anyone tell an agent's action from the same user's manual edit?

## What is recorded — verified from Google's documentation

**Drive log events carry app attribution.** From Google's
[Drive log events](https://knowledge.workspace.google.com/admin/reports/drive-log-events)
reference:

| Field | Google's description |
|---|---|
| **App ID** | *"OAuth client ID of the third-party app that performed the action"* |
| **App name** | *"The app that performed the action"* |
| **API method** | *"The API method used by the action … for example, `drive.files.export`"* |
| **Impersonation** | *"An application used domain-wide delegation to make a request on a user's behalf"* |
| **Agent info** | Agent ID, Agent name, Agent product |
| **User device info** | User device ID, OS version, device type (`DESKTOP_MAC`, `DESKTOP_WINDOWS`) |

Also present across Workspace logs: `originating_app_id`, described as the application that
performed the operation on behalf of a user, explicitly including third-party SaaS and
**endpoint applications running on the user's device** — which is what this server is.

**So the answer to the headline question is yes.** A CSA administrator can filter Drive log events
by App ID and see every action taken through this server, separated from the same user's manual
edits. That is a real audit property, it costs us nothing, and it is **unforgeable from the
client** — Google records the OAuth client server-side, so a compromised machine cannot alter or
suppress it. This is exactly the property a local log file cannot have.

**Rollout context.** The April 2026 Workspace Updates
[changelog](https://workspaceupdates.googleblog.com/2026/04/workspace-audit-logs-new-functionality-and-expanded-event-fields-in-the-admin-console.html)
records *Actor application info* expanding to more log types, plus the new *User device info*
attribute, rolling out from 2026-04-29. Google is actively widening app attribution.

**Worth noting: `Agent info` is not in that changelog.** It is on the live Drive log events
reference and absent from the announcement posts, so it is either newer than April or shipped
quietly. Either way, **Google has begun modelling "an agent did this" as distinct from "an app did
this"** — which is the most interesting single fact in this note.

## The four things it cannot record

This is where the research question is.

### 1. App ≠ agent ≠ session ≠ intent

App ID identifies the **OAuth client**, and that is all. Every action taken through this server, by
every user, with the same client, is one App ID. The log cannot distinguish:

- the user deliberately asking the agent to resolve a thread, from
- **a prompt injection inside a document** making the agent resolve the same thread

Same actor, same App ID, same API method, same minute. **The audit trail cannot see intent — and
intent is the entire content of the confused-deputy problem.** A perfect, tamper-proof,
provider-side log of a confused deputy's actions still does not tell you whose idea any of them
was.

That is not a Google shortcoming. No provider-side log can carry it, because the decision happened
in a model on someone's laptop. It is a genuine structural limit of audit-as-control for agentic
systems, and it deserves to be said plainly somewhere.

### 2. There is no way for a third-party agent to declare itself

`Agent info` exists as a slot. Nothing in the Drive API, in OAuth, or in MCP lets a third-party
agent **populate** it. There is no header, no request field, no `agent_id` parameter — so if
Google fills that field only for its own Gemini agents, third-party agents are structurally
second-class in the record: visible as an *app*, invisible as an *agent*.

**This is the publishable gap.** Enterprises are being told to govern AI agents, and the audit
trail they must govern them through has a field for agent identity that only the platform vendor
can write. Nobody appears to have written this up.

Adjacent prior art to check before claiming novelty: GitHub ships
[agentic audit log events](https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/agentic-audit-log-events)
for Copilot, and Google has separate
[Gemini Enterprise audit logging](https://cloud.google.com/gemini/enterprise/docs/audit-logging).
Both are **first-party agents in first-party logs**. The third-party case is the hole.

### 3. Attribution is automatic and unforgeable, therefore un-enrichable

The same property that makes App ID trustworthy makes it inert: because Google derives it
server-side from the credential, **we cannot add to it.** There is no way to annotate an action
with the session, the prompt that caused it, the human confirmation obtained, or which of the
three ways to work produced it. The client's richest context is exactly the context the durable log
cannot hold.

Which means, for us: **the local log and the provider log are not redundant, they are
complementary and neither is sufficient.** Google's has integrity and no intent; ours has intent
and no integrity. Saying only "the real record is Google's" was too simple.

### 4. Completeness depends on a choice the model makes

From the multi-account spec: an action taken with a personal account lands in **no corporate audit
log at all**. So the corporate record's completeness is decided per-call by which identity the
agent used — and if that choice is implicit, so is the gap.

This is the strongest argument for `account` being required and echoed, and it is an audit
argument rather than a usability one: **an audit trail whose coverage depends on an unlogged
runtime decision is not a trail.**

## Consequences for this project

- **A shared organizational OAuth client is an audit feature, not just a convenience.** One App ID
  for all CSA users gives an administrator a single filter for "actions via our MCP server", with
  the individual user still in the Actor field. A bring-your-own-client deployment gives every user
  a different App ID and is therefore **invisible in aggregate** — nobody can write that rule. The
  CSA client living in `CSA-Plugins` turns out to have an audit rationale on top of the ToS one.
- **`SECURITY.md` should state the division honestly** — Google's log has integrity and no intent;
  a local log has intent and no integrity; and neither answers "was this the user's idea?"
- **The App name is worth setting deliberately.** It is what an administrator reads. Whatever the
  OAuth client is called is what appears in CSA's audit log forever.
- **#145 gains a purpose it did not have**: a local log's distinctive value is precisely the intent
  context Google cannot record — which session, which prompt, whether a human confirmed. That is a
  better justification for it than "diagnostics", while still not making it evidence.

## The probe this needs

**Nothing here is verified against a live log.** Documentation describes fields; only a probe
establishes what is actually populated. `experiments/` is the place, and the questions are:

1. Does a Drive edit made through this server actually populate **App ID** and **App name**, and
   with what values?
2. Is **`API method`** populated for writes, or only for the download/content-access events the
   documentation mentions?
3. Is **`Agent info`** ever populated for a third-party OAuth client, or is it first-party only?
4. Does **User device info** appear for a local stdio server — which would make an unauthorized
   local MCP server detectable by device, a control nobody is using.
5. How long is retention, and is it long enough to matter for incident response?

Requires a Workspace admin account, so this is not runnable from a personal Google account.

## Paper shape, if it is worth writing

**"Agentic actions in enterprise audit trails: what providers record, what they cannot, and the
declaration gap."**

Findings that would carry it, in order of how much they surprised us:

1. Provider-side app attribution is **better than commonly assumed** — the "you can't tell an agent
   from a human" complaint is wrong at the app level, and the field has been there.
2. It is nonetheless **blind to intent**, permanently and structurally, which is precisely the
   dimension the confused-deputy risk lives in.
3. **Agent identity fields exist and third parties cannot write them.** First-party agents are
   audit-visible as agents; everyone else is visible only as software.
4. **Audit coverage can depend on an unlogged runtime decision** — which identity the agent chose —
   and multi-account AI tooling makes that common rather than exotic.

CSA is a reasonable venue and this is adjacent to
[#113](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/113)'s report, which
already plans to use this repo as a specimen.

---

## Sources

- [Drive log events](https://knowledge.workspace.google.com/admin/reports/drive-log-events) — the field list, including App ID, App name, API method, Impersonation, Agent info
- [OAuth log events](https://knowledge.workspace.google.com/admin/reports/oauth-log-events) — token grants and use, with `client_id`
- [Workspace audit logs: expanded event fields, April 2026](https://workspaceupdates.googleblog.com/2026/04/workspace-audit-logs-new-functionality-and-expanded-event-fields-in-the-admin-console.html)
- [Audit logs for Google Workspace, Cloud Logging](https://docs.cloud.google.com/logging/docs/audit/gsuite-audit-logging)
- [GitHub agentic audit log events](https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/agentic-audit-log-events) — first-party agent, first-party log
- [Gemini Enterprise audit logging](https://cloud.google.com/gemini/enterprise/docs/audit-logging) — same shape
