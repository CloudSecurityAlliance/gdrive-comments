# TODO / backlog

The feature roadmap (comments · content read/write · Sheets cell-mapping · Docs
suggestions read) is **complete and live-verified** — see `CHANGELOG.md`. This file
is the post-roadmap backlog: the phase-2 delivery layer (below), plus enhancements and
polish to the library itself (comments + content on Google Docs/Sheets/Slides), none of
the latter blocking.

Ordered by leverage-to-effort. Nothing here is committed to — it's a menu. Each item,
when picked up, follows the plan-then-execute rhythm (spec/plan under
`docs/superpowers/`, then TDD via `FakeBackend`). `CHANGELOG.md` is the shipped-work
ledger; the phase plans in `docs/superpowers/plans/` are the per-phase detail.

## Phase 2 — the built-in MCP server — ✅ SHIPPED (v0.2.0–v0.2.3, 2026-08-24/25)

`csa_google_workspace.mcp` is on PyPI: a local stdio server on MCP revision `2026-07-28`
(SDK `mcp>=2.1`), with **nine tools** carrying structured output and read-only/destructive
annotations, per-user OAuth via a separate `login` subcommand, and a CSA-branded consent page.
Spec: [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](docs/superpowers/specs/2026-07-23-mcp-server-design.md).

Built directly from the spec without a separate plan file — the spec's §10 phasing served as
the task list.

**Deferred from v1, deliberately:**

- [ ] **Content-write tools through MCP** — Docs `replace_text`/`insert_text`/`append_text`/
  `delete_range`, Sheets `update`/`append_rows`/`clear`, Slides `insert_text`. The library API
  has them; the MCP layer exposes comment writes only. **Blocked on file allowlisting below** —
  exposing document mutation to a model over a full-Drive token, with no per-file scope, is the
  confused-deputy scenario #82 describes.
- [ ] **Docs suggestions** (`list_suggestions`) and the `as_text(suggestions=…)` preview.
- [x] **Resources — the configuration ones, done 2026-08-25** (v0.11.0): `csa-gw://config`
  (effective policy, live) and `csa-gw://help/configuration` (the reference), plus a
  `describe_configuration` tool for clients that do not surface resources.
- [ ] **The document-text Resource and comment-triage Prompt** — both in the spec, neither built.
- [ ] **A launcher shim for Claude Desktop on macOS.** GUI apps inherit a minimal `PATH` where
  `python3` is the system 3.9, below the 3.10 floor — so Desktop fails where Claude Code works.
  Documented in the README's troubleshooting table; no fix yet.
- [ ] **Verify the PowerShell setup scripts.** `CSA-Plugins/internal-setup/*.ps1` and the
  `DesktopSetup` Windows hook have never been executed — they were written on a machine with no
  `pwsh`. A Windows colleague should not be the first to find out.

- [ ] **File allowlisting — scope a `Workspace` to specific files and operations.**
  ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) Listed here
  rather than in the library-internal section below because **it is arguably a phase-2
  dependency, not a parallel nicety.** The locked phase-2 decision is *read + write on by
  default*, hedged with tool annotations and `CSA_GW_READ_ONLY=1`. That hedge is all-or-nothing:
  the only choices an operator gets are "this agent may write to everything you can reach" or
  "nothing". An allowlist is the missing middle, and it is what makes write-on-by-default
  defensible rather than merely convenient.
  **Shape settled 2026-08-21**: an explicit **write-allowlist of Drive URLs** — read stays as broad
  as the credentials allow, only mutation is gated. The goal is damage containment rather than
  confidentiality: the agent already sees whatever the user sees, so what must be bounded is what
  it can *break*. Keyed on URLs because that is what people paste (`parse_file_id` normalises to
  IDs internally). And the list is **curated, not per-user** — e.g. the CSA WG document URLs —
  which means a volunteer installs the tooling and it is physically incapable of damaging anything
  outside the list, whether or not they understand why. That is a better story than per-user config,
  because it does not depend on the least-equipped person making a good decision.
  **Cheap to build**: every one of the 25 `Backend` Protocol methods takes `file_id` first, so a
  wrapping `AllowlistBackend` enforces uniformly with no changes to existing methods, composed
  through the documented `Workspace(backend=…)` seam. `read_only` is the precedent — the
  allowlist is its fine-grained sibling and the two should be one mechanism, not two.
  **The MCP server also answers the hard half.** #82 notes that session scoping only means
  something if it is monotonically narrowing *and* set by the host rather than callable by the
  guest — otherwise an agent just widens its own scope. **An MCP server session is exactly that
  boundary**: the server constructs the scoped `Workspace` per session, and the client has no
  in-band way to broaden it. So "session-level allowlisting" has a concrete home in phase 2
  rather than being an open question.
  **Requirement surface is captured in full on #82** so nothing is rediscovered mid-build. Summary
  of what must be considered: **two independent dimensions** — capability gating *at all* (write /
  create-comment / update / delete / resolve / accept-suggestion, each on-or-off globally) and
  **per-URL scope** for each capability that is enabled — with the composition rule that **global
  is a ceiling and per-file grants narrow, never widen**. Plus the parts that decide whether it is
  actually usable: **obtaining the URLs** (folder enumeration as a *generator* producing a
  reviewable committed list, never as a live rule — folder-as-rule reintroduces TOCTOU when someone
  drops a file in), **config ergonomics** (plain-text and diffable so it reviews like code, a
  reason field per entry so "why is this writable" is answerable in six months, URL forms accepted
  as pasted, validation on load), **fail-closed behaviour** for every failure mode including the
  no-policy-configured default, **operational lifecycle** (immediate revocation, optional expiry,
  dead-entry detection, and new-file creation which probably sits outside the list since it cannot
  damage anything existing), and **observability** — log allowed *and* denied with the matching
  rule, since denials are the security signal, plus a dry-run mode answering "what would this run
  touch" before it touches anything.
  **Driver**: CSA-Plugins#27 wants agentic read/edit/comment on live Google Docs authored by
  volunteers. The blocker there is not capability — this library already has it — it is that
  handing volunteers unscoped write access to their own Drive is not defensible. Prevention has
  to carry the weight, because Docs has no selective undo.

Deferred out of phase 2, recorded during the 2026-08-05 auth revision (spec §11):

- [ ] **Hosted / server-side login for the MCP server.** A remote, multi-user server (Streamable
  HTTP + the MCP OAuth 2.1 resource-server model, per-user token custody in a real secret store)
  is a **separate design**, not a flag on the local one — it inverts the token-custody model
  `SECURITY.md` is built around. v1 is local, self-hosted, single-user.
- [ ] **Credential provenance — decide whether CSA ships a verified OAuth client.** Users supply
  their own client secrets today, because full `.../auth/drive` is a *restricted* scope: a public
  CSA-owned client would need Google app verification **plus** an annual CASA third-party security
  assessment, and the API ToS forbid embedding credentials in an open-source project. This is a
  cost/ownership call, not an engineering one — `main()` reads `CSA_GW_CLIENT_SECRETS` either way,
  so it can land any time without redesign.

Note the scope shift: everything *below* this section is library-internal, but phase 2 is a
**delivery layer over** the library — it adds no document logic, only maps MCP primitives
onto the existing `Workspace` API.

## What 1.0.0 is, and what it is not

**1.0.0 is the local MCP server plus the library, with a stable API.** The hosted server is
**2.x** — different transport, different auth model, different threat model (its own section
below). Nothing about hosting belongs in a 1.0 gate.

The point of a 1.0 is a *promise*: this API will not change under you without a major bump. So
the gate list is not "everything good" — it is **everything whose absence would force a
breaking change later**, plus the minimum that makes calling it 1.0 honest.

### Gate A — parity, because a reader will check — ✅ CLOSED 2026-08-25

The eight tools the other two servers had and we did not. **All eight ship**; every tool either
server offers is now here under the same name and argument shapes. Kept in full rather than
collapsed to a tick, because the order these landed in was the point: the destructive three
arrived *after* the gate that turns them off.

