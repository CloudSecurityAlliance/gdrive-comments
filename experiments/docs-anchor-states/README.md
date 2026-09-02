# Docs anchor states

Two probes settling what **Google Docs** comment anchors actually do, and what the Docs/Sheets APIs
can and cannot tell a consumer about *where a comment is about*. Filed for issues **#358** (anchors
as a localization hint, not ground truth) and **#361** (can the three anchor states be told apart).

Results, raw: [`RESULTS.md`](RESULTS.md).

| script | needs a human? | what it answers |
|---|---|---|
| [`probe.py`](probe.py) | **yes, for the anchors** | what a real UI-placed Docs anchor looks like, per state; and what `documents.get` gives a context window to work with |
| [`probe_notes.py`](probe_notes.py) | no | are Sheets **notes** reachable and cheap to count; can a cell comment report its row/column headers |

## Why the anchor half needs a human

Measured in the 2026-07-09 [`anchor-probe`](../anchor-probe/): a comment created through the Drive
API has its anchor **stored verbatim** and is then treated as *un-anchored* by the editor. Google
says the same. **An API-created comment cannot produce a real anchor**, so no amount of scripting
substitutes for a right-click.

For this run the "human" was keyboard-driven Playwright attached to a signed-in Chrome over CDP —
which is a human's browser doing a human's keystrokes, not the API. Note that **Docs renders to
canvas**, so DOM selection is unavailable and everything goes through `Cmd+F`, `Shift+arrow` and
`Cmd+Alt+M`.

That automation has one failure mode worth knowing before reusing it: after a formatting command
the editor's selection can stick, and `Cmd+F` then stops moving it — two comments in the probe
document landed on the wrong text (labelled `5b` and `5c`; ignore them).

## Run

```bash
# 1. create the throwaway document with numbered paragraphs and a table
python probe.py --create

# 2. place comments in the UI (see RESULTS.md for the six states), then:
python probe.py --file-id <ID> --dump --structure

# 3. the state a script CAN make - a comment with no anchor at all
python probe.py --file-id <ID> --file-level

# notes and cell headers, no human needed
python probe_notes.py
```

Both create throwaway files under the signed-in account. Trash them when done; the document is the
evidence, so keep it until the findings are folded into `research/`.

## The one-line answer

**A real Docs anchor is an opaque `kix.*` id with no position — and it does not matter**, because
Docs snaps a bare caret to its enclosing word and refuses to comment on empty space, so quoted text
is available wherever text exists. See *THE CONSEQUENCE* in the results.
