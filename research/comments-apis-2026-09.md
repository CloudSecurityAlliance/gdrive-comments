# Two comment APIs: Drive (GA, what we use) and the native editor APIs (Developer Preview)

**Background research, 2026-09-02.** Not a plan — the decision is recorded at the bottom and in
`TODO.md`. This file exists because the situation changed under the project: for its whole life
there was one way to reach a comment, and now there are two, with different capabilities and
different anchoring models.

Two sources, kept apart on purpose:

1. **§1 — a technical note supplied to the project**, reproduced as received. It is the reason we
   went looking.
2. **§2 — what we then measured** against the live API, which both confirmed it and corrected it in
   three places.

The order matters: the note came first and was right about the shape of things. §2 is not a
rebuttal, it is the verification the note itself invites.

---

## 1. The supplied note, as received

> # Google Workspace Comments APIs — Short Technical Note
> **Current as of September 2, 2026**
>
> Google now has two materially different commenting mechanisms:
>
> 1. **Drive Comments API — GA/stable**
>    - Generic comments applicable to Drive files.
>    - Can create anchored or unanchored comments.
>    - For native Google Docs/Sheets/Slides, Google explicitly states that Drive API anchors are
>      treated by the Workspace editors as **unanchored**.
>    - Therefore it does not reproduce native editor anchoring reliably.
>
> 2. **Native Docs, Sheets and Slides Comments APIs — Developer Preview**
>    - These expose the editors' native comment model.
>    - Docs: comments can be anchored to document ranges.
>    - Sheets: comments can be anchored to specific cells/grid coordinates and returned with
>      `CommentAnchor` → `GridRange` mappings.
>    - Slides: comments can be anchored to slides, objects, text ranges, table cells or table
>      ranges.
>    - Google states that API-created comments receive behavior similar to comments created through
>      the editor, including formatting and notifications.
>
> ## Web UI vs APIs
>
> The native comments APIs should be considered substantially closer to the **web-editor commenting
> system** than the Drive Comments API.
>
> A human-created editor comment and a native-API-created comment appear to participate in the
> editor-native `CommentThread` model. Google does not, however, currently publish a complete
> interoperability guarantee describing exactly which comments appear through both the Drive and
> native APIs.
>
> For comprehensive ingestion during the preview period, the safest design is therefore:
>
> - Read native comments through Docs/Sheets/Slides API.
> - Also read Drive comments.
> - Normalize and deduplicate the results.
> - Prefer native anchor information where available.
>
> ## Comment author identity
>
> The new native APIs expose a `PostAuthor` containing fields including:
>
> - `displayName`
> - `me`
> - `anonymous`
> - `user`
>
> The important identity field is `user`, represented as a Google user resource such as
> `users/{user}`. `displayName` should be treated only as display metadata because users can change
> it.
>
> The old Drive Comments API is substantially weaker for identity. Although its `author` is a Drive
> `User`, Google explicitly states that the author's **email address and permission ID are not
> populated** for comment authors.
>
> ## Creation provenance
>
> Neither API exposes a reliable field saying:
>
> - created through web UI
> - created through Drive API
> - created through Docs/Sheets/Slides API
>
> Therefore the comment itself generally cannot establish its creation channel.
>
> Workspace audit logs may provide additional evidence such as the OAuth client/application
> responsible for an action, but this is separate from the comment object and does not necessarily
> identify the exact API endpoint used.
>
> For AI/MCP-created comments, maintain your own provenance log containing at least:
>
> - Google comment ID
> - file/document ID
> - Google user identity
> - API surface used
> - OAuth/client identity
> - agent/run/session ID
> - timestamp
> - operation/tool
> - intent or justification
>
> ## Developer Preview / GA
>
> Google states that Workspace Developer Preview features **usually remain in preview for 3–6
> months**, although this is not a guarantee of GA.
>
> Sheets comments entered Developer Preview July 23, 2026. Slides comments are documented as
> Developer Preview as of August 31, 2026. Docs comments/suggestions are also currently Developer
> Preview.
>
> Google has **not announced deprecation of the Drive Comments API**. It continues to serve an
> important generic-file use case that native Docs/Sheets/Slides APIs cannot replace, so
> coexistence is currently the most likely architecture.
>
> ### Google primary sources
>
> Drive — Manage comments and replies:
> <https://developers.google.com/workspace/drive/api/guides/manage-comments>
>
> Drive — Comment resource and author fields:
> <https://developers.google.com/workspace/drive/api/reference/rest/v3/comments>
>
> Docs — Comments and suggestions:
> <https://developers.google.com/workspace/docs/api/how-tos/suggestions>
>
> Sheets — Native comments and anchors:
> <https://developers.google.com/workspace/sheets/api/guides/comments>
>
> Sheets — API release notes: <https://developers.google.com/workspace/sheets/release-notes>
>
> Slides — Native comments: <https://developers.google.com/workspace/slides/api/guides/comments>
>
> Slides — Comment request/anchor schema:
> <https://developers.google.com/workspace/slides/api/reference/rest/v1/presentations/request>
>
> Google Workspace — Developer Preview rules, including the typical **3–6 month** period:
> <https://developers.google.com/workspace/preview>

---

## 2. What we measured (2026-09-02)

Method: none of the preview surface appears in any public discovery document, so it cannot be
enumerated. Instead each candidate request name was sent to the live API. A control name proves
what "does not exist" looks like:

```
totallyMadeUpRequest  ->  Unknown name "totallyMadeUpRequest" at 'requests[0]': Cannot find field.
insertComment         ->  Invalid requests[0]: No request set.
```

`Unknown name` means the field is absent from the proto. **`No request set` means the name was
accepted** and the request then failed at dispatch. Field names inside a request were discovered
the same way — a valid name yields `No request set`, an invalid one is rejected by name.

