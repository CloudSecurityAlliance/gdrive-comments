"""Resources that explain the server to whoever is using it.

Two of them, doing different jobs:

* **`csa-gw://config`** — the *effective* policy right now: which capabilities are on, what
  each allowlist permits, and — when something permits nothing — the diagnosis of why. Live,
  computed from the same `Settings` the tools enforce, so it cannot drift from reality.
* **`csa-gw://help/configuration`** — the reference. Every variable, the accepted forms, the
  three outcomes, what each kind of mistake looks like, and the limits worth knowing before
  someone hits them.

Resources rather than tools because this is *reading material*: an MCP client can surface it
to the user directly, and the model can read it when it needs to explain a refusal instead of
guessing. `describe_configuration` exists as a tool as well, for the same information in a
shape the model can reason over and in clients that do not surface resources.

**Reasons are deliberately omitted.** An allowlist entry's trailing comment is written for the
human reviewing the configuration and may name people or unannounced work — the same
reasoning that keeps it out of `Entry.__repr__`. File ids are included, since those are
exactly the files the agent may already touch.
"""
from __future__ import annotations

from mcp.server import MCPServer

from .._environment import describe_environment
from ..policy import (
    _GATES,
    ALL_CAPABILITIES,
    CAPABILITY_NOTES,
    DEFAULT_DISABLED,
    DEFAULT_ENABLED,
    MODIFY,
    PROFILES,
    READ,
    Policy,
    Scope,
)
from ._capabilities import reachable_capabilities
from ._config import MODIFY_ALLOWLIST_VAR, READ_ALLOWLIST_VAR, Settings

CONFIG_URI = "csa-gw://config"
HELP_URI = "csa-gw://help/configuration"
CEILING_URI = "csa-gw://help/capabilities"



# Google's own interface labels, for the generated table only. NOT accepted as configuration
# values - `policy.UI_LABELS` exists to REFUSE them with the right word, since a config with two
# spellings for every value is a config whose meaning depends on which vocabulary its author
# happened to know. Shown here so an operator who knows "Content manager" can find the row.
DRIVE_UI_LABEL = {
    "reader": "Viewer",
    "commenter": "Commenter",
    "writer": "Editor · Contributor",
    "fileOrganizer": "Content manager",
    "organizer": "Manager",
}


def _profile_rows() -> list[str]:
    """The profile table, rendered from `PROFILES` rather than restated.

    `PROFILES` nests - reader < commenter < editor < full - so each row can say "the above,
    plus" and stay short. That nesting is a property of today's profiles, not a rule, so it is
    CHECKED rather than assumed: a future non-nested profile renders its full list instead of
    silently claiming to include a capability it dropped.
    """
    rows: list[str] = []
    previous: frozenset[str] = frozenset()
    previous_name = ""
    for name, caps in PROFILES.items():
        label = DRIVE_UI_LABEL.get(name, "")
        if not caps:
            rows.append(f"| `{name}` | {label} | **nothing** - read and report only, whatever "
                        f"the allowlists say |")
        else:
            builds_on = bool(previous) and previous <= caps
            shown = sorted(caps - previous) if builds_on else sorted(caps)
            labels = " · ".join(CAPABILITY_NOTES[c][0] for c in shown)
            rows.append(f"| `{name}` | {label} | "
                        + (f"everything `{previous_name}` may, plus {labels} |"
                           if builds_on else f"{labels} |"))
        previous, previous_name = caps, name
    return rows


def _capability_rows() -> list[str]:
    """Every capability with its name, meaning and whether it can be undone.

    The `CSA_GW_CAPABILITIES` names were documented nowhere a reader could find them - the
    reference said "an explicit capability list" and left them to be guessed from an error
    message.
    """
    return [f"| `{name}` | {meaning} | {undo} |"
            for name, (meaning, undo) in
            sorted(CAPABILITY_NOTES.items(), key=lambda kv: kv[0])]