- [x] **A1** `search_files`, `list_recent_files` — **done 2026-08-25** (v0.5.0). The account
      axis exists: `workspace.files` is a `FileCollection` returning `FileRef`s, per the
      structure spec. Live-verified. It was the biggest usability win here — a session no
      longer has to begin with a pasted URL.
- [x] **A2** `get_file_permissions` — **done 2026-08-25** (v0.6.0). A `PermissionsMixin`
      beside `CommentsMixin`, since permissions are the same shape as comments: one Drive API,
      identical across all three types. Adds `public` / `writers` roll-ups so the model does
      not have to derive them. Live-verified.
- [x] **A3** `create_file`, `copy_file` — **done 2026-08-25** (v0.13.0). Gated on
      `file.create`, which is in the default `editor` profile: there is nothing existing to
      damage, and the *new* file is not in the modify allowlist either, so `create_file`
      followed by `append_text` is still refused unless an operator lists it. `create_file`
      takes Markdown in `content` and lets Drive convert it into real structure. `copy_file`
      checks the **read** scope, not modify, because it reads a source — and the copy it
      produces has a new id, so copying cannot manufacture a writable duplicate of something
      unwritable. → **completed Google's 8.**
- [~] **A4** **#82 allowlisting** — **dimension 1 done 2026-08-25** (v0.7.0), dimension 2 open.
      - [x] **Capability gating.** `policy.py`: named capabilities, a `Policy`, and a
            `PolicyBackend` wrapper that **fails closed** — a `Backend` method with no declared
            gate is refused, not delegated, so a new method arrives *off*. `CSA_GW_CAPABILITIES`
            is the complete permitted list, not a delta, so it reviews like code. Default
            refuses the three that cannot be undone - edit a comment, delete a comment,
            share a file (regrouped on recoverability in v0.21.0; see A5). Cannot be
            widened in-band.
      - [x] **Per-URL scope** — **done 2026-08-25** (v0.8.0, split by access kind in v0.9.0).
            Two flat lists of document URLs held **in the environment** —
            `CSA_GW_ALLOWLIST_READ` and `CSA_GW_ALLOWLIST_MODIFY`, no file — matched by
            file id. **Both fail closed**: unset permits
            nothing, and `*` must be typed. Folder URLs are a **loud error**, not an inert
            entry. `search_files` results are filtered to the read scope. Denials log at
            WARNING.
      - [ ] **Still open in the basic form:** per-capability scope ("commentable but not
            editable" needs a structured value, which the flat list cannot express), optional
            expiry, dead-entry detection (an allowlisted file that has been trashed), and a
            **dry-run** answering "what would this run touch" before it touches anything.
            Note that any structured format has to stay *environment-shaped* — the decision
            that the policy lives in the client config, not in a file, is deliberate.
      - [x] **The no-allowlist default: decided and flipped** (v0.9.0). Unset is fail closed
            in the MCP server; `*` is the typed escape hatch. The library keeps a permissive
            default, because `from_credentials` is called by a developer who has made a
            decision while the server is configuration handed to a model.
      - [x] **~~Superseded by the broader model, eventually.~~** ✅ **Resolved by the item two
            above**, and the recommendation it made ("flip it at 1.0.0") was overtaken by
            actually flipping it in v0.9.0. Struck rather than deleted because it named a
            variable that no longer exists — `CSA_GW_ALLOWLIST=any` — and anyone who read this
            file earlier may still be looking for it. The current spelling is
            `CSA_GW_ALLOWLIST_READ` / `CSA_GW_ALLOWLIST_MODIFY`, and the escape hatch is `*`.
      - [ ] **Folders** — see the next section. Deliberately not attempted yet.

### What shipped is a first control, not the design

Worth stating plainly so nobody reads more into it than is there. v0.8–0.9 give **per-capability
gating plus two flat lists of document URLs**. That is enough to be concrete — a volunteer's
install is physically unable to change a document nobody listed — and it is enough to demonstrate
that the project takes the read→act path seriously. It is **not** a general authorization model.

A broader long-term design is being researched separately. Two properties of what is here should
survive into it, because they are what make it worth relying on at all: enforcement lives in a
**`Backend` wrapper**, so library embedders and MCP clients get the same guarantee from one
auditable place; and the policy **cannot be widened in-band**, because no tool changes it. Any
richer model that gives those up is a step backwards regardless of what else it adds.

### Folders in the allowlist — the design questions, unanswered

A folder URL looks like the obvious convenience: allowlist
`https://drive.google.com/drive/folders/1HXZ…` and let everything inside be writable. The
obvious implementation is *ancestor traversal*: on each access, `files.get(fileId,
fields="parents")` and walk up until an allowlisted folder appears or the root is reached.

**That works, and it is not safe, and the unsafety is not fixable by writing it more
carefully.** Recording why, plus everything else it drags in, so none of it is rediscovered
mid-build.

**1. Anyone who can add to the folder can grant write access.** This is the killer, and it is
why #82 already settled on *folder-as-generator, not folder-as-rule*. A WG folder may have
dozens of contributors. Any of them dropping a file in — or moving one in — silently extends
the agent's write scope to it. Worse, it works in reverse: someone copies a sensitive document
into the folder for convenience and it becomes agent-writable. The allowlist stops describing a
decision anybody made.

**2. Shortcuts break the traversal outright.** `application/vnd.google-apps.shortcut` is a file
whose parent is the allowlisted folder and whose `shortcutDetails.targetId` is a document
somewhere else entirely. Traversing the *shortcut's* parents answers "allowed"; the thing that
gets written is the target. Any traversal must resolve shortcuts and check the **target's**
ancestry, and must decide what to do when the target is unreachable. This is classic alias
confusion, and it is easy to implement without noticing.

**3. Multiple parents.** Drive has mostly moved to single-parent, but the API still returns
`parents` as a *list*, and older files can have several. If a file sits in folder A (allowed)
and folder B (not), "any allowed ancestor wins" makes the most permissive path the rule.
"All ancestors must be allowed" is defensible but surprising, and unenumerable in practice.

**4. Cost, and the cache that must not exist.** Traversal is an extra `files.get` per level per
access — for a document four folders deep, five calls before the write. The obvious fix is a
cache; but this project deliberately runs uncached (live multi-reviewer sessions), and a *security*
cache going stale is strictly worse than a data cache going stale: it means a revoked grant
still works for the cache's lifetime. Any caching here needs an explicit revocation story.

**5. Copies and shares.** A copy of an allowlisted document has a **new file id**, so under the
current flat list it is *not* writable. That is the right default and it should survive any
folder design. Note the asymmetry: id-based entries are immune to renames and moves (an entry
keeps pointing at the same document), whereas folder rules make a *move* into a silent grant and
a move out into a silent revocation — with no diff anywhere to review.

**6. Shared drives.** A file's ancestry terminates at a shared drive, not at "My Drive", and
`driveId` is a separate field. Traversal has to stop somewhere sensible, and "allowlist a whole
shared drive" is a much bigger grant than it reads as.

**7. Where does a newly created file sit?** `create_file` produces an id nobody listed. Today
`file.create` is `file_scoped=False`, because a new file cannot damage an existing one. With
folders in play the question sharpens: is a file the agent created inside an allowlisted folder
then writable? Saying yes lets the agent widen its own scope, one file at a time — which is
exactly the in-band widening the whole design forbids.

**The likely resolution, consistent with what #82 already settled:** keep the **flat id list as
the only enforcement primitive**, forever. Add folders as a **generator** — a command that
enumerates a folder *once*, emits the URLs it found with a comment saying where they came from,
and expects a human to commit the result. Then the TOCTOU disappears (the list is what was
reviewed, not what the folder currently holds), review remains possible (a `git diff` shows
exactly which documents were added), and enforcement stays O(1) with no extra API calls. The
cost moves to a process problem — the list must be regenerated when the folder changes — which
is a much better problem than a silent grant.

None of that is built. The questions above are the work.
- [x] **A5** `update_file`, `trash_file`, `share_file` — **done 2026-08-25** (v0.15.0), behind
      A4 as planned. Each has its **own** capability (`file.update`, `file.trash`,
      `file.share`), none is in any profile but `full`, and each also requires the file in the
      modify allowlist — so a default install cannot reach any of them. `update_file` is
      metadata only; `trash_file` is recoverable and there is no permanent delete anywhere in
      this library; `share_file` is the one call that can move data out of the organisation,
      which is why Google's own server declines to offer it. All three go through the **account
      axis** rather than `open()`, so they work on folders too. → **completed Claude's 11.**

      Two policy questions this raised, **both answered in v0.21.0** by regrouping the profiles
      on a single criterion — *can this be undone?*:
      - ~~`editor` has `file.create` and not `file.trash`, so it cannot clear up after itself.~~
        **`file.trash` moved into `editor`.** Trash is a 30-day bin the owner can see and
        restore from, so withholding it was withholding a *reversible* capability in order to
        produce *irreversible* litter in somebody's Drive. Wrong trade.
      - ~~`comment.delete` sits in `editor`.~~ **Moved to `full`, along with `comment.edit`.**
        Both are genuinely unrecoverable — Google keeps no comment edit history, and the soft
        delete strips content *and* author — so they belong with `file.share` rather than beside
        creating a comment. The old grouping had the default permitting the two irreversible
        operations while forbidding the reversible one.

      The regrouping exposed a **latent bug** in the demonstration: only capabilities that were
      off by default declared `requires`, so a `reader` or `commenter` profile already walked
      into refusals `demonstration_plan` was supposed to predict — sixteen of them, one at a
      time. `requires` is now derived from `TOOL_CAPABILITIES`, so a gated step cannot be
      unannotated.

**Still deliberately excluded from "parity":** their `read_file_content` covers 13 mime types
including PDF, Office and PNG/JPEG; ours covers the three Google-native types. Closing that
means parsing untrusted binary formats in-process, which is new attack surface and new
dependencies on the read path SECURITY.md calls the primary risk. Document the difference
instead. (Drive's own PDF/image → Doc conversion is not an option: it *creates a file*, so it
is not a read.)

### Gate B — the differentiator has to be reachable — ✅ CLOSED 2026-08-26

- [x] **B1 Content writes through MCP** — **done 2026-08-25** (v0.13.0), after A4 as required.
      `replace_text`, `append_text`, `update_cells`, `append_rows` and `insert_slide_text`, all
      behind the single `content.write` capability. "The only one of the three that can edit an
      existing document" is now true of the server as well as the library.
- [x] **B2 Docs suggestions through MCP** — **done 2026-08-26** (v0.20.0). `list_suggestions`
      returns them as objects (id, `insertion`/`deletion`, text) and `read_file_content` gained
      `suggestions="accepted"|"rejected"|"inline"`, which is the one that gets used: *"what would
      this document say if the edits were taken"* is the review question, and Google renders that
      preview server-side rather than us applying edits in our head.

      **Read-only, and the wording is the control.** The Docs API has no accept or reject
      endpoint, so the risk is not an exception - it is a model answering "done" to *"accept
      these"* when nothing happened. So the refusal is stated in the tool description, again in a
      `can_accept_or_reject` field of the result, and again in the `detail` string; a test asserts
      all three, because there is no API call to get wrong and therefore nothing else to check.
      Two smaller decisions: `tab` and `suggestions` together are **refused** rather than
      resolved (one is Sheets-only, one Docs-only, so honouring either would answer a different
      question), and there is deliberately **no `author` field** - Google exposes none, and a
      permanently-null field invites attributing an edit to nobody.

**Gate B is closed.** The library and the MCP server now expose the same capabilities; there is
no longer anything this project can do that a client cannot reach.

### Gate C — the part that literally *is* 1.0

- [x] **C1 A written API-stability and deprecation policy** — **done 2026-08-26** (v0.21.0):
      [`API-STABILITY.md`](./API-STABILITY.md). The **MCP tool surface is the contract** and the
      Python API is best-effort-but-serious, for a stated reason rather than by preference: a
      Python embedder breaks loudly, in their own test suite, having pinned a version; an MCP
      tool is called by a model reading a schema from a prompt written weeks ago, where the
      failure surfaces as *"I couldn't do that"* and sometimes with the message suppressed
      outright. The surface with the weaker feedback loop gets the stronger promise.

      Two things it settles that were not obvious: **which capability gates which tool is part
      of the contract** (moving a tool between capabilities silently changes what an existing
      config permits, so it is breaking with no name changed), and **profile membership is
      explicitly NOT** (they are curated sets, recurated in v0.21.0; name capabilities
      explicitly if you need an exact one).

      It also came with the **pre-1.0.0 API review** the policy is only meaningful with — see
      the v0.21.0 CHANGELOG entry for the three findings, two of which were defects that would
      have been permanent after 1.0.0.
- [ ] **C2 The flavour switch.** Restrict the server to Google's or the claude.ai connector's
      surface. It is a **config surface**, so its shape must land pre-1.0 even though the
      feature itself is optional. Registration-time filter — see the `_tools/` split.
- [ ] **C3 Decide the caching knob**, even if the default stays off. Caching is off *by design*
      (live multi-reviewer sessions make a self-invalidated cache actively wrong), but adding
      one later changes observable behaviour. Name the parameter now; leave it off.

### Gate D2 — release history and provenance

Housekeeping that only gets harder with time, and that a public 1.0 at a security organisation
should not skip. Prompted by noticing the changelog claimed versions nobody could install.

- [x] **Reconcile the changelog against reality** — done 2026-08-25. `v0.3.0` and
      `v0.4.0`–`v0.10.1` were development versions: bumped in code as each change landed, never
      tagged, never published, all shipped together as `v0.11.0`. `CHANGELOG.md` now says so at
      the top instead of implying eleven installable releases.
- [x] **Reconcile tags against PyPI** — done 2026-08-25, and it corrected this entry, which
      claimed 0.1.0 and 0.1.1 were untagged. **They were tagged**; the real discrepancy was that
      v0.1.0's changelog heading did not use the versioned format, so it read as unpublished.
      Now enforced rather than remembered: `tests/test_release_history.py` (offline, in CI) plus
      `scripts/check_release_history.py` for the three-way reconcile against tags and PyPI. It
      found the discrepancy on its first run, which is the argument for having it. Development
      versions stay untagged — a tag should mean released.
- [x] **PEP 740 attestations** — done 2026-08-25. They *are* attached: every artifact carries a
      bundle naming publisher `GitHub` and repository
      `CloudSecurityAlliance/csa-google-workspace`. The command to check one yourself, without
      asking us, is in `PROVENANCE.md`.
- [x] **Authorship stated** — done 2026-08-25 in [`PROVENANCE.md`](PROVENANCE.md): all non-bot
      commits are authored by Kurt Seifried, a large share of the content was AI-drafted under
      his direction and review, and **review is single-person** — which is the part that carries
      the weight, so it is named rather than implied.
- [x] **Decision index** — done 2026-08-25: [`docs/DECISIONS.md`](docs/DECISIONS.md). What was
      settled when, what evidence settled it, and which earlier belief it replaced. Corrections
      are rows of their own rather than edits, because being able to see that we believed
      something wrong is more useful than a clean record.
- [x] **Full-history secret scan** — done 2026-08-25 across 177 commits. **trufflehog: 0
      verified, 0 unverified.** gitleaks: one hit, triaged as a false positive — the
      `generic-api-key` rule firing on the entropy of a sentence containing
      `CSA_GW_INTEGRATION=1` — now allowlisted in `.gitleaks.toml` *with the reasoning*, so a
      real finding is not lost in noise. Both commands are in `RELEASING.md`'s pre-tag checklist.
- [x] **Yank policy** — done 2026-08-25, in [`PROVENANCE.md`](PROVENANCE.md#yanking). The bar is
      "installing this by accident is harmful", not "this is old": a leaked credential, data
      loss or corruption, a write the configured policy should have refused (the policy failing
      *open*), or an artifact not matching its tag. Not for an outdated surface or embarrassment.
- [ ] **Consider `Assisted-by:` trailers going forward.** `PROVENANCE.md` states the division of
      labour at project level; per-commit attribution would make it greppable. Deferred because
      it is only useful if applied consistently, and retrofitting 113 commits is not worth a
      history rewrite.
- [ ] **Add `scripts/check_release_history.py` to CI**, guarded so an unreachable PyPI is not a
      failure. Today it is a pre-tag manual step, which means it runs when someone remembers.

This overlaps **C1** (the API-stability and deprecation policy): both are about what the project
owes someone who depends on it. C1 says what will not change; this says what did.

### Gate D — the unglamorous ones that will bite a colleague

- [ ] **D1 Run the PowerShell scripts on real Windows.** `CSA-Plugins/internal-setup/*.ps1` and
      the `DesktopSetup` hook have **never been executed** — written on a machine with no
      `pwsh`. A colleague should not be the first to find out.
- [ ] **D2 Claude Desktop on macOS.** GUI apps inherit a minimal `PATH` where `python3` is the
      system 3.9, below our 3.10 floor, so Desktop fails where Claude Code works. Documented in
      the README; unfixed. Half our intended clients are Desktop.
- [ ] **D3 `Location.tab`, or an explicit limitation.** Multi-tab spreadsheets cannot
      disambiguate a comment's cell today. Either resolve it (`workbook.xml` + rels) or say so
      in `comments_by_cell`'s own description — a silently-wrong cell is worse than an absent one.

### Explicitly not 1.0

| Item | Why not |
|---|---|
| **Hosted server, `files.watch` push** | **2.x.** Different transport, auth model and threat model. |
| **13-mime-type reading** | Untrusted binary parsers on the primary-risk path. Document the gap. |
| **#7 approvals · revisions · changes** | Genuine differentiators, purely additive — 1.1, 1.2, 1.3. |
| **#8 Docs `batchUpdate` breadth** | A programme, not a release gate. Tables first, post-1.0. |
| **MCPB bundle for Desktop drag-and-drop** | Distribution polish; does not shape the API. |
| **`PlaywrightBackend`** | For the API-impossible ops. Its own major decision. |

### Decided 2026-08-25

**1.0.0 is a public release.** Local stdio MCP server, the Google/Claude flavour switch, and
#82 allowlisting — all three are gates, not stretch goals. **C2 (the flavour switch) is therefore
mandatory for 1.0, not a "should".**

Consequence to plan around rather than discover: public + full `drive` scope means **Google app
verification and an annual CASA assessment**. That is weeks of calendar time and a recurring
cost, and it is on 1.0's critical path — so start it in parallel with Gate A rather than after
Gate D. It is the one item whose schedule is not ours.

**`share_file` and `trash_file` both ship.** Built now; **#82 must land before 1.0.0.**

That leaves a window where destructive and exfiltration tools exist without per-file scoping.
Close the cheap half of it immediately: #82's requirement surface already has **two independent
dimensions** — global capability gating and per-URL scope — so ship both tools **behind a global
capability flag, default off**. That is #82's first dimension, not extra work, and it means no
default install can share or trash anything before the allowlist arrives. Per-URL scoping
follows with the rest of #82.

## Roadmap — nine subsystems, in order

**Six of the nine are done** (1, 3, 4a, 4b, 5a, 5b), and #2 shipped its first control. What is
left is #7 (approvals, revisions, changes+watch), #8 (Docs `batchUpdate` breadth), #9 (hosted
server), and the open remainder of #2.

Everything below this line was one item called "feature parity" until a code review showed it
is nine independent pieces with real dependencies between them. Each is its own spec → plan →
implement cycle; **do not try to plan them together.** At the granularity this project uses
(every task a failing test, a run, an implementation, a run, a commit) a combined plan runs to
several hundred steps and nobody executes it.

| # | Subsystem | Touches | Blocked on | Notes |
|---|---|---|---|---|
| ~~**1**~~ | ~~**Tool alignment**~~ — their names, argument shapes, and Claude's model-facing guidance | MCP layer only | — | ✅ **done 2026-08-25** (v0.4.0). |
| **2** | **File allowlisting** ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) | `Backend` wrapper | — | 🟡 **first control shipped** 2026-08-25 (v0.7.0–v0.10.0): capability gating, two fail-closed URL lists, profiles. It **did** land before 4 and 5, as required. Open: folders, per-capability scope, expiry, dead-entry detection, dry-run. See A4. |
| ~~**3**~~ | ~~**Discovery**~~ — `search_files`, `list_recent_files` | library: new axis on `Workspace` | — *(**not** 2 — see below)* | ✅ **done 2026-08-25** (v0.5.0). Biggest usability win: a session no longer begins with a pasted URL. Reads, so the write-narrow allowlist does not gate them — but `search_files` results **are** filtered to the read scope. |
| ~~**4a**~~ | ~~**File creation**~~ — `create_file`, `copy_file` | library: new axis | 3 | ✅ **done 2026-08-25** (v0.13.0). Gated on `file.create` after all — cheap, and it makes "may this install create files?" answerable. `create_file(content=…)` takes Markdown and lets Drive convert, which closes the document-pipeline loop. |
| ~~**4b**~~ | ~~**File mutation**~~ — `update_file`, `trash_file` | library: new axis | **2** | ✅ **done 2026-08-25** (v0.15.0), after 2. Rename/move and trash an *existing* file, each behind its own capability, neither in any profile but `full`. |
| ~~**5a**~~ | ~~**Permissions read**~~ — `get_file_permissions` | library | — | ✅ **done 2026-08-25** (v0.6.0). A read, so not gated. Adds `public` / `writers` roll-ups. |
| ~~**5b**~~ | ~~**Sharing**~~ — `share_file` | library | **2** | ✅ **done 2026-08-25** (v0.15.0), after 2. Still an exfiltration primitive and still one Google's own server declines to ship — which is why it needs `file.share` named explicitly, defaults to notifying the recipient, and refuses ownership transfer. |
| ~~**6**~~ | ~~**Format breadth**~~ — Markdown, PDF, Office, ODF, EPUB (**not** images) | `export` plumbing + a format table | — | ✅ **done 2026-08-25** (v0.4.0), with `_formats.py` and `download_file_content`. |
| **7** | **Differentiators** — `approvals`, `revisions`, `changes`+`watch` | 3 new API surfaces | — | Own brainstorm each. `approvals` is the most on-mission thing found. |
| **8** | **Docs `batchUpdate` breadth** — 37 unused request types | library | — | A programme, not a plan. Tables first. |
| **9** | **Hosted server** — unlocks `files.watch` push, and removes install/OAuth-client/login for everyone | new transport + auth + custody | **2**, and a CASA decision | Largest item here, and almost all of it is security rather than features. Own section below. |

