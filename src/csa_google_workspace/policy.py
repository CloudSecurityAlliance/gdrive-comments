"""Capability gating — the first of #82's two dimensions.

https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82

#82's settled requirement surface separates two independent things:

1. **Capability gating at all** — may this deployment create comments? trash files? share
   them? Each on or off, globally. *This module.*
2. **Per-URL scope** for each enabled capability — *and* which files. Still to come.

The composition rule is that **global is a ceiling and per-file grants narrow, never
widen**, so building dimension 1 first is not a half-measure: dimension 2 can only ever
subtract from what is allowed here.

Why that ordering matters in practice: it lets the destructive tools ship *off*. A default
install cannot trash or share anything before the per-file allowlist exists, which closes
the window that would otherwise open between shipping those tools and finishing #82.

**Enforcement is a `Backend` wrapper, not a check in the tool layer.** Every `Backend`
method takes `file_id` first (or, for the account axis, nothing), which is what makes a
uniform wrapper possible at all — and it means an embedder using the library directly gets
the same guarantee as one going through MCP. `read_only` is the precedent; this is its
fine-grained sibling.

**Fail closed.** `_GATES` must name every `Backend` method. An unlisted name raises rather
than delegating, so adding a method to the protocol without deciding its gate is a loud
failure at import/first-call, not a silent hole. `tests/test_policy.py` asserts the
coverage so it fails in CI instead.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import exceptions as exc
from .allowlist import Entry, Listing

log = logging.getLogger(__name__)

# --- the capabilities -------------------------------------------------------

COMMENT_CREATE = "comment.create"
COMMENT_REPLY = "comment.reply"
COMMENT_RESOLVE = "comment.resolve"
COMMENT_EDIT = "comment.edit"
COMMENT_DELETE = "comment.delete"
CONTENT_WRITE = "content.write"
FILE_CREATE = "file.create"
FILE_UPDATE = "file.update"
FILE_TRASH = "file.trash"
FILE_SHARE = "file.share"

ALL_CAPABILITIES = (COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, COMMENT_EDIT,
                    COMMENT_DELETE, CONTENT_WRITE, FILE_CREATE, FILE_UPDATE, FILE_TRASH,
                    FILE_SHARE)

# On by default because they are what this library already did — turning them off here
# would be a silent behaviour change dressed as a security improvement. `file.create` joins
# them because creating a file cannot damage one that already exists.
DEFAULT_ENABLED = frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, COMMENT_EDIT,
                             COMMENT_DELETE, CONTENT_WRITE, FILE_CREATE})

# Off by default. Each one alters or exposes a file that already exists, and each is one
# Google's own MCP server declines to offer at all.
DEFAULT_DISABLED = frozenset({FILE_UPDATE, FILE_TRASH, FILE_SHARE})

# Named capability sets, so "what may this install do?" has an answer shorter than a list.
#
# Profiles cover *capabilities only*. The file allowlists are not profiled and never will be:
# which documents a deployment may touch is inherently specific to that deployment, and a
# named default for it would be a named default for "which of your files an agent may change".
# That is the one thing nobody else gets to decide.
PROFILES: dict[str, frozenset[str]] = {
    # Read and report. Cannot change anything, whatever the allowlists say.
    "reader": frozenset(),
    # Join the conversation: comment, reply, resolve. Cannot alter document *content*, cannot
    # delete a thread, cannot touch the file itself. The useful default for review work.
    "commenter": frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE}),
    # Also edit content, tidy comments, and create new files. Still cannot rename, move, trash
    # or share an existing one.
    "editor": frozenset({COMMENT_CREATE, COMMENT_REPLY, COMMENT_RESOLVE, COMMENT_EDIT,
                         COMMENT_DELETE, CONTENT_WRITE, FILE_CREATE}),
    # Everything, including the three Google's own server declines to offer.
    "full": frozenset(ALL_CAPABILITIES),
}
# `editor` is exactly the historical default set. `tests/test_policy.py` holds them together —
# not an `assert` here, which bandit rightly flags and `python -O` strips.

READ = "read"
MODIFY = "modify"


@dataclass(frozen=True)
class Scope:
    """Which files one *kind* of access may touch: everything, or a named set.

    `all_files` and "an empty set" are deliberately different states. Empty means *nothing is
    permitted* — the fail-closed default for the MCP server — and `all_files` is a decision
    somebody typed as a literal `*`. Collapsing them into one representation is how a
    fail-closed default turns into a fail-open one during a refactor.
    """
    all_files: bool = False
    ids: frozenset[str] = frozenset()
    entries: tuple[Entry, ...] = field(default=(), repr=False)
    # Why this scope is empty, when it is. Carried so a denial can say *which* variable to set
    # and why it currently yields nothing — "not set" and "set but empty" behave identically
    # and have completely different fixes.
    reason: str | None = None

    @classmethod
    def everything(cls) -> Scope:
        return cls(all_files=True)

    @classmethod
    def nothing(cls, reason: str | None = None) -> Scope:
        return cls(all_files=False, reason=reason)

    @classmethod
    def from_listing(cls, listing: Listing) -> Scope:
        return cls(all_files=listing.all_files, ids=listing.file_ids,
                   entries=listing.entries)

    def allows(self, file_id: str) -> bool:
        return self.all_files or file_id in self.ids

    def describe(self) -> str:
        if self.all_files:
            return "every file"
        if not self.ids:
            return "no files"
        return f"{len(self.ids)} listed file(s)"


@dataclass(frozen=True)
class Gate:
    """What a `Backend` method needs in order to proceed.

    Both facts belong in one place because `_GATES` is the security contract: a reader
    should see, per method, which capability it costs *and* whether the file allowlist
    applies. `file_scoped=False` is for calls with no file to check — the account axis, and
    creation, which cannot damage a file that already exists.
    """
    capability: str | Callable[..., str] | None
    access: str = MODIFY            # READ or MODIFY — which allowlist applies
    file_scoped: bool = True        # False for the account axis, which has no file id


# A per-file read: no capability needed, but the read allowlist applies.
READS_FILE = Gate(capability=None, access=READ, file_scoped=True)
# A listing (the account axis). No file id to check, so the *results* are filtered instead.
READS_LISTING = Gate(capability=None, access=READ, file_scoped=False)


def _reply_gate(file_id: str, comment_id: str, content: Any = None,
                action: Any = None) -> str:
    """`create_reply` is two operations wearing one method name.

    Resolve and reopen are **action-replies**, never a PATCH — probe-verified, and the
    reason `resolve_comment` posts a reply at all. So the capability depends on the
    arguments, not the method: a gate keyed only on the name would let anyone who may reply
    also resolve, which is the difference between adding to a thread and closing it.
    """
    return COMMENT_RESOLVE if action else COMMENT_REPLY


# Which capability each Backend method needs. `None` means "a read, always allowed" — reads
# are deliberately ungated: #82 is about damage containment, not confidentiality, because
# the agent already sees whatever the user's credentials see. A callable is consulted with
# the call's own arguments, for methods whose capability depends on them.
_GATES: dict[str, Gate] = {
    # reads — never gated: #82 is damage containment, not confidentiality. The agent already
    # sees whatever the user's credentials see.
    "get_file_metadata": READS_FILE,
    "list_permissions": READS_FILE,
    "search_files": READS_LISTING,
    "list_comments": READS_FILE,
    "get_comment": READS_FILE,
    "export_file": READS_FILE,
    "get_document": READS_FILE,
    "get_spreadsheet": READS_FILE,
    "get_values": READS_FILE,
    "get_presentation": READS_FILE,
    # comment writes
    "create_comment": Gate(COMMENT_CREATE, MODIFY),
    "create_reply": Gate(_reply_gate, MODIFY),   # reply vs resolve/reopen — see above
    "update_comment": Gate(COMMENT_EDIT, MODIFY),
    "update_reply": Gate(COMMENT_EDIT, MODIFY),
    "delete_comment": Gate(COMMENT_DELETE, MODIFY),
    "delete_reply": Gate(COMMENT_DELETE, MODIFY),
    # content writes
    "docs_batch_update": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_update": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_append": Gate(CONTENT_WRITE, MODIFY),
    "sheets_values_clear": Gate(CONTENT_WRITE, MODIFY),
    "sheets_batch_update": Gate(CONTENT_WRITE, MODIFY),
    "slides_batch_update": Gate(CONTENT_WRITE, MODIFY),
    # API-impossible today; ApiBackend raises UnsupportedOperation. Gated anyway so a future
    # PlaywrightBackend does not arrive ungated.
    "accept_suggestion": Gate(CONTENT_WRITE, MODIFY),
    "create_cell_anchored_comment": Gate(COMMENT_CREATE, MODIFY),
}


@dataclass(frozen=True)
class Policy:
    """What this deployment may do: which capabilities, and which files for read vs modify.

    Three independent bounds, composing one way only — **each is a ceiling, none can widen
    another**. A capability absent from `enabled` cannot be reached by listing a file; a file
    absent from `modify` cannot be reached by enabling a capability; and a file absent from
    `read` cannot be reached at all.

    Reads and mutations are separated because they are different risks. The usual posture is
    `read=Scope.everything()` — matching what Google's and Anthropic's Drive servers do, since
    the agent already sees whatever the user's credentials see — with `modify` a short,
    reviewed list. Bounding what can be *broken* is the part that helps.

    `Policy.default()` is **permissive** on both scopes. That is deliberate and it is *not*
    the MCP server's default: this class is also the library's, and `Workspace.from_credentials`
    is called by a developer writing code who has already made a decision. The MCP server is
    configuration handed to a model, so it fails closed when nothing is configured. Two
    artifacts, two threat models — see `mcp/_config.py`.
    """
    enabled: frozenset[str]
    read: Scope = field(default_factory=Scope.everything)
    modify: Scope = field(default_factory=Scope.everything)

    @classmethod
    def default(cls) -> Policy:
        return cls(enabled=DEFAULT_ENABLED)

    @classmethod
    def of(cls, *capabilities: str) -> Policy:
        unknown = sorted(set(capabilities) - set(ALL_CAPABILITIES))
        if unknown:
            raise ValueError(f"unknown capabilities: {', '.join(unknown)}; "
                             f"known: {', '.join(ALL_CAPABILITIES)}")
        return cls(enabled=frozenset(capabilities))

    def scope_for(self, access: str) -> Scope:
        return self.read if access == READ else self.modify

    def allows(self, capability: str | None) -> bool:
        return capability is None or capability in self.enabled

    def with_scopes(self, *, read: Scope | None = None,
                    modify: Scope | None = None) -> Policy:
        return Policy(enabled=self.enabled, read=read or self.read,
                      modify=modify or self.modify)

    def with_enabled(self, *capabilities: str) -> Policy:
        """Widen the capability set. Only ever called by whoever *configures* the server,
        never in-band: an agent that can widen its own policy does not have one."""
        widened = Policy.of(*(self.enabled | set(Policy.of(*capabilities).enabled)))
        return Policy(enabled=widened.enabled, read=self.read, modify=self.modify)

    def without(self, *capabilities: str) -> Policy:
        return Policy(enabled=self.enabled - set(capabilities), read=self.read,
                      modify=self.modify)


class PolicyBackend:
    """A `Backend` that refuses operations its `Policy` does not permit.

    Composed through the documented `Workspace(backend=…)` seam:

        Workspace(PolicyBackend(ApiBackend(services), Policy.of(COMMENT_CREATE)))
    """

    def __init__(self, inner: Any, policy: Policy):
        self._inner = inner
        self._policy = policy

    @property
    def policy(self) -> Policy:
        return self._policy

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in _GATES:
            # Fail closed: an unlisted method is one whose gate nobody decided.
            raise exc.UnsupportedOperation(
                f"{name!r} has no capability gate declared in policy._GATES, so it is "
                f"refused. Add it there (with None for a read) rather than bypassing this.")
        gate = _GATES[name]
        inner = getattr(self._inner, name)

        def guarded(*args: Any, **kwargs: Any) -> Any:
            rule = gate.capability
            capability = rule(*args, **kwargs) if callable(rule) else rule
            if not self._policy.allows(capability):
                log.warning("policy denied %s: capability %r is disabled", name, capability)
                raise exc.ReadOnlyError(
                    f"the {capability!r} capability is disabled for this server, so {name} "
                    f"is refused. An operator enables it in configuration; it cannot be "
                    f"turned on from here.")

            scope = self._policy.scope_for(gate.access)
            if gate.file_scoped:
                file_id = kwargs.get("file_id") or (args[0] if args else None)
                if file_id is None:
                    # Fail closed: a file-scoped call we cannot attribute to a file is one
                    # the allowlist cannot check.
                    raise exc.UnsupportedOperation(
                        f"{name} is declared file-scoped but was called without a file id, "
                        f"so the allowlist cannot be applied. This is a bug.")
                if not scope.allows(file_id):
                    log.warning("policy denied %s on %s: outside the %s allowlist",
                                name, file_id, gate.access)
                    raise self._denied(name, file_id, gate.access, scope)
                return inner(*args, **kwargs)

            result = inner(*args, **kwargs)
            # A listing has no single file to check, so the *results* are filtered. Anything
            # outside the read scope is not merely unreadable — it must not be named either,
            # or search becomes a way to enumerate files the policy excludes.
            return self._filter_listing(name, result, scope)

        guarded.__name__ = name
        return guarded

    @staticmethod
    def _filter_listing(name: str, result: Any, scope: Scope) -> Any:
        if scope.all_files or not isinstance(result, dict) or "files" not in result:
            return result
        kept = [f for f in result["files"] if scope.allows(f.get("id", ""))]
        dropped = len(result["files"]) - len(kept)
        if dropped:
            log.warning("policy filtered %d result(s) from %s: outside the read allowlist",
                        dropped, name)
        return {**result, "files": kept}

    def _denied(self, name: str, file_id: str, access: str, scope: Scope) -> Exception:
        which = "CSA_GW_ALLOWLIST_READ" if access == READ else "CSA_GW_ALLOWLIST_MODIFY"
        if not scope.all_files and not scope.ids:
            why = scope.reason or f"no {access} allowlist is configured."
            detail = (f"nothing is permitted for {access}. {why} An operator sets {which} to a "
                      f"list of document URLs, or to `*` for unrestricted {access} access.")
        else:
            detail = (f"it is not in the {access} allowlist ({scope.describe()}). An operator "
                      f"adds the document's URL to {which}.")
        message = f"{name} is refused on file {file_id}: {detail} It cannot be changed from here."
        # A refused *read* is not a ReadOnlyError — nothing about writing is involved.
        return exc.AccessError(message) if access == READ else exc.ReadOnlyError(message)

    def __repr__(self) -> str:
        return (f"PolicyBackend(inner={type(self._inner).__name__}, "
                f"enabled={sorted(self._policy.enabled)}, "
                f"read={self._policy.read.describe()}, "
                f"modify={self._policy.modify.describe()})")
