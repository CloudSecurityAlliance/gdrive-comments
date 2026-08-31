"""Drive labels — what a document is *classified* as, in words rather than ids.

A per-file, uniform Drive concern, so it arrives as a mixin like comments and permissions.
Read-only, and that is a decision rather than a limitation: see below.

## It takes two APIs, and that is the whole difficulty

Drive v3's `files.listLabels` says **which** labels are on a file. It does not say what they are
called. The `Label` it returns is `{id, revisionId, fields}` — no title, and selection values are
opaque choice ids too. Rendering `Confidential` instead of `bXlsYWJlbA` requires the **Drive
Labels API** (`drivelabels.googleapis.com`), which is a *separate* API with its own scope and its
own enablement in the Cloud project.

So `labels` does a join: one `list_file_labels` call, then one `get_label_definition` per applied
label. A document typically carries none or one, so that is one or two calls — well inside the
"accessors re-fetch per call" rule this library settled on, and not worth a cache.

## Names can be unavailable, and that must never look like "unlabelled"

Two ways the second API can fail while the first succeeds:

* the **API is not enabled** in the Cloud project — a granted scope does not enable an API, and
  this is the trap `CLAUDE.md` already records for Docs/Sheets/Slides;
* the **token predates the scope**, because `drive.labels.readonly` was added in v0.34.0 and a
  cached token from before it will not carry it.

In both cases the file's labels are still known — the ids are real — so failing the whole call
would throw away true information. Instead `Label.name` is `None` and `Label.unresolved_reason`
says which of the two happened and what to do about it.

**The rule that makes this safe: an id is never presented as a name.** `name` is `None`, not the
id, and `display` falls back to a form that is visibly an id (`label bXlsYWJlbA`). A label whose
name could not be resolved must not be mistaken for a label called something — and a file with
labels must never be reported as unlabelled, which is the error that matters, because
*"is this document classified?"* answered wrongly in that direction is the one people act on.

## Read-only, deliberately

This library never requests `drive.labels`, only `drive.labels.readonly`, so there is no
capability to enable and no configuration that permits writing. Labels are a **classification**
system: DLP and retention policies key on them, so setting one is not an edit to a document, it
is a claim about how the organisation must treat that document. A model that could relabel
`Confidential` to `Public` would be defeating a control rather than using one — and unlike a bad
edit, nobody sees a diff.

Reading is the useful half regardless: *"what is this classified as, and should I be pasting it
into a chat?"* is the question that actually comes up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import exceptions as exc

if TYPE_CHECKING:                                      # pragma: no cover
    from .backend import Backend

# Why a name could not be resolved. Two causes, two different fixes, so they are not merged into
# one "unavailable" — an operator who reads "enable the API" when the real problem is a stale
# token will enable the API and still see no names.
API_DISABLED = ("the Drive Labels API is not enabled for this Google Cloud project, so label "
                "names cannot be read. Enable drivelabels.googleapis.com; the label ids below "
                "are still accurate.")
SCOPE_MISSING = ("this credential does not carry the drive.labels.readonly scope, so label "
                 "names cannot be read. Sign in again to grant it; the label ids below are "
                 "still accurate.")


@dataclass
class LabelField:
    """One field on an applied label, with its value already rendered to text where possible.

    `values` is a list because Drive's label fields are natively repeated — a selection field can
    carry several choices. A single-valued field is a one-element list rather than a bare string,
    so a caller never has to handle both shapes.
    """
    id: str
    name: str | None                 # None when the definition could not be read
    value_type: str                  # text | selection | integer | user | dateString
    values: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or f"field {self.id}"

    def __repr__(self) -> str:
        # Values are omitted, and this class needs the rule MORE than `Label` does, not less:
        # `Label.__repr__` never recurses into these, but anything that logs a field directly
        # would otherwise print a matter number, a client name, or free text somebody typed.
        # The COUNT is kept, because "this field has a value" is the useful part in a log.
        return (f"LabelField(id={self.id!r}, name={self.name!r}, "
                f"value_type={self.value_type!r}, values={len(self.values)})")


@dataclass
class Label:
    """One label applied to a file."""
    id: str
    name: str | None = None          # None when the definition could not be read
    fields: list[LabelField] = field(default_factory=list)
    revision_id: str | None = None
    # Set only when `name` is None. Says WHICH of the two causes, because they need different
    # fixes; `None` here means the name was resolved and there is nothing to explain.
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.name is not None

    @property
    def display(self) -> str:
        """A name when there is one, and something visibly an id when there is not.

        Never returns a bare id: `label bXlsYWJlbA` reads as an unresolved reference, while
        `bXlsYWJlbA` alone reads as a label somebody named that.
        """
        return self.name or f"label {self.id}"

    def __repr__(self) -> str:
        # Redacted like the other models. A label's TITLE is organisational vocabulary and safe
        # to log, but its FIELD VALUES are not - a text field can hold a matter number, a client
        # name, or a free-text note somebody typed - so values never appear here.
        return (f"Label(id={self.id!r}, name={self.name!r}, "
                f"fields={len(self.fields)}, resolved={self.resolved})")


def _field_values(applied: dict) -> tuple[str, list[Any]]:
    """(value_type, raw values) out of Drive's parallel-array field shape.

    Drive sends `{"valueType": "text", "text": ["x"]}` — the type names the key that holds the
    values. Read the type first rather than probing keys, so an unknown future type degrades to
    "no values" instead of silently picking the wrong array.
    """
    value_type = applied.get("valueType", "")
    raw = applied.get(value_type)
    return value_type, list(raw) if isinstance(raw, list) else []


def _choice_names(definition_field: dict) -> dict[str, str]:
    """choice id -> display name, for a selection field."""
    choices = (definition_field.get("selectionOptions") or {}).get("choices") or []
    return {c.get("id", ""): (c.get("properties") or {}).get("displayName", "")
            for c in choices}


def _render(value_type: str, values: list, definition_field: dict | None) -> list[str]:
    """Values as text. Selection choices resolve through the definition; everything else is
    already human-readable once stringified.

    `str(v)` and not `str(v or "")` — a label field can legitimately hold `0`, and #161 is the
    recorded case of that idiom turning a real value into an absence.
    """
    if value_type == "selection":
        # `definition_field is None` is the unresolved case, and it must STILL go through this
        # branch. Falling through to `str(v)` returns the bare choice id - `chConf` - which
        # reads as the value itself rather than as an unresolved reference. That is the exact
        # "an id is never presented as a name" failure this module exists to avoid, and it
        # shipped in the first draft here until a test caught it.
        names = _choice_names(definition_field or {})
        return [names.get(v) or f"choice {v}" for v in values]
    if value_type == "user":
        # A user field holds `{"emailAddress": ...}` objects rather than scalars.
        return [v.get("emailAddress", "") if isinstance(v, dict) else str(v) for v in values]
    return [str(v) for v in values]


def build_label(applied: dict, definition: dict | None,
                unresolved_reason: str | None = None) -> Label:
    """Join one applied label (Drive v3) with its definition (Drive Labels API).

    `definition` is None when it could not be read, and then `unresolved_reason` says why.
    """
    props = (definition or {}).get("properties") or {}
    by_id = {f.get("id", ""): f for f in (definition or {}).get("fields") or []}

    fields = []
    for field_id, applied_field in sorted((applied.get("fields") or {}).items()):
        value_type, raw = _field_values(applied_field)
        definition_field = by_id.get(field_id)
        name = ((definition_field or {}).get("properties") or {}).get("displayName") or None
        fields.append(LabelField(id=field_id, name=name, value_type=value_type,
                                 values=_render(value_type, raw, definition_field)))

    return Label(id=applied.get("id", ""), name=props.get("title") or None, fields=fields,
                 revision_id=applied.get("revisionId") or None,
                 unresolved_reason=None if definition is not None else unresolved_reason)


class LabelsMixin:
    """Provides `labels` uniformly across document types. Read-only by construction."""

    _backend: Backend
    id: str

    @property
    def labels(self) -> list[Label]:
        """Every label applied to this file, with names where they can be read.

        Ungated: a classification is disclosure about the file, like its permissions, and #82 is
        damage containment rather than confidentiality.

        Never raises for a missing name. If the Drive Labels API is off or the token predates the
        scope, the labels still come back — with `name` None and `unresolved_reason` set — because
        the ids are true and reporting a labelled file as unlabelled is the dangerous direction.
        """
        applied = self._backend.list_file_labels(self.id)
        out = []
        for one in applied:
            definition, reason = None, None
            try:
                definition = self._backend.get_label_definition(one.get("id", ""))
            except exc.ServiceDisabledError:
                reason = API_DISABLED
            except exc.AccessError:
                # The scope is missing, or this user may not read this label's definition. Both
                # leave the id true and the name unknown, which is what the caller is told.
                reason = SCOPE_MISSING
            except exc.NotFoundError:
                # A label applied to the file whose definition has since been deleted. Rare, and
                # not an error for the caller: the file really does carry it.
                reason = ("this label's definition no longer exists, so it cannot be named. "
                          "The file does still carry it.")
            out.append(build_label(one, definition, reason))
        return out