### Correction (2026-08-25): #2 gates less than the table used to say

The table read "#3 blocked on 2" and "#5 blocked on 2". That was written before #82's shape was
settled, and the settled shape makes it wrong. #82 is **write-narrow**: *read stays as broad as
the credentials allow, only mutation is gated*, because the goal is damage containment, not
confidentiality — the agent already sees whatever the user sees.

Sort the eight parity tools by *whether they can damage something that already exists* and the
dependency falls out:

| Tool | Kind | Gated by #82? |
|---|---|---|
| `search_files`, `list_recent_files` | read | **no** |
| `get_file_permissions` | read | **no** |
| `create_file` | creates a new file | **no** — nothing existing to damage |
| `copy_file` | reads one, creates a new one | **no** |
| `update_file` | mutates an existing file | **yes** |
| `trash_file` | destroys | **yes** |
| `share_file` | exposes | **yes** |

**Those last three are exactly the three Google's own server omits.** So the two parity targets
have very different costs:

- **Google's 8 → five more tools, no #82 dependency.** Startable immediately.
- **Claude's 11 → three more on top, every one gated on #82** — and every one a tool Google's
  team looked at and chose not to ship.

What #2 still gates, unchanged: **content writes through MCP** (the library has them; the server
does not), plus `update_file` / `trash_file` / `share_file`.