### 2.1 All three editors have it, and each anchors in its own model

| editor | request types the live server recognises | `insertComment` fields accepted | rejected |
|---|---|---|---|
| **Docs** | `insertComment`, `addCommentReply`, `updateCommentPost`, `deleteComment`, `deleteCommentReply`, **`acceptSuggestion`**, **`rejectSuggestion`**, `deleteSuggestion` | `content`, **`range`** | `text`, `quotedText`, `anchor`, `location`, `reply`, `post` |
| **Sheets** | the five comment types | `content`, **`coordinate`** | `anchor`, `range`, `gridRange`, `cell`, `post`, `comment` |
| **Slides** | the five comment types | `content`, **`objectId`** | `anchor`, `coordinate`, `pageObjectId`, `textRange` |

The anchor field is **per-editor and matches each editor's own addressing**: a character range in
Docs, a `GridCoordinate` in Sheets, an object id in Slides. `createComment` / `addComment` /
`updateComment` are **not** the names in any of them — worth recording, because they are the names
one would guess.

**Everything is gated.** A fully-formed `insertComment{content, range}` still returns
`No request set`: the fields are in the shared proto and dispatch is disabled for callers not in
the Developer Preview Program.

### 2.2 Correction — Sheets anchoring is asymmetric, and the READ side is the bigger prize

The note treats Sheets anchoring as one capability. It is two different fields:

- **write:** `insertComment.coordinate` — a `GridCoordinate` (`sheetId`, `rowIndex`, `columnIndex`)
- **read:** `spreadsheets.get?commentsViewMode=…`, returning a global `comments` array plus
  **`sheets.commentAnchors`** mapping `anchorId` → `GridRange`

The read parameter is real: a bogus value errors against
`type.googleapis.com/google.apps.sheets.v4.CommentsViewMode`, a genuine enum type. The documented
value parses and then fails as *"field could not be found in request message"* — the same gate, one
layer further in.

### 2.3 Correction — this obsoletes two of this project's architectural facts

`CLAUDE.md` fact 3 says *"You cannot create a cell-anchored comment via the API, and mapping a
comment→cell requires an XLSX-export-and-parse detour."* Both halves are superseded by the preview:

- `insertComment.coordinate` **is** cell-anchored creation.
- `sheets.commentAnchors` **is** the cell mapping, as a field — which is the entire reason
  `_cellmap.py` exists. That module performs an XLSX export, a `defusedxml` parse and a three-hop
  relationship walk to recover what this returns directly.

Fact 4 says the Docs API has *"no accept/reject endpoint (proven by full API enumeration)"*. It was
true of the **published** surface when written, and the enumeration was sound; `acceptSuggestion`
and `rejectSuggestion` now exist.

Neither fact is wrong about **what we use**. Both are wrong as statements about what Google offers,
which is why they now carry a pointer to this file.

### 2.4 Consequence — the `PlaywrightBackend` loses both its reasons to exist

`CLAUDE.md` fact 5 reserves a `PlaywrightBackend` for *"the genuinely API-impossible ops
(accept/reject suggestion, true cell-anchored comment)"*. Those are exactly the two capabilities
above. Post-GA that seam has no remaining justification — worth knowing **before** anybody builds
it, which is the only reason this is written down now rather than later.

### 2.5 Where the note's dedup recommendation rests on something unknown

The note recommends reading both surfaces, normalising and deduplicating — and separately notes
that Google publishes no interoperability guarantee. Those two sit together uncomfortably, and the
gap between them is the first thing to probe with access:

**do native and Drive comments share an identity?** If the two surfaces return the same threads
under different id spaces, deduplication falls back to content + author + timestamp heuristics —
fragile, and the kind of guess this project refuses elsewhere (`comments_by_cell` reports
`tab_ambiguous` rather than picking a sheet). If the ids correspond, dedup is trivial. Unanswerable
without enrolment.

### 2.6 The identity gain is larger than the note suggests

`PostAuthor.user` (`users/{user}`) is a **stable key**. The Drive comment author has no email at
all — probe-verified, and recorded as invariant 2 because the models had to be `Optional` for it.

That limitation sits under `TODO.md`'s most compelling query: *"show me everything Bob has said"*
across a folder is currently **display-name matching**, which is neither unique nor stable. The
work-handoff inventory (#350) carries the same caveat in a `matched_on` column on every row. Native
comments would fix it properly rather than reporting it honestly.

### 2.7 The provenance-log recommendation collides with an existing decision

The note recommends maintaining our own provenance log — comment id, file id, user, API surface,
OAuth client, agent/run id, intent. Sensible for an agent platform.

But this library states **"No persistent storage of comment content"** as an architectural
property, and a provenance log is a new persistence surface with its own retention, governance and
threat-model questions. It plausibly belongs in the **embedder** rather than here. Recorded as an
open question rather than resolved, because it is a decision and not a detail.

---

## 3. The decision (CINO, 2026-09-02)

**Stay on the Drive API. It works.**

- Native comment support is **post-1.0, possibly post-2.0**. No rush.
- Add it **before general availability**, so we are not scrambling at GA — but
- ship it **behind a flag**, because most users will not be enrolled in the Developer Preview
  Program and a default that most callers cannot use is not a default.
- Google has not announced deprecation of the Drive Comments API, and it serves generic Drive files
  that the native APIs cannot. **Coexistence, not migration.**

The `Backend` protocol is already the seam this would slot into — the same one that was going to
hold `PlaywrightBackend`, which now will not be needed.

Tracked in `TODO.md`. Also tracked there: a **comprehensive comments reference** covering the web
editor, both APIs, every behavioural difference and the XLSX-export detour — a programming resource
that does not currently exist anywhere, written primarily for an AI to read while implementing.
