"""Who can reach a file, and at what role.

A **per-file, uniform Drive concern** — one API, identical across Docs/Sheets/Slides — so it
arrives the same way comments did: a mixin composed into `Document`, with its model beside it
(docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md §3).

Read-only here on purpose. `share_file` — creating a permission — is a separate, gated thing
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)): granting an
arbitrary address access to a document is an exfiltration primitive, and one Google's own MCP
server declines to expose. Listing who *already* has access is not.
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
    """Provides `permissions` uniformly across document types."""

    _backend: Backend
    id: str

    @property
    def permissions(self) -> list[Permission]:
        """Every grant on this file. Re-fetched per call, like every other accessor here."""
        return [Permission.from_api(p) for p in self._backend.list_permissions(self.id)]