### Why #2 must still come before the mutating half — and it is not only the security argument

**Every one of `Backend`'s 22 methods takes `file_id` as its first parameter.** That uniformity
is precisely what makes #82's `AllowlistBackend` trivial: wrap the backend, `policy.check(file_id,
op)`, delegate. No changes to existing methods.

The new operations break that shape:

- `search_files(query)` — **no `file_id` at all**, and it discloses titles and content snippets,
  which is information leakage even with nothing opened
- `list_recent_files()` — no `file_id`
- `create_file(title, content, parent_id)` — no `file_id`; it *produces* one
- `copy_file(file_id, …)` — has one, but also produces a new one

So #82 is not a security chore that can be deferred; it is **a schema decision with a
deadline.** Design the policy while 22 methods are uniform and the exceptions are deliberate.
Add discovery and creation first and the policy has to be retrofitted around them.

### First step — **shipped 2026-08-25** (v0.4.0)

**#1 + #6 together.** Done. It: ships the naming alignment and the transferability that
makes the flavour switch possible, adds format breadth almost for free, and leaves `mcp/` split
into a `_tools/` package — a shape that can absorb the rest. `server.py` is 265 lines with 10
tools today; the next dozen tools need that split regardless.

- Plan: [`docs/superpowers/plans/2026-08-25-tool-alignment-and-format-breadth.md`](docs/superpowers/plans/2026-08-25-tool-alignment-and-format-breadth.md)
- Shape it lands in: [`docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md`](docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md)

Two corrections that came out of writing it, both from probing rather than reading:

- **#6 is not quite "no library change".** It needs a small one — a per-type export-format
  table, because the formats genuinely differ (a Doc exports Markdown; a deck exports
  PDF/PPTX/ODP/text and nothing else). One shared enum would hand two thirds of callers an
  unfixable 400. Library, not delivery layer: it is domain fact, and library users want the
  same guard.
- **"images" was wrong.** Only *drawings* export PNG/JPEG/SVG, and the library cannot open a
  drawing. See [`experiments/export-formats/RESULTS.md`](experiments/export-formats/RESULTS.md).

### Why #6 is worth more than "a few more mime types"

`text/markdown` export is Drive's own conversion, so headings, lists, tables and links survive —
unlike `as_text()`, which is text runs only. That turns a Google Doc into a usable **source**
for a Markdown toolchain rather than a dead end, and CSA already has the toolchain: the internal
**`document-pipeline`** plugin (v2.3.1) takes *Markdown → tagged PDF/UA-1* with a design-rule
preflight, composition review, citations and CSA brand styling. **A public version is planned**,
which is what makes this worth designing around rather than treating as one org's convenience.

Drive also *imports* `text/markdown` into a Doc, so the loop closes:

    Google Doc --export text/markdown--> document-pipeline --> branded, accessible PDF/UA-1
         ^                                                                 |
         +----- import text/markdown (#4 create_file) <--- revised source -+

Draft and review where the comments are, typeset where the brand rules are, put the result back
where it can be reviewed again. The export half is #6 and lands now; the import half is #4 —
`create_file` should accept `text/markdown` and let Drive convert, rather than uploading plain
text and losing the structure.

## Hosted MCP server — wanted, and a large piece of work

Wanted for real, not hypothetically: a hosted server is what unlocks **push notifications**
(`files.watch`), reacting the instant a comment appears rather than sweeping on a timer — and it
removes the install, the per-user OAuth client, and the `login` step for everyone.

It is also the single largest piece of work on this roadmap, and almost all of it is security
rather than features. Recording that honestly now, so nobody later mistakes it for "the same
server, on a box".

### Why it is not just a transport change

The local server has exactly one user, whose credentials live on their own machine. A hosted one
holds **per-user Google refresh tokens for many people** — each of which is full read/write/delete
on that person's entire Drive. `SECURITY.md` calls a single such token the crown jewel; this is
the crown jewels, plural, in one place, reachable from the internet.

### Inbound auth — the part MCP actually specifies

This is where MCP's OAuth framework finally applies: HTTP transports authenticate the *client to
the server*, which the stdio server deliberately skips.

- [ ] OAuth 2.1 **resource server**: validate every bearer token, reject anything not issued for
  us (RFC 8707 audience binding). **Token passthrough is explicitly forbidden** by the spec.
- [ ] Protected Resource Metadata (RFC 9728) + authorization-server discovery, so clients can
  find the AS. `WWW-Authenticate` on 401 with a `scope` hint.
- [ ] Client registration: **Client ID Metadata Documents** preferred; DCR is deprecated as of
  revision `2026-07-28` and kept only for compatibility.
- [ ] PKCE `S256`, mandatory. Refuse to proceed if the AS does not advertise
  `code_challenge_methods_supported`.
- [ ] **RFC 9207 `iss` validation** — new in `2026-07-28`, and required before an authorization
  code is sent to any token endpoint.
- [ ] Insufficient-scope handling: `403` + `WWW-Authenticate` with the scopes needed, so clients
  can step up rather than fail.

### Outbound Google auth — the part nobody specifies

- [ ] **Two token systems, never conflated.** The MCP client's token authenticates them *to us*;
  a separate per-user Google token authorizes *us to Google*. Mixing them is the confused-deputy
  vulnerability the spec names.
- [ ] Per-user Google refresh tokens in a real secret store, encrypted at rest, **isolated per
  user**. `Workspace.from_credentials(creds)` is already the entry point for this; the token file
  is not.
- [ ] Key management and rotation; revocation on offboarding that actually takes effect.
- [ ] **Reject domain-wide delegation** as the shortcut. A DWD service account can impersonate
  anyone in the org — a single key with more authority than every user token combined.

### Multi-tenancy

- [ ] One `Workspace` per request/user, never shared — the rule `SECURITY.md` already states,
  now load-bearing rather than advisory. `googleapiclient` clients are not thread-safe.
- [ ] No cross-user bleed in any cache (the `Sheet` cell-map cache is per-instance today; keep it
  that way).
- [ ] Per-user rate limiting and quota attribution, not global.
- [ ] Audit log of every mutation, attributed to a user, so a hijacked action is detectable after
  the fact.

### The push webhook itself

- [ ] Verified domain + valid certificate — Drive will not deliver otherwise.
- [ ] Validate the channel token on every delivery; treat the endpoint as **unauthenticated and
  hostile** until it is.
- [ ] Channel lifecycle: expiry, renewal, and cleanup of channels for revoked users.
- [ ] A public endpoint is new attack surface on a service holding many people's Drive tokens.
  Rate-limit and monitor it accordingly.

### And the thing that gets worse, not better

- [ ] **File allowlisting ([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) matters more here.**
  Prompt injection through document content is the named primary risk; a hosted server runs that
  read→act path for many users continuously and unattended. The mitigation that does not depend
  on a model behaving well is the only one that scales.
- [ ] Public + full `drive` scope means Google **app verification plus an annual CASA
  assessment**. Real recurring cost, and a decision to make before building rather than after.

### Prior art in-house

CSA has already worked most of this shape out once: `CINO-Customer-360`'s
`docs/IT-SETUP.md` is a runbook for exactly this deployment — a FastMCP server behind an
**Internal** Google OAuth consent screen, secrets in AWS Secrets Manager, a Cloudflare Tunnel
hostname for the public surface, and Cloudflare Access in front of it. Start there rather than
from scratch. Two caveats: the tunnel is **specified but not deployed** there (`cloudflared` was
removed in its V1 — "we run no inbound web surface"), and its OAuth is `openid email profile`
only, i.e. *identifying* the user to the service. That is the inbound half. Holding a full-Drive
token per user on their behalf is the half nobody at CSA has built yet.

## Flavour switch — restrict this server to Google's or Claude's surface

- [ ] **`CSA_GW_FLAVOUR=google | claude | full`** (default `full`). Registers only the tools the
  chosen server exposes, under **their** names, with **their** descriptions and argument shapes.

  Why it is worth building:
  - **A predictable, smaller surface on request.** `google` is 8 tools with no share, no trash,
    no rename/move — a materially safer profile, chosen by a vendor who could have exposed more.
  - **Drop-in substitution.** Anyone already prompting against those servers keeps working;
    switching costs nothing and can be reverted.
  - **It forces the alignment work anyway.** Same names, same parameters, same descriptions is
    exactly what makes tools transferable between servers, whether or not the switch is used.

  Prerequisite: implement the overlapping tools with matching names and argument shapes
  (see the coverage section below). The verified detail that matters — the tool *names and
  parameters* are identical between Google's and Claude's; only the *descriptions* differ, with
  Claude's carrying extra model-facing guidance (e.g. "do not put document-type words inside
  `title`/`fullText` clauses"). Copy that guidance: it exists because models get it wrong.

- [ ] Decide what `full` says about itself. A flavour that is a superset of both should be
  explicit in its server description that it can edit documents and hold full-Drive scope, so
  nobody arrives from a read-mostly connector and assumes read-mostly behaviour.

## Underlying API capability inventory — what we could build

Enumerated from the discovery documents (see
[`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)).
This is the honest ceiling of the Python client, not a plan — but several items are closer to
"help people get work done" than more file management would be.

