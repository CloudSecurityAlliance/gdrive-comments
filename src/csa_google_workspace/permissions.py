"""Who can reach a file, and at what role.

A **per-file, uniform Drive concern** — one API, identical across Docs/Sheets/Slides — so it
arrives the same way comments did: a mixin composed into `Document`, with its model beside it
(docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md §3).

Reading is ungated; **granting is not**. `share()` creates a permission, and granting an
arbitrary address access to a document is an exfiltration primitive — one Google's own MCP
server declines to expose at all. Ours exposes it behind two independent bounds
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)): the
`file.share` capability, which is OFF unless named explicitly, and the modify allowlist, which
must name the file. Listing who *already* has access needs neither.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:                                      # pragma: no cover
    from .backend import Backend

# Drive's roles, weakest first. Ordered so "who can change this?" is answerable without a
# lookup table at the call site.
ROLES = ("reader", "commenter", "writer", "fileOrganizer", "organizer", "owner")
WRITE_ROLES = frozenset(ROLES[ROLES.index("writer"):])


@dataclass
class Permission:
    """One grant. `email` is the payload here, unlike everywhere else in this library —
    the whole question is *who*. It is still kept out of `__repr__`; see below."""
    id: str
    type: str                    # user | group | domain | anyone
    role: str                    # see ROLES
    display_name: str | None = None
    email: str | None = None
    domain: str | None = None
    deleted: bool = False
    pending_owner: bool = False

    @classmethod
    def from_api(cls, d: dict) -> Permission:
        return cls(id=d.get("id", ""), type=d.get("type", ""), role=d.get("role", ""),
                   display_name=d.get("displayName"), email=d.get("emailAddress"),
                   domain=d.get("domain"), deleted=bool(d.get("deleted", False)),
                   pending_owner=bool(d.get("pendingOwner", False)))

    @property
    def can_write(self) -> bool:
        return self.role in WRITE_ROLES

    @property
    def is_public(self) -> bool:
        """`type == "anyone"` — a link anybody can follow. The thing worth noticing in a
        permission list, so it gets a name rather than a string comparison."""
        return self.type == "anyone"

    def __repr__(self) -> str:
        # Redacted like Author: email is PII and embedders log these objects. Same rule as
        # comment content — returned by the tool, absent from the log. `type` and `role`
        # carry the security-relevant shape without naming anybody.
        return (f"Permission(id={self.id!r}, type={self.type!r}, role={self.role!r}, "
                f"named={self.email is not None or self.display_name is not None})")


class PermissionsMixin:
    """Provides `permissions` and `share` uniformly across document types."""

    _backend: Backend
    id: str

    def _require_writable(self) -> None:      # provided by Document; declared for type-checking
        ...  # pragma: no cover

    @property
    def permissions(self) -> list[Permission]:
        """Every grant on this file. Re-fetched per call, like every other accessor here."""
        return [Permission.from_api(p) for p in self._backend.list_permissions(self.id)]

    def share(self, email: str, role: str = "reader", *, notify: bool = True) -> Permission:
        """Grant `email` access at `role`. Requires the `file.share` capability.

        `notify=True` by default, and deliberately: a share the recipient is told about is one
        somebody can notice and question. Silent grants are how access accumulates unobserved.

        `role` is validated against Drive's vocabulary here rather than at the API, so a typo
        is a clear error instead of a 400 from Google.

        **`owner` is refused.** Transferring ownership is a different act from sharing: it
        needs Drive's `transferOwnership` flag, it can leave the current owner unable to undo
        it, and on some account types it cannot be reversed at all. Refusing it here means a
        model cannot give a document away by choosing a plausible-looking role.
        """
        if role == "owner":
            raise ValueError(
                "share() will not transfer ownership; use the Drive UI deliberately. "
                "Pass 'writer' to grant full edit access.")
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; expected one of {', '.join(ROLES)}")
        if not email or "@" not in email:
            raise ValueError(f"expected an email address, got {email!r}")
        self._require_writable()
        return Permission.from_api(self._backend.create_permission(
            self.id, email=email, role=role, notify=notify))
