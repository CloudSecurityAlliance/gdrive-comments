# The fourth anchor state is real, and only the API can make it

**Measured 2026-09-03** against live Google Drive, on a throwaway Doc (created, probed, trashed).
Settles [#372](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/372).

Run: `probe.py --create`, then `--comments`, then `--dump`, then `--trash`.

## The question

A consumer measured 90 real threads and found **4 with `anchored=false` and substantial
`quoted_text`** — 119, 111, 244 and 35 characters. The documented contract says `anchored=false`
means the comment is about the whole file, so those four are mishandled silently. They could not
tell from outside whether Drive returns a quote with no anchor, or whether the library loses the
anchor somewhere.

## Answer: Drive returns it. The library loses nothing.

Six comments created through `comments.create`, read back with the **same field mask the library
uses** (`backend.py:577`, which does include `anchor`):

| # | sent | `anchor` back | `quotedFileContent` back | `Comment.anchored` |
|---|---|---|---|---|
| A | `content` only | absent | absent | `False` |
| **B** | **`content` + quote (244 chars)** | **absent** | **present, verbatim** | **`False`** ← the state |
| **C** | **`content` + quote (85 chars)** | **absent** | **present, verbatim** | **`False`** ← the state |
| D | `content` + anchor + quote | present, verbatim | present, verbatim | `True` |
| E | `content` + anchor only | present, verbatim | absent | `True` |
| **F** | **`content` + quote with `\n`, `\t`, padding** | **absent** | **present, verbatim** | **`False`** ← the state |

So the state is not merely possible, it is **the ordinary result of creating a comment with a
quote and no anchor** — and Drive accepts that combination without complaint.

`Comment.anchored` is `self.anchor is not None` (`comments.py:153`), so it reported `False` on a
comment carrying 244 characters of quoted text. The derivation is faithful to Drive; **the
contract built on it was wrong**.

## Why the earlier measurement could not have found this

`experiments/docs-anchor-states/` (2026-09-02) produced the three-state table now quoted in four
places. Every comment in that run was created **by the editor**, plus one file-level comment
created through the API. The editor cannot produce a quote without an anchor — it snaps a bare
caret to the enclosing word and refuses to comment on empty space, both measured. So this shape
was **unreachable by construction**, and the table is complete for editor-created comments while
being stated as complete for all comments.

That is the same failure as #361 one level up: a claim derived from a proxy, where the proxy's
coverage silently became the claim's scope.

## Why a sensible tool creates such a comment on purpose

Measured 2026-07-09 (`experiments/anchor-probe/`): an API-supplied anchor is stored verbatim and
returned intact, and the editors then treat the comment as **un-anchored**. Confirmed again here
— D and E round-tripped `kix.probe372anchornotreal` unchanged, an anchor that corresponds to
nothing.

So a client that knows this **omits the anchor as useless** while still recording what it quoted.
That is the better-informed choice, not a bug. Which means this shape should be **expected on any
file another tool has written to**, and treating it as corruption would be wrong.

## Corroboration: the ids say "one API batch"

The reporter noted their four ids "share a prefix and differ only in the final character". These
six, from one run, do exactly the same:

```
A  AAACGezoGWc      common prefix: 'AAACGezoGW' (10 of 11 chars)
B  AAACGezoGWg      final chars:   c  g  k  o  s  w
C  AAACGezoGWk
D  AAACGezoGWo
E  AAACGezoGWs
F  AAACGezoGWw
```

Sequential within a batch, stepping by 4 in the final base64 character. This does not *prove* the
provenance of somebody else's four rows — provenance is not observable from outside — but an
independent reproduction produced the same id signature from the same cause, which is as close as
this can get.

## Two findings that were not the question

**`quotedFileContent.mimeType` carries no information at all.** Sent `text/plain` (case C), Drive
returned **`text/html`**. It normalises the field regardless of what the client sends, so every
comment reports `text/html` whatever it was created with — while the value stays plain text, as
measured on 2026-07-20. The existing note said the mimeType "is `text/html` but the value is
plain text"; the reason is now known, and it is stronger than described: **do not branch on this
field**, because it is a constant.

**The quote value is byte-verbatim.** Case F round-tripped leading spaces, an embedded newline
and a tab unchanged. So a stored quote can be matched against extracted text without
normalisation — which is what `_context.py` already relies on, now confirmed for the API-created
path as well as the editor one.

## The blast radius is smaller than it looks

Three of the reporter's four rows still resolved to `context_kind: paragraph`, because
`_context.py` **locates by quoted text, not by the anchor** — a decision forced by the anchor
carrying no position. That choice made the context feature immune to this bug, and it confines
the damage to the `anchored` flag and the prose describing it.

## Still open, and it needs a browser

**How does the editor render a quoted-but-unanchored comment?** Whether it appears in the Docs
sidebar at all, and whether it shows its quote, is not observable through the API. Recorded as
open rather than guessed at.