### Drive v3 — exposed by nobody, including us

- [ ] **`approvals`** — a **document review workflow already in the API**, adjacent to the
  comment workflow this project owns. The strongest item on this list. Ships as four tools:
  `list_approvals` (`approvals.list`/`get`), `start_approval` (`approvals.start`),
  `respond_to_approval` (`approve`/`decline`/`comment`), `reassign_approval`
  (`reassign`/`cancel`). Worth its own brainstorm: an approval is a *state machine*, unlike
  every tool shipped so far, and the library has no precedent for modelling one.
- [ ] **`revisions`** — `list`, `get`, `update` (`keepForever`), `delete`. **Version history:**
  read a prior version, diff two revisions, pin one. Obvious pairing with suggestions review.
- [ ] **`changes`** — `getStartPageToken`, `list`, `watch`. Incremental sync: the correct answer
  to "sweep my documents" instead of re-reading everything, and it directly addresses the
  autonomous-sweep cost `SECURITY.md` worries about.
- [ ] **`files.watch` / `changes.watch`** — push notification. **Planned, for the hosted
  server** (see its own section below), not for local stdio: Drive push requires a publicly
  reachable HTTPS endpoint on a *verified domain*, which a process behind NAT cannot be.
  `changes.list` polling covers the same ground locally until then. This is a genuine want —
  reacting the moment a comment lands is a different product from sweeping on a timer.