def _scope_lines(label: str, scope: Scope, variable: str) -> list[str]:
    if scope.all_files:
        return [f"### {label}: every file",
                "",
                f"`{variable}` is `*`, so this permits every file the signed-in Google account "
                f"can reach. Narrow it by replacing `*` with a list of document URLs."]
    if not scope.ids:
        return [f"### {label}: nothing",
                "",
                f"**Every {label.lower()} operation will be refused.** "
                + (scope.reason or f"`{variable}` is not configured."),
                "",
                f"Set `{variable}` to a list of document URLs, or to `*` for no restriction."]
    listed = "\n".join(f"- `{fid}`" for fid in sorted(scope.ids))
    return [f"### {label}: {len(scope.ids)} document(s)", "", listed, "",
            f"Anything else is outside `{variable}`. Reasons recorded next to each entry are "
            f"not reproduced here — they are for whoever reviews the configuration."]


def render_config(settings: Settings) -> str:
    """The effective policy, as Markdown. Computed from the same Settings the tools use."""
    policy = settings.policy or Policy.default()
    reachable = reachable_capabilities()
    on = sorted(policy.enabled & reachable)
    unreachable = sorted(policy.enabled - reachable)
    off = sorted(set(ALL_CAPABILITIES) - policy.enabled)

    env = describe_environment()
    lines = [
        "# csa-google-workspace — effective configuration",
        "",
        # First, because it is the first question asked of any bug report and the cheapest one
        # to answer wrongly from memory.
        f"`{env.server_version}` on {env.os} ({env.architecture}), Python "
        f"{env.python_version}, installed via {env.installed_via}.",
        "",
        "Everything below is read from the environment at startup. **Nothing here can be "
        "changed by a tool**, by this model, or by anything a document asks for; only whoever "
        "launched the server can change it.",
        "",
        "## Files",
        "",
        *_scope_lines("Read", policy.read, READ_ALLOWLIST_VAR),
        "",
        *_scope_lines("Modify", policy.modify, MODIFY_ALLOWLIST_VAR),
        "",
        "The two are independent. Reads being broad while modification is narrow is the "
        "intended shape: the agent already sees whatever the account sees, so what is worth "
        "bounding is what it can change.",
        "",
        "## Mutation kinds",
        "",
        *([f"Profile: **{settings.profile}** (`CSA_GW_PROFILE`).", ""]
          if settings.profile else []),
        "Available here: " + (", ".join(f"`{c}`" for c in on) if on else "*none*"),
        "",
        "Refused: " + (", ".join(f"`{c}`" for c in off) if off else "*none*"),
        "",
        *([
            "Permitted by policy but **not reachable through this server** — no tool here uses "
            "them, so do not plan work around them: "
            + ", ".join(f"`{c}`" for c in unreachable) + ".",
            "",
            "They are not a mistake in the policy. The policy governs the underlying library "
            "too, where these operations do exist; this server simply does not expose a tool "
            "for them yet.",
            "",
          ] if unreachable else []),
        # Derived from DEFAULT_DISABLED, not written out. The previous version said the
        # default "excludes renaming, trashing and sharing" while LISTING file.update and
        # file.trash two clauses earlier - true when written, and contradicted by the v0.21.0
        # regrouping, in the resource whose entire job is telling the truth about the config.
        # `tests/test_resources.py` now asserts the sentence agrees with the constant.
        f"Set with `CSA_GW_CAPABILITIES`. Unset means the default set "
        f"({', '.join(f'`{c}`' for c in sorted(DEFAULT_ENABLED))}), which excludes "
        f"{', '.join(f'`{c}`' for c in sorted(DEFAULT_DISABLED))} - the three Google gives "
        f"you no way to undo.",
        "",
        "## Other",
        "",
        f"- Read-only mode: **{'on' if settings.read_only else 'off'}** (`CSA_GW_READ_ONLY`) — "
        f"when on, it overrides everything above and also narrows the OAuth scopes.",
        f"- Token cache: `{settings.token_path}`",
        "",
        "## If something is refused",
        "",
        "The refusal names the variable to change and why. Relay that to the user rather than "
        "retrying: the policy cannot be widened from here, so a retry will fail identically. "
        f"See `{HELP_URI}` for the formats.",
        "",
        "**Do not route around it.** If another Google Drive integration is available in this "
        "conversation, using it to do what this server refused defeats the point of the "
        "refusal — the operator scoped this deliberately. Say what was refused and why, and "
        "let the user decide.",
    ]
    return "\n".join(lines)


