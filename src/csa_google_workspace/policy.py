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
from .allowlist import Entry

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

@dataclass(frozen=True)
class Gate:
    """What a `Backend` method needs in order to proceed.

    Both facts belong in one place because `_GATES` is the security contract: a reader
    should see, per method, which capability it costs *and* whether the file allowlist
    applies. `file_scoped=False` is for calls with no file to check — the account axis, and
    creation, which cannot damage a file that already exists.
    """
    capability: str | Callable[..., str] | None
    file_scoped: bool = True


READ = Gate(capability=None, file_scoped=False)


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
    "get_file_metadata": READ,
    "list_permissions": READ,
    "search_files": READ,
    "list_comments": READ,
    "get_comment": READ,
    "export_file": READ,
    "get_document": READ,
    "get_spreadsheet": READ,
    "get_values": READ,
    "get_presentation": READ,
    # comment writes
    "create_comment": Gate(COMMENT_CREATE),
    "create_reply": Gate(_reply_gate),       # reply vs resolve/reopen — see above
    "update_comment": Gate(COMMENT_EDIT),
    "update_reply": Gate(COMMENT_EDIT),
    "delete_comment": Gate(COMMENT_DELETE),
    "delete_reply": Gate(COMMENT_DELETE),
    # content writes
    "docs_batch_update": Gate(CONTENT_WRITE),
    "sheets_values_update": Gate(CONTENT_WRITE),
    "sheets_values_append": Gate(CONTENT_WRITE),
    "sheets_values_clear": Gate(CONTENT_WRITE),
    "sheets_batch_update": Gate(CONTENT_WRITE),
    "slides_batch_update": Gate(CONTENT_WRITE),
    # API-impossible today; ApiBackend raises UnsupportedOperation. Gated anyway so a future
    # PlaywrightBackend does not arrive ungated.
    "accept_suggestion": Gate(CONTENT_WRITE),
    "create_cell_anchored_comment": Gate(COMMENT_CREATE),
}


@dataclass(frozen=True)
class Policy:
    """What this deployment may mutate: which capabilities, and on which files.

    The two dimensions compose one way only — **global is a ceiling, the file list narrows**.
    A capability absent from `enabled` cannot be reached by listing a file, and a file absent
    from `allowed_files` cannot be reached by enabling a capability.

    `allowed_files=None` means *no file restriction* — every file the credentials can reach.
    That is the default, because it is what this library has always done; making it
    fail-closed is a deliberate 1.0.0 decision recorded in `TODO.md`, not something to change
    silently under existing users.

    Construct with `Policy.default()` for today's behaviour, or `Policy(enabled=frozenset())`
    for a policy that permits no mutation at all — the same outcome as `read_only=True`,
    reached from the other direction.
    """
    enabled: frozenset[str]
    allowed_files: frozenset[str] | None = None
    entries: tuple[Entry, ...] = field(default=(), repr=False)

    @classmethod
    def from_entries(cls, enabled: frozenset[str], entries: tuple[Entry, ...]) -> Policy:
        return cls(enabled=enabled, allowed_files=frozenset(e.file_id for e in entries),
                   entries=entries)

    def allows_file(self, file_id: str) -> bool:
        return self.allowed_files is None or file_id in self.allowed_files

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

    def allows(self, capability: str | None) -> bool:
        return capability is None or capability in self.enabled

    def with_enabled(self, *capabilities: str) -> Policy:
        """Widen the capability set. Only ever called by whoever *configures* the server,
        never in-band: an agent that can widen its own policy does not have one."""
        widened = Policy.of(*(self.enabled | set(Policy.of(*capabilities).enabled)))
        return Policy(enabled=widened.enabled, allowed_files=self.allowed_files,
                      entries=self.entries)

    def without(self, *capabilities: str) -> Policy:
        return Policy(enabled=self.enabled - set(capabilities),
                      allowed_files=self.allowed_files, entries=self.entries)


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
        if gate.capability is None:
            return inner                                  # a read; no wrapper needed

        def guarded(*args: Any, **kwargs: Any) -> Any:
            rule = gate.capability
            capability = rule(*args, **kwargs) if callable(rule) else rule
            if not self._policy.allows(capability):
                log.warning("policy denied %s: capability %r is disabled", name, capability)
                raise exc.ReadOnlyError(
                    f"the {capability!r} capability is disabled for this server, so {name} "
                    f"is refused. An operator enables it in configuration; it cannot be "
                    f"turned on from here.")
            if gate.file_scoped:
                file_id = kwargs.get("file_id") or (args[0] if args else None)
                if file_id is None:
                    # Fail closed: a file-scoped call we cannot attribute to a file is one
                    # the allowlist cannot check.
                    raise exc.UnsupportedOperation(
                        f"{name} is declared file-scoped but was called without a file id, "
                        f"so the allowlist cannot be applied. This is a bug.")
                if not self._policy.allows_file(file_id):
                    log.warning("policy denied %s on %s: not in the write allowlist",
                                name, file_id)
                    raise exc.ReadOnlyError(self._not_allowlisted(name, file_id))
            log.debug("policy allowed %s (%s)", name, capability)
            return inner(*args, **kwargs)

        guarded.__name__ = name
        return guarded

    def _not_allowlisted(self, name: str, file_id: str) -> str:
        count = len(self._policy.allowed_files or ())
        return (f"{name} is refused: file {file_id} is not in the write allowlist "
                f"({count} file(s) listed). Reads are unaffected. To permit it, an operator "
                f"adds the document's URL to the allowlist file — it cannot be added from "
                f"here.")

    def __repr__(self) -> str:
        scope = ("unrestricted" if self._policy.allowed_files is None
                 else f"{len(self._policy.allowed_files)} file(s)")
        return (f"PolicyBackend(inner={type(self._inner).__name__}, "
                f"enabled={sorted(self._policy.enabled)}, files={scope})")