- [ ] **`files.modifyLabels` / `listLabels`** — Drive labels, i.e. classification and data
  governance. Plainly relevant to CSA's own work.
- [ ] `permissions.*` (full: list/create/get/update/delete) — **gated on
  [#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)**, see below.
- [ ] `accessproposals` — resolve "can I have access?" requests.
- [ ] ~~`drives.*` — shared drive administration.~~ Out of scope: it does not help anyone
  review a document.
- [ ] ~~`files.delete` / `emptyTrash` — **permanent** deletion.~~ Out of scope for now. Both
  other servers stop at trash. That is a considered line, and an agent holding full-Drive scope
  with attacker-influenceable input in front of it is the worst possible holder of an
  irreversible delete.
- [ ] ~~`files.generateCseToken`~~ — client-side encryption tokens; no reviewer workflow needs it.

### Docs v1 — we use 3 of 40 `batchUpdate` request types

`documents.get` / `create` / `batchUpdate` are the only three methods; everything lives in the
request types. We use `replaceAllText`, `insertText`, `deleteContentRange`. Unused, grouped:

- [ ] **Tables** — `insertTable`, `insertTableRow`/`Column`, `deleteTableRow`/`Column`,
  `mergeTableCells`, `unmergeTableCells`, `pinTableHeaderRows`, `updateTableCellStyle`,
  `updateTableRowStyle`, `updateTableColumnProperties`. The largest single gap.
- [ ] **Styling** — `updateTextStyle`, `updateParagraphStyle`, `updateDocumentStyle`,
  `updateNamedStyle`, `updateSectionStyle`. Needed for anything that formats rather than types.
- [ ] **Structure** — `createHeader`, `createFooter`, `createFootnote`, `insertPageBreak`,
  `insertSectionBreak`, `createParagraphBullets`, `deleteParagraphBullets`.
- [ ] **Images** — `insertInlineImage`, `replaceImage`, `deletePositionedObject`.
- [ ] **Named ranges** — `createNamedRange`, `deleteNamedRange`, `replaceNamedRangeContent`.
  A stable anchor for repeated edits, which is a better primitive than raw indices.
- [ ] **Tabs** — `addDocumentTab`, `deleteTab`, `updateDocumentTabProperties`. Relevant to the
  deferred `Location.tab` work.
- [ ] **Rich inserts** — `insertPerson` (smart chips), `insertRichLink`, `insertDate`.

### Sheets v4 — we use 6 of 17 methods

- [ ] `values.batchGet` / `batchUpdate` / `batchClear` — one round trip instead of N.
- [ ] The `*ByDataFilter` variants — address ranges by developer metadata rather than A1.
- [ ] `developerMetadata.get` / `search` — durable per-range annotation that survives edits.
- [ ] `sheets.copyTo` — copy a tab between spreadsheets.
- [ ] `spreadsheets.create`.

### Slides v1 — we use 2 of 5 methods

- [ ] **`pages.getThumbnail`** — render a slide to an image. The cheapest route to letting a
  model actually *see* a deck.
- [ ] `pages.get`, `presentations.create`.

## Coverage vs the Drive MCP servers  *(was: "feature parity" — premise corrected)*

> **Read [`research/drive-mcp-servers-and-api-surface.md`](research/drive-mcp-servers-and-api-surface.md)
> before acting on this section.** Reading the actual tool schemas overturned the premise this
> item was written on. In brief: the connector's **`update_file` is metadata-only** (rename and
> move), and **neither server can edit an existing file's content at all**. So "parity" is the
> wrong goal — the overlap is small, the differentiator (content editing, comment lifecycle,
> cell mapping, suggestions) is already ours, and the real gaps are **discovery, file lifecycle,
> permissions and format breadth**. The research note also surfaces `approvals` and `revisions`,
> two Drive APIs neither server exposes, one of which is a document review workflow.

Match the built-in connector's tool surface so anyone moving between it and this server does
not have to relearn anything — same names, same argument shapes, comparable prompt
suggestions and description. **With one deliberate divergence: say plainly that this server
does full read/write and is correspondingly dangerous.** The connector is a read-mostly
convenience; this is a full-authority tool on the user's entire Drive.

Its surface is 11 tools. Names below are the connector's own, taken from its live schemas
rather than screenshots:

**Read-only (6)** — `search_files`, `list_recent_files`, `get_file_metadata`,
`get_file_permissions`, `read_file_content`, `download_file_content`

**Write/delete (5)** — `create_file`, `update_file`, `copy_file`, `share_file`, `trash_file`

### Google's own Drive MCP server is deliberately narrower — and that is the finding

[Google ships one too](https://developers.google.com/workspace/drive/api/reference/mcp)
(`drivemcp.googleapis.com`), and comparing the three is more instructive than either
target on its own:

| | Google's official | claude.ai connector | this server (proposed) |
|---|---|---|---|
| Transport | remote HTTP | remote | **local stdio** |
| OAuth scope | **`drive.file` / `drive.readonly`** | — | **full `drive`** |
| Tools | **8** | 11 | 11 + comments/content |
| `update_file`, `share_file`, `trash_file` | **absent** | present | proposed |

Two things stand out.

**Google omits exactly the three most dangerous tools.** They control the API and could
expose anything; they ship `copy_file` and `create_file` but no update, share or trash. That
is not an oversight, and it is worth treating as informed opinion about which operations are
safe to hand a model.

**Google never uses full-Drive scope.** `drive.file` is the *per-file* scope: an app sees
only files it created or the user explicitly picked. That is **allowlisting, enforced by
Google**, and it is why their server can be relaxed about the rest — it physically cannot
reach the document the user did not choose.

This project needs full `drive` for a real reason: it opens arbitrary files the user names by
URL, which `drive.file` cannot do
([`SECURITY.md`](SECURITY.md) §Scope breadth). That is a defensible trade, but it means **we
gave up the safety property Google gets for free, and file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)) is how we
buy it back in software.** Adding this tool surface on full-Drive scope with no allowlist
would make this server strictly more dangerous than either comparator, which is not a
position to ship from.