def render_help() -> str:
    """The configuration reference. Static, so it can be read before anything goes wrong."""
    reads = sorted(n for n, g in _GATES.items() if g.access == READ and g.capability is None)
    modifies = sorted(n for n, g in _GATES.items() if g.access == MODIFY)
    profile_rows = "\n".join(_profile_rows())
    capability_rows = "\n".join(_capability_rows())
    return f"""# Configuring csa-google-workspace

Three independent bounds, all environment variables, set wherever this server is declared —
a shell, `.mcp.json`, or Claude Desktop's config. Each is a ceiling: none can widen another.

| Variable | Bounds | Unset |
|---|---|---|
| `{READ_ALLOWLIST_VAR}` | which files may be **read** | **every file** |
| `{MODIFY_ALLOWLIST_VAR}` | which files may be **changed, added to or deleted** | **every file** |
| `CSA_GW_PROFILE` | a **named** capability set — see Profiles below | everything on |
| `CSA_GW_CAPABILITIES` | an explicit capability list — overrides the profile | see profile |
| `CSA_GW_READ_ONLY=1` | everything — no writes, narrower OAuth scopes | off |

**Everything is on out of the box, and narrowing is the thing you configure.** That is the
opposite of the pre-v0.31.0 posture, and the reason is that a capability enabled here is **not a
permission granted**: every call still runs as you, against Google's own ACLs. `organizer` on a
file where you are merely a Commenter still cannot edit it. This model is a ceiling *below*
Drive's, never an expansion, so "everything on" means *subtract nothing; let Drive decide*.

A **malformed** list is still refused, loudly, and the server will not start. Unset is an
operator who has not narrowed anything; malformed is one who tried and failed, and widening that
to every file would hand them the opposite of what they wrote.

Two further switches are **data handling, not permissions** — they cannot contain confidential
data, because by the time either runs the content is already in the model's context:

| Variable | Governs | Unset |
|---|---|---|
| `CSA_GW_LOCAL_READ` | `apply_comment_actions` reading a register from this machine | on |
| `CSA_GW_LOCAL_WRITE` | `export_comments` writing a `.csv`/`.xlsx`, and write-back of markers | on |

Turn them off to keep review material inside the MCP client rather than on disk, where it
persists outside the client's retention policy. Not a disclosure control — see above.

Four further variables are **settings, not ceilings** — none of them widens what the three
bounds above allow, which is why they are listed separately rather than mixed in:

| Variable | Sets | Unset |
|---|---|---|
| `CSA_GW_TOKEN` | where the cached OAuth token is read and written | `~/.csa_google_workspace/token.json` |
| `CSA_GW_CLIENT_SECRETS` | the installed-app OAuth client, for `login` **only** | none — `login` fails |
| `CSA_GW_EXPORT_DIR` | where a `.csv` lands when the caller names one without a path | `~/Downloads` |
| `CSA_GW_DEMO_REPO` | source repo for `demonstration_plan` | this project's repo |
| `CSA_GW_DEMO_SHARE` | who a demonstration's files are shared with | nobody |

A cached token carries its own client id and secret, which is why `CSA_GW_CLIENT_SECRETS`
is needed for `login` and never afterwards.

`CSA_GW_EXPORT_DIR` is the one worth a second look, because it is the only variable here that
names **a location on the machine running this server** rather than something in Drive. It
does not authorize the write — `destination="file"` is a capability an operator turns on —
but it decides where an authorized one lands. A full path given by the caller is honoured
over it, deliberately: what makes that safe is that the failure modes are inert, not that the
path is validated.

## Profiles

`CSA_GW_PROFILE` names a capability set, so "what may this install do?" has a short answer:

| Profile | Google's interface calls it | May |
|---|---|---|
{profile_rows}

Profiles cover **capabilities only**. The file allowlists are deliberately not profiled: which
documents a deployment may touch is specific to that deployment, and a named default for it
would be a named default for "which of your files an agent may change".

`CSA_GW_CAPABILITIES` overrides a profile if both are set, and says so in the log. These are
the names it accepts:

| Capability | Lets an install | Can it be undone? |
|---|---|---|
{capability_rows}

**The line between `editor` and `full` is drawn on that last column** — not on how alarming
the verb sounds. `file.trash` is in `editor` because Drive's bin is 30 days the file's owner
can see and reverse; `comment.edit` is in `full` because Google keeps no edit history at all.
"Content edits are versioned so editing is safe" holds for document content and is false for
comments, which is the assumption the older grouping encoded.

## The usual posture

    {READ_ALLOWLIST_VAR}=*
    {MODIFY_ALLOWLIST_VAR}=https://docs.google.com/document/d/AAA.../edit  # why this one

Reads as broad as any other Drive integration; changes narrow. That is deliberate rather than
lazy — the agent already sees whatever the account sees, so bounding what it can *break* is
the part that helps.

## Three outcomes, and the third is the point

1. `*` — every file. Logged as a warning each time it is read, because unrestricted access
   should be visible.
2. **Document URLs** — those files and no others.
3. **Anything else** — unset, blank, or malformed — permits **nothing**. Never "ignore the
   setting".

## Format

One URL per entry. Newlines separate them (`\\n` in a JSON value); commas, semicolons and
whitespace also separate when no comment is present. `#` starts a comment, and the comment is
the *reason*, so a diff of your configuration shows what was granted and why.

    https://docs.google.com/document/d/AAA.../edit?tab=t.0   # CCM v5 mapping, per WG lead
    https://docs.google.com/spreadsheets/d/BBB.../edit        # AICM tracker

Indentation, tabs, alignment and blank lines are insignificant — line the reasons up if that
reads better. The reason is free text: apostrophes, quotes and further `#`s are fine (whatever
holds the value has its own quoting rules, which is a separate layer). A comment starts at a
`#` that begins the line or follows whitespace, so a URL keeps an `#gid=0` or `#heading=h.x`
fragment.

**There is no allowlist file.** The variables hold the lists themselves, because the client
configuration is the artifact an operator controls and can see. A path-shaped value is
reported as a mistake rather than read.

## What each mistake looks like

| You set | You are told |
|---|---|
| nothing | *is not set. It holds the list itself — there is no file to create.* |
| an empty value | *set but empty — not the same as unset. Usually a config template or an unexpanded shell variable.* |
| `.../document/d/` | *the URL stops after '/d/', so the file id is missing.* |
| `.../d/AAA.../edit` | *contains '...', so it looks like a placeholder copied from documentation.* |
| a bare file id | *the allowlist needs the full URL — a link can be opened and checked by whoever reviews it.* |
| a folder URL | *folders are not supported yet. List the documents inside it instead.* |
| a file path | *the allowlist is set in the environment, not read from a file.* |
| two URLs on one line | *only the first would be allowlisted.* |
| a URL inside a comment | *that document is NOT being allowlisted — a comment runs to the end of the line.* |

The last two are errors rather than dropped entries on purpose. Both would fail *closed*, so
nothing gets over-permitted — but a policy quietly smaller than intended is the kind of thing
that gets worked around instead of fixed.

## Limits worth knowing before you hit them

- **Folders are not supported.** Not an oversight: anyone who can add a file to an allowlisted
  folder could thereby grant write access to it, shortcuts break ancestor traversal via their
  targets, and the per-access API calls invite a cache whose staleness means a revoked grant
  still works. A folder URL is rejected loudly rather than matching nothing.
- **Matching is by file id.** Every URL form for one document is one entry, and a **copy** has
  a different id, so it is not included. Entries survive renames and moves.
- **Per-capability file scope is not expressible** — "commentable but not editable" for one
  document needs a structured value the flat list cannot carry.
- **Reads are not restricted to a whitelist of *operations***, only of files: {len(reads)}
  read operations are always available for a file in the read scope.
- **Mutations gated by capability:** {len(modifies)} operations, each mapped to one of
  `CSA_GW_CAPABILITIES`.

## What this is, and is not

A deliberately simple first control: per-capability gating plus flat lists of documents. It is
enforced below the tool layer, so it applies identically to anything using the underlying
library, and it **cannot be widened from inside a session** — no tool changes it. It is not a
general authorization model, and a broader design is being worked on separately.
"""



