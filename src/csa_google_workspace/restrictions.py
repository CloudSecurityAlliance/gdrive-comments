"""The Google-side controls: what actually prevents an edit, a copy or a re-share.

**These are a different KIND of control from everything else in this library, and that is the
whole reason they are worth exposing.** `policy.py` builds a ceiling below Drive's — it bounds
what *this agent* does, and `README.md` concedes the limit out loud: running the built-in Drive
connector alongside this server "defeats the scoping entirely", because our gates bind only our
own calls.

A protected range, `writersCanShare=false`, or `driveMembersOnly` binds **every** client — this
server, that connector, the web UI, a script, a phone. So when a model is deciding whether it is
safe to do something, "Google will refuse this" is a categorically stronger answer than "our
policy is configured not to", and it is the answer this module reports.

## Read-only, by construction rather than by configuration

Nothing here can change a restriction, and `policy._GATES` has no write entry to switch on. The
reasoning is the same one that makes `labels.py` read-only: these controls bound an entire drive
or an entire file *for every client*, which makes them the broadest authority this library could
touch and therefore the last it should be able to modify. An agent that can lift the restriction
protecting a document has not been restricted.

## Absence is not permission

Every field here is `None` when Drive did not say, and `None` never means "unrestricted". A
restriction we could not read is a restriction we must not report as absent — the same asymmetry
`labels.py` and `_inventory.py` are built around, and the same dangerous direction: silence
reading as safety. `FileRestrictions.unknown` exists so a caller can tell the two apart without
inspecting each field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProtectedRange:
    """A protected range on a spreadsheet — the control that actually prevents an edit.

    `warning_only` is the field to read before reporting this as protection: a warning-only
    range shows a dialog and then **allows the edit anyway**, so treating it as enforcement is
    the exact mistake this dataclass exists to prevent. Google's own UI calls it "show a warning
    when editing this range".

    `requesting_user_can_edit` is the effective answer for *this* user, which is usually what a
    caller wants and is not derivable from the editor lists: a range may permit a domain, a
    group, or nobody.
    """
    protected_range_id: int | None
    description: str | None
    warning_only: bool
    requesting_user_can_edit: bool | None
    tab_id: int | None
    tab_title: str | None
    a1_range: str | None
    named_range_id: str | None
    editor_users: tuple[str, ...] = ()
    editor_groups: tuple[str, ...] = ()
    domain_users_can_edit: bool | None = None

    @property
    def enforced(self) -> bool:
        """Whether this range actually STOPS an edit, as against warning about one."""
        return not self.warning_only

    def __repr__(self) -> str:
        # `description` is author-written text about the document and the editor lists are
        # collaborator PII, so both are counted rather than shown - the rule invariant 2 sets.
        return (f"ProtectedRange(id={self.protected_range_id!r}, tab={self.tab_title!r}, "
                f"range={self.a1_range!r}, enforced={self.enforced}, "
                f"editors={len(self.editor_users) + len(self.editor_groups)})")

    @classmethod
    def from_api(cls, raw: dict, *, tab_id: int | None = None,
                 tab_title: str | None = None, a1_range: str | None = None) -> ProtectedRange:
        editors = raw.get("editors") or {}
        return cls(
            protected_range_id=raw.get("protectedRangeId"),
            description=raw.get("description"),
            # ABSENT means enforced. Google omits `warningOnly` when false, so defaulting to
            # True here would silently downgrade every real protection to a warning.
            warning_only=bool(raw.get("warningOnly", False)),
            requesting_user_can_edit=raw.get("requestingUserCanEdit"),
            tab_id=tab_id, tab_title=tab_title, a1_range=a1_range,
            named_range_id=raw.get("namedRangeId"),
            editor_users=tuple(editors.get("users") or ()),
            editor_groups=tuple(editors.get("groups") or ()),
            domain_users_can_edit=editors.get("domainUsersCanEdit"),
        )


@dataclass(frozen=True)
class FileRestrictions:
    """File-level restrictions, plus what this user may EFFECTIVELY do.

    The two halves answer different questions and both are needed. The restriction flags say
    *what is configured*; `can_*` says *what Drive will actually permit me*, after the flags,
    the ACL and any drive-level policy have all been applied. A model deciding whether to try
    something wants the second; somebody auditing the document's posture wants the first.
    """
    copy_requires_writer_permission: bool | None = None
    writers_can_share: bool | None = None
    can_edit: bool | None = None
    can_comment: bool | None = None
    can_share: bool | None = None
    can_copy: bool | None = None
    can_delete: bool | None = None
    can_read_revisions: bool | None = None

    @property
    def unknown(self) -> bool:
        """True when Drive told us nothing — so a caller can tell "not restricted" from
        "not read". Reporting an unread restriction as absent is the dangerous direction."""
        return all(getattr(self, f.name) is None for f in field_names(self))

    @classmethod
    def from_api(cls, raw: dict) -> FileRestrictions:
        caps = raw.get("capabilities") or {}
        return cls(
            copy_requires_writer_permission=raw.get("copyRequiresWriterPermission"),
            writers_can_share=raw.get("writersCanShare"),
            can_edit=caps.get("canEdit"), can_comment=caps.get("canComment"),
            can_share=caps.get("canShare"), can_copy=caps.get("canCopy"),
            can_delete=caps.get("canDelete"),
            can_read_revisions=caps.get("canReadRevisions"),
        )


@dataclass(frozen=True)
class SharedDrive:
    """A shared drive and its restrictions — the broadest Google-side controls there are.

    `download_restriction` was **not** in the request that asked for this and IS set on real
    drives, which is why the field list was probed rather than transcribed from the issue.
    """
    id: str
    name: str | None
    hidden: bool | None = None
    drive_members_only: bool | None = None
    domain_users_only: bool | None = None
    copy_requires_writer_permission: bool | None = None
    sharing_folders_requires_organizer_permission: bool | None = None
    admin_managed_restrictions: bool | None = None
    download_restricted_for_readers: bool | None = None
    download_restricted_for_writers: bool | None = None
    raw_restrictions: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __repr__(self) -> str:
        # A drive NAME identifies an organisational unit, so it is counted out like other
        # third-party strings rather than printed into an embedder's logs.
        return (f"SharedDrive(id={self.id!r}, members_only={self.drive_members_only}, "
                f"domain_only={self.domain_users_only})")

    @classmethod
    def from_api(cls, raw: dict) -> SharedDrive:
        r = raw.get("restrictions") or {}
        dl = r.get("downloadRestriction") or {}
        return cls(
            id=raw.get("id", ""), name=raw.get("name"), hidden=raw.get("hidden"),
            drive_members_only=r.get("driveMembersOnly"),
            domain_users_only=r.get("domainUsersOnly"),
            copy_requires_writer_permission=r.get("copyRequiresWriterPermission"),
            sharing_folders_requires_organizer_permission=r.get(
                "sharingFoldersRequiresOrganizerPermission"),
            admin_managed_restrictions=r.get("adminManagedRestrictions"),
            download_restricted_for_readers=dl.get("restrictedForReaders"),
            download_restricted_for_writers=dl.get("restrictedForWriters"),
            raw_restrictions=dict(r),
        )


def field_names(obj: Any):
    """`dataclasses.fields` without importing it at every call site."""
    from dataclasses import fields as _fields
    return [f for f in _fields(obj) if f.name != "raw_restrictions"]