### This reverses a documented capability boundary — decide that first

`README.md` currently states, as a deliberate design boundary: *"No document discovery. You
hand the library a file id/URL; there is no `files.list`/search."* `search_files` and
`list_recent_files` are exactly that. So this is **a library change, not an MCP-layer
change**: it needs `Backend` methods, `FakeBackend` parity, the conformance guard, and a
decision to widen the library's scope. Not a tool-registration exercise.

**Correction to an earlier note here:** this file previously implied discovery was excluded
for a security reason. It was not. There is **no recorded rationale anywhere** — not in the
design spec, not in `SECURITY.md`, not in either MCP spec. The only justification on record is
circular ("the library is document-scoped, so every tool takes a file id/URL"), and the README
had it filed under *"what the Google APIs can't do"* next to two genuine impossibilities —
while its own workaround calls `files.list()` successfully. A scope choice had hardened into an
apparent constraint.

The honest case *for* keeping it out of the library: Drive query syntax, pagination, shared
drives and corpora are a sizeable surface to own forever, and this library's value is comments
and cell mapping, not Drive browsing. The case against: the documented workaround needs a
Drive client anyway, so the boundary saves a caller nothing but a loop — and for the MCP
server there is no host application to hand us a file id, which makes it the difference
between "ask about a document" and "paste a URL first". Both Google's own server and the
claude.ai connector lead with `search_files`.

Separately worth weighing, but as a *consequence* rather than the reason: `SECURITY.md` names
the **autonomous sweep** as the highest-risk use case because it ingests comments from many
documents, and search is what makes such a sweep easy. That argues for landing discovery
alongside #82, not for leaving it out.

### `share_file` is an exfiltration primitive — gate it behind #82

Worth separating from the other writes. `share_file(fileId, emailAddress, role)` grants an
**arbitrary email address** reader/commenter/writer access. Every other write tool modifies
content the user can see afterwards; this one silently hands an outsider a copy, and the user
may never notice.

Combined with the two things already true of this server — document text is
attacker-influenceable, and there is no file allowlist — an injected comment saying *"share
this with archive-bot@…"* is a working data-exfiltration path that no amount of tool-
annotation hinting prevents. **`share_file` should not ship before file allowlisting
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)), and
arguably wants its own explicit opt-in even then.**

`trash_file` is destructive but recoverable (Drive trash, not permanent delete), so it ranks
below `share_file` despite sounding worse.

### Checklist

- [ ] **Decide the discovery question.** Widen the library to support `files.list`/search, or
  decline parity on those two tools and say why in the README. Everything else waits on this.
- [ ] **Decide how much parity is actually wanted.** Google's 8 tools may be the better
  target than the connector's 11: matching Google means matching a vendor's considered
  judgement about what is safe to expose, and the three it omits are the three this project
  would most need to gate anyway. Full parity with the connector is a choice to be more
  permissive than either existing implementation, on a broader scope than either — worth
  making deliberately rather than by default.
- [ ] `search_files` — reuse the connector's **Drive query syntax** verbatim
  (`title contains`, `fullText contains`, `mimeType`, `modifiedTime`, `parentId`, `owner`,
  `sharedWithMe`, combined with `and`/`or`/`not`). Also copy its hard-won prompt guidance:
  *do not put document-type words inside `title`/`fullText` clauses; map them to `mimeType`
  instead* — that instruction exists because models get it wrong.
- [ ] `list_recent_files` — `orderBy` of `recency` | `lastModified` | `lastModifiedByMe`,
  page size default 10, token pagination.
- [ ] `get_file_metadata`, `read_file_content`, `download_file_content` — largely wrappers
  over what the library already does (`open`, `as_text`, `export`).
- [ ] `get_file_permissions` — new surface (Drive permissions API). Read-only but sensitive:
  it reveals who a document is shared with.
- [ ] `create_file`, `update_file`, `copy_file`, `trash_file` — new surface (Drive files API).
  Note the library is deliberately document-scoped today; file *lifecycle* is a new axis.
- [ ] `share_file` — **blocked on #82.** See above.
- [ ] **Tool descriptions and the server description must state the danger explicitly.**
  Parity of names must not imply parity of risk. A user who has used the connector will
  assume read-mostly; the description has to correct that before their first write.
- [ ] Prompt suggestions, matching the connector's shape.
- [ ] Pagination convention (`pageToken` / `next_page_token`) — the library has no paginated
  accessor today; `ApiBackend.list_comments` paginates internally and returns everything.
  Decide whether tools expose page tokens or keep hiding them.

## Publish — ✅ DONE

- [x] **Release automation** — `.github/workflows/release.yml` (Trusted Publishing / OIDC);
  steps in `RELEASING.md`.
- [x] **Published to PyPI** — `0.1.0`, `0.1.1` (docs patch), and `0.1.2` (first release
  through the hardened pipeline — attestations + env gate) all cut via `gh release create`
  → CI-built, tagged, GitHub-Released, uploaded over OIDC. Page:
  <https://pypi.org/project/csa-google-workspace/>. Since then: `0.2.0`–`0.2.3` (the MCP
  server and its follow-ups). Current `__version__`: **0.2.3**.

## Release-process / supply-chain hardening — ✅ DONE

From a 2026-07-23 release-process review (re-verified). Fixed in PR #69 (code) + repo-admin
settings, worst-first:

- [x] **⚙️ `main` is protected.** Branch protection via API: required status checks (`lint`,
  `test (3.10–3.14)`, `security`), PRs required, direct + force pushes blocked, **enforced for
  admins**. `required_approving_review_count = 0` so the solo/AI PR flow still merges (checks
  gate, no human-approval bottleneck). *Residual (optional):* also require the CodeQL contexts,
  and/or raise the review count if a second reviewer is ever available.
