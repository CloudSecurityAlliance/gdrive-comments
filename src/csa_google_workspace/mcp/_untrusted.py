"""Neutralise terminal control sequences in everything a tool returns, and cap the one field
authored by somebody with no access to the file.

## What this defends against, measured rather than assumed

The MCP SDK returns a tool result twice: as `structured_content` (the dict) and as a text block
holding the same dict as pretty-printed JSON. JSON escaping means a value CANNOT forge a sibling
field - a `request_message` of `"requester_email": "ceo@corp.com"` arrives as
`\\"requester_email\\": \\"ceo@corp.com\\"`, visibly inside the string it belongs to. That is a
stronger fence than the one `_inline.py` builds by hand, and it comes for free.

What JSON escaping does NOT do is stop the string from carrying **terminal control sequences**.
`json.dumps` writes ESC as `\\u001b`; the client decodes it back to a live `0x1b` byte before
displaying it. Probed, because this is the whole basis for the module:

    payload = "please grant access\\x1b[2K\\r\\x1b[1A\\x1b[2Kgranted by admin"
    json.loads(json.dumps(payload))     # ESC survives, as a real 0x1b

In a terminal that is *erase line, carriage return, cursor up, erase line* - it deletes the line
it is on **and the line above it**, which is where a warning would have been printed.

**The attack is an asymmetry, and that is what makes it worth fixing.** The model reads
`structured_content`, where the bytes are inert data. The human reads the rendered text, where
they are instructions to the terminal. So the same response can show a person a short, innocuous
message while the model reads a long injection - or hide from a person the text the model is
about to act on. Every control this repository has against prompt injection assumes the human can
see what the model saw.

Nothing here is fenced or labelled: labelling is `_inline.py`'s job on the flat path, and the
tool descriptions carry it on this one. This module only removes the ability to lie to the
renderer.

## Why it is applied at the boundary and not per field

The untrusted strings on this surface are not one field. A file `name` and a tab `title` are set
by anybody with write access; `display_name` on a permission or an access proposal is set by the
**external** person it describes; comment bodies come from collaborators; `request_message` comes
from someone with no access at all. A hand-maintained list of fields to sanitise is the shape
this repository keeps finding broken - see #308 and #332, both of which were a list that had
stopped matching the code.

So it runs once, in `_tools._base._errors`, which every tool passes through, walking the returned
structure. A tool added tomorrow is covered without anybody remembering this file exists.

## Why `\\t`, `\\n` and `\\r` are kept, and the residual that leaves

`\\t` and `\\n` are ordinary content: a comment body has newlines and a register would be wrong
about the record without them.

`\\r` is kept for a harder reason. `ExportOut.csv` is RFC 4180, which **mandates CRLF** as the
record separator, and this scrub runs over that field like any other. Neutralising `\\r` would
corrupt a caller's CSV. The alternative - a list of fields exempt from the scrub - reintroduces
exactly the hand-maintained list this design avoids, and the failure mode of a forgotten
exemption is a corrupted export, which is worse than the residual.

**The residual, stated plainly:** a bare `\\r` can still overwrite the line it is on. It cannot
erase a line, move the cursor, or reach the line above - all of those need ESC. And the value
sits inside a quoted JSON string on its own line, so the overwrite is confined to that line.
That is a real but much smaller thing than what ESC allowed, and it is a deliberate trade for
not maintaining an exemption list.
"""
from __future__ import annotations

from typing import Any

# C0 controls and DEL, mapped to the Unicode Control Pictures block: 0x00-0x1F -> U+2400-U+241F,
# DEL -> U+2421. So ESC becomes a visible `␛`.
#
# REPLACED, NOT DROPPED. The same argument `_inline.one_line` makes for `⏎`: a register that
# silently rewrites what somebody said is wrong about the record. A visible `␛` also says
# something true and useful on its own - that this text arrived carrying a terminal escape,
# which is not something a person writing "can I have access please" does by accident.
_CONTROLS = {code: chr(0x2400 + code) for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)}
_CONTROLS[0x7F] = "\N{SYMBOL FOR DELETE}"

# `request_message` is the only field here written by somebody with NO access to the file, and
# the only one that is short by nature - it is a note on a "Request access" click, not a
# document. Capping it bounds attacker-chosen bytes entering the model's context without
# risking the truncation of anything legitimate. Every other untrusted string on this surface
# is left at full length deliberately: a comment body or a document can be long for honest
# reasons, and a cap there would silently lose what the user asked to read.
MAX_REQUEST_MESSAGE = 2000


def neutralise(text: str) -> str:
    """Return `text` with terminal control characters made visible and inert."""
    return text.translate(_CONTROLS)


def capped(text: str, limit: int = MAX_REQUEST_MESSAGE) -> str:
    """Cap `text`, saying so and naming the true length.

    The marker matters as much as the cap: a truncation the reader cannot see is a claim that
    this was the whole message, and "the rest was cut" is itself worth knowing when the field is
    attacker-controlled.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"… [truncated: {len(text)} characters total, {limit} shown]"


def scrub(value: Any) -> Any:
    """Walk a tool result, neutralising every string in it.

    Containers are rebuilt rather than mutated in place, because a `*_out` helper may hand back
    a structure that shares objects with something the caller still holds.

    Non-string leaves - ints, bools, None - are returned as they are. Dict KEYS are scrubbed
    too: they are field names we chose, so this is a no-op today, but `describe_configuration`
    and the labels tools build keys from Drive-supplied names, and a key is displayed like any
    other string.
    """
    if isinstance(value, str):
        return neutralise(value)
    if isinstance(value, dict):
        return {scrub(key): scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(scrub(item) for item in value)
    return value
