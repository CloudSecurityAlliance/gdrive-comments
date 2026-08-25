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

from ..policy import _GATES, ALL_CAPABILITIES, DEFAULT_ENABLED, MODIFY, READ, Policy, Scope
from ._config import MODIFY_ALLOWLIST_VAR, READ_ALLOWLIST_VAR, Settings

CONFIG_URI = "csa-gw://config"
HELP_URI = "csa-gw://help/configuration"


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
    on = sorted(policy.enabled)
    off = sorted(set(ALL_CAPABILITIES) - policy.enabled)

    lines = [
        "# csa-google-workspace — effective configuration",
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
        "Permitted: " + (", ".join(f"`{c}`" for c in on) if on else "*none*"),
        "",
        "Refused: " + (", ".join(f"`{c}`" for c in off) if off else "*none*"),
        "",
        f"Set with `CSA_GW_CAPABILITIES`. Unset means the default set "
        f"({', '.join(f'`{c}`' for c in sorted(DEFAULT_ENABLED))}), which excludes renaming, "
        f"trashing and sharing.",
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
    return f"""# Configuring csa-google-workspace

Three independent bounds, all environment variables, set wherever this server is declared —
a shell, `.mcp.json`, or Claude Desktop's config. Each is a ceiling: none can widen another.

| Variable | Bounds | Unset |
|---|---|---|
| `{READ_ALLOWLIST_VAR}` | which files may be **read** | nothing — fail closed |
| `{MODIFY_ALLOWLIST_VAR}` | which files may be **changed, added to or deleted** | nothing — fail closed |
| `CSA_GW_PROFILE` | a **named** capability set: `reader`, `commenter`, `editor`, `full` | `editor` |
| `CSA_GW_CAPABILITIES` | an explicit capability list — overrides the profile | see profile |
| `CSA_GW_READ_ONLY=1` | everything — no writes, narrower OAuth scopes | off |

## Profiles

`CSA_GW_PROFILE` names a capability set, so "what may this install do?" has a short answer:

| Profile | May |
|---|---|
| `reader` | nothing — read and report only, whatever the allowlists say |
| `commenter` | comment, reply, resolve. Not edit content, not delete a thread, not touch the file |
| `editor` | the above, plus edit content, tidy comments, create new files |
| `full` | everything, including rename/move, trash and share |

Profiles cover **capabilities only**. The file allowlists are deliberately not profiled: which
documents a deployment may touch is specific to that deployment, and a named default for it
would be a named default for "which of your files an agent may change".

`CSA_GW_CAPABILITIES` overrides a profile if both are set, and says so in the log.

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