- [x] **🔧 Actions pinned to commit SHAs** (PR #69) — `checkout` v4, `setup-python` v5,
  `gh-action-pypi-publish` v1.14.1, across `tests.yml` + `release.yml`; Dependabot keeps them current.
- [x] **🔧+⚙️ Environment gate on publish** — protected `pypi` GitHub Environment (required
  reviewer: repo owner) + `environment: pypi` on the publish job (PR #69). **Residual now closed
  (2026-08-25):** the PyPI Trusted Publisher is constrained to environment `pypi` (was `(Any)`).

  Worth recording *why* this mattered rather than just that it is done. While the publisher
  accepted any environment, the approval gate was enforced only by a line of YAML **in the repo
  being published** — anyone able to edit `.github/workflows/release.yml` could drop
  `environment: pypi` and PyPI would still accept the upload. The control guarding releases was
  itself guarded by the thing it protects. Constrained at the registry, removing that line now
  *breaks* publishing instead of bypassing review: a convention became an invariant. Same move as
  `auth.load_cached_credentials` simply not containing the interactive branch.

  PyPI had been emailing this recommendation after every publish since 0.1.2 (five times).
- [x] **🔧 PEP 740 attestations** — `attestations: true` on the pinned publisher (PR #69),
  **✅ verified** against PyPI's **Integrity API**: `0.1.0`, `0.1.1`, and `0.1.2` all return
  `200` on `/integrity/csa-google-workspace/<ver>/<file>/provenance` — every release is
  attested. *Correction:* the earlier "no provenance" reading was a **measurement error** —
  the legacy `/pypi/<pkg>/<ver>/json` `urls[].provenance` field is unreliable (reads `false`
  even when attestations exist); use the Integrity API. Attestations have shipped since
  `0.1.0` (Trusted Publishing default), so there was never a gap to fix — the explicit
  `attestations: true` just makes it intentional.
- [x] **🔧 Security gate at release time** — `pip-audit` + `bandit` run before publish in
  `release.yml` (PR #69).
- [x] **🔧 Dependency automation + pinned build** — `.github/dependabot.yml` (`pip` +
  `github-actions`); `build`/`twine` pinned in the release job (PR #69). *(Full CI lockfile
  still optional/deferred.)*
- [x] **🔧 Polish** — `SECURITY.md` disclosure text completed; sdist-contents guard added
  (PR #69). *Deferred (optional):* SBOM publication; a post-publish "install from PyPI + import"
  smoke step.

## Tier 0 — audit findings (correctness) — ✅ DONE

Confirmed by an external review (2026-07-21), re-verified against the code, and fixed:

- [x] **`Workspace.open()` leaks a raw `HttpError`.** ✅ Fixed in PR #26. `ApiBackend.get_file_metadata`
  (`backend.py:190`) is the *only* data method that calls `.execute()` without
  `_errors.call(...)`, so the first call a consumer makes raises a raw
  `googleapiclient.errors.HttpError` on a missing/forbidden/service-disabled file
  instead of the typed `NotFoundError`/`PermissionError`/`ServiceDisabledError` the spec
  promises. **Fix:** wrap in `_errors.call`, **and** add an `ApiBackend`-level test that
  feeds a stub service raising `HttpError` and asserts typed translation — no
  `FakeBackend` test can catch this class of bug, because the fake raises typed errors
  directly (the one blind spot of the fake/real seam).
- [x] **Cell-map degrade is spec-noncompliant (no recorded warning).** ✅ Fixed in PR #26
  (stdlib `logging` WARNING on degrade; genuine no-match stays quiet). The spec
  (`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md:334`) requires
  `_cellmap` to degrade to `location=None` **plus a recorded warning**. `sheet.py:63`
  does the `location=None` half but records nothing, so export-cap-exceeded,
  access-denied, malformed XLSX, and genuine no-match are indistinguishable to callers.
  Shares a root cause with the tracked "10 MB export cap silently degrades" item:
  **there is no logging/warnings story.** **Fix (shared, minimal):** adopt stdlib
  `logging` + `warnings.warn`; closes both. Resist anything heavier.

## Tier 1 — make the "embeddable, typed" promise real (small, high leverage)

Both items below were independently flagged by the same external review — good signal
they're the right release-readiness priorities.

- [x] **`py.typed` marker (PEP 561).** ✅ Shipped in PR #27 (marker + `package-data`;
  verified present in a built wheel + a packaging test guards it).
- [x] **Package metadata.** ✅ Done: `readme`, SPDX `license = "Apache-2.0"` +
  `license-files`, `authors`/`maintainers`, `keywords`, trove `classifiers`
  (incl. `Typing :: Typed`), `[project.urls]`, and a single-sourced dynamic version.
  Bumped to `0.1.0`; `build` + `twine check` green for sdist + wheel.
- [x] **CI that runs the test suite.** ✅ Added in PR #28 — GitHub Actions runs
  `pytest -q` across Python 3.10–3.13 on push + PR (offline; live suite stays gated).

## Tier 2 — formalize the guarantees — ✅ DONE

- [x] **ruff + mypy in dev deps and CI.** ✅ ruff (lint; E/F/W/I/B/UP, ignoring the
  deliberate `E702` semicolon style, no auto-formatter) + mypy (`check_untyped_defs`,
  google stack marked untyped) now run as a dedicated `lint` CI job. Fixed the findings
  (mostly test cleanups + typing the injected `_backend`/`_file_id` fields and the
  `CommentsMixin` attributes).
- [x] **Coverage reporting** (`pytest-cov`). ✅ Wired into the CI matrix with
  `fail_under = 85` (total ~87%; the shortfall is the integration-only ApiBackend +
  interactive OAuth paths).

## Tier 3 — real API-surface gaps — ✅ DONE

- [x] **Sheets `append_rows`** (`spreadsheets.values.append`, `INSERT_ROWS`). ✅ Added;
  non-idempotent so never auto-retried on 5xx.
- [x] **Slides write symmetry.** ✅ Added `Slides.insert_text(object_id, text, index=0)`
  (shape-addressed, symmetric to `Doc.insert_text`) + `Slide.shape_ids` to discover
  targetable shapes. Decision: a fuller shape model (bulk shape CRUD) stays out — raw
  `batch_update` remains the escape hatch; the asymmetry with Docs is inherent (Slides is
  shape-addressed, Docs is a linear index).
- [x] **`Sheet.as_text(tab=…)`** ✅ now renders **all** tabs by default (each with a
  `# <tab>` header when >1), fixing the silent first-tab-only data loss; `tab=` selects one.

### Tier 3 minor / polish — ✅ already resolved (verified in code)

- [x] `replace_text` returns `occurrencesChanged` + `match_case` kwarg (Doc + Slides) —
  fixed in an earlier batch; a no-match (`0`) is distinguishable from a match.
- [x] `Sheet.batch_update` invalidates the cell-map cache (`self._cell_map_cache = None`).
- [x] `Doc.suggestions` is typed `list[Suggestion]`.

## Tier 4 — prove the pitch (scope-adjacent)

- [ ] **`examples/` reference consumer** — ~~a small MCP server or~~ a comment-triage bot
  built on the library. **Mostly superseded by phase 2:** the earlier "stays out of the
  *core* per the design" framing was reversed when the built-in MCP server was approved, and
  that server is now the reference consumer + the proof of the "embed in MCP/plugins"
  positioning. What's left of this item is only a *non-MCP* example (e.g. a plain triage
  bot), if one is still wanted after phase 2 ships.
- [ ] **Async story — decide.** Sync-only forces `asyncio.to_thread` on async callers. Lean:
  *document the `to_thread` pattern* (cheap) rather than build an async facade (large, and
  `google-api-python-client` is sync). **Phase 2 forces the call** — the MCP server is the
  first in-tree async-adjacent consumer, so decide it while writing that plan.

## Integration / live testing

Three tiers:

- **unit** — `tests/`, offline (`FakeBackend`), 217 tests; gates every PR.
- **integration** — `tests/integration/`, real Google API, opt-in via `CSA_GW_INTEGRATION=1`
  (needs a cached token or a first-run browser login). Covers the full surface incl. Tier 3.
- **oauth** — `tests/oauth/`, the **interactive browser-login** suite (real `from_oauth`,
  token-file permissions, `read_only` contract). **Separate** because it needs a human at a
  browser and touches the very sensitive cached token; own gate `CSA_GW_OAUTH=1`.

```
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
CSA_GW_OAUTH=1       CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

- [ ] **Optional: a manual `workflow_dispatch` CI job** running the live suite with a stored
  Google credentials secret. **Deferred to the security audit** — putting Google creds in CI
  is a threat-model decision, not a default.

## Deferred — bigger / genuinely out of reach today (already tracked)

These are recorded design decisions, **not bugs**:

- [ ] **`Location.tab` resolution** — multi-tab cell disambiguation via `workbook.xml` +
  rels (part → sheet-name). Real correctness gap for multi-tab sheets; its own task.
- [ ] **Caching pass** — accessors re-fetch per call by design (the tool is used in live
  multi-reviewer sessions where a self-only-invalidated cache goes stale). An *opt-in* /
  request-scoped cache is the biggest runtime win for embedded review sessions.
- [x] **10 MB XLSX export cap** — large sheets degrade the cell-map. ✅ No longer *silent*
  as of PR #26: the shared logging story records a WARNING naming the cause. (Raising the
  cap itself is still out of reach — it's a Google export limit.)
- [ ] **Accept/reject suggestions & true cell-anchored comment creation** — API-impossible
  (proven by probe); reserved for a future `PlaywrightBackend`. `ApiBackend` raises
  `UnsupportedOperation`.