def render_ceiling() -> str:
    """What this server cannot do, and why — written for the MODEL, not for an evaluator.

    A limitations list in a README is read by somebody choosing a tool. This is read by an agent
    mid-task that has just been asked to accept a suggestion, and the alternative to telling it
    is letting it find out by failing — then inventing a workaround, which is the expensive
    outcome: retries, a plausible-sounding account of why it "should" work, or a detour through
    some other integration.

    Every entry says whether the limit is Google's or ours, because those call for different
    responses. A Google limit means stop and tell the user. One of ours means an operator could
    change it.
    """
    return f"""# What this server cannot do

Read this before concluding a task is impossible, and before working around a refusal.

Two kinds of limit, and they call for different responses. **Google's limits cannot be
configured away** — say so and stop. **Ours can** — an operator may be able to change the
configuration, so say which one it is.

## Google's limits — no configuration changes these

**Accept or reject a suggestion.** The Docs API exposes no endpoint for it, proven by full API
enumeration rather than assumed. You *can* read suggestions (`list_suggestions`) and preview the
outcome (`read_file_content(suggestions=...)`); applying one is something only the Docs web
interface can do.

**Create a comment anchored to a specific cell.** The Sheets anchor is an opaque
`workbook-range` id that an API client cannot construct. `create_comment(cell=...)` posts a
file-level comment carrying a deep link to the cell instead, which is the closest thing that
exists.

**Tell which tab a spreadsheet comment belongs to.** `Location.tab` is unresolved for multi-tab
files; the mapping needs a detour through the workbook's internal XML.

## This project's limits — deliberate, and an operator could revisit them

**Permanently delete anything, or empty the trash.** There is no permanent delete here and no
capability that empties the bin. The worst any configuration can do to a file is trash it, where
its owner can see it and restore it.

**Change a file's access settings** — *"Allow editors to change permissions and share"*, *"Limit
access to…"*. These decide who may *set* policy rather than use the file, and one of them
silently **removes** access from people who are not present; Google's own dialog warns *"Some
people may lose access."* Governance decisions belong in Drive's interface with a human.

**Write a live formula into a spreadsheet.** `update_cells` and `append_rows` store values
verbatim. Formula-writing exists in the library for a developer who has decided; it is not
offered here, because content passing through this server is frequently derived from untrusted
document text.

## If you hit one of these

Say which limit it is, and stop. Do **not** substitute a different mechanism to reach the same
end — editing a document's body to simulate accepting a suggestion, or using another integration
to do what this server declined. A refusal is information, not an obstacle.

For what this server is currently *permitted* to do, which is a different question, read
`{CONFIG_URI}`.
"""



def register_resources(app: MCPServer, settings: Settings) -> None:
    @app.resource(CONFIG_URI, name="Effective configuration", mime_type="text/markdown",
                  description="What this server is currently permitted to read and change, "
                              "and why anything refused was refused.")
    def config() -> str:
        return render_config(settings)

    @app.resource(HELP_URI, name="Configuration reference", mime_type="text/markdown",
                  description="How to configure the file allowlists and capability gating, "
                              "including what each kind of misconfiguration looks like.")
    def help_configuration() -> str:
        return render_help()

    @app.resource(CEILING_URI, name="What this server cannot do", mime_type="text/markdown",
                  description="The operations that are impossible here, split into Google's "
                              "limits and this project's, so a refusal is not worked around.")
    def help_capabilities() -> str:
        return render_ceiling()
